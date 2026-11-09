import pytest

from synth import RUN_CFG, RawBuilder


@pytest.fixture
def raw(tmp_path):
    return RawBuilder(tmp_path)


@pytest.fixture
def run_cfg():
    return RUN_CFG
