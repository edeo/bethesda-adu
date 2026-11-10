from pathlib import Path

import pytest
import yaml

from adu.config import ConfigError, load_sources, load_zones

CONFIG = Path(__file__).resolve().parent.parent / "config"
SOURCE_KEYS = ("parcels", "zoning", "footprints", "sdat", "zcta", "places", "imagery")


def test_real_configs_load():
    zones = load_zones(CONFIG / "zones.yaml")
    sources = load_sources(CONFIG / "sources.yaml")
    assert zones["zones"]["R-60"]["adu_eligible"] is True
    for key in SOURCE_KEYS:
        assert sources[key]["url"]
        assert sources[key]["verified"]


def test_real_sources_have_required_roles():
    sources = load_sources(CONFIG / "sources.yaml")
    assert {"parcel_id", "sdat_account"} <= set(sources["parcels"]["fields"])
    assert "zone" in sources["zoning"]["fields"]
    assert {"sdat_account", "land_use", "structure", "living_area", "address"} <= set(
        sources["sdat"]["fields"]
    )
    assert "zcta" in sources["zcta"]["fields"]
    assert "name" in sources["places"]["fields"]


def test_load_sources_missing_url_raises(tmp_path):
    data = yaml.safe_load((CONFIG / "sources.yaml").read_text())
    del data["zoning"]["url"]
    p = tmp_path / "sources.yaml"
    p.write_text(yaml.safe_dump(data))
    with pytest.raises(ConfigError, match=r"zoning.*url"):
        load_sources(p)


def test_load_sources_missing_source_raises(tmp_path):
    data = yaml.safe_load((CONFIG / "sources.yaml").read_text())
    del data["imagery"]
    p = tmp_path / "sources.yaml"
    p.write_text(yaml.safe_dump(data))
    with pytest.raises(ConfigError, match=r"imagery"):
        load_sources(p)


def test_real_mixed_use_zone_flags_missing_sdat_not_sfd():
    zones = load_zones(CONFIG / "zones.yaml")["zones"]
    assert zones["CRT-2.0"]["missing_sdat_not_sfd"] is True
    assert not zones["R-60"].get("missing_sdat_not_sfd")


def test_real_corner_rear_setbacks():
    z = load_zones(CONFIG / "zones.yaml")["zones"]
    for code in ("R-60", "R-90", "R-40"):
        assert z[code]["setbacks_ft"]["rear_corner"] == 10
    for code in ("R-200", "RE-1", "RE-2", "RE-2C"):
        assert z[code]["setbacks_ft"]["rear_corner"] == 12
    assert "corner" in z["R-60"]["citation"] and "rear_corner" in z["R-60"]["citation"]
