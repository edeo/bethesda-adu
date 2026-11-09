"""Fit stage end to end on a synthetic block (EPSG:2248 feet).

Subject lot "1" is 60 x 120 with its front on the south side (y = 0). Neighbors sit west,
east and north; a right-of-way polygon covers the street to the south.
"""
import geopandas as gpd
import pandas as pd
import pytest

import adu.fit as fit_mod
from adu.fit import fit_stage, run_fit
from synth import CRS, X0, rect

R60 = {"adu_eligible": True, "setbacks_ft": {"front": 60, "side": 5, "side_street": 25, "rear": 5},
       "height_ft": 15, "coverage_cap": 0.35, "behind_front_line": True, "behind_rear_building_line": True}
RUN = {"min_dim_ft": 20, "min_area_sqft": 400, "separation_ft": 5, "shed_ignore_sqft": 0,
       "story_height_ft": 10, "max_stories": 1, "flag_pole_max_width_ft": 25, "rotations_deg": [0, 15, -15]}


def zones(**rule):
    return {"zones": {"R-60": {**R60, **rule}}, "adu_size_cap_ratio": 0.75, "corner_lot_front": "shorter"}


def row(pid, geom, status=None, reason=None, zone="R-60", is_row=False, living=1500.0, flags=""):
    return {"parcel_id": pid, "geometry": geom, "lot_area_sqft": geom.area, "zone": zone,
            "living_area_sqft": living, "status": status, "reason": reason, "flags": flags,
            "is_row": is_row, "town": None}


def block(subject_status=None, subject_zone="R-60", street_is_row=True):
    rows = [
        row("1", rect(0, 0, 60, 120), status=subject_status, zone=subject_zone),
        row("w", rect(-60, 0, 60, 120), status="ineligible", reason="not_sfd"),
        row("e", rect(60, 0, 60, 120), status="ineligible", reason="not_sfd"),
        row("n", rect(-60, 120, 180, 120), status="ineligible", reason="not_sfd"),
        row("street", rect(-100, -50, 300, 50), status="ineligible", reason="not_sfd",
            zone=None, is_row=street_is_row, living=None),
    ]
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=CRS)
    gdf["status"] = gdf["status"].astype(object).where(gdf["status"].notna(), None)
    return gdf


def footprints():
    house = rect(15, 25, 30, 40)
    return gpd.GeoDataFrame([{"fp_id": 0, "parcel_id": "1", "geometry": house, "fp_area_sqft": house.area,
                              "outside_frac": 0.0, "is_principal": True}], geometry="geometry", crs=CRS)


def subject(out):
    return out.set_index("parcel_id").loc["1"]


def test_end_to_end_rectangle_lot():
    out, layers = run_fit(block(), footprints(), zones(), RUN)
    s = subject(out)
    assert s["status"] == "fits" and s["fit_result"] == "fits"
    assert pd.isna(s["reason"]) and pd.isna(s["fit_reason"])
    assert "odd_shape" not in s["flags"]
    assert s["rect_w_ft"] >= 20 and s["rect_l_ft"] >= 20
    assert s["pocket_area_sqft"] == pytest.approx(50 * 45, rel=0.03)
    remaining = 7200 * 0.35 - 1200
    assert s["usable_footprint_sqft"] == pytest.approx(remaining)
    assert s["max_adu_floor_area"] == pytest.approx(min(0.75 * 1500, remaining))
    mine = layers[layers["parcel_id"] == "1"]
    kinds = set(mine["layer"])
    assert {"front", "side", "rear", "envelope", "pocket", "adu_rect"} <= kinds
    assert (mine["layer"] == "adu_rect").sum() == 1
    rect_geom = mine.loc[mine["layer"] == "adu_rect", "geometry"].iloc[0]
    assert rect(0, 0, 60, 120).contains(rect_geom)
    # parcels that are not fit keep null fit columns
    others = out[out["parcel_id"] != "1"]
    assert others["fit_result"].isna().all()
    assert set(others["status"]) == {"ineligible"}


def test_coverage_exhausted_reason():
    out, layers = run_fit(block(), footprints(), zones(coverage_cap=0.2), RUN)  # 1440 - 1200 = 240 < 400
    s = subject(out)
    assert s["status"] == "no_fit" and s["fit_result"] == "no_fit"
    assert s["reason"] == "coverage_exhausted" and s["fit_reason"] == "coverage_exhausted"
    assert pd.isna(s["max_adu_floor_area"])


