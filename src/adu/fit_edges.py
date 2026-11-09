"""Label a lot's boundary edges as front / side_street / side / rear.

Pipeline: simplify the exterior, split it into segments, merge near-collinear consecutive
segments into edges, mark edges that face a street (not hugging a neighbor parcel), group
consecutive street edges into street runs, decide the lot type from the runs (interior,
corner, through, flag), then pick the rear opposite the primary front. Everything else is
`side`. Geometry is in the parcel's CRS (EPSG:2248, feet).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import shapely
from shapely.geometry import GeometryCollection, LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient

EdgeKind = Literal["front", "side_street", "side", "rear"]

SIMPLIFY_FT = 0.5
MERGE_DEG = 10.0  # consecutive segments closer than this in bearing form one edge
NEIGHBOR_TOL_FT = 1.0  # boundary within this of a neighbor parcel is not street-facing
STREET_SHARE = 0.5  # edge is street-facing if more than this share of it is
PARALLEL_DEG = 30.0
RUN_SPLIT_DEG = 50.0  # a street run turning more than this starts a new run (corner)
FLAG_PROBE_FT = 30.0
REAR_TIE_FT = 1.0
NEIGHBOR_PAD_FT = 5.0


@dataclass
class Edge:
    geom: LineString
    kind: EdgeKind


def _dir(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dy, dx))


def _dir_diff(a: float, b: float) -> float:
    """Absolute difference of two directed bearings, in [0, 180]."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _axis_diff(a: float, b: float) -> float:
    """Absolute difference of two undirected bearings, in [0, 90]."""
    d = (a - b) % 180.0
    return min(d, 180.0 - d)


def _chord_dir(pts: list[tuple[float, float]]) -> float:
    return _dir(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])


def _ring_edges(poly: Polygon) -> list[list[tuple[float, float]]]:
    """Exterior (CCW) split into merged near-collinear edges, each a vertex list."""
    simple = poly.simplify(SIMPLIFY_FT, preserve_topology=True)
    if simple.is_empty or not isinstance(simple, Polygon):
        simple = poly
    coords = list(orient(simple, 1.0).exterior.coords)[:-1]
    pts = [coords[0]]
    for c in coords[1:]:
        if math.dist(c, pts[-1]) > 1e-6:
            pts.append(c)
    if len(pts) > 1 and math.dist(pts[0], pts[-1]) <= 1e-6:
        pts.pop()
    n = len(pts)
    seg_dir = [_dir(pts[(i + 1) % n][0] - pts[i][0], pts[(i + 1) % n][1] - pts[i][1]) for i in range(n)]
    # Start at the sharpest vertex so no merged edge wraps around the ring start.
    turns = [_dir_diff(seg_dir[i], seg_dir[i - 1]) for i in range(n)]
    start = max(range(n), key=turns.__getitem__)
    pts = pts[start:] + pts[:start]
    seg_dir = seg_dir[start:] + seg_dir[:start]

    edges: list[list[tuple[float, float]]] = []
    prev = None
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        # Merge when the turn from the previous segment AND the drift from the edge's chord
        # are both small, so gentle arcs break into pieces instead of swallowing a corner.
        if edges and _dir_diff(seg_dir[i], prev) < MERGE_DEG and \
                _dir_diff(seg_dir[i], _chord_dir(edges[-1])) < MERGE_DEG:
            edges[-1].append(b)
        else:
            edges.append([a, b])
        prev = seg_dir[i]
    return edges


def _local_neighbors(parcel: BaseGeometry, neighbors: BaseGeometry) -> BaseGeometry:
    if neighbors is None or neighbors.is_empty:
        return GeometryCollection()
    x0, y0, x1, y1 = parcel.bounds
    p = NEIGHBOR_PAD_FT
    # intersection, not clip_by_rect: clip_by_rect raises on some valid real-world rings
    local = shapely.make_valid(neighbors).intersection(shapely.box(x0 - p, y0 - p, x1 + p, y1 + p))
    # Guard against the parcel itself being part of the neighbor layer.
    return local.difference(parcel)


def _street_runs(lines: list[LineString], street: list[bool]) -> list[list[int]]:
    """Group consecutive (cyclic) street-facing edges; split where the run turns a corner."""
    n = len(lines)
    if not any(street):
        return []
    start = next((i for i in range(n) if street[i] and not street[i - 1]), 0)
    runs: list[list[int]] = []
    cur: list[int] = []
    for k in range(n):
        i = (start + k) % n
        if not street[i]:
            if cur:
                runs.append(cur)
            cur = []
            continue
        if cur:
            run_pts = [lines[cur[0]].coords[0], lines[cur[-1]].coords[-1]]
            if _dir_diff(_chord_dir(list(lines[i].coords)), _chord_dir(run_pts)) >= RUN_SPLIT_DEG:
                runs.append(cur)
                cur = []
        cur.append(i)
    if cur:
        runs.append(cur)
    return runs


