"""Edge classification on synthetic lots (EPSG:2248 feet). Streets are simply gaps with no neighbor."""
from collections import Counter

from shapely.geometry import MultiPolygon
from shapely.ops import unary_union

from adu.fit_edges import Edge, classify_edges
from synth import X0, Y0, rect


def kinds(edges):
    return Counter(e.kind for e in edges)


def of_kind(edges, kind):
    return [e for e in edges if e.kind == kind]


def mid(edge):
    p = edge.geom.interpolate(0.5, normalized=True)
    return p.x - X0, p.y - Y0


def test_interior_rectangle():
    lot = rect(0, 0, 60, 100)
    nb = unary_union([rect(-60, 0, 60, 100), rect(60, 0, 60, 100), rect(0, 100, 60, 100)])
    edges, odd = classify_edges(lot, nb, "shorter")
    assert not odd
    assert all(isinstance(e, Edge) for e in edges)
    assert kinds(edges) == {"front": 1, "rear": 1, "side": 2}
    assert abs(mid(of_kind(edges, "front")[0])[1] - 0) < 1
    assert abs(mid(of_kind(edges, "rear")[0])[1] - 100) < 1
    total = sum(e.geom.length for e in edges)
    assert abs(total - lot.exterior.length) < 1


def test_sliver_gap_neighbors_still_interior():
    lot = rect(0, 0, 60, 100)
    g = 0.8  # digitizing gap against every neighbor
    nb = unary_union([rect(-60 - g, 0, 60, 100), rect(60 + g, 0, 60, 100), rect(0, 100 + g, 60, 100)])
    edges, odd = classify_edges(lot, nb, "shorter")
    assert not odd
    assert kinds(edges) == {"front": 1, "rear": 1, "side": 2}


def test_corner_lot_shorter_front():
    lot = rect(0, 0, 60, 100)
    nb = unary_union([rect(-60, 0, 60, 100), rect(0, 100, 60, 100)])
    edges, odd = classify_edges(lot, nb, "shorter")
    assert not odd
    assert kinds(edges) == {"front": 1, "side_street": 1, "rear": 1, "side": 1}
    assert abs(mid(of_kind(edges, "front")[0])[1] - 0) < 1
    assert abs(mid(of_kind(edges, "side_street")[0])[0] - 60) < 1
    assert abs(mid(of_kind(edges, "rear")[0])[1] - 100) < 1
    assert abs(mid(of_kind(edges, "side")[0])[0] - 0) < 1


def test_corner_lot_longer_front():
    lot = rect(0, 0, 60, 100)
    nb = unary_union([rect(-60, 0, 60, 100), rect(0, 100, 60, 100)])
    edges, odd = classify_edges(lot, nb, "longer")
    assert not odd
    assert abs(mid(of_kind(edges, "front")[0])[0] - 60) < 1
    assert abs(mid(of_kind(edges, "side_street")[0])[1] - 0) < 1
    assert abs(mid(of_kind(edges, "rear")[0])[0] - 0) < 1


def test_through_lot():
    lot = rect(0, 0, 60, 100)
    nb = unary_union([rect(-60, 0, 60, 100), rect(60, 0, 60, 100)])
    edges, odd = classify_edges(lot, nb, "shorter")
    assert not odd
    assert kinds(edges) == {"front": 2, "side": 2}


def _flag_case(pole_x):
    main = rect(0, 40, 100, 100)
    pole = rect(pole_x, 0, 20, 40)
    lot = unary_union([main, pole])
    flank = [r for r in (rect(0, 0, pole_x, 40), rect(pole_x + 20, 0, 100 - pole_x - 20, 40)) if r.area > 0]
    nb = unary_union(flank + [rect(-100, 0, 100, 140), rect(100, 0, 100, 140), rect(0, 140, 100, 100)])
    return lot, nb


def _assert_flag(edges, odd):
    assert not odd
    fronts = of_kind(edges, "front")
    assert len(fronts) == 1
    assert all(mid(e)[1] > 39 for e in fronts)  # junction line, not the pole frontage
    assert fronts[0].geom.length > 90  # spans the main lot
    rears = of_kind(edges, "rear")
    assert len(rears) == 1
    assert abs(mid(rears[0])[1] - 140) < 1


def test_flag_lot():
    lot, nb = _flag_case(40)
    _assert_flag(*classify_edges(lot, nb, "shorter"))


def test_flag_lot_pole_flush_with_side():
    lot, nb = _flag_case(0)
    _assert_flag(*classify_edges(lot, nb, "shorter"))


def test_short_frontage_without_pole_is_not_flag():
    lot = unary_union([rect(40, 0, 20, 20), rect(0, 20, 100, 100)])  # pole only 20 ft deep
    nb = unary_union([rect(0, 0, 40, 20), rect(60, 0, 40, 20), rect(-100, 0, 100, 120),
                      rect(100, 0, 100, 120), rect(0, 120, 100, 100)])
    edges, odd = classify_edges(lot, nb, "shorter")
    assert not odd
    assert abs(mid(of_kind(edges, "front")[0])[1] - 0) < 1


def test_multipolygon_is_odd():
    lot = MultiPolygon([rect(0, 0, 60, 100), rect(200, 0, 30, 30)])
    edges, odd = classify_edges(lot, rect(-60, 0, 60, 100), "shorter")
    assert odd
    assert edges


def test_invalid_bowtie_is_odd_not_crash():
    from synth import bowtie
    edges, odd = classify_edges(bowtie(), rect(-500, -500, 1, 1), "shorter")
    assert odd


def test_landlocked_is_odd():
    lot = rect(0, 0, 60, 100)
    nb = rect(-100, -100, 260, 300).difference(lot)
    edges, odd = classify_edges(lot, nb, "shorter")
    assert odd
    assert edges and not of_kind(edges, "front")


def test_three_street_runs_is_odd():
    lot = rect(0, 0, 60, 100)
    nb = rect(-60, 0, 60, 100)
    edges, odd = classify_edges(lot, nb, "shorter")
    assert odd


def test_notched_frontage_not_through():
    notch = rect(45, 0, 10, 10)
    lot = rect(0, 0, 100, 100).difference(notch)
    nb = unary_union([notch, rect(-100, 0, 100, 100), rect(100, 0, 100, 100), rect(0, 100, 100, 100)])
    edges, odd = classify_edges(lot, nb, "shorter")
    assert not odd
    fronts = of_kind(edges, "front")
    assert len(fronts) == 2 and all(abs(mid(e)[1]) < 1 for e in fronts)
    rears = of_kind(edges, "rear")
    assert len(rears) == 1 and abs(mid(rears[0])[1] - 100) < 1


def test_two_unrelated_runs_is_odd():
    corner = rect(50, 0, 10, 10)  # neighbor parcel cut out of the SE corner separates the two streets
    lot = rect(0, 0, 60, 100).difference(corner)
    nb = unary_union([corner, rect(-60, 0, 60, 100), rect(0, 100, 60, 100)])
    edges, odd = classify_edges(lot, nb, "shorter")
    assert odd
    assert of_kind(edges, "front")


def test_neighbors_including_parcel_itself():
    lot = rect(0, 0, 60, 100)
    nb = unary_union([lot, rect(-60, 0, 60, 100), rect(60, 0, 60, 100), rect(0, 100, 60, 100)])
    edges, odd = classify_edges(lot, nb, "shorter")
    assert not odd
    assert kinds(edges) == {"front": 1, "rear": 1, "side": 2}
