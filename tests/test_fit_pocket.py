"""Buildable pocket and coverage on synthetic rectangular lots (EPSG:2248 feet).

Lots sit at (X0, Y0) with the front on the south side (y = 0) unless noted.
"""
import math

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from adu.fit_edges import Edge
from adu.fit_pocket import (build_pocket, exclusion_widths, front_yard_exclusion,
                            remaining_coverage, setback_envelope)
from synth import X0, Y0, rect

RUN = {"separation_ft": 5, "shed_ignore_sqft": 0}


def seg(x1, y1, x2, y2):
    return LineString([(X0 + x1, Y0 + y1), (X0 + x2, Y0 + y2)])


def rect_edges(w, h, south="front", east="side", north="rear", west="side"):
    return [Edge(seg(0, 0, w, 0), south), Edge(seg(w, 0, w, h), east),
            Edge(seg(w, h, 0, h), north), Edge(seg(0, h, 0, 0), west)]


def rule(front=25, side=5, rear=5, side_street=15, behind_front_line=True, **extra):
    return {"setbacks_ft": {"front": front, "side": side, "side_street": side_street, "rear": rear},
            "behind_front_line": behind_front_line, **extra}


def pocket_union(pieces):
    return unary_union(pieces)


def min_y(geom):
    return geom.bounds[1] - Y0


def test_envelope_rectangle():
    lot = rect(0, 0, 60, 100)
    edges = rect_edges(60, 100)
    sb = {"front": 25, "side": 5, "rear": 5, "side_street": 15}
    env = setback_envelope(lot, edges, sb)
    # Round buffers are slightly circumscribed (conservative), so the 50x70 box loses a hair
    assert 3500 * 0.995 <= env.area <= 3500 + 1e-6
    for e in edges:
        assert env.distance(e.geom) >= sb[e.kind] - 1e-6
    assert 25 - 1e-6 <= min_y(env) < 25.1  # round-cap buffers are circumscribed, so >= the true setback


def test_envelope_missing_kind_raises():
    lot = rect(0, 0, 60, 100)
    # side_street is unused here, so this must not raise
    setback_envelope(lot, rect_edges(60, 100), {"front": 25, "side": 5, "rear": 5})
    try:
        setback_envelope(lot, rect_edges(60, 100, east="side_street"), {"front": 25, "side": 5, "rear": 5})
    except KeyError:
        return
    raise AssertionError("missing side_street setback must raise KeyError")


def test_front_yard_excluded():
    lot = rect(0, 0, 60, 120)
    house = rect(15, 30, 30, 30)
    pieces = build_pocket(lot, rect_edges(60, 120), house, [], rule(front=5, behind_rear_building_line=False), RUN)
    assert pieces
    assert min_y(pocket_union(pieces)) >= 30 - 0.01


def test_front_yard_kept_when_switch_off():
    lot = rect(0, 0, 60, 120)
    house = rect(15, 30, 30, 30)
    pieces = build_pocket(lot, rect_edges(60, 120), house, [],
                          rule(front=5, behind_front_line=False, behind_rear_building_line=False), RUN)
    assert min_y(pocket_union(pieces)) < 6


def test_house_separation():
    lot = rect(0, 0, 60, 120)
    house = rect(15, 30, 30, 30)
    pieces = build_pocket(lot, rect_edges(60, 120), house, [], rule(front=5, behind_front_line=False), RUN)
    assert pieces
    for p in pieces:
        assert p.distance(house) >= 5 - 0.01


def test_pocket_splits():
    lot = rect(0, 0, 60, 120)
    house = rect(0, 40, 60, 20)  # spans the whole envelope width
    pieces = build_pocket(lot, rect_edges(60, 120), house, [], rule(front=5, behind_front_line=False), RUN)
    assert len(pieces) == 2


def test_shed_ignored_below_threshold():
    lot = rect(0, 0, 60, 120)
    house = rect(15, 10, 30, 30)
    shed = rect(25, 90, 10, 10)  # 100 sq ft
    r = rule(front=5, behind_front_line=False)
    kept = build_pocket(lot, rect_edges(60, 120), house, [shed], r, {"separation_ft": 5, "shed_ignore_sqft": 150})
    cut = build_pocket(lot, rect_edges(60, 120), house, [shed], r, {"separation_ft": 5, "shed_ignore_sqft": 50})
    assert abs(pocket_union(kept).area - pocket_union(cut).area - 100) < 1


def test_tiny_pieces_dropped():
    lot = rect(0, 0, 60, 120)
    house = rect(15, 10, 30, 30)
    pieces = build_pocket(lot, rect_edges(60, 120), house, [], rule(front=5, behind_front_line=False), RUN)
    assert all(p.area >= 1 for p in pieces)


def test_remaining_coverage_clamps():
    assert remaining_coverage(6000, 0.30, [1900]) == 0.0
    assert abs(remaining_coverage(6000, 0.30, [1000, 200]) - 600) < 1e-9


def test_behind_rear_building_line():
    lot = rect(0, 0, 60, 120)
    house = rect(15, 30, 30, 40)  # rear wall 70 ft from the front
    pieces = build_pocket(lot, rect_edges(60, 120), house, [],
                          rule(front=5, behind_rear_building_line=True), RUN)
    assert pieces
    assert min_y(pocket_union(pieces)) >= 70 - 0.01


def test_front_building_line_offset():
    lot = rect(0, 0, 60, 120)
    house = rect(15, 20, 30, 30)  # front wall 20 ft back
    pieces = build_pocket(lot, rect_edges(60, 120), house, [],
                          rule(front=5, front_building_line_offset_ft=10), RUN)
    assert pieces
    assert min_y(pocket_union(pieces)) >= 30 - 0.01


