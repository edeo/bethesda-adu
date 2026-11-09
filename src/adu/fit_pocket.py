"""Buildable pocket (where a detached ADU may legally sit) and remaining lot coverage.

The pocket is the parcel minus each edge's setback strip, minus the yards the zone's
placement rules forbid (front yard / area in front of the house's rear wall / street side
of the house), minus the house separation buffer and existing accessory buildings.
Geometry is in the parcel's CRS (EPSG:2248, feet). Rule values come from the zone dict.
"""
from __future__ import annotations

import math

import shapely
from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from adu.fit_edges import Edge

MIN_PIECE_SQFT = 1.0
SAME_SIDE_MAX_DEG = 90.0  # front pieces whose house-ward normals differ less than this share a frontage


def setback_envelope(parcel: Polygon, edges: list[Edge], setbacks_ft: dict[str, float]) -> BaseGeometry:
    """Parcel minus a flat-capped buffer of each edge by its kind's setback (KeyError if absent)."""
    strips = [e.geom.buffer(setbacks_ft[e.kind], cap_style="flat") for e in edges if setbacks_ft[e.kind] > 0]
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


def _frontages(edges: list[Edge], house: Polygon) -> list[list[int]]:
    """Group `front` edge indices into frontages: pieces facing the same way are one frontage."""
    groups: list[tuple[tuple[float, float], list[int]]] = []
    for i, e in enumerate(edges):
        if e.kind != "front":
            continue
        n = _house_normal(e, house)
        for gn, idx in groups:
            dot = max(-1.0, min(1.0, n[0] * gn[0] + n[1] * gn[1]))
            if math.degrees(math.acos(dot)) < SAME_SIDE_MAX_DEG:
                idx.append(i)
                break
        else:
            groups.append((n, [i]))
    return [idx for _, idx in groups]


def _max_distance(line: BaseGeometry, house: Polygon) -> float:
    return max(line.distance(Point(c)) for c in house.exterior.coords)


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

    The flat buffer is two-sided; its outer half lies outside the parcel (and so outside
    the envelope) for boundary edges, so subtracting it equals removing the parcel side.
    """
    strips = [e.geom.buffer(w, cap_style="flat") for e, w in zip(edges, exclusion_widths(edges, house, zone_rule))
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
