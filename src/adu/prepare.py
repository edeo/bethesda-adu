"""Prepare stage: raw downloads -> one clean parcel table plus a footprint table."""
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry import box

from adu.config import load_run_config, load_sources

WORKING_CRS = "EPSG:2248"
PARCEL_COLUMNS = [
    "parcel_id", "sdat_account", "geometry", "lot_area_sqft", "zone",
    "zone_overlap_pct", "zcta", "town", "land_use", "structure",
    "living_area_sqft", "address", "sdat_duplicate",
]
FOOTPRINT_COLUMNS = [
    "fp_id", "parcel_id", "geometry", "fp_area_sqft", "outside_frac", "is_principal",
]


def _polygonal(geom):
    """Repair a geometry and keep only its polygon parts (None if nothing is left)."""
    if geom is None or geom.is_empty:
        return None
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    parts = [g for g in getattr(geom, "geoms", []) if g.geom_type in ("Polygon", "MultiPolygon")]
    if not parts:
        return None
    return shapely.union_all(parts)


def _read(raw_dir: Path, name: str, columns: list[str]) -> gpd.GeoDataFrame:
    """Read a raw layer into the working CRS; an empty layer still has its expected columns."""
    gdf = gpd.read_file(raw_dir / f"{name}.geojson")
    gdf = gdf.reindex(columns=[*columns, "geometry"]).set_geometry("geometry")
    gdf = gdf.set_crs("EPSG:4326", allow_override=True).to_crs(WORKING_CRS)
    gdf["geometry"] = gdf.geometry.map(_polygonal) if name != "sdat" else gdf.geometry
    gdf = gdf[gdf.geometry.notna()].reset_index(drop=True)
    return gdf


def _eval_transform(df: pd.DataFrame, transform: str) -> pd.Series:
    """Evaluate a join_transform such as "'16' + DISTRICT + ACCT" (literals and columns joined by +)."""
    result = None
    for token in (t.strip() for t in transform.split("+")):
        if re.fullmatch(r"'[^']*'|\"[^\"]*\"", token):
            part = token[1:-1]
        else:
            part = df[token].astype("string")
        result = part if result is None else result + part
    return result


def _first_match(points: gpd.GeoDataFrame, layer: gpd.GeoDataFrame, column: str) -> pd.Series:
    joined = gpd.sjoin(points[["geometry"]], layer[[column, "geometry"]], predicate="within", how="left")
    joined = joined[~joined.index.duplicated(keep="first")]
    return joined[column].reindex(points.index).astype(object).where(lambda s: s.notna(), None)


def _study_area(raw_dir: Path, area: str, run_cfg: dict):
    """Study ZCTA union; for the pilot, only the part of it inside the pilot bbox."""
    zctas = gpd.read_file(raw_dir / "zcta.geojson").to_crs(WORKING_CRS).geometry.union_all()
    if area == "pilot":
        bbox = gpd.GeoSeries([box(*run_cfg["pilot_bbox_lonlat"])], crs="EPSG:4326").to_crs(WORKING_CRS).iloc[0]
        return bbox.intersection(zctas)
    return zctas


