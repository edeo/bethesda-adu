"""Fit stage: label edges, build the pocket, fit the largest ADU rectangle, cap its size.

For each candidate parcel (status None / flagged_town / uncertain, with a principal house
footprint and an ADU-eligible zone rule) this writes the fit columns and the geometry
layers used to draw the result. Geometry is in EPSG:2248 (feet).
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
from shapely.ops import unary_union

from adu.classify import merge_flags
from adu.config import load_run_config, load_zones
from adu.fit_edges import classify_edges
from adu.fit_pocket import build_pocket, remaining_coverage, setback_envelope
from adu.fit_rect import largest_rectangle, lot_axis_deg, max_adu_floor_area
from adu.prepare import NEIGHBORS_FILE

FIT_STATUSES = {"flagged_town", "uncertain"}  # plus None
NEIGHBOR_DIST_FT = 5.0
FIT_COLUMNS = ["fit_result", "fit_reason", "pocket_area_sqft", "rect_w_ft", "rect_l_ft",
               "usable_footprint_sqft", "max_adu_floor_area"]


def _is_null(v) -> bool:
    return v is None or v is pd.NA or (isinstance(v, float) and v != v)


def _fit_one(geom, house, accessories, fp_areas, lot_area, living, zone_rule, zones, run, neighbors):
    edges, odd = classify_edges(geom, neighbors, zones["corner_lot_front"], run["flag_pole_max_width_ft"])
    pieces = build_pocket(geom, edges, house, accessories, zone_rule, run)
    pocket_area = float(sum(p.area for p in pieces))
    layers = [(e.kind, e.geom) for e in edges]
    layers.append(("envelope", setback_envelope(geom, edges, zone_rule["setbacks_ft"])))
    layers.append(("pocket", unary_union(pieces) if pieces else shapely.Polygon()))
    res = {c: None for c in FIT_COLUMNS}
    res["pocket_area_sqft"] = pocket_area
    if not pieces:
        res.update(fit_result="no_fit", fit_reason="no_pocket")
        return res, layers, odd

    axis = lot_axis_deg(geom)
    best = None
    for piece in pieces:
        found = largest_rectangle(piece, axis, run["rotations_deg"], run["min_dim_ft"])
        if found is not None and (best is None or found[1] * found[2] > best[1] * best[2]):
            best = found
    if best is None:
        res.update(fit_result="no_fit", fit_reason="pocket_too_small")
        return res, layers, odd

    poly, w, l = best
    layers.append(("adu_rect", poly))
    remaining = remaining_coverage(lot_area, zone_rule["coverage_cap"], fp_areas)
    usable = min(w * l, remaining)
    res.update(rect_w_ft=w, rect_l_ft=l, usable_footprint_sqft=usable)
    if usable < run["min_area_sqft"]:
        res.update(fit_result="no_fit", fit_reason="coverage_exhausted")
        return res, layers, odd
    res["fit_result"] = "fits"
    if not _is_null(living):
        res["max_adu_floor_area"] = max_adu_floor_area(
            float(living), usable, zone_rule["height_ft"], run["story_height_ft"], run["max_stories"],
            zones["adu_size_cap_ratio"])
    return res, layers, odd


def run_fit(classified: gpd.GeoDataFrame, footprints: gpd.GeoDataFrame, zones: dict,
            run: dict, neighbors: gpd.GeoDataFrame | None = None) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Fit every candidate parcel.

    `neighbors` (parcel_id, is_row, geometry) is the parcel layer used to find adjacent lots
    when classifying edges; pass the unclipped layer so lots at the study-area edge keep
    their neighbors. Defaults to `classified` itself. ROW polygons and the parcel itself
    (by parcel_id) are never neighbors.
    """
    out = classified.copy().reset_index(drop=True)
    crs = out.crs
    src = out if neighbors is None else neighbors.to_crs(crs)
    is_row = src["is_row"].fillna(False).astype(bool) if "is_row" in src else pd.Series(False, index=src.index)
    nb_layer = src.loc[~is_row, ["parcel_id", "geometry"]].reset_index(drop=True)
    nb_layer["parcel_id"] = nb_layer["parcel_id"].astype(str)
    nb_index = nb_layer.sindex
    fp_by_parcel = {pid: g for pid, g in footprints.groupby("parcel_id")}
    zone_cfg = zones["zones"]

    cols = {c: [None] * len(out) for c in FIT_COLUMNS}
    statuses = out["status"].astype(object).tolist()
    reasons = out["reason"].astype(object).tolist()
    flags = out["flags"].fillna("").astype(str).tolist()
    layer_rows = []

    for i, rec in enumerate(out.itertuples(index=False)):
        status = None if _is_null(statuses[i]) else statuses[i]
        if status is not None and status not in FIT_STATUSES:
            continue
        zone_rule = zone_cfg.get(rec.zone) if not _is_null(rec.zone) else None
        if not zone_rule or not zone_rule.get("adu_eligible"):
            continue
        fps = fp_by_parcel.get(rec.parcel_id)
        if fps is None or not fps["is_principal"].astype(bool).any():
            continue
        principal = fps["is_principal"].astype(bool)
        house = fps.loc[principal].geometry.iloc[0]
        accessories = list(fps.loc[~principal].geometry)
        geom = rec.geometry

        near = nb_index.query(geom, predicate="dwithin", distance=NEIGHBOR_DIST_FT)
        nb = nb_layer.iloc[near]
        nb = nb[nb["parcel_id"] != str(rec.parcel_id)]
        neighbors = shapely.union_all(nb.geometry.values) if len(nb) else shapely.GeometryCollection()

        res, layers, odd = _fit_one(geom, house, accessories, list(fps["fp_area_sqft"].astype(float)),
                                    float(rec.lot_area_sqft), rec.living_area_sqft, zone_rule, zones,
                                    run, neighbors)
        for c in FIT_COLUMNS:
            cols[c][i] = res[c]
        if odd:
            flags[i] = merge_flags(flags[i], "odd_shape")
            if status is None:
                status = "uncertain"
        if status is None:
            statuses[i] = res["fit_result"]
        else:
            statuses[i] = status
        if _is_null(reasons[i]):
            reasons[i] = res["fit_reason"]
        layer_rows += [{"parcel_id": rec.parcel_id, "layer": k, "geometry": g} for k, g in layers]

    for c in FIT_COLUMNS:
        dtype = object if c in ("fit_result", "fit_reason") else float
        out[c] = pd.Series(cols[c], index=out.index, dtype=dtype)
    out["status"] = pd.Series(statuses, index=out.index, dtype=object)
    out["reason"] = pd.Series(reasons, index=out.index, dtype=object)
    out["flags"] = flags
    fit_layers = gpd.GeoDataFrame(layer_rows, columns=["parcel_id", "layer", "geometry"],
                                  geometry="geometry", crs=crs)
    return out, fit_layers


def fit_stage(area: str) -> tuple[Path, Path]:
    base = Path("data/interim") / area
    classified = gpd.read_parquet(base / "parcels_classified.parquet")
    footprints = gpd.read_parquet(base / "footprints.parquet")
    neighbors = gpd.read_parquet(base / NEIGHBORS_FILE)
    out, layers = run_fit(classified, footprints, load_zones(), load_run_config(), neighbors=neighbors)
    p_fit, p_layers = base / "parcels_fit.parquet", base / "fit_layers.parquet"
    out.to_parquet(p_fit)
    layers.to_parquet(p_layers)
    return p_fit, p_layers
