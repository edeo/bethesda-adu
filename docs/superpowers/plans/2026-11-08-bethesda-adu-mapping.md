# Bethesda ADU Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A rerunnable Python pipeline that finds Bethesda lots (ZCTAs 20814/20816/20817) where a detached ADU geometrically fits, verified on a pilot via an aerial viewer, producing a map, ranked CSV and summary.

**Architecture:** Five stages (fetch → prepare → classify → fit → publish), each reading/writing files under `data/`. All regulatory numbers live in `config/zones.yaml` with citations; run parameters in `config/run.yaml`. Geometry is split into three focused modules (edges, pocket, rectangle).

**Tech Stack:** Python 3.13 via `uv`, geopandas ≥ 1.0, shapely ≥ 2.0, pyproj, pyarrow, numpy, requests, pyyaml, pytest; Leaflet 1.9.4 (CDN) for HTML outputs.

**Spec:** `docs/superpowers/specs/2026-11-08-bethesda-adu-mapping-design.md`

## Global Constraints

- Working CRS: EPSG:2248 (Maryland State Plane, US feet). Downloads in EPSG:4326.
- No regulatory number in code. Every zone rule comes from `config/zones.yaml`, each zone with a `citation`.
- Raw files in `data/raw/` are never modified after download; `data/raw/manifest.json` records URL + date per file.
- Defaults (`config/run.yaml`): `min_dim_ft: 20`, `min_area_sqft: 400`, `separation_ft: 5`, `shed_ignore_sqft: 0`, `story_height_ft: 10`, `misalign_threshold: 0.10`, `flag_pole_max_width_ft: 25`, `rotations_deg: [0, 15, -15, 30, -30, 45, -45]`, `sample_size: 40`.
- `adu_size_cap_ratio: 0.75` (in `zones.yaml`, cited).
- Statuses exactly: `fits`, `no_fit`, `ineligible`, `flagged_town`, `uncertain`. Precedence: ineligible > flagged_town > uncertain > fits/no_fit.
- Reasons exactly: no_fit ∈ {`pocket_too_small`, `coverage_exhausted`, `no_pocket`}; ineligible ∈ {`not_sfd`, `zone_ineligible`, `no_house_footprint`}; flags ∈ {`odd_shape`, `footprint_misaligned`, `missing_living_area`, `split_zoned`}. Multiple flags joined with `;`.
- Pilot gate: ≥ 90% ✓ and no ✗ reason count > 2.
- `out/summary.md` must state: "This is a screening estimate, not a permitting determination."
- `data/raw/`, `data/interim/`, `out/` are git-ignored except `data/raw/manifest.json`.

## Review Focus

1. **Invalid or multipart parcel geometry** (self-intersections, MultiPolygon parcels): expect `make_valid` repair; multipart parcels get `odd_shape`, never a crash. → Task 4 and Task 6 tests.
2. **Lots already over their coverage cap** (grandfathered): remaining coverage must clamp at 0 and yield `no_fit/coverage_exhausted`, not negative numbers. → Task 7 test.
3. **Long narrow pocket strips** with area ≥ 400 sq ft but width < 20 ft: must be `no_fit/pocket_too_small`. → Task 8 test.
4. **Parcels with no SDAT match or duplicate SDAT accounts**: `uncertain` with `missing_living_area`, not dropped or duplicated rows. → Task 4 test.
5. **Parcels with zero footprints or many footprints** (condo pads, townhouse rows on one parcel): zero → `ineligible/no_house_footprint`; townhouse use codes → `not_sfd`. → Task 5 test.

---

