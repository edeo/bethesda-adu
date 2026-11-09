import pytest

from adu import __main__ as cli


def test_from_requires_existing_outputs(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as e:
        cli.main(["run", "--area", "pilot", "--from", "fit"])
    assert e.value.code != 0
    err = capsys.readouterr().err
    assert "parcels_classified.parquet" in err


def test_stage_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(cli, "fetch_all", lambda area, force=False: calls.append("fetch") or {})
    monkeypatch.setattr(cli, "prepare", lambda raw, out, area: calls.append("prepare"))
    monkeypatch.setattr(cli, "classify_stage", lambda area: calls.append("classify"))
    monkeypatch.setattr(cli, "fit_stage", lambda area: calls.append("fit"))
    monkeypatch.setattr(cli, "print_summary", lambda area: None)
    cli.main(["run", "--area", "pilot"])
    assert calls == ["fetch", "prepare", "classify", "fit"]

    # inputs for classify must exist before --from classify
    base = tmp_path / "data/interim/pilot"
    base.mkdir(parents=True, exist_ok=True)
    for n in ("parcels_prepared", "footprints", "parcels_neighbors"):
        (base / f"{n}.parquet").touch()
    calls.clear()
    cli.main(["run", "--area", "pilot", "--from", "classify"])
    assert calls == ["classify", "fit"]
