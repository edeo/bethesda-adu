"""Build the aerial verification viewer: viewer/index.html + viewer/sample.geojson."""
import json
import math
from importlib import resources
from pathlib import Path

import geopandas as gpd
import pandas as pd

from adu.config import _load_yaml
from adu.sample import select_sample

PRECISION = 7
OUT_DIR = Path("viewer")
PROPERTY_COLUMNS = (
    "parcel_id", "sdat_account", "address", "zone", "zcta", "town", "lot_area_sqft",
    "living_area_sqft", "status", "reason", "flags", "fit_result", "fit_reason",
    "pocket_area_sqft", "rect_w_ft", "rect_l_ft", "usable_footprint_sqft",
    "max_adu_floor_area", "stratum",
)


def _round(coords):
    if isinstance(coords[0], (int, float)):
        return [round(c, PRECISION) for c in coords]
    return [_round(c) for c in coords]


def _geom(g) -> dict | None:
    """GeoJSON geometry dict with coordinates rounded to 7 decimals."""
    if g is None or g.is_empty:
        return None
    d = g.__geo_interface__
    if d["type"] == "GeometryCollection":
        return {"type": d["type"], "geometries": [_geom(x) for x in g.geoms]}
    return {"type": d["type"], "coordinates": _round(d["coordinates"])}


def _clean(v):
    if v is None or v is pd.NA:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float):
        return round(v, 2)
    return v


def build_collection(area: str, sample: gpd.GeoDataFrame, layers: gpd.GeoDataFrame,
                     footprints: gpd.GeoDataFrame, imagery: dict) -> dict:
    """One Feature per sampled parcel; properties.layers maps layer name -> geometry."""
    sample = sample.to_crs(4326)
    ids = set(sample.parcel_id)
    layers = layers[layers.parcel_id.isin(ids)].to_crs(4326)
    fps = footprints[footprints.parcel_id.isin(ids)].to_crs(4326)

    by_parcel: dict[str, dict] = {pid: {} for pid in ids}
    for pid, name, geom in zip(layers.parcel_id, layers["layer"], layers.geometry):
        by_parcel[pid][name] = _geom(geom)
    for pid, grp in fps.groupby("parcel_id"):
        principal = grp[grp.is_principal.astype(bool)]
        other = grp[~grp.is_principal.astype(bool)]
        if len(principal):
            by_parcel[pid]["house"] = _geom(principal.geometry.union_all())
        if len(other):
            by_parcel[pid]["accessory"] = _geom(other.geometry.union_all())

    features = []
    for _, row in sample.iterrows():
        props = {c: _clean(row[c]) for c in PROPERTY_COLUMNS if c in sample.columns}
        props["layers"] = {k: v for k, v in by_parcel[row.parcel_id].items() if v}
        features.append({"type": "Feature", "geometry": _geom(row.geometry), "properties": props})
    return {"type": "FeatureCollection", "area": area, "imagery": imagery, "features": features}


def build_viewer(area: str) -> Path:
    """Write viewer/sample.geojson and viewer/index.html; return the viewer directory."""
    base = Path("data/interim") / area
    fit = gpd.read_parquet(base / "parcels_fit.parquet")
    layers = gpd.read_parquet(base / "fit_layers.parquet")
    footprints = gpd.read_parquet(base / "footprints.parquet")
    src = _load_yaml(Path("config/sources.yaml"))["imagery"]
    imagery = {"url": src["url"], "fallback": src["fallback"]["url"]}

    sample = select_sample(fit)
    collection = build_collection(area, sample, layers, footprints, imagery)

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "sample.geojson").write_text(json.dumps(collection, separators=(",", ":")))
    html = resources.files("adu").joinpath("templates/viewer.html").read_text(encoding="utf-8")
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    print(sample["stratum"].value_counts().sort_index().to_string())
    return OUT_DIR