### Task 1: Scaffold and config validation

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/adu/__init__.py`, `src/adu/config.py`, `config/run.yaml`, `config/zones.yaml` (skeleton with one example zone marked `citation: "PLACEHOLDER"`), `tests/test_config.py`

**Interfaces:**
- Produces:
  - `load_run_config(path: Path = Path("config/run.yaml")) -> dict`
  - `load_zones(path: Path = Path("config/zones.yaml")) -> dict` — raises `ConfigError` if any zone with `adu_eligible: true` lacks any of `setbacks_ft.{front,side,side_street,rear}`, `height_ft`, `coverage_cap`, `behind_front_line`, `citation`, or if any citation equals `"PLACEHOLDER"`.
  - `class ConfigError(Exception)`
  - zones.yaml top-level keys: `zones: {<code>: {...}}`, `adu_size_cap_ratio`, `adu_size_cap_citation`, `sfd_codes: {land_use: [str], structure: [str], citation: str}`, `corner_lot_front: "shorter"|"longer"`, `corner_lot_citation`.
  - run.yaml also holds `zctas: ["20814","20816","20817"]` and `pilot_bbox_lonlat: [-77.106, 38.962, -77.094, 38.970]`.

- [ ] **Step 1:** `uv init --package --name adu`, add deps (`uv add geopandas shapely pyproj pyarrow numpy requests pyyaml` and `uv add --dev pytest`). Write `.gitignore` per Global Constraints.
- [ ] **Step 2: Write failing tests** in `tests/test_config.py`:
  - `test_run_config_defaults`: loaded `min_dim_ft == 20`, `min_area_sqft == 400`, `separation_ft == 5`, `zctas == ["20814","20816","20817"]`.
  - `test_zone_missing_field_raises`: a tmp zones.yaml with an eligible zone missing `coverage_cap` → `ConfigError` naming the zone and field.
  - `test_placeholder_citation_raises`: eligible zone with `citation: "PLACEHOLDER"` → `ConfigError`.
  - `test_ineligible_zone_needs_no_rules`: zone with `adu_eligible: false` and only `citation` loads fine.
- [ ] **Step 3:** `uv run pytest tests/test_config.py -v` → FAIL (module missing).
- [ ] **Step 4:** Implement `src/adu/config.py`.
- [ ] **Step 5:** `uv run pytest tests/test_config.py -v` → PASS.
- [ ] **Step 6:** Commit `feat: scaffold project and config validation`.

### Task 2: Regulatory and data-source research (fills config)

Research task; deliverable is verified by the Task 1 validator plus user review.

**Files:**
- Modify: `config/zones.yaml`
- Create: `config/sources.yaml`, `docs/research/regulatory-notes.md`, `tests/test_real_config.py`

**Interfaces:**
- Produces: `config/sources.yaml` with keys `parcels`, `zoning`, `footprints`, `sdat`, `zcta`, `places`, `imagery`, each `{url: str, layer_type: "arcgis_rest"|"xyz_tiles", fields: {<role>: <field name>}, join_key: str|null, fallback: {...}|null, verified: "2026-11-DD"}`. Field roles needed: parcels `{parcel_id, sdat_account}`, zoning `{zone}`, sdat `{sdat_account, land_use, structure, living_area, address}`, zcta `{zcta}`, places `{name}`.
- `load_sources(path=Path("config/sources.yaml")) -> dict` added to `src/adu/config.py`.

- [ ] **Step 1:** Confirm ZTA 26-06 final text and effective date (county council / Montgomery Planning sources). Record in `regulatory-notes.md` with URLs.
- [ ] **Step 2:** For every zone present in the study area that allows single-family detached, record accessory-structure front/side/side-street/rear setbacks, height, lot coverage cap, and whether accessory structures must be behind the front building line, citing Chapter 59 sections. Record the corner-lot front rule. Write into `zones.yaml`.
- [ ] **Step 3:** Identify and test-query each data endpoint (one `resultRecordCount=1` request each); record exact URLs, field names, join key, and the SDAT land-use/structure codes meaning single-family detached. Write `sources.yaml`.
- [ ] **Step 4:** Check the pilot bbox contains R-60 and R-90 parcels and part of Somerset (one zoning query); adjust `pilot_bbox_lonlat` if not and note why.
- [ ] **Step 5: Write test** `tests/test_real_config.py::test_real_configs_load` — `load_zones()` and `load_sources()` on the real files raise nothing; every source has `url` and `verified`.
- [ ] **Step 6:** `uv run pytest -v` → PASS.
- [ ] **Step 7: User checkpoint.** Present `regulatory-notes.md` summary (zone table + date confirmation) to the user; proceed only after they accept the numbers.
- [ ] **Step 8:** Commit `docs: regulatory research and source config`.

### Task 3: Fetch stage

**Files:**
- Create: `src/adu/fetch.py`, `tests/test_fetch.py`

**Interfaces:**
- Consumes: `load_sources`, `load_run_config`.
- Produces:
  - `fetch_arcgis(url: str, bbox_lonlat: tuple[float,float,float,float], out_path: Path, where: str = "1=1", page_size: int = 2000, session: requests.Session | None = None) -> int` — pages with `resultOffset` until a page returns fewer than `page_size` features or `exceededTransferLimit` is false; writes one GeoJSON FeatureCollection; returns feature count; appends `{file, url, where, bbox, count, downloaded_at}` to `data/raw/manifest.json`. Refuses to overwrite an existing raw file unless `force=True` (add `force: bool = False`).
  - `fetch_all(area: Literal["pilot","full"]) -> dict[str, int]` — fetches every arcgis source into `data/raw/<area>/<name>.geojson`. For `full`, bbox = bounds of the ZCTA union (ZCTAs fetched first by `where=ZCTA5 IN (...)`). If a primary source raises or returns 0 features, it retries once with `sources[name]["fallback"]` and the manifest entry records `used_fallback: true`.
  - Add test `test_fallback_used_and_recorded`: primary raises → fallback fetched, manifest has `used_fallback: true`.

- [ ] **Step 1: Write failing tests** using a fake session object returning canned pages:
  - `test_paging_concatenates`: pages of 2000, 2000, 500 → file has 4500 features, returns 4500, three requests made with offsets 0/2000/4000.
  - `test_manifest_appended`: manifest gains one entry with `count == 4500`.
  - `test_refuses_overwrite`: second call without `force` raises `FileExistsError`.
  - `test_http_error_raises`: page with `{"error": {...}}` JSON raises `RuntimeError` including the message.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `src/adu/fetch.py`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Live smoke: `uv run python -c "from adu.fetch import fetch_all; print(fetch_all('pilot'))"` → nonzero counts for every source.
- [ ] **Step 6:** Commit `feat: fetch stage with paging and manifest`.

### Task 4: Prepare stage

**Files:**
- Create: `src/adu/prepare.py`, `tests/test_prepare.py`, `tests/conftest.py` (synthetic GeoDataFrame fixtures in EPSG:2248)

**Interfaces:**
- Consumes: raw GeoJSON from Task 3, `load_sources` field mapping.
- Produces:
  - `prepare(raw_dir: Path, out_dir: Path, area: str) -> tuple[Path, Path]` writing:
    - `parcels_prepared.parquet` columns: `parcel_id: str`, `sdat_account: str|None`, `geometry` (Polygon/MultiPolygon, EPSG:2248, valid), `lot_area_sqft: float`, `zone: str|None`, `zone_overlap_pct: float`, `zcta: str|None`, `town: str|None`, `land_use: str|None`, `structure: str|None`, `living_area_sqft: float|None`, `address: str|None`, `sdat_duplicate: bool`.
    - `footprints.parquet` columns: `fp_id: int`, `parcel_id: str`, `geometry`, `fp_area_sqft: float`, `outside_frac: float` (share of the footprint's area outside its parcel), `is_principal: bool` (largest on parcel).
  - Footprint→parcel assignment: the parcel containing the largest share of the footprint.
  - Parcels whose centroid is outside the study area are dropped (pilot: bbox; full: ZCTA union).

- [ ] **Step 1: Write failing tests** with fixtures:
  - `test_reprojects_to_2248` and `lot_area_sqft` of a 100×60 ft fixture == 6000 ± 1.
  - `test_zone_by_centroid_and_overlap`: parcel 70% in R-60, 30% in R-90 → `zone == "R-60"`, `zone_overlap_pct == 70 ± 1`.
  - `test_invalid_geometry_repaired`: bow-tie parcel → valid geometry out, no exception.
  - `test_missing_sdat_kept`: parcel with no SDAT row → present, `living_area_sqft` is null.
  - `test_duplicate_sdat_no_row_explosion`: two SDAT rows same account → one parcel row, `sdat_duplicate == True`.
  - `test_footprint_assigned_to_majority_parcel` and `outside_frac` ≈ 0.3 for a footprint 30% over the line.
  - `test_principal_is_largest`.
  - `test_town_assigned_by_centroid`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `src/adu/prepare.py` (use `shapely.make_valid`, `gpd.overlay`/`sjoin`).
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Run on pilot raw data; print row counts and null rates per column; sanity: >90% of parcels have a zone.
- [ ] **Step 6:** Commit `feat: prepare stage`.

### Task 5: Classify stage

**Files:**
- Create: `src/adu/classify.py`, `tests/test_classify.py`

**Interfaces:**
- Consumes: Task 4 parquet files, `load_zones`, `load_run_config`.
- Produces: `classify(parcels: GeoDataFrame, footprints: GeoDataFrame, zones: dict, run: dict) -> GeoDataFrame` adding `status: str|None` (None = proceed to fit), `reason: str|None`, `flags: str` ("" if none). Written to `parcels_classified.parquet`.
  - Rules in order: `not_sfd` (land_use/structure not in `sfd_codes`, or SDAT missing *and* >1 footprint ≥ 400 sq ft), `zone_ineligible` (zone absent from config or `adu_eligible: false`), `no_house_footprint` → `ineligible`. Then `town` not null → `flagged_town`. Flags: `footprint_misaligned` (principal `outside_frac` > `misalign_threshold`), `missing_living_area`, `split_zoned` (`zone_overlap_pct` < 90), `odd_shape` (MultiPolygon). Any flag and status still None → `uncertain`. A `flagged_town` parcel keeps its flags.

- [ ] **Step 1: Write failing tests**, one per rule, plus:
  - `test_precedence_ineligible_beats_town`: townhouse code inside a town → `ineligible/not_sfd`.
  - `test_town_keeps_flags`: town parcel with missing living area → `flagged_town`, flags contains `missing_living_area`.
  - `test_zero_footprints_ineligible` and `test_townhouse_code_not_sfd` (Review Focus 5).
  - `test_clean_parcel_status_none`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: classify stage`.

