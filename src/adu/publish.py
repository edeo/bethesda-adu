"""Final outputs: out/adu_map.html, out/adu_candidates.csv, out/summary.md."""
import json
import math
from importlib import resources
from pathlib import Path

import geopandas as gpd
import pandas as pd

from adu.config import load_run_config

INTERIM_DIR = Path("data/interim")
OUT_DIR = Path("out")
SCREENING_CAVEAT = "This is a screening estimate, not a permitting determination."
CANDIDATE_STATUSES = ("fits", "flagged_town", "uncertain")
STATUS_ORDER = ("fits", "flagged_town", "uncertain", "no_fit", "ineligible")
SIMPLIFY_FT = 1.0
PRECISION = 6

CSV_COLUMNS = (
    "address", "sdat_account", "zcta", "zone", "lot_sqft", "house_living_sqft",
    "house_footprint_sqft", "rect_w_ft", "rect_l_ft", "usable_footprint_sqft",
    "max_adu_floor_area", "status", "reason", "flags",
)
RENAME = {"lot_area_sqft": "lot_sqft", "living_area_sqft": "house_living_sqft"}
# Properties shown in the map popup (empty ones are left out to keep the file small).
POPUP_COLUMNS = CSV_COLUMNS


def _load(area: str, interim_dir: Path | None) -> gpd.GeoDataFrame:
    d = Path(interim_dir) if interim_dir else INTERIM_DIR / area
    df = gpd.read_parquet(d / "parcels_fit.parquet")
    fps = gpd.read_parquet(d / "footprints.parquet")
    fps = fps[fps["is_principal"]]
    house = fps.groupby("parcel_id")["fp_area_sqft"].sum().rename("house_footprint_sqft")
    df = df.merge(house, left_on="parcel_id", right_index=True, how="left")
    df = df.rename(columns=RENAME)
    for col in ("reason", "flags"):
        df[col] = df[col].fillna("")
    return df


def candidates_table(df: pd.DataFrame) -> pd.DataFrame:
    c = df[df["status"].isin(CANDIDATE_STATUSES)].copy()
    c = c.sort_values(["max_adu_floor_area", "pocket_area_sqft"], ascending=False,
                      na_position="last", kind="stable")
    return pd.DataFrame(c[list(CSV_COLUMNS)]).round(1).reset_index(drop=True)


def _md_table(ct: pd.DataFrame) -> str:
    cols = [c for c in STATUS_ORDER if c in ct.columns]
    ct = ct[cols].copy()
    ct["total"] = ct.sum(axis=1)
    lines = ["| | " + " | ".join(ct.columns) + " |", "|---" * (len(ct.columns) + 1) + "|"]
    for idx, row in ct.iterrows():
        lines.append(f"| {idx} | " + " | ".join(str(int(v)) for v in row) + " |")
    tot = ct.sum()
    lines.append("| **total** | " + " | ".join(f"**{int(v)}**" for v in tot) + " |")
    return "\n".join(lines)


def build_summary(df: pd.DataFrame, run: dict) -> str:
    n = int((df["status"] == "fits").sum())
    flagged = int((df["status"] == "flagged_town").sum())
    unc = int((df["status"] == "uncertain").sum())
    fit_geom = df["fit_result"] == "fits" if "fit_result" in df else pd.Series(False, index=df.index)
    flagged_fit = int(((df["status"] == "flagged_town") & fit_geom).sum())
    unc_fit = int(((df["status"] == "uncertain") & fit_geom).sum())
    by_zcta = pd.crosstab(df["zcta"].fillna("none"), df["status"])
    by_zone = pd.crosstab(df["zone"].fillna("none"), df["status"])
    assumptions = "\n".join(f"| {k} | {v} |" for k, v in run.items()
                            if k != "pilot_bbox_lonlat")
    return f"""# Bethesda detached ADU screening: summary

{SCREENING_CAVEAT}

## Headline

**Maximum detached ADUs: {n} lots**

Of {len(df)} parcels in ZCTAs {", ".join(run.get("zctas", []))}, {n} have status `fits`.
This count does not include the lots below, which are reported separately:

- flagged_town: {flagged} lots (in an incorporated town (town rules may apply); {flagged_fit} fit geometrically)
- uncertain: {unc} ({unc_fit} fit geometrically); the geometry or data was too ambiguous to call

## Method

Each parcel is joined to its zone, SDAT record and building footprints. Parcels that are not
single-family detached, or are in a zone that does not allow a detached ADU, are marked
ineligible. For the rest, the zone's accessory-structure setbacks are cut back from the lot
line, the house footprint plus a separation buffer is removed, and the largest rectangle that
fits in what is left (at several rotations) is measured. A lot fits when that rectangle meets
the minimum dimension and area, and the maximum floor area is capped by lot coverage and the
ADU size cap.

## Notes and limits

- ADUs are modelled as 1-story only (`max_stories: 1`).
- In RE and R zones an ADU must sit behind the rear wall of the house; the screen enforces this.
- Lots with street frontage on both front and back get the front setback from both street frontages.
  Many of these probably back onto alleys, so those lots may be undercounted.
- The corner-lot rear setback is applied to all corner lots (conservative; the code applies it
  only where the abutting lot fronts the side street).
- The R-60/R-90 rule adding +1 ft of setback per foot of ADU length beyond 24 ft along a lot line
  is not modelled. It does not change which lots fit, but it overstates `usable_footprint_sqft`,
  `max_adu_floor_area` and the CSV ranking for large ADUs.
- `corner_lot_front: shorter` is a heuristic.
- Building footprints may predate recent construction, so a few lots may differ on the ground.
- Pilot verification against aerial imagery passed at 40/40 on 2026-11-09.
- Not modelled: tree canopy, slope, easements, floodplain or stream buffers, HOA covenants,
  utility capacity, existing or licensed ADUs, attached or interior ADUs, cost.

## Counts by status and ZIP (ZCTA)

{_md_table(by_zcta)}

## Counts by status and zone

{_md_table(by_zone)}

## Assumptions (from config/run.yaml)

| setting | value |
|---|---|
{assumptions}

{SCREENING_CAVEAT}
"""


