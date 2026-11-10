"""Classify stage: apply the non-geometric filters and flags."""
from pathlib import Path

import geopandas as gpd
import pandas as pd

from adu.config import load_run_config, load_zones

SPLIT_ZONE_MIN_PCT = 90.0


def merge_flags(existing: str, *new: str) -> str:
    """Deduplicated, alphabetically sorted ';'-joined flag set ('' for none)."""
    parts = {f for f in (existing or "").split(";") if f}
    parts.update(f for f in new if f)
    return ";".join(sorted(parts))


def _not_sfd(row, n_big: int, sfd: dict, zone_rule: dict) -> bool:
    lu, st = row["land_use"], row["structure"]
    has_lu, has_st = pd.notna(lu), pd.notna(st)
    if not has_lu and not has_st:
        return n_big > 1 or bool(zone_rule.get("missing_sdat_not_sfd", False))
    if has_lu and lu not in sfd["land_use"]:
        return True
    return bool(has_st and st not in sfd["structure"])


def classify(parcels: gpd.GeoDataFrame, footprints: gpd.GeoDataFrame, zones: dict, run: dict) -> gpd.GeoDataFrame:
    sfd = zones["sfd_codes"]
    zone_cfg = zones["zones"]
    min_area = run["min_area_sqft"]
    threshold = run["misalign_threshold"]

    footprints = footprints.assign(
        fp_area_sqft=pd.to_numeric(footprints["fp_area_sqft"]),
        outside_frac=pd.to_numeric(footprints["outside_frac"]),
        is_principal=footprints["is_principal"].astype(bool),
    )
    fp_count = footprints.groupby("parcel_id").size()
    big_count = footprints[footprints["fp_area_sqft"] >= min_area].groupby("parcel_id").size()
    principal = footprints[footprints["is_principal"]].groupby("parcel_id")["outside_frac"].max()

    statuses, reasons, flags = [], [], []
    for _, row in parcels.iterrows():
        pid = row["parcel_id"]
        reason = None
        if _not_sfd(row, int(big_count.get(pid, 0)), sfd, zone_cfg.get(row["zone"], {})):
            reason = "not_sfd"
        elif not zone_cfg.get(row["zone"], {}).get("adu_eligible", False):
            reason = "zone_ineligible"
        elif fp_count.get(pid, 0) == 0:
            reason = "no_house_footprint"

        f = ""
        if pd.notna(principal.get(pid)) and principal.get(pid) > threshold:
            f = merge_flags(f, "footprint_misaligned")
        if pd.isna(row["living_area_sqft"]):
            f = merge_flags(f, "missing_living_area")
        if pd.notna(row["zone_overlap_pct"]) and row["zone_overlap_pct"] < SPLIT_ZONE_MIN_PCT:
            f = merge_flags(f, "split_zoned")
        if row.geometry is not None and row.geometry.geom_type == "MultiPolygon":
            f = merge_flags(f, "odd_shape")

        if reason:
            status = "ineligible"
        elif pd.notna(row["town"]):
            status = "flagged_town"
        elif f:
            status = "uncertain"
        else:
            status = None
        statuses.append(status)
        reasons.append(reason)
        flags.append(f)

    out = parcels.copy()
    out["status"] = pd.Series(statuses, index=out.index, dtype=object)
    out["reason"] = pd.Series(reasons, index=out.index, dtype=object)
    out["flags"] = flags
    return out


def classify_stage(area: str) -> Path:
    base = Path("data/interim") / area
    parcels = gpd.read_parquet(base / "parcels_prepared.parquet")
    footprints = gpd.read_parquet(base / "footprints.parquet")
    out = classify(parcels, footprints, load_zones(), load_run_config())
    path = base / "parcels_classified.parquet"
    out.to_parquet(path)
    return path
