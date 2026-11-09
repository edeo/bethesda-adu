# Bethesda ADU Mapping — Design Spec

**Date:** 2026-11-08
**Status:** Draft for review
**Path:** Architectural (new project)

## 1. Purpose and success criteria

**Purpose.** Estimate where a *detached* accessory dwelling unit (ADU) could be built on existing lots in Bethesda, Montgomery County, MD, and how many lots qualify. Primarily a learning project in reproducible GIS analysis with Claude Code (method clarity matters); secondarily a usable, parcel-level prospect list.

**Success looks like:**
1. A rerunnable pipeline (`python -m adu run --area pilot|full`) that produces every output from raw downloads.
2. A pilot verified against aerial imagery with ≥ 90% of sampled parcels judged correct, and no single error category recurring more than twice.
3. A full-area interactive map, a ranked candidate CSV, and a summary with the headline count and stated caveats.

**What the user decided (vs. assumptions):**

| Decision | Source |
|---|---|
| Use: learning/portfolio first, prospect-finding second | User |
| Fit test: geometric (parcel + footprint shapes), not arithmetic | User |
| Detached ADUs only; no attached/interior | User |
| Study area: union of ZCTAs 20814, 20816, 20817 | User |
| Deliverable: interactive web map + ranked CSV | User |
| Approach: county data, pilot-first, with aerial verification viewer | User |
| Parcels in incorporated towns are flagged, not dropped | Proposed, accepted |
| Min ADU footprint 20×20 ft (400 sq ft), configurable | Assumption |
| House–ADU separation buffer 5 ft, configurable | Assumption (practical access, not a cited rule) |
| Story height for converting height limit to stories: 10 ft | Assumption |

## 2. Regulatory basis (to be verified in plan task 1)

From prior research; every number used by the pipeline lives in `config/zones.yaml` with a citation, and nothing is hard-coded.

- **ZTA 26-06** aligns county ADU zoning with Maryland state law: an ADU is allowed wherever a single-family detached house is allowed (expands eligibility to R-40, R-30, R-20, R-10, etc.). Effective date reported as 2026-10-05 — confirm, and confirm final text.
- One ADU per lot; principal dwelling must be single-family detached.
- Max ADU size: 75% of the principal dwelling's size.
- Detached ADU must meet the zone's **accessory structure** setback, height, and lot-coverage standards.
- No minimum size in zoning; practical floor is the building code. The 400 sq ft default is a screening assumption.
- Bethesda is unincorporated; county zoning applies. Incorporated towns in or near the study area (e.g., Somerset, Glen Echo) may impose their own building/accessory-structure rules → flagged.

**Plan task 1 must produce**, with citations: the eligible zone list; per-zone accessory setbacks (front, side, rear), height limit, lot-coverage cap, and whether accessory structures must be behind the front building line; the SDAT codes that identify single-family detached use.

## 3. Architecture: five-stage pipeline

Python 3.11+, geopandas/shapely/pyproj. Each stage reads the prior stage's file and writes its own (GeoParquet in `data/interim/`), so any stage can be rerun or inspected alone.

1. **fetch** → `data/raw/`. Downloads raw layers; raw files are never modified. Records source URL and download date in `data/raw/manifest.json`.
2. **prepare** → `parcels_prepared.parquet`. Clip to study area (pilot box or ZCTA union). Reproject to Maryland State Plane, US feet (EPSG:2248). Spatial-join zoning (by parcel centroid; record % overlap and flag split-zoned parcels), SDAT attributes (by account ID), footprints (intersection), ZCTA and incorporated place (by centroid).
3. **classify** → `parcels_classified.parquet`. Non-geometric filters, each recording a reason. Every parcel ends with exactly one status (§5).
4. **fit** → `parcels_fit.parquet`. Geometry per §4 for parcels still eligible (including flagged-town parcels, so their potential is known).
5. **publish** → `out/` and `viewer/`. Verification viewer (pilot) and final map/CSV/summary (full).

Configuration: `config/zones.yaml` (per-zone rules + citations), `config/run.yaml` (pilot bbox, min footprint, separation buffer, shed-ignore threshold, story height, sample size).

## 4. Fit geometry (stage 4)

All units feet / square feet.