def test_town_status_preserved():
    out, _ = run_fit(block(subject_status="flagged_town"), footprints(), zones(), RUN)
    s = subject(out)
    assert s["status"] == "flagged_town"
    assert s["fit_result"] == "fits"


def test_row_polygons_are_not_neighbors():
    # With the street counted as a neighbor the lot has no frontage -> odd_shape / uncertain.
    out, layers = run_fit(block(street_is_row=False), footprints(), zones(), RUN)
    s = subject(out)
    assert "odd_shape" in s["flags"] and s["status"] == "uncertain"
    out, layers = run_fit(block(street_is_row=True), footprints(), zones(), RUN)
    assert "front" in set(layers.loc[layers["parcel_id"] == "1", "layer"])


def test_no_zone_rule_no_fit():
    out, layers = run_fit(block(subject_zone="XYZ"), footprints(), zones(), RUN)
    s = subject(out)
    assert pd.isna(s["fit_result"]) and pd.isna(s["pocket_area_sqft"])
    assert (layers["parcel_id"] == "1").sum() == 0


def test_no_pocket_reason():
    # rear setback so deep nothing is left behind the house's rear wall (y = 65)
    out, _ = run_fit(block(), footprints(), zones(setbacks_ft={**R60["setbacks_ft"], "rear": 60}), RUN)
    s = subject(out)
    assert s["fit_result"] == "no_fit" and s["fit_reason"] == "no_pocket"


def test_pocket_too_small_reason():
    # pocket is the strip y 70..80 (10 ft deep) plus slivers: no 20 x 20 rectangle
    out, _ = run_fit(block(), footprints(), zones(setbacks_ft={**R60["setbacks_ft"], "rear": 40}), RUN)
    s = subject(out)
    assert s["fit_result"] == "no_fit" and s["fit_reason"] == "pocket_too_small"
    assert s["pocket_area_sqft"] > 0


def test_fit_stage_writes_files(tmp_path, monkeypatch):
    base = tmp_path / "data" / "interim" / "t"
    base.mkdir(parents=True)
    block().to_parquet(base / "parcels_classified.parquet")
    footprints().to_parquet(base / "footprints.parquet")
    block()[["parcel_id", "is_row", "geometry"]].to_parquet(base / "parcels_neighbors.parquet")
    monkeypatch.setattr(fit_mod, "load_zones", lambda: zones())
    monkeypatch.setattr(fit_mod, "load_run_config", lambda: RUN)
    monkeypatch.chdir(tmp_path)
    p_fit, p_layers = fit_stage("t")
    assert p_fit.name == "parcels_fit.parquet" and p_layers.name == "fit_layers.parquet"
    assert subject(gpd.read_parquet(p_fit))["status"] == "fits"
    assert "adu_rect" in set(gpd.read_parquet(p_layers)["layer"])


def _east_kinds(layers):
    """Edge kinds of the subject's east side (x = 60)."""
    mine = layers[(layers["parcel_id"] == "1") & layers["layer"].isin(["front", "side_street", "side", "rear"])]
    east = [k for k, g in zip(mine["layer"], mine.geometry)
            if abs(g.bounds[0] - (X0 + 60)) < 1e-6 and abs(g.bounds[2] - (X0 + 60)) < 1e-6]
    return east


def test_neighbor_outside_clip_not_street():
    full = block()
    clipped = full[full["parcel_id"] != "e"]  # east neighbor lies outside the study area
    neighbors = full[["parcel_id", "is_row", "geometry"]]
    out, layers = run_fit(clipped, footprints(), zones(), RUN, neighbors=neighbors)
    s = subject(out)
    assert _east_kinds(layers) == ["side"]
    assert "odd_shape" not in s["flags"] and s["status"] == "fits"
    # Without the unclipped layer the east side looks like a street (the bug being fixed).
    _, layers_clip = run_fit(clipped, footprints(), zones(), RUN)
    assert _east_kinds(layers_clip) != ["side"]


def test_coverage_over_cap_clamps_to_zero():
    # lot 7200 * 0.1 = 720 < 1200 sq ft of footprint; the pocket itself is non-empty
    out, _ = run_fit(block(), footprints(), zones(coverage_cap=0.1), RUN)
    s = subject(out)
    assert s["pocket_area_sqft"] > 0
    assert s["status"] == "no_fit" and s["reason"] == "coverage_exhausted"
    assert s["usable_footprint_sqft"] == 0
