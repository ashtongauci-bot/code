"""
model_builder.py — Assembles an ETABSModel from vision analysis results.

Pipeline:
  1. For each PDF level page, load the vision analysis JSON.
  2. Convert PDF-point coordinates to real-world metres using drawing scale.
  3. Build column instances: use detected sizes or auto-size from tributary load.
  4. Build wall segments: decompose each core polygon into wall panel edges.
  5. Build slab panels: one per level using the floor plate polygon.
  6. Assemble the ETABSModel data structure.

⚠️  PRELIMINARY — all output requires structural engineer review.
"""

from __future__ import annotations

import math
from typing import Optional

from structural_elements import (
    ETABSModel,
    Level,
    ConcreteMaterial,
    ColumnSection,
    WallSection,
    SlabSection,
    ColumnInstance,
    WallSegment,
    SlabPanel,
    LoadPattern,
)
from load_definitions import get_loads, list_usages
from sizing_engine import (
    size_column_simple,
    size_core_wall,
    voronoi_tributary_areas,
    unique_column_sections,
    _col_label,
)
from vision_analyzer import pts_to_m, polygon_pts_to_m


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------

def _mm_per_pt(drawing_scale: str) -> float:
    """Real-world mm per PDF point at the given drawing scale."""
    try:
        scale = int(drawing_scale.split(":")[1])
    except (IndexError, ValueError):
        scale = 100
    return scale * 25.4 / 72.0


def _coord_m(val_pts: float, mpp: float) -> float:
    return val_pts * mpp / 1000.0


def _polygon_m(pts_list: list[dict], mpp: float) -> list[tuple[float, float]]:
    """Convert [{x_pts, y_pts}, ...] list to [(x_m, y_m), ...] tuples."""
    return [(_coord_m(p["x_pts"], mpp), _coord_m(p["y_pts"], mpp)) for p in pts_list]


def _polygon_area_m2(polygon: list[tuple[float, float]]) -> float:
    """Shoelace formula."""
    n = len(polygon)
    if n < 3:
        return 0.0
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return abs(sum(xs[i] * ys[(i+1) % n] - xs[(i+1) % n] * ys[i] for i in range(n))) / 2.0


def _centroid_m(polygon: list[tuple[float, float]]) -> tuple[float, float]:
    if not polygon:
        return (0.0, 0.0)
    return (
        sum(p[0] for p in polygon) / len(polygon),
        sum(p[1] for p in polygon) / len(polygon),
    )


# ---------------------------------------------------------------------------
# Alignment / origin shift
# ---------------------------------------------------------------------------

def _shift_to_origin(
    columns: list[ColumnInstance],
    walls: list[WallSegment],
    slabs: list[SlabPanel],
    ox: float,
    oy: float,
) -> None:
    """Translate all elements so (ox, oy) becomes the model origin (0, 0)."""
    for col in columns:
        col.x_m -= ox
        col.y_m -= oy
    for wall in walls:
        wall.x1_m -= ox
        wall.y1_m -= oy
        wall.x2_m -= ox
        wall.y2_m -= oy
    for slab in slabs:
        slab.polygon_m = [(x - ox, y - oy) for x, y in slab.polygon_m]


# ---------------------------------------------------------------------------
# Column processing
# ---------------------------------------------------------------------------

