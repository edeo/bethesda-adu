from pathlib import Path

import pytest
import yaml

from adu.config import ConfigError, load_run_config, load_zones

RUN = Path(__file__).resolve().parent.parent / "config" / "run.yaml"


def write_zones(tmp_path, zone):
    p = tmp_path / "zones.yaml"
    p.write_text(yaml.safe_dump({"zones": {"Z-1": zone}}))
    return p


def good_zone(**over):
    z = {
        "adu_eligible": True,
        "setbacks_ft": {"front": 25, "side": 8, "side_street": 25, "rear": 20},
        "height_ft": 35,
        "coverage_cap": 0.35,
        "behind_front_line": True,
        "citation": "Sec. 59-4.4.7",
    }
    z.update(over)
    return z


def test_run_config_defaults():
    cfg = load_run_config(RUN)
    assert cfg["min_dim_ft"] == 20
    assert cfg["min_area_sqft"] == 400
    assert cfg["separation_ft"] == 5
    assert cfg["zctas"] == ["20814", "20816", "20817"]


def test_valid_zone_loads(tmp_path):
    assert "Z-1" in load_zones(write_zones(tmp_path, good_zone()))["zones"]


def test_zone_missing_field_raises(tmp_path):
    z = good_zone()
    del z["coverage_cap"]
    with pytest.raises(ConfigError, match=r"Z-1.*coverage_cap"):
        load_zones(write_zones(tmp_path, z))


def test_zone_missing_nested_setback_raises(tmp_path):
    z = good_zone()
    del z["setbacks_ft"]["rear"]
    with pytest.raises(ConfigError, match=r"Z-1.*setbacks_ft.rear"):
        load_zones(write_zones(tmp_path, z))


def test_placeholder_citation_raises(tmp_path):
    with pytest.raises(ConfigError, match=r"Z-1.*PLACEHOLDER"):
        load_zones(write_zones(tmp_path, good_zone(citation="PLACEHOLDER")))


def test_ineligible_zone_needs_no_rules(tmp_path):
    z = {"adu_eligible": False, "citation": "Sec. 1"}
    assert load_zones(write_zones(tmp_path, z))["zones"]["Z-1"]["adu_eligible"] is False