### Task 6: Lot edge classification

**Files:**
- Create: `src/adu/fit_edges.py`, `tests/test_fit_edges.py`

**Interfaces:**
- Produces:
  - `@dataclass Edge: geom: LineString; kind: Literal["front","side_street","side","rear"]`
  - `classify_edges(parcel: Polygon, neighbors: BaseGeometry, corner_lot_front: str, flag_pole_max_width_ft: float = 25) -> tuple[list[Edge], bool]` — returns edges and `odd_shape: bool`.
- Algorithm (not determined by tests alone):
  - Simplify exterior (0.5 ft), split into segments, merge consecutive segments whose bearing differs < 10°.
  - Street-facing = segment portion not within 1 ft of `neighbors` (union of adjacent parcel geometries). A segment is street-facing if > 50% of its length is.
  - 1 street run → front. 2 runs meeting at a vertex (corner) → per `corner_lot_front` the shorter/longer is `front`, the other `side_street`. 2 runs on opposite sides (bearing within 30° of parallel, not adjacent) → both `front` (through lot, no rear). Flag lot: street run shorter than `flag_pole_max_width_ft` and parcel width at 30 ft back from it < `flag_pole_max_width_ft` → pole edges are `side`, the pole/main-lot junction line is treated as `front`.
  - Rear = non-front edge(s) within 30° of parallel to the primary front, with midpoint farthest from it. Remaining → `side`.
  - `odd_shape = True` if: MultiPolygon, no street-facing edge, > 2 street runs, or no rear found on a non-through lot.

