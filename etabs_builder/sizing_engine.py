"""
sizing_engine.py — Preliminary sizing of columns and walls.

Based on AS3600:2018 (Australian Standard — Concrete Structures) and
AS/NZS 1170.1:2002 load intensities.

All sizing is VERY PRELIMINARY — axial load only for columns, minimum
thickness for walls. No bending, slenderness, biaxial, or punching shear
checks are performed.

⚠️  PRELIMINARY — must be verified by a registered structural engineer.
"""

from __future__ import annotations

import math
from typing import Optional

from load_definitions import get_loads, uls_load_kpa, CONCRETE_UNIT_WEIGHT_KN_M3

# Concrete density (reinforced)
RHO_KN_M3 = CONCRETE_UNIT_WEIGHT_KN_M3


# ---------------------------------------------------------------------------
# Column sizing
# ---------------------------------------------------------------------------

def size_column_from_load(
    tributary_area_m2: float,
    levels: list[dict],           # [{usage, height_m, slab_thickness_mm}, ...]
    fc_mpa: float = 50.0,
    min_size_mm: float = 400.0,
    rounding_mm: float = 50.0,
) -> dict:
    """
    Preliminary square column size from accumulated ULS axial load.

    Method: For each floor above, compute ULS gravity intensity (kPa) from
    1.2G + 1.5Q (G = slab SW + SDL, Q = LL). Sum over all floors to get N*.
    Size the section using the AS3600 phi·f'c·0.3 rule of thumb.

    Args:
        tributary_area_m2:  Tributary floor area per column (m²).
        levels:             List of level dicts, from top level downward.
                            Each needs keys: 'usage', 'slab_thickness_mm'.
                            Only levels ABOVE the column base are included.
        fc_mpa:             Column concrete strength (MPa).
        min_size_mm:        Minimum column dimension (mm).
        rounding_mm:        Round size to nearest this value (mm).

    Returns dict with: width_mm, depth_mm, N_star_kN, section_label, notes.
    """
    N_star_kN = 0.0
    floor_breakdown = []

    for lv in levels:
        usage = lv.get("usage", "office")
        thk_mm = lv.get("slab_thickness_mm", 250)

        # ULS load intensity for this floor (kPa)
        q_uls = uls_load_kpa(usage, thk_mm)
        contrib_kN = q_uls * tributary_area_m2
        N_star_kN += contrib_kN
        floor_breakdown.append({
            "usage": usage,
            "uls_kpa": round(q_uls, 2),
            "N_contrib_kN": round(contrib_kN, 1),
        })

    # AS3600 S10.1.1 phi·Puo approximation for concentric compression
    # phi = 0.65 (Table 2.2.2), Puo ≈ 0.3·fc'·Ag (ignoring reinforcement contribution
    # which typically adds ~10–15% — kept conservative for preliminary sizing)
    phi = 0.65
    required_area_mm2 = (N_star_kN * 1000.0) / (phi * 0.3 * fc_mpa)

    side_raw = math.sqrt(required_area_mm2)
    side_mm = max(min_size_mm, math.ceil(side_raw / rounding_mm) * rounding_mm)
    label = _col_label(side_mm, side_mm)

    return {
        "width_mm": side_mm,
        "depth_mm": side_mm,
        "shape": "rectangular",
        "N_star_kN": round(N_star_kN, 1),
        "required_area_mm2": round(required_area_mm2),
        "tributary_area_m2": round(tributary_area_m2, 1),
        "n_floors": len(levels),
        "fc_mpa": fc_mpa,
        "section_label": label,
        "floor_breakdown": floor_breakdown,
        "notes": (
            "Axial load only — no bending, slenderness, or biaxial check. "
            f"Min size {min_size_mm:.0f} mm enforced. AS3600 phi·0.3·fc rule."
        ),
    }


def size_column_simple(
    tributary_area_m2: float,
    num_floors: int,
    usage: str,
    slab_thickness_mm: float,
    fc_mpa: float = 50.0,
    min_size_mm: float = 400.0,
) -> dict:
    """Convenience wrapper: uniform floor usage across all floors."""
    levels = [{"usage": usage, "slab_thickness_mm": slab_thickness_mm}] * num_floors
    return size_column_from_load(
        tributary_area_m2, levels, fc_mpa, min_size_mm
    )