def _clean(v):
    if v is None or v is pd.NA:
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float):
        if math.isnan(v):
            return None
        return round(v, 1)
    return v


def _round(coords):
    if isinstance(coords[0], (int, float)):
        return [round(c, PRECISION) for c in coords]
    return [_round(c) for c in coords]


def build_map_collection(df: gpd.GeoDataFrame, columns: list[str] = POPUP_COLUMNS) -> dict:
    g = df.copy()
    g["geometry"] = g.geometry.simplify(SIMPLIFY_FT, preserve_topology=True)
    g = g.to_crs(4326)
    feats = []
    for rec in g.to_dict("records"):
        geom = rec["geometry"]
        if geom is None or geom.is_empty:
            continue
        props = {}
        for col in columns:
            v = _clean(rec.get(col))
            if v is not None and v != "":
                props[col] = v
        d = geom.__geo_interface__
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": d["type"], "coordinates": _round(d["coordinates"])}})
    return {"type": "FeatureCollection", "features": feats}


def publish(area: str, interim_dir: Path | None = None, out_dir: Path | None = None) -> list[Path]:
    out = Path(out_dir) if out_dir else OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    df = _load(area, interim_dir)

    csv_path = out / "adu_candidates.csv"
    candidates_table(df).to_csv(csv_path, index=False)

    summary_path = out / "summary.md"
    summary_path.write_text(build_summary(df, load_run_config()))

    template = resources.files("adu").joinpath("templates/map.html").read_text()
    data = json.dumps(build_map_collection(df), separators=(",", ":")).replace("</", "<\\/")
    map_path = out / "adu_map.html"
    map_path.write_text(template.replace("__PARCELS__", data))
    return [map_path, csv_path, summary_path]


# Fields that identify a specific property; left out of the public website.
PRIVATE_COLUMNS = ("address", "sdat_account")
SITE_DIR = Path("docs")
SUMMARY_LINK = "<a href='summary.html'>Method and limits</a>"

SUMMARY_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bethesda ADU screening: method and limits</title>
<style>
body {{ font: 16px/1.6 system-ui, sans-serif; max-width: 860px; margin: 0 auto; padding: 24px 16px; color: #1b1b1b; background: #fff; }}
table {{ border-collapse: collapse; margin: 12px 0; display: block; overflow-x: auto; }}
th, td {{ border: 1px solid #ccc; padding: 4px 8px; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
a {{ color: #0b5cad; }}
</style></head><body>
<p><a href="index.html">&larr; Back to the map</a></p>
{body}
</body></html>
"""


def publish_site(area: str = "full", interim_dir: Path | None = None, site_dir: Path | None = None) -> list[Path]:
    """Public website: map without property identifiers, plus the summary as HTML. No CSV."""
    import markdown

    site = Path(site_dir) if site_dir else SITE_DIR
    site.mkdir(parents=True, exist_ok=True)
    df = _load(area, interim_dir)
    columns = [c for c in POPUP_COLUMNS if c not in PRIVATE_COLUMNS]

    template = resources.files("adu").joinpath("templates/map.html").read_text()
    template = template.replace("Assumes 1-story ADUs.</div>", "Assumes 1-story ADUs. " + SUMMARY_LINK + "</div>")
    data = json.dumps(build_map_collection(df, columns), separators=(",", ":")).replace("</", "<\\/")
    map_path = site / "index.html"
    map_path.write_text(template.replace("__PARCELS__", data))

    body = markdown.markdown(build_summary(df, load_run_config()), extensions=["tables"])
    summary_path = site / "summary.html"
    summary_path.write_text(SUMMARY_PAGE.format(body=body))

    nojekyll = site / ".nojekyll"
    nojekyll.write_text("")
    return [map_path, summary_path, nojekyll]
