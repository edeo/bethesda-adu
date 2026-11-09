import json

import geopandas as gpd
from shapely.geometry import box

from adu import __main__ as cli
from adu.viewer import build_collection


def test_collection_shape_and_rounding():
    parcel = box(1282000, 472000, 1282100, 472100)
    sample = gpd.GeoDataFrame(
        {"parcel_id": ["a"], "status": ["fits"], "reason": [None], "flags": [""],
         "stratum": ["fits"], "lot_area_sqft": [float("nan")]},
        geometry=[parcel], crs=2248)
    layers = gpd.GeoDataFrame(
        {"parcel_id": ["a", "z"], "layer": ["pocket", "pocket"]},
        geometry=[parcel.buffer(-5), parcel], crs=2248)
    fps = gpd.GeoDataFrame(
        {"parcel_id": ["a", "a"], "is_principal": [True, False]},
        geometry=[box(1282020, 472020, 1282040, 472040), box(1282060, 472060, 1282070, 472070)],
        crs=2248)
    out = build_collection("pilot", sample, layers, fps, {"url": "u", "fallback": "f"})
    json.dumps(out)
    (f,) = out["features"]
    assert set(f["properties"]["layers"]) == {"pocket", "house", "accessory"}
    assert f["properties"]["lot_area_sqft"] is None
    lon, lat = f["geometry"]["coordinates"][0][0]
    assert -78 < lon < -76 and 38 < lat < 40
    assert len(repr(lon).split(".")[1]) <= 7


def test_viewer_subcommand(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("adu.viewer.build_viewer", lambda area: tmp_path / area)
    cli.main(["viewer"])
    out = capsys.readouterr().out
    assert "python -m http.server 8000" in out and "localhost:8000/viewer/" in out
