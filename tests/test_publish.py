import csv
import json

import geopandas as gpd
import pytest
from shapely.geometry import box

from adu.publish import CSV_COLUMNS, SCREENING_CAVEAT, publish

# (parcel_id, status, zcta, zone, max_adu, pocket)
ROWS = [
    ("a", "fits", "20814", "R-60", 600.0, 900.0),
    ("b", "fits", "20816", "R-90", 800.0, 700.0),
    ("c", "fits", "20817", "R-60", 600.0, 1200.0),
    ("d", "flagged_town", "20814", "R-60", 900.0, 1000.0),
    ("e", "uncertain", "20816", "R-90", None, None),
    ("f", "no_fit", "20817", "R-60", None, None),
    ("g", "ineligible", "20817", "CR-1", None, None),
]


@pytest.fixture
def interim(tmp_path):
    d = tmp_path / "interim" / "full"
    d.mkdir(parents=True)
    recs = []
    for i, (pid, status, zcta, zone, adu, pocket) in enumerate(ROWS):
        x = i * 200
        recs.append({
            "parcel_id": pid, "sdat_account": f"acct{pid}", "geometry": box(x, 0, x + 100, 100),
            "lot_area_sqft": 10000.0, "zone": zone, "zone_overlap_pct": 100.0, "zcta": zcta,
            "town": "Chevy Chase" if status == "flagged_town" else None,
            "land_use": "R", "structure": "S", "living_area_sqft": 2000.0,
            "address": f"{i} Main St", "sdat_duplicate": False, "is_row": False,
            "status": status, "reason": "r" if status in ("no_fit", "ineligible") else None,
            "flags": "", "fit_result": None, "fit_reason": None, "pocket_area_sqft": pocket,
            "rect_w_ft": 20.0 if adu else None, "rect_l_ft": 30.0 if adu else None,
            "usable_footprint_sqft": adu, "max_adu_floor_area": adu,
        })
    gpd.GeoDataFrame(recs, crs=2248).to_parquet(d / "parcels_fit.parquet")
    fps = [{"fp_id": i, "parcel_id": r[0], "geometry": box(i * 200 + 10, 10, i * 200 + 50, 60),
            "fp_area_sqft": 2000.0, "outside_frac": 0.0, "is_principal": True}
           for i, r in enumerate(ROWS)]
    gpd.GeoDataFrame(fps, crs=2248).to_parquet(d / "footprints.parquet")
    return d


@pytest.fixture
def outputs(interim, tmp_path):
    paths = publish("full", interim_dir=interim, out_dir=tmp_path / "out")
    return {p.name: p for p in paths}


def test_returns_three_files(outputs):
    assert set(outputs) == {"adu_map.html", "adu_candidates.csv", "summary.md"}
    assert all(p.exists() for p in outputs.values())


def test_csv_columns_exact(outputs):
    with open(outputs["adu_candidates.csv"]) as f:
        header = next(csv.reader(f))
    assert header == [
        "address", "sdat_account", "zcta", "zone", "lot_sqft", "house_living_sqft",
        "house_footprint_sqft", "rect_w_ft", "rect_l_ft", "usable_footprint_sqft",
        "max_adu_floor_area", "status", "reason", "flags"]
    assert header == list(CSV_COLUMNS)


def test_csv_rows_and_ordering(outputs):
    with open(outputs["adu_candidates.csv"]) as f:
        rows = list(csv.DictReader(f))
    # d (900) > b (800) > c (600, pocket 1200) > a (600, pocket 900) > e (no size, last)
    assert [r["sdat_account"] for r in rows] == ["acctd", "acctb", "acctc", "accta", "accte"]
    assert {r["status"] for r in rows} == {"fits", "flagged_town", "uncertain"}
    assert rows[0]["house_footprint_sqft"] == "2000.0"


def test_headline_counts_only_fits(outputs):
    text = outputs["summary.md"].read_text()
    assert "Maximum detached ADUs: 3 lots" in text
    assert "flagged_town" in text and "uncertain" in text


def test_caveat_present(outputs):
    text = outputs["summary.md"].read_text()
    assert "This is a screening estimate, not a permitting determination." in text
    assert SCREENING_CAVEAT in text
    for note in ("1-story", "rear wall", "both street frontages", "predate", "40/40"):
        assert note in text


def test_map_embeds_data_and_is_standalone(outputs):
    html = outputs["adu_map.html"].read_text()
    assert "preferCanvas: true" in html
    assert "const PARCELS =" in html
    assert 'fetch("' not in html
    start = html.index("const PARCELS =") + len("const PARCELS =")
    end = html.index(";\n", start)
    data = json.loads(html[start:end])
    assert len(data["features"]) == len(ROWS)
    props = data["features"][0]["properties"]
    assert "status" in props


def _summary_df(fit_results):
    import pandas as pd
    return pd.DataFrame({
        "status": ["uncertain"] * len(fit_results) + ["flagged_town"] * 2 + ["fits"],
        "fit_result": list(fit_results) + ["fits", "no_fit", "fits"],
        "zcta": "20814", "zone": "R-60"})


def test_limits_lines_present(outputs):
    text = outputs["summary.md"].read_text()
    assert "corner-lot rear setback is applied to all corner lots" in text
    assert "only where the abutting lot fronts the side street" in text
    assert "+1 ft of setback per foot of ADU length beyond 24 ft" in text
    assert "usable_footprint_sqft" in text and "max_adu_floor_area" in text
    assert "front setback from both" in text and "undercounted" in text
    assert "`corner_lot_front: shorter` is a heuristic" in text


def test_uncertain_line_shows_geometric_fits():
    from adu.publish import build_summary
    text = build_summary(_summary_df(["fits", "fits", "no_fit", None]), {"zctas": ["20814"]})
    assert "uncertain: 4 (2 fit geometrically)" in text


def test_flagged_town_wording():
    from adu.publish import build_summary
    text = build_summary(_summary_df(["fits"]), {"zctas": ["20814"]})
    assert "flagged_town: 2 lots (in an incorporated town (town rules may apply); 1 fit geometrically)" in text
    assert "would fit" not in text
