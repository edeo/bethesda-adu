# Regulatory and data-source notes: Bethesda detached ADUs

Researched 2026-11-08 for ZCTAs 20814, 20816, 20817. Values live in `config/zones.yaml` and `config/sources.yaml`. This file explains where each value comes from and what the pipeline simplifies.

The Chapter 59 text was read from the current American Legal "Montgomery County Zoning Ordinance (2014)" pages (`codelibrary.amlegal.com/.../montgomeryco_md_zone2014/...`). The ZTA 26-06 text comes from the enacted ordinance PDF.

## Summary table

All values are **accessory-structure** standards for the detached-house building type under the standard method. "Side" and "rear" are the values used for a 15–20 ft tall ADU (see "Height-dependent setbacks"). Setbacks are in feet. "Rear line" means the ADU must sit wholly behind the house's rear wall.

| Zone | Eligible | Front | Side | Side street | Rear | Height | Coverage | Behind front line | Extra placement rule | Confidence |
|---|---|---|---|---|---|---|---|---|---|---|
| RE-2 | yes | 80 | 15 | 50 | 10 | 50 | 25% | yes | rear line | confirmed |
| RE-2C | yes | 80 | 15 | 50 | 10 | 50 | 25% | yes | rear line | confirmed |
| RE-1 | yes | 80 | 15 | 50 | 10 | 50 | 15% | yes | rear line | confirmed |
| R-200 | yes | 65 | 12 | 40 | 7 | 35 | 25% | yes | rear line | confirmed |
| R-90 | yes | 60 | 15 (5 if ≤15 ft tall) | 30 | 15 (5) | 20 | 30% | yes | rear line | confirmed |
| R-60 | yes | 60 | 15 (5 if ≤15 ft tall) | 25 | 15 (5) | 20 | 35% | yes | rear line | confirmed |
| R-40 (not mapped here) | yes | 60 | 15 (5) | 25 | 15 (5) | 20 | 35% | yes | rear line | confirmed |
| TLD | yes | 20* | 4 | 15 | 4 | 25 | 35% | yes | 10 ft behind front wall | confirmed |
| TMD | yes | 20* | 4 | 15 | 4 | 25 | 40% | yes | 10 ft behind front wall | confirmed |
| THD | yes | 20* | 4 | 15 | 4 | 25 | 50% | yes | 10 ft behind front wall | confirmed |
| R-30 | yes | 20* | 4 | 15 | 4 | 25 | 50% | yes | 10 ft behind front wall | confirmed |
| R-20 | yes | 20* | 4 | 15 | 4 | 25 | 75% | yes | 10 ft behind front wall | confirmed |
| R-10 | yes | 20* | 4 | 15 | 4 | 25 | 90% | yes | 10 ft behind front wall | confirmed |
| CRN / CRT / CR (all density suffixes) | yes | 5* | 4 | 15 | 4 | 25 | 90% | yes | 5 ft behind front wall | **unconfirmed** |
| GR, NR, EOF (all suffixes) | yes | 5* | 4 | 15 | 4 | 25 | 90% | yes | 5 ft behind front wall | **unconfirmed** |
| IM (industrial) | no | – | – | – | – | – | – | – | – | confirmed |
| RT-8.0 / RT-10.0 / RT-12.5, R-H (retained zones) | no | – | – | – | – | – | – | – | – | **unconfirmed** |
| CRF, CRTF, EOFF (floating zones) | no (not modeled) | – | – | – | – | – | – | – | – | **unconfirmed** |

\* In these zones the code states the accessory front setback relative to the house ("N' behind front building line"), not as a distance from the lot line. `front` holds the principal-building front setback as a floor. The binding rule is in `front_building_line_offset_ft`.

Other top-level values:

| Item | Value | Source |
|---|---|---|
| ADU size cap | 75% of the primary single-family detached dwelling | Ch. 59 §3.3.3.A.1 as amended by Ord. 20-36 |
| SFD codes (SDAT) | LU = `R`; STRUBLDG ∈ `0001`, `0004`, `0005` | MD iMap Parcel Points code descriptions; cross-checked against county land use 111 |
| Corner-lot front | `shorter` (heuristic) | §1.4.2: the owner elects the front |
| Pilot bbox | unchanged `[-77.106, 38.962, -77.094, 38.970]` | passes the check; an alternative is suggested below |

## ZTA 26-06 status

**Enacted.** It is Ordinance No. 20-36, Zoning Text Amendment 26-06, "Accessory Residential Uses – Accessory Dwelling Unit":

- Introduced 2026-04-21; public hearing 2026-06-09.
- **Adopted 2026-09-15; effective 2026-10-05.** The ordinance states it takes effect 20 days after adoption.
- Enacted text: https://assets.montgomerycountymd.gov/files/2026-09/Ordinance%2020-36%20%28ZTA%2026-06%29.pdf, listed as "Enacted - 20-36" on the Council ZTA index at https://www.montgomerycountymd.gov/COUNCIL/leg/zta/index.html.
- DPS confirms it: "Reflects ZTA 26-06, Ordinance No. 20-36, effective October 5, 2026." https://www.montgomerycountymd.gov/department-permitting-services/all-permits/residential-permits/guidelines-accessory-dwelling-units-adu
- Planning staff report (2026-05-21): https://montgomeryplanningboard.org/wp-content/uploads/2026/05/SR-ZTA-26-06-ADUs.pdf

**What changed (Ord. 20-36 vs. prior code):**

1. **Use table (§3.1.6).** Attached and detached ADUs become a limited use in R-40, TLD, TMD, THD, R-30, R-20, R-10, CRN, CRT, CR, GR, NR, LSC and EOF. They were already allowed in AR, R, RC, RNC, RE-2, RE-2C, RE-1, R-200, R-90 and R-60. They remain not allowed in IL, IM and IH. Staff report: SFD is allowed "in all zones except the Industrial zones".
2. **Definition (§3.3.3.A.1).** An ADU is "a second dwelling unit that is not greater than 75% of the size of and subordinate in use to the primary single-family detached dwelling unit". This tracks the state definition.
3. **Size caps repealed.** The detached cap was the least of 50% of the house footprint, 10% of lot area, or 1,200 sf (§3.3.3.C.2.e). The attached 1,200 sf cap is also gone. The 75% definition is now the only size limit.
4. **Setbacks (§3.3.3.A.2.c.v and §3.3.3.C).** The phrase "unless modified by the use standards for an ADU" is struck. The detached-ADU-specific setbacks are deleted: side equal to the principal dwelling, 12 ft rear, and the 24 ft length rule with a 12 ft rear starting point. **A detached ADU now uses the zone's accessory-structure setback, height and coverage standards.**
5. **Parking.** If a new driveway is needed, the two-space requirement is replaced by one space for the ADU. The waiver now also covers lots whose size or shape precludes parking. The exemption within 1 mile of Metrorail, Purple Line or MARC remains.
6. **Density.** ADUs are excluded from density calculations in all zones, not just Ag/Rural.
7. **Unchanged.** One ADU per lot. No ADU on a lot with a Short-Term Residential Rental. Pre-5/31/2012 structures can be converted without regard to setbacks or floor area (§3.3.3.C.2.b; out of scope).

**State law.** Md. HB 1466 (2025), Chapter 197, cross-filed as SB 891, took effect 2025-10-01. It required local ADU laws by 2026-10-01. Local law may not set side or rear ADU setbacks above the existing accessory-structure setbacks. https://mgaleg.maryland.gov/mgawebsite/Legislation/Details/hb1466?ys=2025RS

## Zone rules in detail

Every eligible zone draws on two Ch. 59 provisions:

- §3.3.3.A.2.c.v (as amended): an ADU "must comply with the setback, height, and building lot coverage standards of an accessory structure in the underlying zone".
- §3.3.3.A.2.c.iv: an ADU's footprint, "in combination with other structures on the site, is limited by the total lot coverage limit in the underlying zone".

