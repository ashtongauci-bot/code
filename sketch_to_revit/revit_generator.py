"""
revit_generator.py — Generate a pyRevit Python script from sketch analysis data.

Takes the structured JSON from sketch_analyzer.py and writes a self-contained
Python script that runs inside Revit via pyRevit or Revit Python Shell to create:
  • Structural columns at each grid intersection on every floor
  • Structural beams connecting adjacent columns on every floor
  • Structural floor slabs at each level

⚠️  PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION
All output must be reviewed by a registered structural engineer.
"""

from __future__ import annotations

import math
from pathlib import Path


# ---------------------------------------------------------------------------
# pyRevit script template
# Placeholders: {scheme_name}, {column_rows}, {beam_rows}, {slab_rows},
#               {levels_data}, {n_columns}, {n_beams}, {n_slabs},
#               {grid_info}, {warnings_list}
# ---------------------------------------------------------------------------

_REVIT_TEMPLATE = '''\
"""
Revit Structural Model — {scheme_name}
Generated from hand-drawn sketch by sketch_to_revit tool.

HOW TO RUN IN REVIT:
  1. Open Revit with a structural or architectural project template.
  2. Ensure at least one Level exists in the project (e.g. "Level 1").
  3. Load families if not already present:
       Structural Columns: Insert > Load Family > Structural > Columns > Concrete
       Structural Framing: Insert > Load Family > Structural > Framing > Concrete
  4. Open pyRevit Shell:  pyRevit tab > pyRevit Shell
     OR open Revit Python Shell if installed.
  5. Open this file in the shell and click Run (or paste and execute).

WHAT THIS SCRIPT CREATES:
  • {n_columns} structural columns
  • {n_beams} structural beams
  • {n_slabs} floor slab(s)
  Grid: {grid_info}

WARNINGS FROM SKETCH ANALYSIS:
{warnings_comment}

⚠  PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION
This model was generated algorithmically from a hand-drawn sketch.
It has NOT been designed or verified by a structural engineer.
It MUST be reviewed and approved by a registered structural engineer
before use in any design documentation or construction.
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilySymbol, Level, Line,
    Transaction, XYZ, CurveLoop, CurveArray, Floor, FloorType,
    BuiltInCategory, ElementId
)
from Autodesk.Revit.DB.Structure import StructuralType

try:
    doc = __revit__.ActiveUIDocument.Document
except NameError:
    raise RuntimeError(
        "Run this script inside pyRevit Shell or Revit Python Shell."
    )

MM_TO_FT = 1.0 / 304.8

# ---------------------------------------------------------------------------
# Structural data (extracted from sketch)
# ---------------------------------------------------------------------------

# Columns: (id, x_m, y_m, width_mm, depth_mm)
# x_m, y_m are real-world metres from the sketch origin (bottom-left corner).
COLUMNS = [
{column_rows}]

# Beams: (id, from_col_id, to_col_id, width_mm, depth_mm)
BEAMS = [
{beam_rows}]

# Slabs: (id, floor_index, thickness_mm, [(x_m, y_m), ...boundary points])
SLABS = [
{slab_rows}]

# Levels: list of (level_name, elevation_m)
# These are target elevations — the script matches them to Revit levels by proximity.
LEVELS = [
{levels_data}]

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def m_to_xyz(x_m, y_m, z_m=0.0):
    return XYZ(x_m * 3.28084, y_m * 3.28084, z_m * 3.28084)


def find_symbol(doc, category_bic, preferred_keywords=None):
    """Return the best-matching FamilySymbol for the given category."""
    preferred_keywords = preferred_keywords or []
    symbols = list(
        FilteredElementCollector(doc)
        .OfCategory(category_bic)
        .OfClass(FamilySymbol)
    )
    if not symbols:
        return None
    for kw in preferred_keywords:
        for sym in symbols:
            name = (sym.Family.Name + " " + sym.Name).lower()
            if kw.lower() in name:
                return sym
    return symbols[0]


def activate(doc, sym):
    if sym and not sym.IsActive:
        sym.Activate()
        doc.Regenerate()


def nearest_level(doc, elevation_m):
    """Return the Revit Level closest to the given elevation (metres)."""
    elevation_ft = elevation_m * 3.28084
    levels = list(FilteredElementCollector(doc).OfClass(Level).ToElements())
    if not levels:
        return None
    return min(levels, key=lambda lv: abs(lv.Elevation - elevation_ft))


def col_positions(columns):
    """Return dict: col_id -> (x_m, y_m) for beam endpoint lookups."""
    return {{col_id: (x_m, y_m) for col_id, x_m, y_m, _w, _d in columns}}


# ---------------------------------------------------------------------------
# Creation logic
# ---------------------------------------------------------------------------

def create_model(doc):
    col_sym  = find_symbol(doc, BuiltInCategory.OST_StructuralColumns,
                           ["concrete", "rect", "square", "rcc"])
    beam_sym = find_symbol(doc, BuiltInCategory.OST_StructuralFraming,
                           ["concrete", "rect", "rcc", "beam"])
    floor_types = list(FilteredElementCollector(doc).OfClass(FloorType).ToElements())
    floor_type  = floor_types[0] if floor_types else None

    missing = []
    if col_sym  is None: missing.append("Structural Column family  (Insert > Load Family > Structural > Columns)")
    if beam_sym is None: missing.append("Structural Framing family (Insert > Load Family > Structural > Framing > Concrete)")
    if not floor_types:  missing.append("Floor type in project (need at least one)")
    if missing:
        print("\\nERROR — load these families first, then re-run:")
        for m in missing:
            print(f"  • {{m}}")
        return

    print(f"Column family : {{col_sym.Family.Name}} / {{col_sym.Name}}")
    print(f"Beam family   : {{beam_sym.Family.Name}} / {{beam_sym.Name}}")
    print(f"Floor type    : {{floor_type.Name}}")

    activate(doc, col_sym)
    activate(doc, beam_sym)

    col_pos = col_positions(COLUMNS)
    stats = {{"cols": 0, "beams": 0, "slabs": 0, "errors": []}}

    with Transaction(doc, "Sketch-to-Revit: Create Structural Model") as t:
        t.Start()

        # ---- Columns (placed at every level) ----------------------------
        for lv_name, lv_elev_m in LEVELS:
            revit_level = nearest_level(doc, lv_elev_m)
            if revit_level is None:
                stats["errors"].append(f"No level found near {{lv_elev_m:.1f}} m")
                continue
            for col_id, x_m, y_m, w_mm, d_mm in COLUMNS:
                try:
                    loc = m_to_xyz(x_m, y_m, lv_elev_m)
                    inst = doc.Create.NewFamilyInstance(
                        loc, col_sym, revit_level, StructuralType.Column
                    )
                    # Try to set section size parameters
                    for pw, pv in [("b", w_mm), ("h", d_mm),
                                   ("Width", w_mm), ("Depth", d_mm),
                                   ("b1", w_mm), ("b2", d_mm)]:
                        p = inst.LookupParameter(pw)
                        if p and not p.IsReadOnly:
                            p.Set(pv * MM_TO_FT)
                            break
                    stats["cols"] += 1
                except Exception as ex:
                    stats["errors"].append(f"Column {{col_id}} @ {{lv_name}}: {{ex}}")

        # ---- Beams (placed at each level) --------------------------------
        for lv_name, lv_elev_m in LEVELS:
            revit_level = nearest_level(doc, lv_elev_m)
            if revit_level is None:
                continue
            for bm_id, from_id, to_id, w_mm, d_mm in BEAMS:
                if from_id not in col_pos or to_id not in col_pos:
                    stats["errors"].append(f"Beam {{bm_id}}: unknown column id")
                    continue
                try:
                    sx, sy = col_pos[from_id]
                    ex, ey = col_pos[to_id]
                    sp = m_to_xyz(sx, sy, lv_elev_m)
                    ep = m_to_xyz(ex, ey, lv_elev_m)
                    if sp.DistanceTo(ep) < 0.01:
                        continue
                    curve = Line.CreateBound(sp, ep)
                    inst = doc.Create.NewFamilyInstance(
                        curve, beam_sym, revit_level, StructuralType.Beam
                    )
                    for pw, pv in [("b", w_mm), ("h", d_mm),
                                   ("Width", w_mm), ("Depth", d_mm)]:
                        p = inst.LookupParameter(pw)
                        if p and not p.IsReadOnly:
                            p.Set(pv * MM_TO_FT)
                            break
                    stats["beams"] += 1
                except Exception as ex:
                    stats["errors"].append(f"Beam {{bm_id}} @ {{lv_name}}: {{ex}}")

        # ---- Slabs -------------------------------------------------------
        for sl_id, floor_idx, thickness_mm, boundary_pts in SLABS:
            lv_name, lv_elev_m = LEVELS[floor_idx] if floor_idx < len(LEVELS) else LEVELS[0]
            revit_level = nearest_level(doc, lv_elev_m)
            if revit_level is None or len(boundary_pts) < 3:
                continue
            try:
                pts = [m_to_xyz(x, y) for x, y in boundary_pts]
                curve_loop = CurveLoop()
                for i in range(len(pts)):
                    p1, p2 = pts[i], pts[(i + 1) % len(pts)]
                    if p1.DistanceTo(p2) > 0.001:
                        curve_loop.Append(Line.CreateBound(p1, p2))
                try:
                    Floor.Create(doc, [curve_loop], floor_type.Id, revit_level.Id)
                except (AttributeError, TypeError):
                    ca = CurveArray()
                    for crv in curve_loop:
                        ca.Append(crv)
                    doc.Create.NewFloor(ca, floor_type, revit_level, True)
                stats["slabs"] += 1
            except Exception as ex:
                stats["errors"].append(f"Slab {{sl_id}}: {{ex}}")

        t.Commit()

    print()
    print("=" * 55)
    print("MODEL CREATED")
    print(f"  Columns: {{stats[\'cols\']}}")
    print(f"  Beams  : {{stats[\'beams\']}}")
    print(f"  Slabs  : {{stats[\'slabs\']}}")
    if stats["errors"]:
        print(f"  Errors : {{len(stats[\'errors\'])}}")
        for e in stats["errors"][:10]:
            print(f"    • {{e}}")
    print()
    print("NEXT STEPS — engineer review required:")
    print("  1. Check all column and beam positions in 3D view")
    print("  2. Resize sections in Properties panel as needed")
    print("  3. Verify slab boundaries and thickness")
    print("  4. Run structural analysis before any construction use")
    print()
    print("⚠  PRELIMINARY SCHEME — NOT ENGINEERED — NOT FOR CONSTRUCTION")
    print("=" * 55)


create_model(doc)
'''


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_revit_script(analysis: dict, output_path: str | None = None) -> str:
    """
    Generate a pyRevit Python script from a sketch analysis dict.

    Args:
        analysis:    Parsed dict from sketch_analyzer.analyse_sketch().
        output_path: Where to write the .py file. Defaults to output/model_revit.py.

    Returns:
        Path to the written script.
    """
    out = Path(output_path) if output_path else Path("output") / "model_revit.py"
    out.parent.mkdir(parents=True, exist_ok=True)

    num_floors = analysis.get("num_floors", 1)
    ftf_m = analysis.get("floor_to_floor_height_m", 3.5)
    columns = analysis.get("columns", [])
    beams = analysis.get("beams", [])
    slabs = analysis.get("slabs", [])
    grid = analysis.get("grid", {})
    warnings = analysis.get("warnings", [])

    # ── Column rows ────────────────────────────────────────────────────────
    col_rows = []
    for col in columns:
        col_id = col["id"]
        x = col.get("x_m", 0.0)
        y = col.get("y_m", 0.0)
        w = col.get("section_width_mm", 500)
        d = col.get("section_depth_mm", 500)
        col_rows.append(f'    ("{col_id}", {x:.3f}, {y:.3f}, {w}, {d}),')

    # ── Beam rows ──────────────────────────────────────────────────────────
    beam_rows = []
    for bm in beams:
        bm_id = bm["id"]
        frm = bm.get("from_col", "")
        to = bm.get("to_col", "")
        w = bm.get("width_mm", 400)
        d = bm.get("depth_mm", 600)
        beam_rows.append(f'    ("{bm_id}", "{frm}", "{to}", {w}, {d}),')

    # ── Slab rows ──────────────────────────────────────────────────────────
    # Build a col_id → (x_m, y_m) lookup for slab boundary resolution
    col_pos_map = {c["id"]: (c.get("x_m", 0.0), c.get("y_m", 0.0)) for c in columns}
    slab_rows = []
    for sl in slabs:
        sl_id = sl["id"]
        fl_idx = sl.get("floor", 1) - 1  # convert 1-based floor to 0-based index
        fl_idx = max(0, min(fl_idx, num_floors - 1))
        thick = sl.get("thickness_mm", 250)
        boundary_col_ids = sl.get("boundary_cols", [])
        boundary_pts = []
        for cid in boundary_col_ids:
            if cid in col_pos_map:
                boundary_pts.append(col_pos_map[cid])
        pts_str = ", ".join(f"({x:.3f}, {y:.3f})" for x, y in boundary_pts)
        slab_rows.append(f'    ("{sl_id}", {fl_idx}, {thick}, [{pts_str}]),')

    # ── Level rows ─────────────────────────────────────────────────────────
    level_rows = []
    for i in range(num_floors):
        elev_m = round(i * ftf_m, 3)
        name = f"Level {i + 1}"
        level_rows.append(f'    ("{name}", {elev_m}),')

    # ── Grid info string ───────────────────────────────────────────────────
    x_labels = grid.get("x_labels", [])
    y_labels = grid.get("y_labels", [])
    x_sp = grid.get("x_spacing_m", [])
    grid_info = (
        f"{len(x_labels)}×{len(y_labels)} grid, "
        f"bays {x_sp[0]:.1f}m" if x_sp else "grid from sketch"
    )

    # ── Warnings comment block ─────────────────────────────────────────────
    if warnings:
        warnings_comment = "\n".join(f"#   • {w}" for w in warnings)
    else:
        warnings_comment = "#   (none)"

    # ── Scheme name ────────────────────────────────────────────────────────
    sketch_type = analysis.get("sketch_type", "sketch")
    scheme_name = f"Structural Model from {sketch_type.replace('_', ' ').title()} Sketch"

    script = _REVIT_TEMPLATE.format(
        scheme_name=scheme_name,
        n_columns=len(columns),
        n_beams=len(beams),
        n_slabs=len(slabs),
        grid_info=grid_info,
        warnings_comment=warnings_comment,
        column_rows="\n".join(col_rows) or "    # no columns extracted",
        beam_rows="\n".join(beam_rows) or "    # no beams extracted",
        slab_rows="\n".join(slab_rows) or "    # no slabs extracted",
        levels_data="\n".join(level_rows),
    )

    out.write_text(script, encoding="utf-8")
    return str(out)


