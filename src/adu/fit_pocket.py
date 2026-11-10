"""Buildable pocket (where a detached ADU may legally sit) and remaining lot coverage.

The pocket is the parcel minus each edge's setback strip, minus the yards the zone's
placement rules forbid (front yard / area in front of the house's rear wall / street side
of the house), minus the house separation buffer and existing accessory buildings.
Geometry is in the parcel's CRS (EPSG:2248, feet). Rule values come from the zone dict.
"""
from __future__ import annotations

import math

import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from adu.fit_edges import Edge

MIN_PIECE_SQFT = 1.0
TOUCH_FT = 0.5  # front edges whose endpoints are this close form one contiguous frontage
OPPOSITE_DEG = 150.0  # frontages whose house-ward normals differ at least this much are separate (through lot)
QUAD_SEGS = 16
# Round buffers are polygons inscribed in the true circle; inflate so every point within the
# nominal distance is covered (conservative by at most ~0.12%).
_ROUND_INFLATE = 1.0 / math.cos(math.pi / (4 * QUAD_SEGS))


def _strip(line: BaseGeometry, width: float) -> BaseGeometry:
    """All points within `width` of the line (round caps and joins)."""
    return line.buffer(width * _ROUND_INFLATE, quad_segs=QUAD_SEGS)


def setback_envelope(parcel: Polygon, edges: list[Edge], setbacks_ft: dict[str, float]) -> BaseGeometry:
    """Parcel minus every point within its kind's setback of each edge (KeyError if absent).

    Corner lots (any `side_street` edge) use `rear_corner` for rear edges when the zone has it.
    Deliberately applied to ALL corner lots (conservative): the code applies it only where the
    abutting lot fronts on the side street.
    """
    setbacks_ft = dict(setbacks_ft)
    if "rear_corner" in setbacks_ft and any(e.kind == "side_street" for e in edges):
        setbacks_ft["rear"] = setbacks_ft["rear_corner"]
    strips = [_strip(e.geom, setbacks_ft[e.kind]) for e in edges if setbacks_ft[e.kind] > 0]
    if not strips:
        return parcel
    return parcel.difference(unary_union(strips))


def _house_normal(edge: Edge, house: Polygon) -> tuple[float, float]:
    """Unit normal of the edge's chord pointing toward the house."""
    (x1, y1), (x2, y2) = edge.geom.coords[0], edge.geom.coords[-1]
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    m = edge.geom.interpolate(0.5, normalized=True)
    c = house.centroid
    if (c.x - m.x) * nx + (c.y - m.y) * ny < 0:
        nx, ny = -nx, -ny
    return nx, ny


def _angle(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1]))))


def _unit(v: tuple[float, float]) -> tuple[float, float]:
    n = math.hypot(*v)
    return (v[0] / n, v[1] / n) if n > 0 else (0.0, 0.0)


def _touch(a: LineString, b: LineString) -> bool:
    ends_a = (Point(a.coords[0]), Point(a.coords[-1]))
    ends_b = (Point(b.coords[0]), Point(b.coords[-1]))
    return any(p.distance(q) <= TOUCH_FT for p in ends_a for q in ends_b)


def _chains(edges: list[Edge], idx: list[int], house: Polygon) -> list[list[int]]:
    """Contiguous runs of front edges (shared endpoints), split only at a hairpin (opposite normals)."""
    parent = {i: i for i in idx}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a in idx:
        for b in idx:
            if a < b and _touch(edges[a].geom, edges[b].geom) and \
                    _angle(_house_normal(edges[a], house), _house_normal(edges[b], house)) < OPPOSITE_DEG:
                parent[find(a)] = find(b)
    groups: dict[int, list[int]] = {}
    for i in idx:
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _chain_normal(edges: list[Edge], chain: list[int], house: Polygon) -> tuple[float, float]:
    sx = sum(_house_normal(edges[i], house)[0] * edges[i].geom.length for i in chain)
    sy = sum(_house_normal(edges[i], house)[1] * edges[i].geom.length for i in chain)
    return _unit((sx, sy))