The 50%-of-house / 600 sf accessory-footprint cap in each residential table explicitly "does not apply to Section 3.3.3.C, Detached Accessory Dwelling Unit". It is **not** applied.

### Residential Detached zones

| Zone | Section (URL) | Lot coverage | Accessory front | Side street (abutting lot fronts side street & is Res. Detached / otherwise) | Side | Rear (corner lot* / otherwise) | Accessory height | Height-setback rule |
|---|---|---|---|---|---|---|---|---|
| RE-2 | §4.4.4.B ([link](https://codelibrary.amlegal.com/codes/montgomerycounty/latest/montgomeryco_md_zone2014/0-0-0-2889)) | 25% | 80 | 50 / 20 | 15 | 12 / 10 | 50 | none |
| RE-2C | §4.4.5.B ([link](https://codelibrary.amlegal.com/codes/montgomerycounty/latest/montgomeryco_md_zone2014/0-0-0-60197)) | 25% | 80 | 50 / 20 | 15 | 12 / 10 | 50 | none |
| RE-1 | §4.4.6.B ([link](https://codelibrary.amlegal.com/codes/montgomerycounty/latest/montgomeryco_md_zone2014/0-0-0-60198)) | 15% | 80 | 50 / 20 | 15 | 12 / 10 | 50 | none |
| R-200 | §4.4.7.B ([link](https://codelibrary.amlegal.com/codes/montgomerycounty/latest/montgomeryco_md_zone2014/0-0-0-60199)) | 25% | 65 | 40 / 15 | 12 | 12 / 7 | 35 | none |
| R-90 | §4.4.8.B ([link](https://codelibrary.amlegal.com/codes/montgomerycounty/latest/montgomeryco_md_zone2014/0-0-0-60200)) | 30% | 60 | 30 / 15 | 5 | 10 / 5 | 20 | yes |
| R-60 | §4.4.9.B ([link](https://codelibrary.amlegal.com/codes/montgomerycounty/latest/montgomeryco_md_zone2014/0-0-0-60201)) | 35% | 60 | 25 / 15 | 5 | 10 / 5 | 20 | yes |
| R-40 | §4.4.10.B ([link](https://codelibrary.amlegal.com/codes/montgomerycounty/latest/montgomeryco_md_zone2014/0-0-0-60207)) | 35% | 60 | 25 / 15 | 5 | 10 / 5 | 20 | yes |

\* "Rear setback, on a corner lot where abutting lot fronts on the side street and is in a Residential Detached zone".

Every zone in this table also has: "In addition to the front setback minimum, any accessory structure must be located behind the rear building line of the principal building." §1.4.2 defines the **Rear Building Line** as "a line along the edge of the principal building facing the rear lot line that extends between side lot lines". On a through lot it is the edge opposite the street of the address. This rule is stricter than the spec's "behind the front building line". It is recorded as `behind_rear_building_line: true`.

Recorded values and why:

- `side_street` takes the larger case (abutting lot fronts the side street). Detecting what the neighbor fronts is not modeled.
- `rear` takes the general (non-corner) value. On corner lots in R-60/R-90/R-40 the rear setback is 10 ft (20 ft for a 20-ft ADU), and in R-200 and RE-* it is 12 ft. That is not modeled, so corner lots are slightly optimistic.
- Coverage is the detached-house lot coverage max, which counts all buildings including accessory buildings (§4.1.7.B.4).

**Height-dependent setbacks (R-60, R-90, R-40), spec. b:** "For any accessory structure with a height greater than 15', the minimum side and rear setback must be increased at a ratio of 2' of additional setback for each foot of height in excess of 15'." The accessory height max is 20 ft.

- A **one-story ADU of 15 ft or less**: side 5, rear 5 (corner rear 10).
- A **two-story ADU at 20 ft**: side 15, rear 15 (corner rear 20).

As instructed, config records the conservative value that covers a typical 1–2 story ADU: **15 / 15**, with `height_ft: 20`, giving 2 stories at a 10 ft story height. This makes `height_ft` and the setbacks internally consistent.

To model the more permissive one-story case instead, set side=5, rear=5 and height_ft=15, which gives 1 story. This is a **user decision**. It materially changes R-60 and R-90 results, because 5 ft vs 15 ft from side and rear lines is a large share of a 60-ft-wide lot.

**Length-dependent setbacks (R-60, R-90, R-40), spec. c:** "For any accessory structure with a length along a rear or side lot line that is longer than 24', the minimum side or rear setback must be increased at a ratio of 2' for every 2' that the dimension exceeds 24 linear feet." That is 1:1 beyond 24 ft. This is **not modeled**. A fitted rectangle longer than 24 ft parallel to a side or rear line is optimistic by the excess length. The 20×20 minimum is unaffected.

**Infill coverage (§4.4.1.B)** reduces coverage on pre-1978 lots under 25,000 sf in R-200/R-90/R-60/R-40 to 30% or less, sliding to 20%. It applies only when the construction is a new house or a >50% demolition or addition. An ADU is none of these, so the zone's base coverage is used. Houses rebuilt under infill rules may already exceed the base cap. The pipeline's coverage arithmetic handles that, and the result is `coverage_exhausted`.

### Townhouse and Multi-Unit zones (TLD, TMD, THD, R-30, R-20, R-10)

These come from the detached-house column of §4.4.11.B through §4.4.16.B (links in `zones.yaml`): accessory "Front setback, behind front building line" 10, side street 15, side 4, rear 4, rear alley 4, accessory height 25. Lot coverage is 35/40/50/50/75/90%. There is no rear-building-line rule and no height or length setback rule. §4.1.7.A.5.c says the front building line is measured "at the front edge of the building", so the ADU must be ≥10 ft behind the house's front wall. This is recorded as `front_building_line_offset_ft: 10`.

### Commercial/Residential and Employment zones (CRN, CRT, CR, GR, NR, EOF)

Ord. 20-36 makes detached ADUs a limited use in all of these. The standard-method tables (§4.5.3.C for CRN/CRT/CR; §4.6.3.C for GR/NR; §4.6.3 EOF table) include a detached-house column: coverage 90%, principal front 5, accessory front "5' behind front building line", side street 15, side 4, rear 4, accessory height 25.

These zones are marked eligible because the code allows it. The pipeline still requires an SDAT single-family-detached house on the lot, so only actual SFDs in these zones are screened.

Marked **unconfirmed** because:

- Overlay zones may modify standards in parts of 20814 (Bethesda Overlay Zone, Ch. 59 Div. 4.9). This was not checked.
- Many SFDs in these zones may predate the zoning and be non-conforming.
- The user may prefer to exclude these zones from the headline count.

### Not eligible / not modeled

- **IM-1.5, IM-2.5 (Industrial).** The Ord. 20-36 use table is blank for IL/IM/IH. Confirmed.
- **RT-8.0, RT-10.0, RT-12.5, R-H (zones retained from the pre-2014 ordinance).** The §8.2.3 RT/R-H use table permits Single-Unit Living (RT: "must satisfy the requirements of the R-60 zone") but lists no ADU, and Ord. 20-36 amended only §3.1.6. Under county text, ADUs are not allowed. State law (HB 1466) requires ADUs "on land with a single-family detached dwelling", so this may be a gap the county has not closed. **Unconfirmed — needs user check.** If treated as eligible, RT detached houses follow R-60 per the footnote.
- **CRF-1.5, CRTF-1.25, EOFF-0.5 (floating zones, Art. 59-5).** Development standards come from the approved floating-zone plan, so there is no fixed table. Not modeled. **Unconfirmed — needs user check.** There are only 3 zoning polygons in the study area.

### Zone keys

The zoning layer's `ZONE` field includes the density suffix (`CRT-0.5`, `CR-3.0`). `zones.yaml` lists every distinct `ZONE` value that intersected the three ZCTAs on 2026-11-08: 57 values, plus R-40. Any other value is treated as `zone_ineligible`. If the zoning layer changes, a new value will silently drop out, so the prepare stage should log unmatched zone values.

## SFD codes

From MD iMap Parcel Points (SDAT), `JURSCODE='MONT' AND LU='R'`, distinct `STRUBLDG`/`DESCBLDG`:

| STRUBLDG | DESCBLDG | SFD? |
|---|---|---|
| 0001 | DWEL Standard Unit | **yes** |
| 0002 | DWEL End Unit | no (townhouse end) |
| 0003 | DWEL Center Unit | no (townhouse interior) |
| 0004 | DWEL Split Foyer | **yes** |
| 0005 | DWEL Split Level | **yes** |
| 0006 | DWEL Mobile Home | no |
| 0007 / 0008 / 0009 | Condo Townhouse / Garden / Hi Rise | no |
| 0014 | Parking Space | no |
| C101, C138, null | Apartment, Office, unknown | no |

`land_use: ["R"]`, `structure: ["0001","0004","0005"]`.

Cross-check: in the county property layer, every parcel in the study envelope with county land use `111` "Single Family Detached" has dwelling type `A/B/C` + `001`, `004` or `005`. Townhouse codes 002, 003 and 007 map to land use 114/116 "Single Family Attached".

Caveats:

- A semi-detached duplex may also be coded "Standard Unit". That case was not checked.
- SFDs coded `LU='E'` (exempt, e.g. church-owned) are excluded.

## Corner-lot rule

§1.4.2 defines "Lot Line, Front" as a lot line abutting a right-of-way or common open space, and adds: "On a corner lot, the owner must elect which lot line is the front lot line." The side-street lot line is any street lot line that is not the front. Corner lot means the interior angle at the intersection is ≤135°.

The code gives no shorter/longer rule. `corner_lot_front: "shorter"` is a **screening heuristic**: most houses face, and are addressed on, the shorter frontage. **Unconfirmed — needs user check.** A better rule would treat the street of the premise address as the front, but the config schema only supports shorter/longer.

## Data endpoints

Each was tested on 2026-11-08 with a single-record query (`resultRecordCount=1&f=json`).

| Role | URL | Key fields | Test result |
|---|---|---|---|
| parcels | https://gis4.montgomerycountymd.gov/arcgis/rest/services/general/property/MapServer/0 | OBJECTID, ACCT, DISTRICT | OK; 587 parcels in pilot bbox; LOAD_DATE 2026-11-05; max 1000/request |
| parcels fallback | https://mdgeodata.md.gov/imap/rest/services/PlanningCadastre/MD_ParcelBoundaries/MapServer/0 | ACCTID | OK; 590 in pilot bbox; POLYDATE 2024JAN |
| zoning | https://gis4.montgomerycountymd.gov/arcgis/rest/services/general/zoning/FeatureServer/1 | ZONE | OK; county copy of M-NCPPC zoning; `outStatistics` with geometry errors, plain queries work |
| footprints | https://gis.montgomerycountymd.gov/arcgis/rest/services/General/BLDG_PS/MapServer/0 | BLDG_ID, BLDG_CLASS, BLDG_PROP_TAX_ID | OK; 588 in pilot bbox; max 2000/request |
| footprints fallback | https://mdgeodata.md.gov/imap/rest/services/PlanningCadastre/MD_BuildingFootprints/MapServer/0 | OBJECTID (geometry only) | OK |
| sdat | https://mdgeodata.md.gov/imap/rest/services/PlanningCadastre/MD_PropertyData/MapServer/0 | ACCTID, LU, STRUBLDG, SQFTSTRC, ADDRESS | OK; SDATDATE 2026AUG |
| zcta | https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/PUMA_TAD_TAZ_UGA_ZCTA/MapServer/1 | ZCTA5 | OK |
| places | https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/4 | NAME | OK; filter `STATE='24'` to drop "Washington city" |
| places fallback | https://gis.montgomerycountymd.gov/arcgis/rest/services/General/municipalities/MapServer/0 | AREA_NAME | OK |
| imagery | https://mdgeodata.md.gov/imagery/rest/services/SixInch/SixInchImagery2023_2024_2025/MapServer (`/export`) | – | OK; 512×512 JPEG of pilot area, 2023 leaf-off |
| imagery fallback | https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x} | – | OK (HTTP 200 JPEG) |

**Parcel to SDAT join.** The SDAT `ACCTID` is `"16"` + parcel `DISTRICT` + parcel `ACCT`: for example, district 07 and account 00429817 give `160700429817`. This was verified on three pilot parcels, and is recorded as `join_transform` in `sources.yaml`.

Endpoint caveats:

- The spec's Microsoft US Building Footprints blob returned HTTP 409 ("Public access is not permitted"). MD iMap footprints replace it as the fallback.
- Imagery: the combined `SixInch/SixInchImagery` MapServer returned a near-empty image at pilot scale. Its tile cache uses a non-standard origin and 512-px tiles, so it does not work as a plain XYZ layer. Use `/export` on the 2023_2024_2025 service, or esri-leaflet.
- `geodata.md.gov` showed a maintenance page. `mdgeodata.md.gov` works.

## Pilot bbox check

Bbox `[-77.106, 38.962, -77.094, 38.970]` (in 20816):

- Zoning polygons intersecting it: R-60 (15), R-90 (10), R-10, TLD, CRT-*, CR-3.0, EOF-1.5, IM-*. **R-60 and R-90 are present.**
- TIGER places intersecting it: **Somerset town**, whose extent is -77.102..-77.0886, 38.962..38.9706.
- Parcels with county land use 111 (SFD) in the bbox: 444 in total. 341 are in Somerset, 90 are county (unincorporated), 7 are blank, and 6 are in Drummond (a special taxing area, not a TIGER place).

**The check passes, so the bbox is unchanged.** About 77% of its SFD parcels are in Somerset, though, and those would all be `flagged_town`. The pilot would then verify mostly town parcels.

Suggested alternative, for the user to decide: `[-77.110, 38.960, -77.098, 38.968]`. This has 199 county, 119 Somerset and 24 blank SFD parcels. It still contains R-60 (25 polygons), R-90 (5) and part of Somerset.

## Unconfirmed — needs user check

1. **Side and rear setback in R-60/R-90/R-40.** Config uses 15 ft (two-story, 20 ft ADU). A one-story ADU of 15 ft or less needs only 5 ft (height_ft 15). Which should drive the headline?
2. **`behind_rear_building_line`.** Ch. 59 requires accessory structures in RE-2, RE-2C, RE-1, R-200, R-90, R-60 and R-40 to be behind the house's rear building line. This is stricter than the spec's "behind front line" exclusion. The pocket-building step must implement it (exclude everything forward of the house's rear wall, between the side lot lines), or fits will be overcounted. The language comes straight from the code, so it is confirmed. How the pipeline implements it is a design decision for the controller.
3. **CR/CRT/CRN/GR/NR/EOF eligibility.** The code makes them eligible. Overlay effects were not checked. Should they be in the headline?
4. **RT-* and R-H.** Treated as ineligible under the county text, although state law may require otherwise.
5. **Floating zones (CRF, CRTF, EOFF).** Not modeled.
6. **Corner-lot front = shorter.** A heuristic. The code lets the owner elect.
7. **Footprint currency.** 432 of 588 pilot footprints carry BLDG_DATE 2003, and small sheds are largely absent. Teardown rebuilds may be stale. Check this during pilot verification.
8. **"Size" in the 75% cap** is not defined in the ordinance. The pipeline uses SDAT `SQFTSTRC` (structure square footage) as the house size.

## User decisions (2026-11-08)

- **1-story ADUs only.** R-60, R-90 and R-40 are modeled at a 15 ft accessory height with 5 ft side and rear setbacks. `run.yaml` `max_stories: 1` limits floor area to one story in every zone.
- **Pilot box moved west** to `[-77.110, 38.960, -77.098, 38.968]`, so most pilot parcels are unincorporated rather than in Somerset.