- [ ] **Step 1: Write failing tests** (synthetic lots in feet, neighbors built as adjacent rectangles):
  - `test_interior_rectangle`: 60×100 lot, street on the short south side → 1 front, 1 rear (north), 2 side, `odd_shape False`.
  - `test_corner_lot_shorter_front`: street on south (60) and east (100) → south `front`, east `side_street`, north `rear`.
  - `test_through_lot`: streets north and south → 2 `front`, 0 `rear`, not odd.
  - `test_flag_lot`: 20-ft pole to a 100×100 main lot → no edge of the pole is `front`; one `rear` exists; not odd.
  - `test_multipolygon_is_odd` (Review Focus 1).
  - `test_landlocked_is_odd`: no street edges → `odd_shape True`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: lot edge classification`.

### Task 7: Pocket and coverage

**Files:**
- Create: `src/adu/fit_pocket.py`, `tests/test_fit_pocket.py`

**Interfaces:**
- Consumes: `Edge` from Task 6.
- Produces:
  - `setback_envelope(parcel: Polygon, edges: list[Edge], setbacks_ft: dict[str, float]) -> BaseGeometry` — parcel minus union of `edge.geom.buffer(setbacks_ft[edge.kind], cap_style="flat")`.
  - `front_yard_exclusion(envelope, edges, house: Polygon) -> BaseGeometry` — for each `front`/`side_street` edge, remove the flat buffer of width = distance from that edge to the house.
  - `build_pocket(parcel, edges, house, accessories: list[Polygon], zone_rule: dict, run: dict) -> list[Polygon]` — envelope → front-yard exclusion if `zone_rule["behind_front_line"]` → minus `house.buffer(run["separation_ft"])` and accessories with area ≥ `run["shed_ignore_sqft"]` → explode to polygons, drop pieces < 1 sq ft.
  - `remaining_coverage(lot_area_sqft: float, coverage_cap: float, footprint_areas: list[float]) -> float` — clamped at 0.

- [ ] **Step 1: Write failing tests:**
  - `test_envelope_rectangle`: 60×100 lot, setbacks side 5 / rear 5 / front 25 → envelope 50×70 = 3500 ± 1 sq ft.
  - `test_front_yard_excluded`: house 30 ft back from front, `behind_front_line: true` → no pocket point closer than 30 ft to the front.
  - `test_front_yard_kept_when_switch_off`.
  - `test_house_separation`: no pocket point within 5 ft of the house.
  - `test_pocket_splits`: house spanning the full envelope width → 2 pieces.
  - `test_shed_ignored_below_threshold`: 100 sq ft shed with `shed_ignore_sqft: 150` not subtracted.
  - `test_remaining_coverage_clamps`: lot 6000, cap 0.30, footprints [1900] → 0.0, not negative (Review Focus 2).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: buildable pocket and coverage`.