def _frontages(edges: list[Edge], house: Polygon) -> list[list[int]]:
    """Group `front` edge indices into frontages.

    Contiguous front edges form a chain (one frontage even when curved). Chains merge into
    one frontage unless their house-ward normals are opposite (>= OPPOSITE_DEG, a through
    lot). Longest chains are placed first so the result does not depend on edge order.
    """
    fronts = [i for i, e in enumerate(edges) if e.kind == "front"]
    chains = sorted(_chains(edges, fronts, house),
                    key=lambda c: (-sum(edges[i].geom.length for i in c), min(c)))
    groups: list[tuple[tuple[float, float], list[int]]] = []
    for c in chains:
        n = _chain_normal(edges, c, house)
        for gn, members in groups:
            if _angle(n, gn) < OPPOSITE_DEG:
                members.extend(c)
                break
        else:
            groups.append((n, list(c)))
    return [sorted(m) for _, m in groups]


def _max_distance(line: BaseGeometry, house: BaseGeometry) -> float:
    # get_coordinates covers MultiPolygon houses (footprints with detached parts) too.
    return max(line.distance(Point(c)) for c in shapely.get_coordinates(house))


def exclusion_widths(edges: list[Edge], house: Polygon, zone_rule: dict) -> list[float]:
    """Per-edge width (ft) of the placement-rule strip removed on the parcel side; 0 = none.

    Only the frontage nearest the house gets the front rule (rear-wall rule when
    `behind_rear_building_line`, else min distance + `front_building_line_offset_ft` when
    `behind_front_line`). Other frontages (through lots) get no exclusion, only their
    setback in the envelope. Side streets get the min distance when either flag is set.
    """
    rear_rule = bool(zone_rule.get("behind_rear_building_line"))
    front_rule = bool(zone_rule.get("behind_front_line"))
    offset = float(zone_rule.get("front_building_line_offset_ft", 0) or 0)
    widths = [0.0] * len(edges)

    frontages = _frontages(edges, house)
    unions = [unary_union([edges[i].geom for i in idx]) for idx in frontages]
    nearest = min(range(len(unions)), key=lambda k: unions[k].distance(house)) if unions else None
    for k, (idx, line) in enumerate(zip(frontages, unions)):
        if k != nearest:
            w = 0.0  # far frontage of a through lot: the area behind the house is rear yard
        elif rear_rule:
            w = _max_distance(line, house)
        elif front_rule:
            w = line.distance(house) + offset
        else:
            w = 0.0
        for i in idx:
            widths[i] = w

    if front_rule or rear_rule:
        for i, e in enumerate(edges):
            if e.kind == "side_street":
                widths[i] = e.geom.distance(house)
    return widths


def front_yard_exclusion(envelope: BaseGeometry, edges: list[Edge], house: Polygon, zone_rule: dict) -> BaseGeometry:
    """Remove the yards the zone's placement rules forbid (see `exclusion_widths`).

    Removes every point within W of the edge (round caps), so no wedge leaks past an
    obtuse front corner. The buffer is two-sided; for boundary edges the outer half lies
    outside the envelope.
    """
    strips = [_strip(e.geom, w) for e, w in zip(edges, exclusion_widths(edges, house, zone_rule))
              if w > 0]
    if not strips:
        return envelope
    return envelope.difference(unary_union(strips))


def _polygons(geom: BaseGeometry) -> list[Polygon]:
    out: list[Polygon] = []
    stack = [geom]
    while stack:
        g = stack.pop()
        if isinstance(g, Polygon):
            out.append(g)
        elif hasattr(g, "geoms"):
            stack.extend(g.geoms)
    return out


def build_pocket(parcel: Polygon, edges: list[Edge], house: Polygon, accessories: list[Polygon],
                 zone_rule: dict, run: dict) -> list[Polygon]:
    """Pieces of the parcel where a detached ADU may sit, largest first; pieces < 1 sq ft dropped."""
    pocket = setback_envelope(parcel, edges, zone_rule["setbacks_ft"])
    pocket = front_yard_exclusion(pocket, edges, house, zone_rule)
    cut = [house.buffer(run["separation_ft"])]
    cut += [a for a in accessories if a.area >= run["shed_ignore_sqft"]]
    pocket = pocket.difference(unary_union(cut))
    if not pocket.is_valid:
        pocket = shapely.make_valid(pocket)
    pieces = [p for p in _polygons(pocket) if p.area >= MIN_PIECE_SQFT]
    return sorted(pieces, key=lambda p: p.area, reverse=True)


def remaining_coverage(lot_area_sqft: float, coverage_cap: float, footprint_areas: list[float]) -> float:
    """Building-coverage allowance left (sq ft), clamped at 0."""
    return max(0.0, lot_area_sqft * coverage_cap - sum(footprint_areas))
