import csv
from pathlib import Path

import pytest

from adu.__main__ import main
from adu.verify import score_verification

HEADER = ["parcel_id", "status", "verdict", "reason", "note"]


def write(path: Path, rows, header=HEADER) -> Path:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


def rows(n_ok, wrongs):
    out = [[f"p{i}", "fit", "correct", "", ""] for i in range(n_ok)]
    out += [[f"w{i}", "fit", "wrong", r, ""] for i, r in enumerate(wrongs)]
    return out


def test_passes_with_split_reasons(tmp_path):
    r = score_verification(write(tmp_path / "a.csv", rows(37, ["wrong_house"] * 2 + ["other"])))
    assert r == {"n": 40, "correct": 37, "pct_correct": 92.5,
                 "wrong_by_reason": {"wrong_house": 2, "other": 1}, "passes": True}


def test_fails_when_one_reason_exceeds_two(tmp_path):
    r = score_verification(write(tmp_path / "a.csv", rows(37, ["wrong_front"] * 3)))
    assert r["passes"] is False
    assert r["wrong_by_reason"] == {"wrong_front": 3}


def test_fails_below_90_pct(tmp_path):
    wrongs = ["wrong_house", "wrong_house", "wrong_front", "wrong_front", "other"]
    r = score_verification(write(tmp_path / "a.csv", rows(35, wrongs)))
    assert r["pct_correct"] == 87.5
    assert r["passes"] is False


def test_note_with_comma_and_quote(tmp_path):
    data = rows(9, []) + [["x", "fit", "wrong", "other", 'has, a "quote"']]
    r = score_verification(write(tmp_path / "a.csv", data))
    assert r["n"] == 10 and r["wrong_by_reason"] == {"other": 1}


def test_bad_header_raises(tmp_path):
    p = write(tmp_path / "a.csv", [], header=["parcel_id", "status", "verdict", "note"])
    with pytest.raises(ValueError, match="header"):
        score_verification(p)


def test_bad_verdict_raises(tmp_path):
    p = write(tmp_path / "a.csv", [["p", "fit", "maybe", "", ""]])
    with pytest.raises(ValueError, match="verdict"):
        score_verification(p)


def test_cli_exit_codes(tmp_path, capsys):
    good = write(tmp_path / "g.csv", rows(10, []))
    bad = write(tmp_path / "b.csv", rows(5, ["other"] * 5))
    with pytest.raises(SystemExit) as e:
        main(["verify", str(good)])
    assert e.value.code == 0
    with pytest.raises(SystemExit) as e:
        main(["verify", str(bad)])
    assert e.value.code == 1
    assert "passes" in capsys.readouterr().out