def _build_columns(
    analyses: dict[int, dict],   # page_index → analysis dict
    levels: list[Level],
    config: dict,
) -> tuple[list[ColumnInstance], list[ColumnSection]]:
    """
    Build ColumnInstance and ColumnSection objects from all vision analyses.

    Strategy:
    - Group levels by page_index (same plan can repeat across many floors).
    - For each unique page, collect detected columns.
    - If the plan provides a size annotation, use it.
    - Otherwise, auto-size from tributary area × floors above.
    """
    struct_cfg = config.get("structural", {})
    fc_col = struct_cfg.get("fc_column_MPa", 50)
    slab_thk = struct_cfg.get("slab_thickness_mm", 250)
    default_size = config.get("columns", {}).get("default_size_mm", 600)
    auto_size = config.get("columns", {}).get("auto_size", True)

    # Map page_index → list of levels that use it
    page_to_levels: dict[int, list[Level]] = {}
    for lv in levels:
        page_to_levels.setdefault(lv.page_index, []).append(lv)

    all_columns: list[ColumnInstance] = []
    all_sections: set[tuple[float, float]] = set()  # (width_mm, depth_mm)

    col_counter = 1

    for page_idx, page_levels in page_to_levels.items():
        analysis = analyses.get(page_idx, {})
        meta = analysis.get("_meta", {})
        mpp = meta.get("mm_per_pt", _mm_per_pt(config.get("drawing_scale", "1:100")))

        raw_cols = analysis.get("columns", [])
        if not raw_cols:
            continue

        # Convert to metres
        col_positions = [
            (_coord_m(c["x_pts"], mpp), _coord_m(c["y_pts"], mpp))
            for c in raw_cols
        ]

        # Floor plate for tributary area estimation
        plate_pts = analysis.get("floor_plate", [])
        plate_poly = _polygon_m(plate_pts, mpp)
        plate_area = _polygon_area_m2(plate_poly)
        n_cols = max(len(col_positions), 1)
        avg_trib = plate_area / n_cols

        # Voronoi tributary areas (per column)
        trib_areas = voronoi_tributary_areas(col_positions, plate_poly)

        # Floors above: all levels that share the same plan page, top→bottom
        floors_info = [
            {"usage": lv.floor_usage, "slab_thickness_mm": slab_thk}
            for lv in page_levels
        ]

        for i, (raw_col, (x_m, y_m)) in enumerate(zip(raw_cols, col_positions)):
            trib_m2 = trib_areas[i] if i < len(trib_areas) else avg_trib

            # Determine section size
            if raw_col.get("width_mm") and raw_col.get("depth_mm"):
                # Use plan-detected size
                w_mm = float(raw_col["width_mm"])
                d_mm = float(raw_col["depth_mm"])
            elif auto_size and len(floors_info) > 0:
                # Auto-size from load
                from sizing_engine import size_column_from_load
                result = size_column_from_load(trib_m2, floors_info, fc_mpa=fc_col)
                w_mm = result["width_mm"]
                d_mm = result["depth_mm"]
            else:
                w_mm = d_mm = default_size

            shape = raw_col.get("shape", "rectangular")
            sec_label = _col_label(w_mm, d_mm, shape)
            all_sections.add((w_mm, d_mm))

            # This column appears on every level that uses this page
            story_names = [lv.name for lv in page_levels]

            all_columns.append(ColumnInstance(
                id=raw_col.get("id", f"C{col_counter}"),
                x_m=x_m,
                y_m=y_m,
                section_label=sec_label,
                story_names=story_names,
                source=raw_col.get("confidence", "medium"),
            ))
            col_counter += 1

    # Build ColumnSection objects
    col_sections: list[ColumnSection] = []
    for w_mm, d_mm in unique_column_sections(list(all_sections)):
        label = _col_label(w_mm, d_mm)
        col_sections.append(ColumnSection(
            label=label,
            width_mm=w_mm,
            depth_mm=d_mm,
            material=f"{int(fc_col)}MPa",
        ))

    return all_columns, col_sections


# ---------------------------------------------------------------------------
# Wall processing
# ---------------------------------------------------------------------------

