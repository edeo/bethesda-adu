"""Load and validate run and zone configuration."""
from pathlib import Path

import yaml


class ConfigError(Exception):
    pass


PLACEHOLDER = "PLACEHOLDER"
SETBACKS = ("front", "side", "side_street", "rear")
ELIGIBLE_FIELDS = ("height_ft", "coverage_cap", "behind_front_line")
TOP_LEVEL_CITATIONS = (
    ("adu_size_cap_citation",),
    ("sfd_codes", "citation"),
    ("corner_lot_citation",),
)


def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_run_config(path: Path = Path("config/run.yaml")) -> dict:
    return _load_yaml(path)


def _check_citation(label: str, value) -> None:
    if value == PLACEHOLDER:
        raise ConfigError(f"{label}: citation is {PLACEHOLDER}")


def load_zones(path: Path = Path("config/zones.yaml")) -> dict:
    data = _load_yaml(path)
    for code, zone in (data.get("zones") or {}).items():
        if "citation" not in zone:
            raise ConfigError(f"zone {code}: missing field citation")
        _check_citation(f"zone {code}", zone["citation"])
        if not zone.get("adu_eligible"):
            continue
        for field in ELIGIBLE_FIELDS:
            if field not in zone:
                raise ConfigError(f"zone {code}: missing field {field}")
        setbacks = zone.get("setbacks_ft") or {}
        for key in SETBACKS:
            if key not in setbacks:
                raise ConfigError(f"zone {code}: missing field setbacks_ft.{key}")
    for keys in TOP_LEVEL_CITATIONS:
        node = data
        for k in keys:
            node = node.get(k) if isinstance(node, dict) else None
        _check_citation(".".join(keys), node)
    return data
