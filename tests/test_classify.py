import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import MultiPolygon

from adu.classify import classify, merge_flags
from adu.config import load_run_config, load_zones
from synth import rect

ZONES = load_zones()
RUN = load_run_config()
SFD_LU = ZONES["sfd_codes"]["land_use"][0]
SFD_ST = ZONES["sfd_codes"]["structure"][0]
ELIGIBLE = next(z for z, v in ZONES["zones"].items() if v.get("adu_eligible"))
INELIGIBLE = next(z for z, v in ZONES["zones"].items() if not v.get("adu_eligible"))


def parcel(pid="1", **over):
    row = {"parcel_id": pid, "sdat_account": "A" + pid, "geometry": rect(0, 0, 100, 100), "lot_area_sqft": 10000.0,
           "zone": ELIGIBLE, "zone_overlap_pct": 100.0, "zcta": "20816", "town": None, "land_use": SFD_LU,
           "structure": SFD_ST, "living_area_sqft": 1500.0, "address": "1 TEST ST", "sdat_duplicate": False}
    row.update(over)
    return row


def fp(pid="1", i=0, area=1500.0, outside=0.0, principal=True, geom=None):
    return {"fp_id": i, "parcel_id": pid, "geometry": geom or rect(10, 10, 30, 30), "fp_area_sqft": area,
            "outside_frac": outside, "is_principal": principal}


def run(parcels, fps):
    p = gpd.GeoDataFrame(parcels, geometry="geometry", crs="EPSG:2248")
    f = gpd.GeoDataFrame(pd.DataFrame(fps, columns=list(fp())), geometry="geometry", crs="EPSG:2248")
    return classify(p, f, ZONES, RUN).set_index("parcel_id")


def one(p=None, fps=None, **over):
    out = run([parcel(**over)], fps if fps is not None else [fp()])
    r = out.loc["1"]
    return r["status"], r["reason"], r["flags"]


def test_clean_parcel_status_none():
    assert one() == (None, None, "")


def test_not_sfd_bad_structure():
    assert one(structure="0002")[:2] == ("ineligible", "not_sfd")


def test_not_sfd_bad_land_use():
    assert one(land_use="C")[:2] == ("ineligible", "not_sfd")


def test_townhouse_code_not_sfd():
    assert one(structure="0003")[:2] == ("ineligible", "not_sfd")


def test_only_present_code_tested():
    assert one(structure=None)[:2] == (None, None)
    assert one(land_use=None, structure="0002")[:2] == ("ineligible", "not_sfd")


def test_missing_sdat_one_house_is_uncertain_flag():
    status, reason, flags = one(land_use=None, structure=None, living_area_sqft=None)
    assert (status, reason) == ("uncertain", None)
    assert flags == "missing_living_area"


def test_missing_sdat_many_footprints_not_sfd():
    fps = [fp(i=0), fp(i=1, area=500.0, principal=False)]
    assert one(fps=fps, land_use=None, structure=None, living_area_sqft=None)[:2] == ("ineligible", "not_sfd")


def test_missing_sdat_small_extra_footprint_ok():
    fps = [fp(i=0), fp(i=1, area=200.0, principal=False)]
    assert one(fps=fps, land_use=None, structure=None, living_area_sqft=None)[1] is None


def test_zone_ineligible_listed():
    assert one(zone=INELIGIBLE)[:2] == ("ineligible", "zone_ineligible")


def test_zone_ineligible_absent():
    assert one(zone="NOPE-ZONE")[:2] == ("ineligible", "zone_ineligible")
    assert one(zone=None)[:2] == ("ineligible", "zone_ineligible")


def test_zero_footprints_ineligible():
    assert one(fps=[])[:2] == ("ineligible", "no_house_footprint")


def test_reason_order():
    assert one(fps=[], zone=INELIGIBLE, structure="0002")[1] == "not_sfd"
    assert one(fps=[], zone=INELIGIBLE)[1] == "zone_ineligible"


def test_town():
    assert one(town="Somerset town")[:2] == ("flagged_town", None)


def test_precedence_ineligible_beats_town():
    assert one(town="Somerset town", structure="0003")[:2] == ("ineligible", "not_sfd")


def test_town_keeps_flags():
    status, _, flags = one(town="Somerset town", living_area_sqft=None)
    assert status == "flagged_town"
    assert "missing_living_area" in flags


def test_misaligned():
    r = one(fps=[fp(outside=0.5)])
    assert r == ("uncertain", None, "footprint_misaligned")


def test_misaligned_uses_principal_only():
    fps = [fp(i=0), fp(i=1, outside=0.9, principal=False)]
    assert one(fps=fps)[2] == ""


def test_split_zoned():
    assert one(zone_overlap_pct=80.0) == ("uncertain", None, "split_zoned")
    assert one(zone_overlap_pct=90.0)[2] == ""


def test_odd_shape_multipolygon():
    g = MultiPolygon([rect(0, 0, 50, 50), rect(60, 0, 40, 50)])
    r = one(geometry=g)
    assert r == ("uncertain", None, "odd_shape")


def test_multiple_flags_sorted_joined():
    assert one(living_area_sqft=None, zone_overlap_pct=50.0)[2] == "missing_living_area;split_zoned"


def test_ineligible_has_no_status_for_others_and_flags_str():
    out = run([parcel("1"), parcel("2", zone=INELIGIBLE)], [fp("1"), fp("2", i=1)])
    assert out["flags"].tolist() == ["", ""]
    assert out.loc["2", "status"] == "ineligible"


def test_merge_flags():
    assert merge_flags("", "odd_shape") == "odd_shape"
    assert merge_flags("split_zoned", "odd_shape", "split_zoned") == "odd_shape;split_zoned"
    assert merge_flags("") == ""


def _zones_with(code, **rule):
    zones = {**ZONES, "zones": {**ZONES["zones"], code: {**ZONES["zones"][ELIGIBLE], **rule}}}
    return zones


def _run_zone(rule_over, **over):
    zones = _zones_with("MIXED-X", **rule_over)
    p = gpd.GeoDataFrame([parcel(zone="MIXED-X", **over)], geometry="geometry", crs="EPSG:2248")
    f = gpd.GeoDataFrame(pd.DataFrame([fp()], columns=list(fp())), geometry="geometry", crs="EPSG:2248")
    r = classify(p, f, zones, RUN).set_index("parcel_id").loc["1"]
    return r["status"], r["reason"], r["flags"]


def test_mixed_use_missing_sdat_is_not_sfd():
    status, reason, _ = _run_zone({"missing_sdat_not_sfd": True},
                                  land_use=None, structure=None, living_area_sqft=None)
    assert (status, reason) == ("ineligible", "not_sfd")


def test_residential_missing_sdat_still_uncertain():
    status, reason, flags = _run_zone({}, land_use=None, structure=None, living_area_sqft=None)
    assert (status, reason) == ("uncertain", None)
    assert "missing_living_area" in flags


def test_mixed_use_with_sfd_codes_proceeds():
    status, reason, _ = _run_zone({"missing_sdat_not_sfd": True})
    assert status != "ineligible" and reason is None