def _build_walls(
    analyses: dict[int, dict],
    levels: list[Level],
    config: dict,
) -> tuple[list[WallSegment], list[WallSection]]:
    """
    Build WallSegment objects from core wall detections.
    Each edge of a core polygon becomes one wall panel per story.
    """
    wall_thk_default = config.get("walls", {}).get("default_thickness_mm", 250)
    fc_wall = config.get("structural", {}).get("fc_wall_MPa", 40)
    n_floors = len(levels)

    page_to_levels: dict[int, list[Level]] = {}
    for lv in levels:
        page_to_levels.setdefault(lv.page_index, []).append(lv)

    all_walls: list[WallSegment] = []
    wall_thicknesses: set[float] = set()
    wall_counter = 1

    for page_idx, page_levels in page_to_levels.items():
        analysis = analyses.get(page_idx, {})
        meta = analysis.get("_meta", {})
        mpp = meta.get("mm_per_pt", _mm_per_pt(config.get("drawing_scale", "1:100")))

        cores = analysis.get("core_walls", [])

        for core in cores:
            core_id = core.get("id", f"CORE{wall_counter}")
            wall_type = core.get("type", "core")

            # Use detected wall segments if available, else decompose polygon
            segments = core.get("wall_segments", [])
            if segments:
                raw_segs = [
                    {
                        "x1": s["x1_pts"], "y1": s["y1_pts"],
                        "x2": s["x2_pts"], "y2": s["y2_pts"],
                        "thickness_mm": s.get("thickness_mm", wall_thk_default),
                    }
                    for s in segments
                ]
            else:
                # Decompose outer polygon edges
                poly_raw = core.get("outer_polygon", [])
                poly_m = _polygon_m(poly_raw, mpp)
                raw_segs = []
                for j in range(len(poly_m)):
                    x1, y1 = poly_m[j]
                    x2, y2 = poly_m[(j + 1) % len(poly_m)]
                    # Skip degenerate edges
                    if math.hypot(x2 - x1, y2 - y1) < 0.05:
                        continue
                    raw_segs.append({
                        "x1": x1 * 1000.0 / mpp * mpp,  # already in pts, convert back
                        "y1": y1 * 1000.0 / mpp * mpp,
                        "x2": x2 * 1000.0 / mpp * mpp,
                        "y2": y2 * 1000.0 / mpp * mpp,
                        "thickness_mm": wall_thk_default,
                        "_already_m": True,
                        "x1_m": x1, "y1_m": y1, "x2_m": x2, "y2_m": y2,
                    })

            for seg_idx, seg in enumerate(raw_segs):
                # Get coordinates in metres
                if seg.get("_already_m"):
                    x1_m, y1_m = seg["x1_m"], seg["y1_m"]
                    x2_m, y2_m = seg["x2_m"], seg["y2_m"]
                else:
                    x1_m = _coord_m(seg["x1"], mpp)
                    y1_m = _coord_m(seg["y1"], mpp)
                    x2_m = _coord_m(seg["x2"], mpp)
                    y2_m = _coord_m(seg["y2"], mpp)

                thk = size_core_wall(
                    seg.get("thickness_mm") or wall_thk_default,
                    wall_type, n_floors
                )
                wall_thicknesses.add(thk)
                sec_label = f"WALL{int(thk)}"

                # One wall panel per level
                for lv in page_levels:
                    wall_id = f"{core_id}_W{seg_idx + 1}_{lv.name.replace(' ', '_')}"
                    all_walls.append(WallSegment(
                        id=wall_id,
                        story_name=lv.name,
                        x1_m=x1_m, y1_m=y1_m,
                        x2_m=x2_m, y2_m=y2_m,
                        section_label=sec_label,
                        wall_type=wall_type,
                    ))
            wall_counter += 1

    # Build WallSection objects
    fc_label = f"{int(fc_wall)}MPa"
    wall_sections = [
        WallSection(label=f"WALL{int(thk)}", thickness_mm=thk, material=fc_label)
        for thk in sorted(wall_thicknesses)
    ]
    if not wall_sections:
        # Ensure at least one default section exists
        default_thk = float(wall_thk_default)
        wall_sections = [WallSection(
            label=f"WALL{int(default_thk)}",
            thickness_mm=default_thk,
            material=fc_label,
        )]

    return all_walls, wall_sections


# ---------------------------------------------------------------------------
# Slab processing
# ---------------------------------------------------------------------------