### Task 8: Rectangle fit, size cap, and fit stage

**Files:**
- Create: `src/adu/fit_rect.py`, `src/adu/fit.py`, `tests/test_fit_rect.py`, `tests/test_fit_stage.py`

**Interfaces:**
- Consumes: Tasks 5–7.
- Produces:
  - `largest_rectangle(pocket: Polygon, axis_deg: float, rotations_deg: list[float], min_dim_ft: float, grid_ft: float = 1.0) -> tuple[Polygon, float, float] | None` — returns (rectangle in original coords, width, length) of the largest-area rectangle with both sides ≥ `min_dim_ft`, or None.
  - Algorithm: for each angle `axis_deg + r`, rotate pocket to axis-aligned, shrink by `grid_ft/2`, rasterize cell centers with `shapely.contains_xy` into a boolean grid, run the maximal-rectangle histogram/stack algorithm over rows, considering every popped (height, width) candidate and keeping the best with both dims ≥ `min_dim_ft` (every maximal rectangle is visited, so the constrained optimum is found). Rotate the winner back.
  - `lot_axis_deg(parcel: Polygon) -> float` — bearing of the longer side of `minimum_rotated_rectangle`.
  - `max_adu_floor_area(living_area_sqft: float, usable_footprint_sqft: float, height_ft: float, story_height_ft: float, cap_ratio: float) -> float` — `min(cap_ratio*living, usable*max(1, floor(height/story)))`.
  - `run_fit(classified: GeoDataFrame, footprints: GeoDataFrame, zones: dict, run: dict) -> tuple[GeoDataFrame, GeoDataFrame]` — for every parcel with status in {None, `flagged_town`, `uncertain`}: computes `fit_result ∈ {"fits","no_fit"}`, `fit_reason`, `pocket_area_sqft`, `rect_w_ft`, `rect_l_ft`, `usable_footprint_sqft`, `max_adu_floor_area`; final `status` = existing status if set else `fit_result`, `reason` likewise. Second frame `fit_layers` (`parcel_id`, `layer ∈ {front,side_street,side,rear,envelope,pocket,adu_rect}`, `geometry`). Written to `parcels_fit.parquet` and `fit_layers.parquet`. `odd_shape` from Task 6 is appended to `flags` and forces `uncertain` if status was None.
  - `fit_reason`: `no_pocket` if pocket empty; `pocket_too_small` if no rectangle; `coverage_exhausted` if rectangle found but `min(rect_area, remaining) < min_area_sqft`.

