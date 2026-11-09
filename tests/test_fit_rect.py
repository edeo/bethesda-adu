"""Largest-rectangle fit and ADU size cap (EPSG:2248 feet)."""
import pytest
from shapely import affinity
from shapely.geometry import box

from adu.fit_rect import largest_rectangle, lot_axis_deg, max_adu_floor_area
from synth import X0, Y0, rect


def test_rect_in_square():
    res = largest_rectangle(rect(0, 0, 50, 50), 0.0, [0], 20)
    assert res is not None
    poly, w, l = res
    assert 49 <= w <= 50 and 49 <= l <= 50
    assert rect(0, 0, 50, 50).buffer(1e-6).contains(poly)


def test_rect_rotated_pocket():
    pocket = affinity.rotate(rect(0, 0, 40, 30), 30, origin=(X0, Y0))
    poly, w, l = largest_rectangle(pocket, 30.0, [0, 15, -15], 20)
    assert w * l >= 1100
    assert pocket.buffer(1e-6).contains(poly)


def test_narrow_strip_none():
    assert largest_rectangle(rect(0, 0, 15, 200), 0.0, [0, 15, -15, 30, -30, 45, -45], 20) is None


def test_l_shape_picks_larger_arm():
    pocket = rect(0, 0, 100, 30).union(rect(0, 0, 30, 60))  # 100x30 arm and 30x60 arm
    poly, w, l = largest_rectangle(pocket, 0.0, [0], 20)
    assert w * l >= 2900
    x0, y0, x1, y1 = poly.bounds
    assert y1 - Y0 <= 30 + 1e-6 and x1 - X0 >= 99


def test_lot_axis_deg():
    assert lot_axis_deg(rect(0, 0, 60, 120)) % 180 == pytest.approx(90, abs=1e-6)
    lot = affinity.rotate(rect(0, 0, 120, 60), 30, origin=(X0, Y0))
    assert lot_axis_deg(lot) % 180 == pytest.approx(30, abs=1e-6)


def test_size_cap_house_limited():
    assert max_adu_floor_area(1200, 600, 20, 10, 2, 0.75) == pytest.approx(900)


def test_size_cap_footprint_limited():
    assert max_adu_floor_area(4000, 500, 15, 10, 2, 0.75) == pytest.approx(500)


def test_size_cap_max_stories_one():
    assert max_adu_floor_area(4000, 600, 20, 10, 1, 0.75) == pytest.approx(600)


def test_rect_exact_min_square():
    # a pocket exactly min_dim on each side still fits (boundary cells count)
    res = largest_rectangle(box(0, 0, 20, 20), 0.0, [0], 20)
    assert res is not None and res[1] == pytest.approx(20) and res[2] == pytest.approx(20)