def _build_slabs(
    analyses: dict[int, dict],
    levels: list[Level],
    config: dict,
) -> tuple[list[SlabPanel], list[SlabSection]]:
    """Build one slab panel per level using the floor plate polygon."""
    slab_thk = config.get("structural", {}).get("slab_thickness_mm", 250)
    fc_slab = config.get("structural", {}).get("fc_slab_MPa", 32)
    fc_label = f"{int(fc_slab)}MPa"
    sec_label = f"SLAB{int(slab_thk)}"

    page_to_levels: dict[int, list[Level]] = {}
    for lv in levels:
        page_to_levels.setdefault(lv.page_index, []).append(lv)

    all_slabs: list[SlabPanel] = []
    slab_counter = 1

    for page_idx, page_levels in page_to_levels.items():
        analysis = analyses.get(page_idx, {})
        meta = analysis.get("_meta", {})
        mpp = meta.get("mm_per_pt", _mm_per_pt(config.get("drawing_scale", "1:100")))

        plate_pts = analysis.get("floor_plate", [])
        if not plate_pts:
            continue
        plate_poly = _polygon_m(plate_pts, mpp)

        for lv in page_levels:
            all_slabs.append(SlabPanel(
                id=f"SLAB_{lv.name.replace(' ', '_')}_{slab_counter}",
                story_name=lv.name,
                polygon_m=plate_poly,
                section_label=sec_label,
                floor_usage=lv.floor_usage,
            ))
            slab_counter += 1

    slab_section = SlabSection(
        label=sec_label,
        thickness_mm=float(slab_thk),
        material=fc_label,
    )
    return all_slabs, [slab_section]


# ---------------------------------------------------------------------------
# Materials builder
# ---------------------------------------------------------------------------

def _build_materials(config: dict) -> list[ConcreteMaterial]:
    struct = config.get("structural", {})
    fc_col  = struct.get("fc_column_MPa", 50)
    fc_wall = struct.get("fc_wall_MPa", 40)
    fc_slab = struct.get("fc_slab_MPa", 32)

    unique_fc = {fc_col, fc_wall, fc_slab}
    mats = []
    for fc in sorted(unique_fc, reverse=True):
        label = f"{int(fc)}MPa"
        mats.append(ConcreteMaterial(label=label, fc_mpa=float(fc)))
    return mats


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_model(
    analyses: dict[int, dict],
    config: dict,
) -> ETABSModel:
    """
    Assemble an ETABSModel from vision analyses and configuration.

    Args:
        analyses:  Dict mapping page_index → vision analysis dict.
        config:    Full tool configuration dict (see config.json).

    Returns:
        A fully populated ETABSModel ready for ETABS API script or E2K export.
    """
    project = config.get("project", {})
    project_name = project.get("name", "ETABSModel")
    base_rl = float(project.get("base_rl_m", 0.0))

    # Build Level objects
    levels: list[Level] = []
    current_rl = base_rl
    for lv_cfg in config.get("levels", []):
        h = float(lv_cfg.get("floor_to_floor_height_m", 3.6))
        current_rl += h
        levels.append(Level(
            name=lv_cfg.get("name", f"Level{len(levels)+1}"),
            rl_m=round(current_rl, 4),
            height_m=h,
            floor_usage=lv_cfg.get("floor_usage", "office"),
            page_index=int(lv_cfg.get("page_index", 0)),
        ))

    # Build structural elements
    materials = _build_materials(config)
    columns, col_sections = _build_columns(analyses, levels, config)
    walls, wall_sections = _build_walls(analyses, levels, config)
    slabs, slab_sections = _build_slabs(analyses, levels, config)

    # Shift model origin to centroid of floor plate (first analysis)
    first_analysis = next(iter(analyses.values()), {})
    meta = first_analysis.get("_meta", {})
    mpp = meta.get("mm_per_pt", _mm_per_pt(config.get("drawing_scale", "1:100")))
    plate_pts = first_analysis.get("floor_plate", [])
    if plate_pts:
        plate_poly = _polygon_m(plate_pts, mpp)
        cx, cy = _centroid_m(plate_poly)
    else:
        cx, cy = 0.0, 0.0

    _shift_to_origin(columns, walls, slabs, cx, cy)

    # Standard load patterns
    usages = sorted({lv.floor_usage for lv in levels})
    load_patterns = [LoadPattern("Dead", "Dead", self_weight_mult=1.0)]
    for usage in usages:
        load_patterns.append(LoadPattern(f"SDL_{usage}", "Super Dead"))
        load_patterns.append(LoadPattern(f"Live_{usage}", "Live"))

    return ETABSModel(
        project_name=project_name,
        base_rl_m=base_rl,
        levels=levels,
        materials=materials,
        column_sections=col_sections,
        wall_sections=wall_sections,
        slab_sections=slab_sections,
        columns=columns,
        walls=walls,
        slabs=slabs,
        load_patterns=load_patterns,
    )