- [ ] **Step 1: Write failing tests:**
  - `test_rect_in_square`: 50×50 pocket → ~50×50 (± 1 ft each).
  - `test_rect_rotated_pocket`: 30×40 pocket rotated 30°, `axis_deg=30` → area ≥ 1150.
  - `test_narrow_strip_none`: 15×200 strip (3000 sq ft) → None (Review Focus 3).
  - `test_l_shape_picks_larger_arm`.
  - `test_size_cap_house_limited`: living 1200, usable 600, height 20, story 10 → 900.
  - `test_size_cap_footprint_limited`: living 4000, usable 500, height 15 → 500.
  - `tests/test_fit_stage.py::test_end_to_end_rectangle_lot`: 60×120 R-60-like lot with a 30×40 house at the front → `status == "fits"`, `adu_rect` layer present.
  - `test_coverage_exhausted_reason`: same lot with cap so tight remaining < 400 → `no_fit`/`coverage_exhausted`.
  - `test_town_status_preserved`: flagged_town parcel keeps status but gets `fit_result`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `fit_rect.py`, then `fit.py`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat: rectangle fit and fit stage`.

### Task 9: CLI orchestration and pilot run

**Files:**
- Create: `src/adu/__main__.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `python -m adu run --area pilot|full [--from STAGE] [--force-fetch]`; `python -m adu viewer`; `python -m adu publish`. Stages write to `data/interim/<area>/`. `--from` skips earlier stages and reads their existing outputs; errors clearly if they're missing.

- [ ] **Step 1: Write failing test** `test_from_requires_existing_outputs`: `--from fit` on an empty tmp dir exits nonzero with message naming the missing file.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** `uv run python -m adu run --area pilot` → completes; prints status × reason counts. Expect a non-trivial mix (not 0% or 100% `fits`); if degenerate, debug with superpowers:systematic-debugging before continuing.
- [ ] **Step 6:** Commit `feat: CLI and pilot run`.

### Task 10: Verification viewer

**Files:**
- Create: `src/adu/sample.py`, `src/adu/viewer.py`, `src/adu/templates/viewer.html`, `tests/test_sample.py`
- Output: `viewer/index.html`, `viewer/sample.geojson`

**Interfaces:**
- Produces:
  - `select_sample(fit_df: GeoDataFrame, n: int = 40, seed: int = 0) -> GeoDataFrame` — includes all `uncertain` and `odd_shape` parcels up to n/2, at least 3 per `no_fit` reason present, at least 3 `flagged_town` if present, fill remainder with `fits`; deterministic for a seed.
  - `build_viewer(area: str) -> Path` — writes `viewer/sample.geojson` (EPSG:4326; per parcel: properties + nested layer geometries from `fit_layers`) and copies the template.