def prepare(raw_dir: Path, out_dir: Path, area: str, sources: dict | None = None,
            run_cfg: dict | None = None) -> tuple[Path, Path]:
    raw_dir, out_dir = Path(raw_dir), Path(out_dir)
    sources = sources or load_sources()
    run_cfg = run_cfg or load_run_config()
    pf, zf, sf = sources["parcels"]["fields"], sources["zoning"]["fields"], sources["sdat"]["fields"]

    raw_parcels = _read(raw_dir, "parcels", [pf["parcel_id"], pf["sdat_account"], pf["sdat_district"]])
    zoning = _read(raw_dir, "zoning", [zf["zone"]])
    footprints = _read(raw_dir, "footprints", [])
    sdat = _read(raw_dir, "sdat", list(sf.values()))
    zcta = _read(raw_dir, "zcta", [sources["zcta"]["fields"]["zcta"]])
    places = _read(raw_dir, "places", [sources["places"]["fields"]["name"]])

    parcels = gpd.GeoDataFrame({
        "parcel_id": raw_parcels[pf["parcel_id"]].astype(str),
        "sdat_account": _eval_transform(raw_parcels, sources["parcels"]["join_transform"])
        .astype(object).where(lambda s: s.notna(), None),
        "geometry": raw_parcels.geometry,
    }, crs=WORKING_CRS)

    # Study-area clip by representative point, so odd-shaped lots stay inside themselves.
    parcels = parcels[parcels.representative_point().within(_study_area(raw_dir, area, run_cfg))]
    parcels = parcels.reset_index(drop=True)
    parcels["lot_area_sqft"] = parcels.area
    points = gpd.GeoDataFrame(geometry=parcels.representative_point(), crs=WORKING_CRS)

    # Zone: the zone at the representative point; overlap = share of the lot in that zone.
    zone_col = zf["zone"]
    parcels["zone"] = _first_match(points, zoning, zone_col)
    pieces = gpd.overlay(
        parcels[["parcel_id", "geometry"]], zoning[[zone_col, "geometry"]],
        how="intersection", keep_geom_type=False,
    )
    pieces["piece_area"] = pieces.area
    by_zone = pieces.groupby(["parcel_id", zone_col])["piece_area"].sum().reset_index()
    by_zone = by_zone.rename(columns={zone_col: "zone"})
    parcels = parcels.merge(by_zone, on=["parcel_id", "zone"], how="left")
    parcels["zone_overlap_pct"] = (100 * parcels.pop("piece_area") / parcels.lot_area_sqft).fillna(0.0).clip(upper=100.0)

    parcels["zcta"] = _first_match(points, zcta, sources["zcta"]["fields"]["zcta"])
    parcels["town"] = _first_match(points, places, sources["places"]["fields"]["name"])

    # SDAT: joined by account, never spatially. Duplicates collapse to one row and are flagged.
    key = sources["sdat"]["join_key"]
    sd = pd.DataFrame({
        "sdat_account": sdat[sf["sdat_account"]].astype(str) if key == sf["sdat_account"] else sdat[key].astype(str),
        "land_use": sdat[sf["land_use"]].astype(object),
        "structure": sdat[sf["structure"]].astype(object),
        "living_area_sqft": pd.to_numeric(sdat[sf["living_area"]], errors="coerce"),
        "address": sdat[sf["address"]].astype(object),
    })
    counts = sd.groupby("sdat_account")["sdat_account"].transform("size")
    sd["sdat_duplicate"] = counts > 1
    sd = sd.drop_duplicates("sdat_account", keep="first")
    parcels = parcels.merge(sd, on="sdat_account", how="left")
    parcels["sdat_duplicate"] = parcels["sdat_duplicate"].fillna(False).astype(bool)
    for col in ("land_use", "structure", "address"):
        parcels[col] = parcels[col].astype(object).where(parcels[col].notna(), None)
    parcels = gpd.GeoDataFrame(parcels[PARCEL_COLUMNS], geometry="geometry", crs=WORKING_CRS)

    # Footprints: assign to the parcel holding the largest share of each footprint.
    footprints = footprints[["geometry"]].copy()
    footprints["fp_id"] = footprints.index.astype(int)
    footprints["fp_area_sqft"] = footprints.area
    footprints = footprints[footprints.fp_area_sqft > 0]
    pieces = gpd.overlay(
        footprints[["fp_id", "geometry"]], parcels[["parcel_id", "geometry"]],
        how="intersection", keep_geom_type=False,
    )
    pieces["inside"] = pieces.area
    best = pieces.sort_values("inside", ascending=False).drop_duplicates("fp_id")[["fp_id", "parcel_id", "inside"]]
    fps = footprints.merge(best, on="fp_id", how="inner")
    fps["outside_frac"] = (1 - fps.pop("inside") / fps.fp_area_sqft).clip(lower=0.0)
    largest = fps.groupby("parcel_id")["fp_area_sqft"].transform("max")
    fps["is_principal"] = False
    fps.loc[fps.groupby("parcel_id")["fp_area_sqft"].idxmax(), "is_principal"] = True
    assert (fps.loc[fps.is_principal, "fp_area_sqft"] == largest[fps.is_principal]).all()
    fps = gpd.GeoDataFrame(fps[FOOTPRINT_COLUMNS], geometry="geometry", crs=WORKING_CRS)

    out_dir.mkdir(parents=True, exist_ok=True)
    parcels_path, fp_path = out_dir / "parcels_prepared.parquet", out_dir / "footprints.parquet"
    parcels.to_parquet(parcels_path)
    fps.to_parquet(fp_path)
    return parcels_path, fp_path