def _run_axis(lines: list[LineString], run: list[int]) -> float:
    return _chord_dir([lines[run[0]].coords[0], lines[run[-1]].coords[-1]])


def _run_length(lines: list[LineString], run: list[int]) -> float:
    return sum(lines[i].length for i in run)


def _adjacent(a: list[int], b: list[int], n: int, lines: list[LineString]) -> bool:
    if (a[-1] + 1) % n == b[0] or (b[-1] + 1) % n == a[0]:
        return True
    ga = shapely.union_all([lines[i] for i in a])
    gb = shapely.union_all([lines[i] for i in b])
    return ga.distance(gb) <= NEIGHBOR_TOL_FT


def _cross_section(poly: Polygon, origin: Point, d: tuple[float, float], n: tuple[float, float],
                   depth: float, reach: float) -> LineString | None:
    """Piece of the parcel cut by the line parallel to `d` at `depth` along `n` nearest its center."""
    cx, cy = origin.x + depth * n[0], origin.y + depth * n[1]
    probe = LineString([(cx - reach * d[0], cy - reach * d[1]), (cx + reach * d[0], cy + reach * d[1])])
    cut = poly.intersection(probe)
    parts = [g for g in getattr(cut, "geoms", [cut]) if isinstance(g, LineString) and g.length > 0]
    if not parts:
        return None
    c = Point(cx, cy)
    return min(parts, key=lambda g: g.distance(c))


def _flag_junction(poly: Polygon, lines: list[LineString], run: list[int], max_w: float) -> tuple[LineString, float] | None:
    """If the single street run is a flag-lot pole, return (junction line, junction depth)."""
    if _run_length(lines, run) >= max_w:
        return None
    a, b = lines[run[0]].coords[0], lines[run[-1]].coords[-1]
    length = math.dist(a, b)
    if length <= 0:
        return None
    d = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
    nrm = (-d[1], d[0])  # CCW ring: interior on the left
    origin = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    x0, y0, x1, y1 = poly.bounds
    reach = math.hypot(x1 - x0, y1 - y0) + 1.0

    def width(t: float) -> float:
        s = _cross_section(poly, origin, d, nrm, t, reach)
        return s.length if s is not None else 0.0

    if width(FLAG_PROBE_FT) >= max_w:
        return None
    lo, hi = FLAG_PROBE_FT, None
    t = FLAG_PROBE_FT
    while t < reach:
        t += 1.0
        if width(t) >= max_w:
            hi = t
            break
        lo = t
    if hi is None:
        return None
    while hi - lo > 0.05:
        m = (lo + hi) / 2
        if width(m) >= max_w:
            hi = m
        else:
            lo = m
    depth = hi + 0.25  # just inside the main lot
    junction = _cross_section(poly, origin, d, nrm, depth, reach)
    if junction is None or junction.length < max_w:
        return None
    return junction, depth


def _signed_depth(p: Point, origin: Point, nrm: tuple[float, float]) -> float:
    return (p.x - origin.x) * nrm[0] + (p.y - origin.y) * nrm[1]