- Viewer requirements (spec §7): Leaflet 1.9.4 from cdnjs; aerial basemap URL from `sources.yaml` `imagery` with fallback; layer toggles for each layer kind (front red, side_street orange, side gray, rear blue, envelope dashed, pocket green fill, adu_rect purple, house/accessory footprints outlined); side panel with parcel numbers, status, reason, flags; ✓/✗ buttons, ✗ reason select {wrong_house, wrong_front, footprint_misaligned, setback_wrong, other}, note field; keys J/K/1/2; autosave to localStorage (wrapped in try/catch); Export button downloads `verification_YYYY-MM-DD.csv` with columns `parcel_id,status,verdict,reason,note`.

- [ ] **Step 1: Write failing tests** for `select_sample`: size ≤ n; all strata present when available; same seed → same ids.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement `sample.py`, `viewer.py`, template. **Step 4:** Run → PASS.
- [ ] **Step 5:** `uv run python -m adu viewer`, then serve with `python -m http.server 8000` and open `http://localhost:8000/viewer/` in the browser pane. Check: aerial loads, every layer toggles, J/K moves, a verdict survives reload, Export downloads a CSV with the header row.
- [ ] **Step 6:** Commit `feat: aerial verification viewer`.

### Task 11: Pilot verification gate and snapshot

**Files:**
- Create: `src/adu/verify.py`, `tests/test_verify.py`, `tests/test_pilot_snapshot.py`, `data/verification/` (verdict CSVs committed), `tests/snapshots/pilot_counts.json`

**Interfaces:**
- Produces: `score_verification(csv_path: Path) -> dict` returning `{n, correct, pct_correct, wrong_by_reason: dict, passes: bool}`; `passes = pct_correct >= 90 and max(wrong_by_reason.values(), default=0) <= 2`.

- [ ] **Step 1: Write failing tests:** 40 rows, 37 ✓, 3 ✗ split 2/1 → passes; 3 ✗ all `wrong_front` → fails; 35 ✓ → fails.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5: User checkpoint.** The user reviews the sample in the viewer and saves the export into `data/verification/`. Run `uv run python -c "from adu.verify import score_verification; ..."`. If it fails, fix root causes (systematic-debugging), rerun pilot, regenerate viewer, user re-verifies. Repeat until it passes.
- [ ] **Step 6:** Write `tests/snapshots/pilot_counts.json` (status × reason counts) and `test_pilot_snapshot.py` that compares the current pilot output to it, skipped when `data/interim/pilot/` is absent.
- [ ] **Step 7:** Commit `feat: pilot verification gate and snapshot`.

### Task 12: Full run and final outputs

**Files:**
- Create: `src/adu/publish.py`, `src/adu/templates/map.html`, `tests/test_publish.py`
- Output: `out/adu_map.html`, `out/adu_candidates.csv`, `out/summary.md`

**Interfaces:**
- Consumes: `parcels_fit.parquet`.
- Produces: `publish(area: str) -> list[Path]`.
  - CSV: rows with status in {fits, flagged_town, uncertain}, sorted by `max_adu_floor_area` desc then `pocket_area_sqft` desc; columns exactly as spec §8.
  - Map: Leaflet with `preferCanvas: true`, geometries simplified to 1 ft before export, colored by status, popup with CSV fields, filters for ZCTA, zone, min ADU size.
  - Summary: status × ZCTA and status × zone tables; headline line `Maximum detached ADUs: N lots` where N = count of `fits`; flagged_town and uncertain counts reported separately; assumptions table copied from `run.yaml`; the caveat sentence from Global Constraints.

- [ ] **Step 1: Write failing tests** on a small fixture: CSV ordering and exact columns; headline N equals fits count; caveat sentence present; flagged_town excluded from N.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** `uv run python -m adu run --area full && uv run python -m adu publish`. Open `out/adu_map.html` in the browser pane; check it loads in < 10 s and filters work. Confirm pilot snapshot test still passes.
- [ ] **Step 6:** Commit `feat: full run outputs` (code only; `out/` stays git-ignored).
