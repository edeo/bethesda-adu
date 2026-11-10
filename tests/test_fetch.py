import json

import pytest

from adu import fetch
from adu.fetch import fetch_arcgis

BBOX = (-77.11, 38.96, -77.098, 38.968)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeSession:
    """Serves canned pages in order; records the params of each request."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        page = self.pages.pop(0)
        if isinstance(page, Exception):
            raise page
        return FakeResponse(page)


def _page(n, start=0):
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"i": start + i}, "geometry": None}
            for i in range(n)
        ],
    }


def _run(tmp_path, pages=(2000, 2000, 500), **kw):
    sess = FakeSession([_page(n) for n in pages])
    out = tmp_path / "pilot" / "x.geojson"
    manifest = tmp_path / "manifest.json"
    n = fetch_arcgis("http://h/0", BBOX, out, session=sess, manifest_path=manifest, **kw)
    return n, sess, out, manifest


def test_paging_concatenates(tmp_path):
    n, sess, out, _ = _run(tmp_path)
    assert n == 4500
    assert len(json.loads(out.read_text())["features"]) == 4500
    assert [c[1]["resultOffset"] for c in sess.calls] == [0, 2000, 4000]
    assert all(c[1]["outSR"] == 4326 and c[1]["f"] == "geojson" for c in sess.calls)


def test_manifest_appended(tmp_path):
    _, _, out, manifest = _run(tmp_path)
    entries = json.loads(manifest.read_text())
    assert len(entries) == 1
    e = entries[0]
    assert e["count"] == 4500 and e["url"] == "http://h/0"
    assert e["file"] == str(out) and e["where"] == "1=1"
    assert e["bbox"] == list(BBOX) and e["downloaded_at"]


def test_refuses_overwrite(tmp_path):
    _run(tmp_path)
    with pytest.raises(FileExistsError):
        _run(tmp_path)


def test_force_overwrites(tmp_path):
    _run(tmp_path)
    n, _, _, _ = _run(tmp_path, pages=(3,), force=True)
    assert n == 3


def test_http_error_raises(tmp_path):
    sess = FakeSession([{"error": {"code": 400, "message": "Invalid query"}}])
    with pytest.raises(RuntimeError, match="Invalid query"):
        fetch_arcgis("http://h/0", BBOX, tmp_path / "a.geojson", session=sess,
                     manifest_path=tmp_path / "m.json")
    assert not (tmp_path / "a.geojson").exists()


def test_stops_when_transfer_limit_false(tmp_path):
    page = _page(2000)
    page["exceededTransferLimit"] = False
    sess = FakeSession([page])
    n = fetch_arcgis("http://h/0", BBOX, tmp_path / "a.geojson", session=sess,
                     manifest_path=tmp_path / "m.json")
    assert n == 2000 and len(sess.calls) == 1


def _patch_config(monkeypatch, tmp_path, sess):
    sources = {
        "parcels": {"url": "http://primary/0", "layer_type": "arcgis_rest",
                    "fields": {"a": "A"}, "max_record_count": 1000,
                    "fallback": {"url": "http://fallback/0", "layer_type": "arcgis_rest",
                                 "where": "J = 1"}},
        "imagery": {"url": "http://img", "layer_type": "xyz_tiles", "fallback": None},
    }
    monkeypatch.setattr(fetch, "load_sources", lambda: sources)
    monkeypatch.setattr(fetch, "load_run_config", lambda: {
        "pilot_bbox_lonlat": list(BBOX), "zctas": ["20814"]})
    monkeypatch.setattr(fetch, "RAW_DIR", tmp_path)
    monkeypatch.setattr(fetch.requests, "Session", lambda: sess)


def test_fallback_used_and_recorded(monkeypatch, tmp_path):
    sess = FakeSession([RuntimeError("boom"), _page(5)])
    _patch_config(monkeypatch, tmp_path, sess)
    counts = fetch.fetch_all("pilot")
    assert counts == {"parcels": 5}
    assert sess.calls[0][0] == "http://primary/0/query"
    assert sess.calls[0][1]["resultRecordCount"] == 1000
    assert sess.calls[1][0] == "http://fallback/0/query"
    assert sess.calls[1][1]["where"] == "J = 1"
    entries = json.loads((tmp_path / "manifest.json").read_text())
    assert entries[-1]["used_fallback"] is True
    assert entries[-1]["url"] == "http://fallback/0"
    assert (tmp_path / "pilot" / "parcels.geojson").exists()


def test_zero_features_triggers_fallback(monkeypatch, tmp_path):
    sess = FakeSession([_page(0), _page(2)])
    _patch_config(monkeypatch, tmp_path, sess)
    assert fetch.fetch_all("pilot") == {"parcels": 2}


def test_full_uses_zcta_bounds_as_bbox(monkeypatch, tmp_path):
    zcta = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {
            "type": "Polygon",
            "coordinates": [[[-77.2, 38.9], [-77.0, 38.9], [-77.0, 39.1], [-77.2, 39.1], [-77.2, 38.9]]]}}]}
    sess = FakeSession([zcta, _page(1)])
    _patch_config(monkeypatch, tmp_path, sess)
    sources = fetch.load_sources()
    sources["zcta"] = {"url": "http://z/0", "layer_type": "arcgis_rest",
                       "fields": {"z": "Z"}, "fallback": None}
    counts = fetch.fetch_all("full")
    assert counts == {"zcta": 1, "parcels": 1}
    assert sess.calls[0][1]["where"] == "ZCTA5 IN ('20814')"
    assert sess.calls[1][1]["geometry"] == "-77.2,38.9,-77.0,39.1"


def test_paging_continues_when_server_caps_below_page_size(tmp_path):
    pages = []
    for n, flag in ((1000, True), (1000, True), (300, False)):
        p = _page(n)
        p["exceededTransferLimit"] = flag
        pages.append(p)
    sess = FakeSession(pages)
    out = tmp_path / "a.geojson"
    n = fetch_arcgis("http://h/0", BBOX, out, page_size=2000, session=sess,
                     manifest_path=tmp_path / "m.json")
    assert n == 2300
    assert [c[1]["resultOffset"] for c in sess.calls] == [0, 1000, 2000]
