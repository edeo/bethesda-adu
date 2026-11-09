"""Largest rectangle that fits in a pocket, the lot axis, and the ADU floor-area cap.

Geometry is in the pocket's CRS (EPSG:2248, feet). The rectangle search rasterizes the
pocket on a grid aligned to each trial angle and runs the maximal-rectangle
histogram/stack algorithm, keeping the largest rectangle whose sides both reach
`min_dim_ft`.
"""
from __future__ import annotations

import math

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import Polygon, box

_EDGE_EPS = 1e-6  # keep cells whose centers sit exactly on the shrunk boundary


def _best_in_grid(grid: np.ndarray, min_cells: int) -> tuple[float, int, int, int, int] | None:
    """Largest all-True rectangle with both sides >= min_cells.

    Returns (area, bottom_row, left_col, width, height) in cells, or None. Every maximal
    rectangle is popped from the stack once per row it bottoms out on, so the constrained
    optimum (which can always be grown into a maximal rectangle) is among the candidates.
    """
    rows, cols = grid.shape
    heights = np.zeros(cols, dtype=np.int64)
    best = None
    best_area = 0
    for r in range(rows):
        heights = np.where(grid[r], heights + 1, 0)
        if heights.max(initial=0) < min_cells:
            continue
        h = heights.tolist()
        h.append(0)
        stack: list[tuple[int, int]] = []  # (start col, height)
        for j, hj in enumerate(h):
            start = j
            while stack and stack[-1][1] >= hj:
                s, hh = stack.pop()
                w = j - s
                if hh >= min_cells and w >= min_cells and hh * w > best_area:
                    best_area = hh * w
                    best = (best_area, r, s, w, hh)
                start = s
            if hj > 0:
                stack.append((start, hj))
    return best


def largest_rectangle(pocket: Polygon, axis_deg: float, rotations_deg: list[float], min_dim_ft: float,
                      grid_ft: float = 1.0) -> tuple[Polygon, float, float] | None:
    """(rectangle in original coords, width, length) of the largest rectangle with both sides
    >= `min_dim_ft`, tried at `axis_deg + r` for each r in `rotations_deg`; None if none fits.

    Width is the shorter side. Sides are multiples of `grid_ft`.
    """
    if pocket is None or pocket.is_empty:
        return None
    g = float(grid_ft)
    min_cells = math.ceil(min_dim_ft / g - 1e-9)
    origin = pocket.centroid
    best = None  # (area, angle, x0, y0, x1, y1) in rotated frame
    for r in rotations_deg:
        angle = axis_deg + r
        rot = affinity.rotate(pocket, -angle, origin=origin)
        shrunk = rot.buffer(-(g / 2 - _EDGE_EPS), join_style="mitre")
        if shrunk.is_empty:
            continue
        bx0, by0, bx1, by1 = rot.bounds
        ncols = int(math.floor((bx1 - bx0) / g + 1e-9))
        nrows = int(math.floor((by1 - by0) / g + 1e-9))
        if ncols < min_cells or nrows < min_cells:
            continue
        xs = bx0 + g / 2 + g * np.arange(ncols)
        ys = by0 + g / 2 + g * np.arange(nrows)
        X, Y = np.meshgrid(xs, ys)
        shapely.prepare(shrunk)
        grid = shapely.contains_xy(shrunk, X, Y)
        found = _best_in_grid(grid, min_cells)
        if found is None:
            continue
        area, row, col, w, h = found
        if best is None or area > best[0]:
            x0 = bx0 + col * g
            y0 = by0 + (row - h + 1) * g
            best = (area, angle, x0, y0, x0 + w * g, y0 + h * g)
    if best is None:
        return None
    _, angle, x0, y0, x1, y1 = best
    poly = affinity.rotate(box(x0, y0, x1, y1), angle, origin=origin)
    a, b = x1 - x0, y1 - y0
    return poly, min(a, b), max(a, b)


def lot_axis_deg(parcel: Polygon) -> float:
    """Bearing (degrees, [0, 180)) of the longer side of the parcel's minimum rotated rectangle."""
    mrr = parcel.minimum_rotated_rectangle
    coords = list(mrr.exterior.coords) if mrr.geom_type == "Polygon" else list(mrr.coords)
    if len(coords) < 2:
        return 0.0
    sides = [(coords[i], coords[i + 1]) for i in range(min(2, len(coords) - 1))]
    (ax, ay), (bx, by) = max(sides, key=lambda s: math.dist(*s))
    return math.degrees(math.atan2(by - ay, bx - ax)) % 180.0


def max_adu_floor_area(living_area_sqft: float, usable_footprint_sqft: float, height_ft: float,
                       story_height_ft: float, max_stories: int, cap_ratio: float) -> float:
    """min(cap_ratio * living area, usable footprint * stories), stories clamped to [1, max_stories]."""
    stories = max(1, min(int(max_stories), math.floor(height_ft / story_height_ft)))
    return min(cap_ratio * living_area_sqft, usable_footprint_sqft * stories)