# ---------------------------------------------------------------------------
# Multi-floor template (one sketch page per floor level)
# ---------------------------------------------------------------------------

_REVIT_MULTIFLOOR_TEMPLATE = '''\
"""
Revit Multi-Floor Structural Model — {scheme_name}
Generated from {n_floors}-page sketch PDF by sketch_to_revit tool.
Each page of the PDF was analysed separately as a distinct floor level.

HOW TO RUN IN REVIT:
  1. Open Revit. Ensure a Level exists for each floor in the project:
{level_setup_comment}
  2. Load families if not already present:
       Structural Columns: Insert > Load Family > Structural > Columns > Concrete
       Structural Framing: Insert > Load Family > Structural > Framing > Concrete
  3. Open pyRevit Shell or Revit Python Shell.
  4. Open this file and click Run.

FLOORS IN THIS MODEL:
{floor_summary_comment}

⚠  PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilySymbol, Level, Line,
    Transaction, XYZ, CurveLoop, CurveArray, Floor, FloorType,
    BuiltInCategory
)
from Autodesk.Revit.DB.Structure import StructuralType

try:
    doc = __revit__.ActiveUIDocument.Document
except NameError:
    raise RuntimeError("Run this script inside pyRevit Shell or Revit Python Shell.")

MM_TO_FT = 1.0 / 304.8

# ---------------------------------------------------------------------------
# Per-floor structural data
# Each entry in FLOOR_DATA describes one floor level extracted from one sketch page.
# columns: (id, x_m, y_m, width_mm, depth_mm)
# beams:   (id, from_col_id, to_col_id, width_mm, depth_mm)
# slab_boundary: [(x_m, y_m), ...]  clockwise or anticlockwise
# ---------------------------------------------------------------------------
FLOOR_DATA = [
{floor_data_rows}]

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def m_to_xyz(x_m, y_m, z_m=0.0):
    return XYZ(x_m * 3.28084, y_m * 3.28084, z_m * 3.28084)


def find_symbol(doc, category_bic, preferred_keywords=None):
    preferred_keywords = preferred_keywords or []
    symbols = list(
        FilteredElementCollector(doc)
        .OfCategory(category_bic)
        .OfClass(FamilySymbol)
    )
    if not symbols:
        return None
    for kw in preferred_keywords:
        for sym in symbols:
            if kw.lower() in (sym.Family.Name + " " + sym.Name).lower():
                return sym
    return symbols[0]


def activate(doc, sym):
    if sym and not sym.IsActive:
        sym.Activate()
        doc.Regenerate()


def nearest_level(doc, elevation_m):
    elevation_ft = elevation_m * 3.28084
    levels = list(FilteredElementCollector(doc).OfClass(Level).ToElements())
    if not levels:
        return None
    return min(levels, key=lambda lv: abs(lv.Elevation - elevation_ft))


def set_param(inst, pairs_mm):
    for pw, pv in pairs_mm:
        p = inst.LookupParameter(pw)
        if p and not p.IsReadOnly:
            p.Set(pv * MM_TO_FT)
            return


# ---------------------------------------------------------------------------
# Creation logic
# ---------------------------------------------------------------------------

def create_model(doc):
    col_sym  = find_symbol(doc, BuiltInCategory.OST_StructuralColumns,
                           ["concrete", "rect", "square", "rcc"])
    beam_sym = find_symbol(doc, BuiltInCategory.OST_StructuralFraming,
                           ["concrete", "rect", "rcc", "beam"])
    floor_types = list(FilteredElementCollector(doc).OfClass(FloorType).ToElements())
    floor_type  = floor_types[0] if floor_types else None

    missing = []
    if col_sym  is None: missing.append("Structural Column family")
    if beam_sym is None: missing.append("Structural Framing family")
    if not floor_types:  missing.append("Floor type in project")
    if missing:
        print("\\nERROR — load these first:")
        for m in missing: print(f"  • {{m}}")
        return

    activate(doc, col_sym)
    activate(doc, beam_sym)

    stats = {{"cols": 0, "beams": 0, "slabs": 0, "errors": []}}

    with Transaction(doc, "Sketch-to-Revit: Multi-Floor Structural Model") as t:
        t.Start()

        for floor in FLOOR_DATA:
            lv_name   = floor["level_name"]
            lv_elev_m = floor["elevation_m"]
            columns   = floor["columns"]
            beams     = floor["beams"]
            boundary  = floor["slab_boundary"]
            thick_mm  = floor["slab_thickness_mm"]

            revit_level = nearest_level(doc, lv_elev_m)
            if revit_level is None:
                stats["errors"].append(f"No level found near {{lv_elev_m:.1f}} m ({{lv_name}})")
                continue

            col_pos = {{col_id: (x_m, y_m) for col_id, x_m, y_m, _w, _d in columns}}

            # Columns
            for col_id, x_m, y_m, w_mm, d_mm in columns:
                try:
                    loc = m_to_xyz(x_m, y_m, lv_elev_m)
                    inst = doc.Create.NewFamilyInstance(
                        loc, col_sym, revit_level, StructuralType.Column
                    )
                    set_param(inst, [("b", w_mm), ("h", d_mm),
                                     ("Width", w_mm), ("Depth", d_mm)])
                    stats["cols"] += 1
                except Exception as ex:
                    stats["errors"].append(f"Col {{col_id}} @ {{lv_name}}: {{ex}}")

            # Beams
            for bm_id, from_id, to_id, w_mm, d_mm in beams:
                if from_id not in col_pos or to_id not in col_pos:
                    stats["errors"].append(f"Beam {{bm_id}}: unknown col id")
                    continue
                try:
                    sx, sy = col_pos[from_id]
                    ex, ey = col_pos[to_id]
                    sp = m_to_xyz(sx, sy, lv_elev_m)
                    ep = m_to_xyz(ex, ey, lv_elev_m)
                    if sp.DistanceTo(ep) < 0.01:
                        continue
                    inst = doc.Create.NewFamilyInstance(
                        Line.CreateBound(sp, ep), beam_sym, revit_level, StructuralType.Beam
                    )
                    set_param(inst, [("b", w_mm), ("h", d_mm),
                                     ("Width", w_mm), ("Depth", d_mm)])
                    stats["beams"] += 1
                except Exception as ex:
                    stats["errors"].append(f"Beam {{bm_id}} @ {{lv_name}}: {{ex}}")

            # Slab
            if floor_type and len(boundary) >= 3:
                try:
                    pts = [m_to_xyz(x, y) for x, y in boundary]
                    curve_loop = CurveLoop()
                    for i in range(len(pts)):
                        p1, p2 = pts[i], pts[(i + 1) % len(pts)]
                        if p1.DistanceTo(p2) > 0.001:
                            curve_loop.Append(Line.CreateBound(p1, p2))
                    try:
                        Floor.Create(doc, [curve_loop], floor_type.Id, revit_level.Id)
                    except (AttributeError, TypeError):
                        ca = CurveArray()
                        for crv in curve_loop: ca.Append(crv)
                        doc.Create.NewFloor(ca, floor_type, revit_level, True)
                    stats["slabs"] += 1
                except Exception as ex:
                    stats["errors"].append(f"Slab @ {{lv_name}}: {{ex}}")

        t.Commit()

    print()
    print("=" * 55)
    print("MULTI-FLOOR MODEL CREATED")
    print(f"  Columns : {{stats[\'cols\']}}")
    print(f"  Beams   : {{stats[\'beams\']}}")
    print(f"  Slabs   : {{stats[\'slabs\']}}")
    if stats["errors"]:
        print(f"  Errors  : {{len(stats[\'errors\'])}}")
        for e in stats["errors"][:10]: print(f"    • {{e}}")
    print()
    print("⚠  PRELIMINARY — REQUIRES STRUCTURAL ENGINEER REVIEW")
    print("=" * 55)


create_model(doc)
'''


