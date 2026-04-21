"""
e2k_writer.py — Writes an ETABS Text (E2K) file from an ETABSModel.

The .e2k format can be imported into ETABS via:
  File → Import → ETABS Text File (.e2k)

This provides a cross-platform alternative to the COM API script; the E2K
file can be generated on any OS and imported on any Windows ETABS machine.

E2K format reference: ETABS 2021 Text File Documentation (CSi).
Units used throughout: kN, m, Celsius.

⚠️  PRELIMINARY MODEL — NOT FOR CONSTRUCTION
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import IO

from structural_elements import ETABSModel, ConcreteMaterial
from load_definitions import get_loads


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _f(v: float, decimals: int = 3) -> str:
    """Format a float to fixed decimal places."""
    return f"{v:.{decimals}f}"


def _label(text: str) -> str:
    """Quote a label for E2K output."""
    return f'"{text}"'


# ---------------------------------------------------------------------------
# Section writers
# ---------------------------------------------------------------------------

def _write_header(f: IO, model: ETABSModel) -> None:
    f.write("$ PROGRAM INFORMATION\n")
    f.write('   PROGRAM "ETABS"   VERSION "21"   REVISION 0   LANG "ENG"\n')
    f.write(f'   UNITS "KN" "m" "C"\n')
    f.write(f'   PROJECTID "{model.project_name}"\n')
    f.write("\n")

    f.write("$ CONTROLS\n")
    f.write('   UNITS "KN" "m" "C"\n')
    f.write(f"   BASEELEV {_f(model.base_rl_m)}\n")
    f.write("\n")


def _write_stories(f: IO, model: ETABSModel) -> None:
    f.write("$ STORY DATA\n")
    # E2K lists stories top → bottom; our model levels are bottom → top
    for lv in reversed(model.levels):
        f.write(
            f"   STORY {_label(lv.name)}"
            f"  HEIGHT {_f(lv.height_m)}"
            f"  MASTERSTORY \"No\""
            f"  SIMILARSTORY \"None\""
            f"  SPLICEABOVE \"No\""
            f"  SPLICEHGT {_f(lv.height_m / 2)}"
            f"  COLOR 16711680\n"
        )
    # Base story
    f.write(
        '   STORY "Base"  HEIGHT 0  MASTERSTORY "No"'
        '  SIMILARSTORY "None"  SPLICEABOVE "No"  SPLICEHGT 0  COLOR 16711680\n'
    )
    f.write("\n")

    f.write("$ DIAPHRAGM NAMES\n")
    f.write('   DIAPHRAGM "RIGID"  TYPE "Rigid"\n')
    f.write("\n")


def _write_materials(f: IO, model: ETABSModel) -> None:
    f.write("$ MATERIAL PROPERTIES\n")
    for mat in model.materials:
        f.write(
            f"   MATERIAL {_label(mat.label)}"
            f'  TYPE "Concrete"'
            f"  FC {mat.fc_kpa:.0f}"
            f"  UNITWEIGHT {mat.unit_weight_kn_m3:.1f}"
            f"  E {mat.E_kpa:.4e}"
            f"  U {mat.poisson}"
            f"  A {mat.thermal:.2e}\n"
        )
    f.write("\n")


def _write_sections(f: IO, model: ETABSModel) -> None:
    f.write("$ FRAME SECTIONS\n")
    for cs in model.column_sections:
        d_m = cs.depth_mm / 1000.0
        b_m = cs.width_mm / 1000.0
        if cs.shape == "circular":
            f.write(
                f"   FRAMESECTION {_label(cs.label)}"
                f'  SHAPE "Circle"'
                f"  MATERIAL {_label(cs.material)}"
                f"  D {_f(d_m)}\n"
            )
        else:
            f.write(
                f"   FRAMESECTION {_label(cs.label)}"
                f'  SHAPE "Rectangular"'
                f"  MATERIAL {_label(cs.material)}"
                f"  D {_f(d_m)}"
                f"  B {_f(b_m)}\n"
            )
    f.write("\n")

    f.write("$ WALL/SLAB/DECK SECTIONS\n")
    for ws in model.wall_sections:
        thk = ws.thickness_mm / 1000.0
        f.write(
            f"   SHELLSECT {_label(ws.label)}"
            f'  TYPE "Shell-Thin"'
            f"  MATERIAL {_label(ws.material)}"
            f"  MEMBRANETHICK {_f(thk)}"
            f"  BENDINGTHICK {_f(thk)}\n"
        )
    for ss in model.slab_sections:
        thk = ss.thickness_mm / 1000.0
        f.write(
            f"   SHELLSECT {_label(ss.label)}"
            f'  TYPE "Plate-Thin"'
            f"  MATERIAL {_label(ss.material)}"
            f"  MEMBRANETHICK {_f(thk)}"
            f"  BENDINGTHICK {_f(thk)}\n"
        )
    f.write("\n")


def _write_points(f: IO, model: ETABSModel) -> tuple[dict, int]:
    """
    Collect all unique 2D plan points and write the POINT COORDINATES section.

    Returns (point_registry, next_id) where point_registry maps (x_m, y_m)
    rounded to 3 decimal places to a point label string.
    """
    registry: dict[tuple[float, float], str] = {}
    counter = [1]

    def register(x: float, y: float) -> str:
        key = (round(x, 3), round(y, 3))
        if key not in registry:
            registry[key] = f"P{counter[0]}"
            counter[0] += 1
        return registry[key]

    # Columns
    for col in model.columns:
        register(col.x_m, col.y_m)

    # Wall endpoints
    for wall in model.walls:
        register(wall.x1_m, wall.y1_m)
        register(wall.x2_m, wall.y2_m)

    # Slab polygon vertices
    for slab in model.slabs:
        for x, y in slab.polygon_m:
            register(x, y)

    f.write("$ POINT COORDINATES\n")
    for (x, y), label in sorted(registry.items(), key=lambda kv: kv[1]):
        f.write(f"   POINT {_label(label)}  {_f(x)}  {_f(y)}\n")
    f.write("\n")

    return registry, counter[0]


def _write_columns(f: IO, model: ETABSModel, pt_reg: dict) -> None:
    f.write("$ COLUMN DATA\n")
    for col in model.columns:
        pt_key = (round(col.x_m, 3), round(col.y_m, 3))
        pt_label = pt_reg.get(pt_key, "P?")
        for story_name in col.story_names:
            col_name = f"{col.id}_{story_name.replace(' ', '_')}"
            f.write(
                f"   COLUMN {_label(col_name)}"
                f"  STORY {_label(story_name)}"
                f"  POINT {_label(pt_label)}"
                f"  SECTION {_label(col.section_label)}"
                f"  ANG 0\n"
            )
    f.write("\n")


def _write_walls(f: IO, model: ETABSModel, pt_reg: dict) -> None:
    """
    Write wall panels as area objects.
    Each wall segment becomes a vertical rectangle spanning the story height.
    In E2K, vertical walls reference two plan points (the wall baseline);
    ETABS infers the height from the story assignment.
    """
    f.write("$ WALL DATA\n")
    for wall in model.walls:
        p1_key = (round(wall.x1_m, 3), round(wall.y1_m, 3))
        p2_key = (round(wall.x2_m, 3), round(wall.y2_m, 3))
        p1 = pt_reg.get(p1_key, "P?")
        p2 = pt_reg.get(p2_key, "P?")
        f.write(
            f"   WALL {_label(wall.id)}"
            f"  STORY {_label(wall.story_name)}"
            f"  POINT1 {_label(p1)}"
            f"  POINT2 {_label(p2)}"
            f"  SECTION {_label(wall.section_label)}\n"
        )
    f.write("\n")


def _write_slabs(f: IO, model: ETABSModel, pt_reg: dict) -> None:
    f.write("$ FLOOR DATA\n")
    for slab in model.slabs:
        pts = [pt_reg.get((round(x, 3), round(y, 3)), "P?") for x, y in slab.polygon_m]
        n = len(pts)
        pt_str = "  ".join(_label(p) for p in pts)
        f.write(
            f"   FLOOR {_label(slab.id)}"
            f"  STORY {_label(slab.story_name)}"
            f"  {n}  {pt_str}"
            f"  SECTION {_label(slab.section_label)}"
            f'  DIAPH "RIGID"\n'
        )
    f.write("\n")


def _write_load_patterns(f: IO, model: ETABSModel) -> None:
    usages = sorted({sl.floor_usage for sl in model.slabs})
    f.write("$ LOAD PATTERNS\n")
    f.write('   LOADPAT "Dead"  TYPE "Dead"  SELFWEIGHT 1\n')
    for usage in usages:
        f.write(f'   LOADPAT "SDL_{usage}"   TYPE "Super Dead"  SELFWEIGHT 0\n')
        f.write(f'   LOADPAT "Live_{usage}"  TYPE "Live"        SELFWEIGHT 0\n')
    f.write("\n")


def _write_floor_loads(f: IO, model: ETABSModel) -> None:
    f.write("$ FLOOR LOADS\n")
    for slab in model.slabs:
        loads = get_loads(slab.floor_usage)
        sdl = loads["sdl_kpa"]
        ll = loads["ll_kpa"]
        f.write(
            f"   FLOORLOAD {_label(slab.id)}"
            f'  LOADPAT "SDL_{slab.floor_usage}"'
            f'  DIR "Gravity"'
            f"  VAL {_f(sdl)}\n"
        )
        f.write(
            f"   FLOORLOAD {_label(slab.id)}"
            f'  LOADPAT "Live_{slab.floor_usage}"'
            f'  DIR "Gravity"'
            f"  VAL {_f(ll)}\n"
        )
    f.write("\n")


def _write_load_cases(f: IO, model: ETABSModel) -> None:
    usages = sorted({sl.floor_usage for sl in model.slabs})
    f.write("$ LOAD CASES\n")
    f.write('   LOADCASE "Dead"  TYPE "Linear Static"\n')
    for usage in usages:
        f.write(f'   LOADCASE "SDL_{usage}"   TYPE "Linear Static"\n')
        f.write(f'   LOADCASE "Live_{usage}"  TYPE "Linear Static"\n')
    f.write("\n")


def _write_combos(f: IO, model: ETABSModel) -> None:
    usages = sorted({sl.floor_usage for sl in model.slabs})
    all_sdl = [f"SDL_{u}" for u in usages]
    all_ll  = [f"Live_{u}" for u in usages]

    f.write("$ LOAD COMBINATIONS\n")

    # ULS 1.2G + 1.5Q
    f.write('   COMBO "ULS_1.2G+1.5Q"  TYPE "Linear Add"\n')
    f.write('   COMBOCASE "ULS_1.2G+1.5Q"  LOADCASE "Dead"  SF 1.200\n')
    for lc in all_sdl:
        f.write(f'   COMBOCASE "ULS_1.2G+1.5Q"  LOADCASE "{lc}"  SF 1.200\n')
    for lc in all_ll:
        f.write(f'   COMBOCASE "ULS_1.2G+1.5Q"  LOADCASE "{lc}"  SF 1.500\n')

    # ULS 1.35G
    f.write('   COMBO "ULS_1.35G"  TYPE "Linear Add"\n')
    f.write('   COMBOCASE "ULS_1.35G"  LOADCASE "Dead"  SF 1.350\n')
    for lc in all_sdl:
        f.write(f'   COMBOCASE "ULS_1.35G"  LOADCASE "{lc}"  SF 1.350\n')

    # SLS
    f.write('   COMBO "SLS_1.0G+1.0Q"  TYPE "Linear Add"\n')
    f.write('   COMBOCASE "SLS_1.0G+1.0Q"  LOADCASE "Dead"  SF 1.000\n')
    for lc in all_sdl:
        f.write(f'   COMBOCASE "SLS_1.0G+1.0Q"  LOADCASE "{lc}"  SF 1.000\n')
    for lc in all_ll:
        f.write(f'   COMBOCASE "SLS_1.0G+1.0Q"  LOADCASE "{lc}"  SF 1.000\n')
    f.write("\n")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_e2k(model: ETABSModel, output_dir: str = "output") -> str:
    """
    Write an ETABS Text (.e2k) file from the model and return the file path.

    Import into ETABS via: File → Import → ETABS Text File (.e2k)
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    filename = f"{model.project_name.replace(' ', '_')}.e2k"
    path = Path(output_dir) / filename

    with open(path, "w", encoding="utf-8") as f:
        _write_header(f, model)
        _write_stories(f, model)
        _write_materials(f, model)
        _write_sections(f, model)
        pt_reg, _ = _write_points(f, model)
        _write_columns(f, model, pt_reg)
        _write_walls(f, model, pt_reg)
        _write_slabs(f, model, pt_reg)
        _write_load_patterns(f, model)
        _write_floor_loads(f, model)
        _write_load_cases(f, model)
        _write_combos(f, model)

        f.write("$ END OF MODEL DEFINITION\n")

    print(f"  E2K file → {path}")
    return str(path)
