import geopandas as gpd
import pandas as pd
import pytest

from adu.prepare import prepare
from synth import bowtie, rect

ACCT = "00000001"
KEY = "160700000001"  # '16' + district 07 + account


def run(raw, tmp_path, run_cfg):
    d = raw.write()
    p, f = prepare(d, tmp_path / "out", "pilot", run_cfg=run_cfg)
    return gpd.read_parquet(p), gpd.read_parquet(f)


def basic(raw):
    raw.parcel(rect(0, 0, 100, 60), 1, ACCT)
    raw.zone(rect(-50, -50, 300, 200), "R-60")
    raw.sdat_row(KEY)


def test_reprojects_to_2248(raw, tmp_path, run_cfg):
    basic(raw)
    parcels, _ = run(raw, tmp_path, run_cfg)
    assert parcels.crs.to_epsg() == 2248
    assert parcels.loc[0, "lot_area_sqft"] == pytest.approx(6000, abs=1)
    assert parcels.loc[0, "parcel_id"] == "1"
    assert parcels.loc[0, "sdat_account"] == KEY
    assert parcels.loc[0, "living_area_sqft"] == 1500.0
    assert parcels.loc[0, "zcta"] == "20816"


def test_zone_by_centroid_and_overlap(raw, tmp_path, run_cfg):
    raw.parcel(rect(0, 0, 100, 60), 1, ACCT)
    raw.zone(rect(-10, -10, 80, 100), "R-60")  # x 0..70 of the lot
    raw.zone(rect(70, -10, 100, 100), "R-90")
    parcels, _ = run(raw, tmp_path, run_cfg)
    assert parcels.loc[0, "zone"] == "R-60"
    assert parcels.loc[0, "zone_overlap_pct"] == pytest.approx(70, abs=1)


def test_invalid_geometry_repaired(raw, tmp_path, run_cfg):
    raw.parcel(bowtie(), 1, ACCT)
    raw.zone(rect(-50, -50, 300, 300), "R-60")
    parcels, _ = run(raw, tmp_path, run_cfg)
    assert len(parcels) == 1
    assert parcels.geometry.is_valid.all()


def test_missing_sdat_kept(raw, tmp_path, run_cfg):
    raw.parcel(rect(0, 0, 100, 60), 1, "99999999")
    raw.zone(rect(-50, -50, 300, 200), "R-60")
    raw.sdat_row(KEY)
    parcels, _ = run(raw, tmp_path, run_cfg)
    assert len(parcels) == 1
    assert pd.isna(parcels.loc[0, "living_area_sqft"])
    assert pd.isna(parcels.loc[0, "land_use"])
    assert not parcels.loc[0, "sdat_duplicate"]


def test_duplicate_sdat_no_row_explosion(raw, tmp_path, run_cfg):
    basic(raw)
    raw.sdat_row(KEY, living=900.0)
    parcels, _ = run(raw, tmp_path, run_cfg)
    assert len(parcels) == 1
    assert bool(parcels.loc[0, "sdat_duplicate"]) is True


def test_footprint_assigned_to_majority_parcel(raw, tmp_path, run_cfg):
    raw.parcel(rect(0, 0, 100, 60), 1, ACCT)
    raw.parcel(rect(100, 0, 100, 60), 2, "00000002")
    raw.zone(rect(-50, -50, 400, 200), "R-60")
    raw.footprint(rect(70, 10, 50, 20))  # 30 of 50 ft in parcel 1 (60%)
    raw.footprint(rect(85, 10, 50, 20))  # 15 of 50 ft in parcel 1, 35 in parcel 2
    _, fps = run(raw, tmp_path, run_cfg)
    by_id = fps.set_index("fp_id")
    assert by_id.loc[0, "parcel_id"] == "1"
    assert by_id.loc[0, "outside_frac"] == pytest.approx(0.4, abs=0.01)
    assert by_id.loc[1, "parcel_id"] == "2"
    assert by_id.loc[1, "outside_frac"] == pytest.approx(0.3, abs=0.01)


def test_outside_frac_thirty_percent(raw, tmp_path, run_cfg):
    raw.parcel(rect(0, 0, 100, 60), 1, ACCT)
    raw.zone(rect(-50, -50, 400, 200), "R-60")
    raw.footprint(rect(65, 10, 50, 20))  # 35 of 50 ft inside -> 30% outside
    _, fps = run(raw, tmp_path, run_cfg)
    assert len(fps) == 1
    assert fps.loc[0, "parcel_id"] == "1"
    assert fps.loc[0, "outside_frac"] == pytest.approx(0.3, abs=0.01)
    assert fps.loc[0, "fp_area_sqft"] == pytest.approx(1000, abs=1)


def test_principal_is_largest(raw, tmp_path, run_cfg):
    basic(raw)
    raw.footprint(rect(5, 5, 20, 10))
    raw.footprint(rect(30, 5, 40, 30))
    _, fps = run(raw, tmp_path, run_cfg)
    assert fps.set_index("fp_id")["is_principal"].to_dict() == {0: False, 1: True}


def test_town_assigned_by_centroid(raw, tmp_path, run_cfg):
    raw.parcel(rect(0, 0, 100, 60), 1, ACCT)
    raw.parcel(rect(500, 0, 100, 60), 2, "00000002")
    raw.zone(rect(-50, -50, 800, 200), "R-60")
    raw.place(rect(-10, -10, 200, 100), "Somerset town")
    parcels, _ = run(raw, tmp_path, run_cfg)
    towns = parcels.set_index("parcel_id")["town"]
    assert towns["1"] == "Somerset town"
    assert pd.isna(towns["2"])