1. **Identify buildings.** Principal house = largest footprint on the parcel. Other footprints = existing accessory structures. Footprint area outside the parcel > 10% → `footprint_misaligned` flag.
2. **Classify lot edges.** Decompose the parcel boundary into edges (merging near-collinear segments). *Front* = edges not shared with another parcel (street-facing). *Rear* = edge(s) roughly opposite and farthest from the front. *Side* = the rest. A *corner lot* has two street-facing edges meeting at a corner; the secondary one is treated as a *side street* edge with its own setback (`side_street` in config). A *through lot* has street-facing edges on opposite sides; both are fronts and there is no rear. A *flag lot* has a narrow street-facing pole (< 25 ft wide); the pole is excluded and the edge where it meets the main lot is treated as the front. These are detected automatically; any parcel where the rules don't resolve cleanly gets `odd_shape` and status `uncertain`.
3. **Setback envelope.** Remove from the parcel a buffer of each edge by its zone's accessory setback for that edge type.
4. **Front-yard exclusion** (per-zone switch): remove the area between the front line(s) and the house's front-most wall.
5. **Obstacles.** Subtract the house buffered by the separation distance, and existing accessory footprints (unless smaller than the shed-ignore threshold, default 0 = keep all).
6. **Pocket.** Result may be multiple pieces; each tested independently.
7. **Coverage allowance.** `remaining_coverage = lot_area × zone_coverage_cap − sum(existing footprints)`.
8. **Fit.** Largest rectangle within any pocket piece, searched at the lot's principal axis and ±15°, ±30°, ±45°; must have both sides ≥ min dimension (20 ft) and area ≥ min area (400 sq ft). `usable_footprint = min(rectangle_area, remaining_coverage)`; must still be ≥ min area.
9. **Size cap.** `stories = floor(zone_height_limit / story_height)` (min 1). `max_adu_floor_area = min(0.75 × house_living_area, usable_footprint × stories)`.

## 5. Statuses

| Status | Meaning | In headline count? |
|---|---|---|
| `fits` | Passes all filters and §4 | Yes |
| `no_fit` | Eligible but fails geometry; reason ∈ {pocket_too_small, coverage_exhausted, no_pocket} | No |
| `ineligible` | reason ∈ {not_sfd, zone_ineligible, no_house_footprint} | No |
| `flagged_town` | In an incorporated town; fit still computed and reported separately | No (reported separately) |
| `uncertain` | Any data-quality flag: odd_shape, footprint_misaligned, missing_living_area, split_zoned | No (reported separately) |

Precedence: ineligible > flagged_town > uncertain > fits/no_fit.

## 6. Data sources

Endpoints are confirmed in plan task 1; a source is replaced by its fallback only if the primary is unavailable or materially incomplete, and the swap is recorded in the manifest.

| Need | Primary | Fallback |
|---|---|---|
| Parcel polygons | Montgomery Planning parcel layer | MD iMap Maryland Parcel Boundaries |
| Zoning | Montgomery Planning zoning layer | — |
| Building footprints | Montgomery County planimetric buildings | Microsoft US Building Footprints |
| Use, structure type, living area | SDAT real property via MD iMap | — |
| ZCTAs, incorporated places | Census TIGERweb | — |
| Aerial imagery (viewer only) | MD iMap six-inch orthoimagery | Esri World Imagery |

## 7. Verification viewer (pilot)

- Single local HTML page (`viewer/index.html` + generated `viewer/sample.geojson`), Leaflet, served with `python -m http.server`.
- Aerial basemap with toggleable layers: parcel outline, edges colored by type (front/side/rear), house and accessory footprints, setback envelope, pocket, fitted ADU rectangle.
- **Sample:** ~40 pilot parcels, stratified: fits, each no_fit reason, all uncertain/odd-shape, a few flagged_town.
- Side panel: parcel numbers and pipeline reason; verdict ✓/✗ with reason ∈ {wrong_house, wrong_front, footprint_misaligned, setback_wrong, other} + note. Keyboard: J/K navigate, 1/2 verdict.
- Verdicts autosave to localStorage; **Export** downloads `verification_YYYY-MM-DD.csv`, which the user saves to `data/verification/`.
- **Gate:** ≥ 90% ✓ and no ✗ reason > 2 occurrences → proceed to full run. Otherwise fix causes, rerun, re-verify.

## 8. Final outputs (full run)

- `out/adu_map.html`: all parcels colored by status; click for details; filters by ZIP, zone, min ADU size.
- `out/adu_candidates.csv`: `fits` parcels (plus `flagged_town` and `uncertain` with a status column), ranked by `max_adu_floor_area` desc, then pocket area. Columns: address, sdat_account, zcta, zone, lot_sqft, house_living_sqft, house_footprint_sqft, rect_w_ft, rect_l_ft, usable_footprint_sqft, max_adu_floor_area, status, reason, flags.
- `out/summary.md`: counts by status × ZCTA and × zone; headline "maximum detached ADUs = N lots"; method, assumptions, and caveat that this is a **screening estimate, not a permitting determination**.

## 9. Testing

- **Geometry unit tests (TDD)** on synthetic parcels with known answers: plain rectangle; corner lot; flag lot; pocket splitting into two pieces; coverage-limited case; too-small pocket; footprint extending past parcel.
- **Config validation:** every eligible zone has all required fields and a citation; run aborts otherwise.
- **Pilot snapshot:** after the pilot passes the gate, status counts are saved; a test fails if later changes alter them without the snapshot being deliberately updated.

## 10. Project layout

```
adu_project/
  pyproject.toml
  config/zones.yaml, run.yaml
  src/adu/{__main__,fetch,prepare,classify,fit,publish}.py
  data/raw/  data/interim/  data/verification/   (git-ignored except manifest)
  viewer/    out/
  tests/
  docs/superpowers/specs/
```

## 11. Out of scope (v1)

Tree canopy, slope, easements, floodplain/stream buffers, HOA covenants, utility capacity, existing/licensed ADUs, attached and interior ADUs, cost/feasibility economics.
