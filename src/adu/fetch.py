"""Download raw GIS layers (EPSG:4326 GeoJSON) and record them in a manifest."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

import requests

from adu.config import load_run_config, load_sources

RAW_DIR = Path("data/raw")
MAX_PAGE_SIZE = 2000
TIMEOUT_S = 120


def _manifest_path() -> Path:
    return RAW_DIR / "manifest.json"


def _append_manifest(path: Path, entry: dict) -> None:
    entries = json.loads(path.read_text()) if path.exists() else []
    entries.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2))


def _more_pages(payload: dict, n: int, page_size: int) -> bool:
    if n < page_size:
        return False
    flag = payload.get("exceededTransferLimit")
    if flag is None:
        flag = (payload.get("properties") or {}).get("exceededTransferLimit")
    return flag is not False


def fetch_arcgis(
    url: str,
    bbox_lonlat: Optional[tuple[float, float, float, float]],
    out_path: Path,
    where: str = "1=1",
    page_size: int = MAX_PAGE_SIZE,
    session: Optional[requests.Session] = None,
    force: bool = False,
    manifest_path: Optional[Path] = None,
    extra_manifest: Optional[dict] = None,
) -> int:
    """Page through an ArcGIS REST layer query and write one GeoJSON file.

    bbox_lonlat None means no spatial filter. Returns the feature count.
    """
    out_path = Path(out_path)
    if out_path.exists() and not force:
        raise FileExistsError(f"{out_path} exists; raw files are not overwritten")
    session = session or requests.Session()
    params = {
        "where": where,
        "outFields": "*",
        "outSR": 4326,
        "f": "geojson",
        "resultRecordCount": page_size,
    }
    if bbox_lonlat is not None:
        params.update(
            geometry=",".join(str(v) for v in bbox_lonlat),
            geometryType="esriGeometryEnvelope",
            inSR=4326,
            spatialRel="esriSpatialRelIntersects",
        )
    features: list = []
    offset = 0
    while True:
        resp = session.get(url + "/query", params={**params, "resultOffset": offset},
                           timeout=TIMEOUT_S)
        resp.raise_for_status()
        payload = resp.json()
        if "error" in payload:
            raise RuntimeError(f"{url}: {payload['error']}")
        page = payload.get("features") or []
        features.extend(page)
        if not _more_pages(payload, len(page), page_size):
            break
        offset += page_size
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    _append_manifest(
        manifest_path or _manifest_path(),
        {
            "file": str(out_path),
            "url": url,
            "where": where,
            "bbox": list(bbox_lonlat) if bbox_lonlat is not None else None,
            "count": len(features),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            **(extra_manifest or {}),
        },
    )
    return len(features)


def _coords(geom_coords):
    if geom_coords and isinstance(geom_coords[0], (int, float)):
        yield geom_coords
    else:
        for c in geom_coords or []:
            yield from _coords(c)


def _bounds(path: Path) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for feat in json.loads(path.read_text())["features"]:
        for pt in _coords((feat.get("geometry") or {}).get("coordinates")):
            xs.append(pt[0])
            ys.append(pt[1])
    return (min(xs), min(ys), max(xs), max(ys))


def _fetch_source(name, src, bbox, where, out, session, force) -> int:
    page_size = min(MAX_PAGE_SIZE, src.get("max_record_count") or MAX_PAGE_SIZE)
    try:
        n = fetch_arcgis(src["url"], bbox, out, where=where, page_size=page_size,
                         session=session, force=force)
        if n > 0:
            return n
        reason = "0 features"
    except FileExistsError:
        raise
    except Exception as exc:  # network, HTTP or server error
        reason = repr(exc)
    fb = src.get("fallback")
    if not fb:
        raise RuntimeError(f"{name}: primary failed ({reason}) and no fallback")
    fb_page = min(MAX_PAGE_SIZE, fb.get("max_record_count") or MAX_PAGE_SIZE)
    return fetch_arcgis(fb["url"], bbox, out, where=fb.get("where", "1=1"),
                        page_size=fb_page, session=session,
                        force=True,  # replaces only the empty file left by the primary
                        extra_manifest={"used_fallback": True})


def fetch_all(area: Literal["pilot", "full"], force: bool = False) -> dict[str, int]:
    """Fetch every arcgis source into data/raw/<area>/<name>.geojson."""
    sources = load_sources()
    run = load_run_config()
    session = requests.Session()
    out_dir = RAW_DIR / area
    counts: dict[str, int] = {}
    arcgis = {k: v for k, v in sources.items() if v.get("layer_type") == "arcgis_rest"
              and v.get("fields")}  # imagery has no fields: an export endpoint, not a query layer

    if area == "pilot":
        bbox = tuple(run["pilot_bbox_lonlat"])
    else:
        src = arcgis["zcta"]
        zctas = ", ".join(f"'{z}'" for z in run["zctas"])
        out = out_dir / "zcta.geojson"
        counts["zcta"] = _fetch_source("zcta", src, None, f"ZCTA5 IN ({zctas})",
                                       out, session, force)
        bbox = _bounds(out)

    for name, src in arcgis.items():
        if name in counts:
            continue
        counts[name] = _fetch_source(name, src, bbox, src.get("where", "1=1"),
                                     out_dir / f"{name}.geojson", session, force)
    return counts
