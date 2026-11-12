# Bethesda detached ADU screening

This project estimates where a detached accessory dwelling unit (ADU) could legally and physically fit on existing lots in Bethesda, Maryland (ZIP codes 20814, 20816 and 20817). It applies Montgomery County's rules as amended by ZTA 26-06, effective 2026-10-05.

**Live map:** https://edeo.github.io/bethesda-adu/ ([method and limits](https://edeo.github.io/bethesda-adu/summary.html))

This is a screening estimate, not a permitting determination.

## How it works

A Python pipeline runs five stages:

1. **fetch** downloads county parcels, zoning and building footprints, state property records, and Census boundaries.
2. **prepare** joins them in Maryland State Plane (feet).
3. **classify** drops lots that are not single-family detached, are in an ineligible zone, or have no house.
4. **fit** works out the buildable pocket on each lot after accessory-structure setbacks, the rule that an ADU sits behind the house's rear wall, house separation, existing buildings and lot coverage, then finds the largest ADU rectangle that fits (minimum 20×20 ft).
5. **publish** writes the map and summary.

A pilot area was checked parcel by parcel against aerial imagery (40/40 correct) before the full run.

- Rules and citations: [`config/zones.yaml`](config/zones.yaml), [`docs/research/regulatory-notes.md`](docs/research/regulatory-notes.md)
- Design: [`docs/superpowers/specs/`](docs/superpowers/specs/)

## Run it

```bash
uv run python -m adu run --area full        # fetch → prepare → classify → fit
uv run python -m adu publish --area full    # local map, ranked CSV, summary in out/
uv run python -m adu publish --site         # public site in docs/ (no addresses)
uv run pytest
```
