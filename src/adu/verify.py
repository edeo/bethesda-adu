"""Score the viewer's verification export against the pilot gate."""
import csv
from collections import Counter
from pathlib import Path

HEADER = ["parcel_id", "status", "verdict", "reason", "note"]
MIN_PCT_CORRECT = 90
MAX_PER_REASON = 2


def score_verification(csv_path: Path) -> dict:
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header != HEADER:
            raise ValueError(f"unexpected CSV header {header!r}; expected {HEADER!r}")
        n = correct = 0
        wrong: Counter = Counter()
        for lineno, row in enumerate(reader, start=2):
            if not row:
                continue
            if len(row) != len(HEADER):
                raise ValueError(f"line {lineno}: expected {len(HEADER)} fields, got {len(row)}")
            verdict, reason = row[2], row[3]
            n += 1
            if verdict == "correct":
                correct += 1
            elif verdict == "wrong":
                wrong[reason] += 1
            else:
                raise ValueError(f"line {lineno}: verdict must be 'correct' or 'wrong', got {verdict!r}")
    pct = 100 * correct / n if n else 0.0
    by_reason = dict(wrong)
    passes = n > 0 and pct >= MIN_PCT_CORRECT and max(by_reason.values(), default=0) <= MAX_PER_REASON
    return {"n": n, "correct": correct, "pct_correct": pct,
            "wrong_by_reason": by_reason, "passes": passes}