def _classify_polygon(poly: Polygon, neighbors: BaseGeometry, corner_lot_front: str,
                      max_w: float) -> tuple[list[Edge], bool]:
    lines = [LineString(e) for e in _ring_edges(poly)]
    n = len(lines)
    kind: list[EdgeKind] = ["side"] * n
    nb = _local_neighbors(poly, neighbors)
    nb_zone = nb.buffer(NEIGHBOR_TOL_FT) if not nb.is_empty else nb
    street = []
    for ln in lines:
        free = ln.difference(nb_zone).length if not nb_zone.is_empty else ln.length
        street.append(free > STREET_SHARE * ln.length)
    runs = _street_runs(lines, street)

    if not runs:
        return [Edge(ln, "side") for ln in lines], True

    odd = len(runs) > 2
    through = False
    extra: list[Edge] = []
    excluded: set[int] = set()  # edges that may not become rear (pole)
    front_geom: BaseGeometry
    front_axis: float

    if len(runs) == 1:
        run = runs[0]
        flag = _flag_junction(poly, lines, run, max_w)
        if flag is None:
            for i in run:
                kind[i] = "front"
            front_geom = shapely.union_all([lines[i] for i in run])
            front_axis = _run_axis(lines, run)
        else:
            junction, depth = flag
            a, b = lines[run[0]].coords[0], lines[run[-1]].coords[-1]
            length = math.dist(a, b)
            nrm = (-(b[1] - a[1]) / length, (b[0] - a[0]) / length)
            origin = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            for i, ln in enumerate(lines):
                if _signed_depth(ln.interpolate(0.5, normalized=True), origin, nrm) < depth:
                    excluded.add(i)  # pole edges (incl. its street frontage) stay `side`
            extra.append(Edge(junction, "front"))
            front_geom = junction
            front_axis = _chord_dir(list(junction.coords))
    else:
        same_side = False
        if len(runs) == 2:
            r1, r2 = runs
            # Directed bearings: on a CCW ring opposite sides run in opposite directions, while
            # a frontage split on the same side (e.g. by a neighbor notch) keeps its direction.
            turn = _dir_diff(_run_axis(lines, r1), _run_axis(lines, r2))
            adjacent = _adjacent(r1, r2, n, lines)
            if turn >= 180.0 - PARALLEL_DEG and not adjacent:
                through = True
            elif turn <= PARALLEL_DEG:
                same_side = True
            elif not adjacent:
                odd = True  # neither a corner nor opposite frontages; corner labels are a best guess
        if through:
            for r in runs:
                for i in r:
                    kind[i] = "front"
        elif same_side:  # one frontage in pieces: all front, primary front is their union
            for r in runs:
                for i in r:
                    kind[i] = "front"
            front_geom = shapely.union_all([lines[i] for i in runs[0] + runs[1]])
            front_axis = _run_axis(lines, max(runs, key=lambda r: _run_length(lines, r)))
        else:
            if len(runs) == 2:
                ordered = sorted(runs, key=lambda r: _run_length(lines, r))
                if corner_lot_front == "shorter":
                    primary = ordered[0]
                elif corner_lot_front == "longer":
                    primary = ordered[1]
                else:
                    raise ValueError(f"corner_lot_front must be 'shorter' or 'longer', got {corner_lot_front!r}")
            else:  # odd shape, best effort: longest run is the front
                primary = max(runs, key=lambda r: _run_length(lines, r))
            for r in runs:
                for i in r:
                    kind[i] = "front" if r is primary else "side_street"
            front_geom = shapely.union_all([lines[i] for i in primary])
            front_axis = _run_axis(lines, primary)

    if not through:
        cands = [i for i in range(n) if kind[i] == "side" and i not in excluded
                 and _axis_diff(_chord_dir(list(lines[i].coords)), front_axis) <= PARALLEL_DEG]
        dist = {i: front_geom.distance(lines[i].interpolate(0.5, normalized=True)) for i in cands}
        if dist:
            far = max(dist.values())
            for i, dv in dist.items():
                if dv >= far - REAR_TIE_FT:
                    kind[i] = "rear"
        else:
            odd = True

    return [Edge(ln, k) for ln, k in zip(lines, kind)] + extra, odd


def _polygon_parts(geom: BaseGeometry) -> list[Polygon]:
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    parts: list[Polygon] = []
    stack = [geom]
    while stack:  # make_valid may return nested collections
        g = stack.pop()
        if isinstance(g, Polygon):
            if g.area > 0:
                parts.append(g)
        elif hasattr(g, "geoms"):
            stack.extend(g.geoms)
    return sorted(parts, key=lambda g: g.area, reverse=True)


def classify_edges(parcel: Polygon, neighbors: BaseGeometry, corner_lot_front: str,
                   flag_pole_max_width_ft: float = 25) -> tuple[list[Edge], bool]:
    """Label the parcel's exterior edges; returns (edges, odd_shape).

    `neighbors` is the union of adjacent parcel geometries (the parcel itself is ignored if
    included). Edges cover the simplified exterior; a flag lot additionally gets its
    pole/main-lot junction line as a `front` Edge (not part of the boundary). Multipart or
    unrepairable parcels are `odd_shape`; the largest part is classified and the other parts'
    edges are returned as `side`.
    """
    parts = _polygon_parts(parcel)
    if not parts:
        return [], True
    main, rest = parts[0], parts[1:]
    edges, odd = _classify_polygon(Polygon(main.exterior), neighbors, corner_lot_front, flag_pole_max_width_ft)
    for p in rest:
        edges += [Edge(LineString(e), "side") for e in _ring_edges(Polygon(p.exterior))]
    return edges, odd or bool(rest)

