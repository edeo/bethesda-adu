import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest

from adu.classify import classify
from adu.config import load_run_config, load_zones
from adu.fit import run_fit

ROOT = Path(__file__).resolve().parent.parent
PILOT = ROOT / "data" / "interim" / "pilot"
INPUTS = ("parcels_prepared.parquet", "footprints.parquet", "parcels_neighbors.parquet")
SNAPSHOT = ROOT / "tests" / "snapshots" / "pilot_counts.json"


def _counts(df):
    reason = df["reason"].where(df["reason"].notna(), "none").astype(str)
    keys = df["status"].astype(str) + "|" + reason
    return {k: int(v) for k, v in sorted(keys.value_counts().items())}


def recompute_pilot_counts():
    """Re-run classify and fit in memory from the prepared pilot inputs and the real configs."""
    parcels = gpd.read_parquet(PILOT / "parcels_prepared.parquet")
    footprints = gpd.read_parquet(PILOT / "footprints.parquet")
    neighbors = gpd.read_parquet(PILOT / "parcels_neighbors.parquet")
    zones, run = load_zones(ROOT / "config" / "zones.yaml"), load_run_config(ROOT / "config" / "run.yaml")
    classified = classify(parcels, footprints, zones, run)
    out, _ = run_fit(classified, footprints, zones, run, neighbors=neighbors)
    return _counts(pd.DataFrame(out))


@pytest.mark.skipif(not all((PILOT / f).exists() for f in INPUTS), reason="pilot prepared files not generated")
def test_pilot_counts_match_snapshot():
    expected = json.loads(SNAPSHOT.read_text())
    actual = recompute_pilot_counts()
    assert actual == expected, (
        "recomputed pilot status/reason counts differ from tests/snapshots/pilot_counts.json. "
        "Regenerate the snapshot only when pilot results change on purpose. "
        f"actual={actual}"
    )