def test_through_lot_rear_rule_from_nearest_front():
    edges = rect_edges(60, 200, north="front")
    house = rect(15, 25, 30, 40)  # 25 ft from the south front, rear wall at 65 ft
    r = rule(front=25, side=5, rear=5, behind_rear_building_line=True)
    w = exclusion_widths(edges, house, r)
    assert abs(w[0] - 65) < 0.01  # south (nearest): rear wall
    assert w[2] == 0  # north (far) frontage: no front-yard exclusion
    assert w[1] == 0 and w[3] == 0
    pieces = build_pocket(rect(0, 0, 60, 200), edges, house, [], r, RUN)
    assert pieces
    u = pocket_union(pieces)
    assert min_y(u) >= 65 - 0.01
    assert 174 < u.bounds[3] - Y0 <= 175 + 1e-6  # far front setback only
    # house nearer the north front: the roles swap
    w = exclusion_widths(edges, rect(15, 135, 30, 40), r)
    assert abs(w[2] - 65) < 0.01 and w[0] == 0


def test_split_frontage_shares_width():
    edges = [Edge(seg(0, 0, 30, 0), "front"), Edge(seg(30, 0, 60, 0), "front"),
             Edge(seg(60, 0, 60, 120), "side"), Edge(seg(60, 120, 0, 120), "rear"),
             Edge(seg(0, 120, 0, 0), "side")]
    house = rect(35, 20, 20, 30)  # in front of the east piece only
    w = exclusion_widths(edges, house, rule(behind_rear_building_line=True))
    assert abs(w[0] - 50) < 0.01 and abs(w[1] - 50) < 0.01
    w = exclusion_widths(edges, house, rule(behind_rear_building_line=False))
    assert abs(w[0] - 20) < 0.01 and abs(w[1] - 20) < 0.01


def test_side_street_uses_min_distance():
    lot = rect(0, 0, 60, 120)
    edges = rect_edges(60, 120, east="side_street")
    house = rect(10, 20, 30, 30)  # side wall 20 ft from the east side street, far corner 50 ft
    r = rule(front=5, side_street=5, behind_rear_building_line=True)
    w = exclusion_widths(edges, house, r)
    assert abs(w[1] - 20) < 0.01
    pieces = build_pocket(lot, edges, house, [], r, RUN)
    assert pieces
    assert pocket_union(pieces).bounds[2] - X0 <= 40 + 0.01
    assert pocket_union(pieces).bounds[2] - X0 > 39  # east strip up to the house side wall line is kept


def test_no_flags_removes_nothing():
    lot = rect(0, 0, 60, 120)
    edges = rect_edges(60, 120, east="side_street")
    house = rect(15, 30, 30, 30)
    env = setback_envelope(lot, edges, rule()["setbacks_ft"])
    out = front_yard_exclusion(env, edges, house, rule(behind_front_line=False))
    assert abs(out.area - env.area) < 1e-6


def P(x, y):
    return (X0 + x, Y0 + y)


def test_curved_frontage_one_W():
    """Pie lot whose front is a 200-degree cul-de-sac arc split into 5 edges."""
    cx, cy, rad = 80.0, 7.0, 40.0  # circle crosses y=0 at -10 and 190 degrees
    angs = [-10 + 40 * k for k in range(6)]
    arc = [(cx + rad * math.cos(math.radians(a)), cy + rad * math.sin(math.radians(a))) for a in angs]
    ring = [(0, 0)] + list(reversed(arc)) + [(160, 0), (160, 160), (0, 160)]
    lot = Polygon([P(*q) for q in ring])
    assert lot.is_valid
    fronts = [Edge(LineString([P(*arc[k + 1]), P(*arc[k])]), "front") for k in range(5)]
    others = [Edge(LineString([P(0, 0), P(*arc[-1])]), "side"), Edge(LineString([P(*arc[0]), P(160, 0)]), "side"),
              Edge(LineString([P(160, 0), P(160, 160)]), "side"), Edge(LineString([P(160, 160), P(0, 160)]), "rear"),
              Edge(LineString([P(0, 160), P(0, 0)]), "side")]
    house = rect(60, 100, 40, 30)
    for order in (fronts + others, others + fronts[::-1], [fronts[2], others[0], fronts[0], fronts[4], fronts[1],
                                                           *others[1:], fronts[3]]):
        for flag in (True, False):
            r = rule(behind_rear_building_line=flag)
            w = [v for e, v in zip(order, exclusion_widths(order, house, r)) if e.kind == "front"]
            assert len(w) == 5 and w[0] > 0 and all(abs(v - w[0]) < 1e-9 for v in w), (flag, w)


def test_widening_trapezoid_no_leak():
    lot = Polygon([P(30, 0), P(70, 0), P(100, 120), P(0, 120)])  # front 40 ft, rear 100 ft
    edges = [Edge(LineString([P(30, 0), P(70, 0)]), "front"), Edge(LineString([P(70, 0), P(100, 120)]), "side"),
             Edge(LineString([P(100, 120), P(0, 120)]), "rear"), Edge(LineString([P(0, 120), P(30, 0)]), "side")]
    house = rect(35, 20, 30, 40)  # rear wall 60 ft back from the front
    r = rule(front=25, side=5, rear=5, behind_rear_building_line=True)
    front = edges[0].geom
    w = exclusion_widths(edges, house, r)[0]
    assert abs(w - 60) < 1e-6
    env = setback_envelope(lot, edges, r["setbacks_ft"])
    assert not env.is_empty and env.distance(front) >= 25 - 1e-6
    pieces = build_pocket(lot, edges, house, [], r, RUN)
    assert pieces
    assert pocket_union(pieces).distance(front) >= w - 1e-6
