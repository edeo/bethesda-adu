import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
PILOT = ROOT / "data" / "interim" / "pilot" / "parcels_fit.parquet"
SNAPSHOT = ROOT / "tests" / "snapshots" / "pilot_counts.json"


def _pilot_counts(path):
    df = pd.read_parquet(path, columns=["status", "reason"])
    reason = df["reason"].where(df["reason"].notna(), "none").astype(str)
    keys = df["status"].astype(str) + "|" + reason
    counts = keys.value_counts()
    return {k: int(v) for k, v in sorted(counts.items())}


@pytest.mark.skipif(not PILOT.exists(), reason="pilot output not generated")
def test_pilot_counts_match_snapshot():
    expected = json.loads(SNAPSHOT.read_text())
    actual = _pilot_counts(PILOT)
    assert actual == expected, (
        "pilot status/reason counts differ from tests/snapshots/pilot_counts.json. "
        "Regenerate the snapshot only when pilot results change on purpose. "
        f"actual={actual}"
    )
