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
        flag = zone.get("missing_sdat_not_sfd", False)
        if not isinstance(flag, bool):
            raise ConfigError(f"zone {code}: missing_sdat_not_sfd must be a bool")
        if not zone.get("adu_eligible"):
            continue
        for field in ELIGIBLE_FIELDS:
            if field not in zone:
                raise ConfigError(f"zone {code}: missing field {field}")
        setbacks = zone.get("setbacks_ft") or {}
        for key in SETBACKS:
            if key not in setbacks:
                raise ConfigError(f"zone {code}: missing field setbacks_ft.{key}")
        if "rear_corner" in setbacks:
            rc = setbacks["rear_corner"]
            if isinstance(rc, bool) or not isinstance(rc, (int, float)):
                raise ConfigError(f"zone {code}: setbacks_ft.rear_corner must be a number")
    for keys in TOP_LEVEL_CITATIONS:
        node = data
        for k in keys:
            node = node.get(k) if isinstance(node, dict) else None
        _check_citation(".".join(keys), node)
    return data


SOURCE_KEYS = ("parcels", "zoning", "footprints", "sdat", "zcta", "places", "imagery")
SOURCE_FIELDS = ("url", "layer_type", "verified")
LAYER_TYPES = ("arcgis_rest", "xyz_tiles")


def load_sources(path: Path = Path("config/sources.yaml")) -> dict:
    data = _load_yaml(path)
    for key in SOURCE_KEYS:
        source = data.get(key)
        if not isinstance(source, dict):
            raise ConfigError(f"source {key}: missing")
        for field in SOURCE_FIELDS:
            if not source.get(field):
                raise ConfigError(f"source {key}: missing field {field}")
        if source["layer_type"] not in LAYER_TYPES:
            raise ConfigError(f"source {key}: bad layer_type {source['layer_type']}")
    return data