def estimate_tributary_area(
    columns_m: list[tuple[float, float]],
    floor_plate_m2: float,
) -> float:
    """Average tributary area per column (m²) = floor plate area / n_columns."""
    n = max(len(columns_m), 1)
    return floor_plate_m2 / n


# ---------------------------------------------------------------------------
# Column section label helpers
# ---------------------------------------------------------------------------

def _col_label(width_mm: float, depth_mm: float, shape: str = "rectangular") -> str:
    w = int(width_mm)
    d = int(depth_mm)
    if shape == "circular":
        return f"COL{w}D"
    if w == d:
        return f"COL{w}x{d}"
    return f"COL{w}x{d}"


def unique_column_sections(
    col_sizes: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Return unique (width, depth) pairs, sorted largest first."""
    seen = set()
    result = []
    for w, d in sorted(col_sizes, key=lambda x: x[0] * x[1], reverse=True):
        key = (round(w), round(d))
        if key not in seen:
            seen.add(key)
            result.append((float(key[0]), float(key[1])))
    return result


# ---------------------------------------------------------------------------
# Wall / core sizing
# ---------------------------------------------------------------------------

def size_core_wall(
    config_thickness_mm: Optional[float],
    wall_type: str = "core",
    num_floors: int = 1,
) -> float:
    """
    Return design wall thickness (mm).

    If the plan provides a thickness (from markup), use it.
    Otherwise, apply minimum rules:
      - Lift/stair cores: 200 mm minimum (AS3600 S11)
      - Shear walls:      200 mm minimum
      - For taller buildings, increase thickness.
    """
    if config_thickness_mm and config_thickness_mm > 0:
        return float(config_thickness_mm)

    # Minimum by type and height
    if wall_type in ("lift", "stair", "core"):
        base_min = 200.0
    else:
        base_min = 200.0

    # Increase for height — add 50 mm per 4 floors above 4
    height_adder = max(0, (num_floors - 4) // 4) * 50.0
    return max(base_min, 200.0 + height_adder)


# ---------------------------------------------------------------------------
# Tributary area estimation from grid
# ---------------------------------------------------------------------------

def voronoi_tributary_areas(
    columns_m: list[tuple[float, float]],
    plate_polygon_m: list[tuple[float, float]],
) -> list[float]:
    """
    Estimate tributary area for each column using Shapely Voronoi tessellation
    clipped to the floor plate.

    Returns a list of areas (m²) in the same order as columns_m.
    If Shapely fails, returns equal shares.
    """
    try:
        from shapely.geometry import MultiPoint, Polygon, Point
        from shapely.ops import voronoi_diagram

        plate = Polygon(plate_polygon_m)
        if not plate.is_valid:
            plate = plate.buffer(0)

        if len(columns_m) < 2:
            return [plate.area] * len(columns_m)

        pts = MultiPoint(columns_m)
        regions = voronoi_diagram(pts, envelope=plate)

        areas = []
        for col_pt in columns_m:
            col = Point(col_pt)
            best_area = 0.0
            for region in regions.geoms:
                if region.contains(col) or region.distance(col) < 1e-6:
                    best_area = region.intersection(plate).area
                    break
            areas.append(round(best_area, 2))

        return areas

    except Exception:
        # Fallback: equal shares
        n = max(len(columns_m), 1)
        try:
            from shapely.geometry import Polygon
            area = Polygon(plate_polygon_m).area
        except Exception:
            area = 0.0
        return [round(area / n, 2)] * len(columns_m)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    result = size_column_simple(36.0, 8, "office", 250, fc_mpa=50)
    print(f"8-floor office, 36 m² trib: {result['section_label']}  N*={result['N_star_kN']} kN")

    result2 = size_column_simple(25.0, 15, "residential", 200, fc_mpa=50)
    print(f"15-floor resi, 25 m² trib:  {result2['section_label']}  N*={result2['N_star_kN']} kN")

    print(f"Wall thickness (lift, 12 floors): {size_core_wall(None, 'lift', 12)} mm")
    print(f"Wall thickness (config=300):      {size_core_wall(300, 'lift', 12)} mm")