def write_revit_script_multifloor(
    floor_analyses: list[dict],
    output_path: str | None = None,
    floor_to_floor_m: float = 3.5,
) -> str:
    """
    Generate a pyRevit script from a list of per-floor sketch analyses.

    Args:
        floor_analyses:   List of analysis dicts from analyse_pdf_all_pages().
                          Each must have a 'floor_index' and 'floor_name' key.
        output_path:      Output .py path. Defaults to output/model_revit.py.
        floor_to_floor_m: Fallback floor-to-floor height if not in analysis.

    Returns:
        Path to the written script.
    """
    out = Path(output_path) if output_path else Path("output") / "model_revit.py"
    out.parent.mkdir(parents=True, exist_ok=True)

    floor_data_rows = []
    level_comments = []
    floor_summary_lines = []

    for fl in floor_analyses:
        fl_idx  = fl.get("floor_index", 0)
        fl_name = fl.get("floor_name", f"Level {fl_idx + 1}")
        ftf     = fl.get("floor_to_floor_height_m", floor_to_floor_m)
        elev_m  = round(fl_idx * ftf, 3)

        columns  = fl.get("columns", [])
        beams    = fl.get("beams", [])
        slabs    = fl.get("slabs", [])
        warnings = fl.get("warnings", [])

        col_pos_map = {c["id"]: (c.get("x_m", 0.0), c.get("y_m", 0.0)) for c in columns}

        # Build column tuples
        col_tuples = []
        for c in columns:
            col_tuples.append(
                f'        ("{c["id"]}", {c.get("x_m", 0.0):.3f}, {c.get("y_m", 0.0):.3f}, '
                f'{c.get("section_width_mm", 500)}, {c.get("section_depth_mm", 500)})'
            )

        # Build beam tuples
        bm_tuples = []
        for b in beams:
            bm_tuples.append(
                f'        ("{b["id"]}", "{b.get("from_col", "")}", "{b.get("to_col", "")}", '
                f'{b.get("width_mm", 400)}, {b.get("depth_mm", 600)})'
            )

        # Build slab boundary from first slab's boundary cols
        slab_thick = 250
        boundary_pts = []
        if slabs:
            sl = slabs[0]
            slab_thick = sl.get("thickness_mm", 250)
            for cid in sl.get("boundary_cols", []):
                if cid in col_pos_map:
                    x, y = col_pos_map[cid]
                    boundary_pts.append(f"({x:.3f}, {y:.3f})")

        col_str      = ",\n".join(col_tuples) or "        # none"
        bm_str       = ",\n".join(bm_tuples)  or "        # none"
        boundary_str = ", ".join(boundary_pts) or ""

        floor_data_rows.append(
            f'    {{\n'
            f'        "level_name": "{fl_name}",\n'
            f'        "elevation_m": {elev_m},\n'
            f'        "columns": [\n{col_str}\n        ],\n'
            f'        "beams": [\n{bm_str}\n        ],\n'
            f'        "slab_boundary": [{boundary_str}],\n'
            f'        "slab_thickness_mm": {slab_thick},\n'
            f'    }}'
        )

        level_comments.append(f'#       {fl_name} at elevation {elev_m:.1f} m')
        floor_summary_lines.append(
            f'#   Page {fl_idx + 1} → {fl_name}  '
            f'({len(columns)} cols, {len(beams)} beams)'
            + (f'  ⚠ {warnings[0]}' if warnings else '')
        )

    script = _REVIT_MULTIFLOOR_TEMPLATE.format(
        scheme_name=f"{len(floor_analyses)}-Floor Building",
        n_floors=len(floor_analyses),
        level_setup_comment="\n".join(level_comments),
        floor_summary_comment="\n".join(floor_summary_lines),
        floor_data_rows=",\n".join(floor_data_rows) + "\n",
    )

    out.write_text(script, encoding="utf-8")
    return str(out)
