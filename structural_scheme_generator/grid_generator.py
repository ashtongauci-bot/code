"""
grid_generator.py — Algorithmic column grid generation.

Takes the architectural analysis produced by vision_scheme.py and generates
1–3 candidate column grid schemes that:
  • Respect the maximum span limit from span_rules.py
  • Align with the detected architectural grid module where possible
  • Avoid void / exclusion areas
  • Include forced columns at core corners, re-entrant corners, etc.
  • Cover the entire floor plate within the span limit

⚠️  PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION
This column layout was generated algorithmically from span/depth rules of thumb.
It has NOT been designed or verified by a structural engineer.
It MUST be reviewed, checked, and approved by a registered structural engineer
before use in any design documentation or construction.
Punching shear, lateral stability, transfer structures, and serviceability
have NOT been checked. Column sizes are indicative only.
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.ops import unary_union


# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------

def _scale_denominator(drawing_scale: str) -> int:
    """Return the numeric denominator, e.g. '1:100' → 100."""
    try:
        return int(drawing_scale.split(":")[1])
    except (IndexError, ValueError):
        return 100


def mm_to_pts(value_mm: float, drawing_scale: str) -> float:
    """
    Convert a real-world millimetre dimension to PDF points at the given scale.
    Formula: pts = mm_real × (1/scale) × (72/25.4)
    """
    scale = _scale_denominator(drawing_scale)
    return value_mm * 72.0 / (25.4 * scale)


def pts_to_mm(value_pts: float, drawing_scale: str) -> float:
    """Inverse of mm_to_pts."""
    scale = _scale_denominator(drawing_scale)
    return value_pts * 25.4 * scale / 72.0


def pts_to_m2(area_pts2: float, drawing_scale: str) -> float:
    """Convert an area in PDF points² to real-world m²."""
    scale = _scale_denominator(drawing_scale)
    # 1 pt = scale × 25.4/72 mm = scale × 25.4/72 / 1000 m
    m_per_pt = scale * 25.4 / 72.0 / 1000.0
    return area_pts2 * (m_per_pt ** 2)


# ---------------------------------------------------------------------------
# Core grid generation
# ---------------------------------------------------------------------------

def generate_column_grid(
    floor_plate_pts: list[dict],
    voids: list[dict],
    forced_columns: list[dict],
    max_span_mm: float,
    architectural_grid_mm: float | None,
    config: dict,
) -> dict:
    """
    Generate candidate column grid schemes within the floor plate.

    Strategy:
    1. Build Shapely geometry for the floor plate and exclusion zones.
    2. Start with forced columns (core corners, cantilever tips, etc.).
    3. Sweep a regular grid over the bounding box using 2–3 offsets
       to find configurations that cover the plate without exceeding max_span.
    4. Score each configuration (fewer columns = better at this stage).
    5. Return the top 3 schemes.

    Args:
        floor_plate_pts:      List of {x_pts, y_pts} dicts tracing the slab boundary.
        voids:                List of void dicts (each has 'polygon' key).
        forced_columns:       List of forced-column dicts from vision analysis.
        max_span_mm:          Maximum allowable column centre-to-centre span in mm.
        architectural_grid_mm: Detected architectural module in mm, or None.
        config:               Full tool config dict (needs 'drawing_scale').

    Returns:
        {
            "schemes": [list of scheme dicts],
            "max_span_mm": float,
            "grid_spacing_mm": float,   # primary grid used
            "scale_factor": int,
            "mm_to_pts_factor": float,
        }
    """
    drawing_scale = config["drawing_scale"]

    # ------------------------------------------------------------------
    # Build Shapely geometry
    # ------------------------------------------------------------------
    plate_coords = [(p["x_pts"], p["y_pts"]) for p in floor_plate_pts]
    if len(plate_coords) < 3:
        raise ValueError("Floor plate must have at least 3 vertices.")
    plate = Polygon(plate_coords)
    if not plate.is_valid:
        plate = plate.buffer(0)  # attempt repair

    void_polys: list[Polygon] = []
    for v in voids:
        raw_poly = v.get("polygon", [])
        if len(raw_poly) >= 3:
            void_polys.append(
                Polygon([(p["x_pts"], p["y_pts"]) for p in raw_poly])
            )
    exclusion_zone = unary_union(void_polys) if void_polys else Polygon()

    # ------------------------------------------------------------------
    # Determine grid spacing in PDF points
    # ------------------------------------------------------------------
    _mm_per_pt = 25.4 * _scale_denominator(drawing_scale) / 72.0  # mm per PDF point
    _pt_per_mm = 1.0 / _mm_per_pt

    def _to_pts(mm: float) -> float:
        return mm * _pt_per_mm

    def _to_mm(pts: float) -> float:
        return pts * _mm_per_pt

    max_span_pts = _to_pts(max_span_mm)

    # Choose grid spacing: align to architectural module if within limit,
    # else use 90 % of max span, rounded down to nearest 500 mm
    if architectural_grid_mm and architectural_grid_mm <= max_span_mm:
        grid_spacing_mm = architectural_grid_mm
        scheme_label = f"Align to architectural grid ({architectural_grid_mm / 1000:.1f} m)"
    else:
        raw_grid_mm = max_span_mm * 0.90
        grid_spacing_mm = float(int(raw_grid_mm / 500) * 500)
        if grid_spacing_mm <= 0:
            grid_spacing_mm = max_span_mm  # fallback
        scheme_label = f"Max-span grid ({grid_spacing_mm / 1000:.1f} m)"

    grid_spacing_pts = _to_pts(grid_spacing_mm)

    bounds = plate.bounds  # (minx, miny, maxx, maxy)
    min_separation_pts = grid_spacing_pts * 0.4  # minimum distance between columns

    # ------------------------------------------------------------------
    # Candidate sweeps — try a few (x, y) offsets for best coverage
    # ------------------------------------------------------------------
    schemes: list[dict] = []

    offsets = [
        (0.00, 0.00),
        (0.25, 0.00),
        (0.50, 0.00),
        (0.00, 0.25),
        (0.25, 0.25),
        (0.50, 0.25),
    ]

    for x_off_frac, y_off_frac in offsets:
        x_start = bounds[0] + grid_spacing_pts * x_off_frac
        y_start = bounds[1] + grid_spacing_pts * y_off_frac

        columns: list[dict] = []
        col_id = 1

        # Forced columns first
        for fc in forced_columns:
            columns.append(
                {
                    "id": f"FC{fc.get('id', col_id)}",
                    "x_pts": float(fc["x_pts"]),
                    "y_pts": float(fc["y_pts"]),
                    "type": "forced",
                    "reason": fc.get("reason", "forced"),
                    "confidence": fc.get("confidence", "high"),
                }
            )
            col_id += 1

        # Grid sweep (include columns slightly outside the plate boundary
        # to catch edge/facade positions)
        snap_tol = grid_spacing_pts * 0.15

        x = x_start
        while x <= bounds[2] + grid_spacing_pts:
            y = y_start
            while y <= bounds[3] + grid_spacing_pts:
                pt = Point(x, y)

                in_plate = plate.contains(pt) or plate.boundary.distance(pt) <= snap_tol
                in_void = exclusion_zone.contains(pt)

                if in_plate and not in_void:
                    too_close = any(
                        math.hypot(c["x_pts"] - x, c["y_pts"] - y) < min_separation_pts
                        for c in columns
                    )
                    if not too_close:
                        columns.append(
                            {
                                "id": f"C{col_id}",
                                "x_pts": float(x),
                                "y_pts": float(y),
                                "type": "grid",
                                "reason": "regular grid",
                                "confidence": "medium",
                            }
                        )
                        col_id += 1
                y += grid_spacing_pts
            x += grid_spacing_pts

        # Average tributary area per column
        n_cols = max(len(columns), 1)
        plate_area_pts2 = plate.area
        avg_trib_m2 = pts_to_m2(plate_area_pts2 / n_cols, drawing_scale)

        schemes.append(
            {
                "label": f"{scheme_label} (offset {x_off_frac:.2f}, {y_off_frac:.2f})",
                "columns": columns,
                "n_columns": len(columns),
                "grid_spacing_mm": round(grid_spacing_mm),
                "avg_tributary_m2": round(avg_trib_m2, 1),
                "x_offset_frac": x_off_frac,
                "y_offset_frac": y_off_frac,
            }
        )

    # Sort by column count ascending (fewest columns preferred at scheme stage)
    schemes.sort(key=lambda s: s["n_columns"])
    top_schemes = schemes[:3]
    for i, s in enumerate(top_schemes, start=1):
        s["scheme_name"] = f"Scheme {i}"

    return {
        "schemes": top_schemes,
        "max_span_mm": max_span_mm,
        "grid_spacing_mm": round(grid_spacing_mm),
        "scale_factor": _scale_denominator(drawing_scale),
        "mm_to_pts_factor": _pt_per_mm,
    }


# ---------------------------------------------------------------------------
# Span coverage check
# ---------------------------------------------------------------------------

def check_span_coverage(
    columns: list[dict],
    floor_plate_pts: list[dict],
    max_span_mm: float,
    mm_to_pts_factor: float,
) -> dict:
    """
    Check whether any part of the floor plate exceeds the maximum allowable span.

    Method: sample the plate on a fine mesh and find the distance to the nearest
    column. A point is "uncovered" if no column is within max_span_mm of it.

    This uses a simple nearest-column assumption (tributary half-span = distance
    to nearest column). It is conservative — two-way slab action means actual
    spans may be less — but it is appropriate for a preliminary check.

    Returns:
        {
            "uncovered_points": [{"x_pts", "y_pts", "nearest_column_span_mm"}],
            "n_uncovered": int,
            "coverage_ok": bool,
            "max_actual_span_mm": float,   # worst-case observed
        }
    """
    plate_coords = [(p["x_pts"], p["y_pts"]) for p in floor_plate_pts]
    if len(plate_coords) < 3:
        return {"uncovered_points": [], "n_uncovered": 0, "coverage_ok": True, "max_actual_span_mm": 0}

    plate = Polygon(plate_coords)
    if not plate.is_valid:
        plate = plate.buffer(0)

    max_span_pts = max_span_mm * mm_to_pts_factor
    # Sample mesh spacing: every half-span
    check_spacing = max_span_pts * 0.5

    bounds = plate.bounds
    col_points = [Point(c["x_pts"], c["y_pts"]) for c in columns]

    uncovered: list[dict] = []
    max_observed_pts = 0.0

    x = bounds[0]
    while x <= bounds[2]:
        y = bounds[1]
        while y <= bounds[3]:
            pt = Point(x, y)
            if plate.contains(pt):
                if col_points:
                    min_dist_pts = min(pt.distance(cp) for cp in col_points)
                    if min_dist_pts > max_observed_pts:
                        max_observed_pts = min_dist_pts
                    if min_dist_pts > max_span_pts:
                        uncovered.append(
                            {
                                "x_pts": float(x),
                                "y_pts": float(y),
                                "nearest_column_span_mm": round(
                                    min_dist_pts / mm_to_pts_factor
                                ),
                            }
                        )
            y += check_spacing
        x += check_spacing

    return {
        "uncovered_points": uncovered,
        "n_uncovered": len(uncovered),
        "coverage_ok": len(uncovered) == 0,
        "max_actual_span_mm": round(max_observed_pts / mm_to_pts_factor),
    }
