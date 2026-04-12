"""
pdf_writer.py — Write proposed column grids as annotated PDFs.

Produces:
  output/scheme_1.pdf, scheme_2.pdf, scheme_3.pdf
    One PDF per scheme — original floor plan with columns overlaid as
    yellow/orange circle annotations (Tribli-importable format).

  output/comparison.pdf
    All schemes on one page, colour-coded by scheme number.

Annotation format is compatible with Tribli's PDF import:
  /Subj   "column"
  /Contents  "D={D} B={B} fc={fc} chain=C{n}"

A mandatory watermark and disclaimer legend are added to every page.

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
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

# ---------------------------------------------------------------------------
# Colour palette (RGB, 0–1 range for fitz)
# ---------------------------------------------------------------------------
SCHEME_COLOURS = [
    (1.0, 0.60, 0.00),   # Scheme 1 — orange
    (0.55, 0.00, 0.80),  # Scheme 2 — purple
    (0.00, 0.75, 0.85),  # Scheme 3 — cyan
]
FORCED_COLOUR = (1.0, 0.20, 0.20)   # red for forced columns
VOID_COLOUR = (0.80, 0.00, 0.00)    # red outline for voids
PLATE_COLOUR = (0.00, 0.40, 0.80)   # blue outline for floor plate
FACADE_COLOUR = (0.20, 0.60, 0.20)  # green for facade line

# Annotation circle radius in PDF points
COLUMN_RADIUS_PT = 6.0
FORCED_RADIUS_PT = 8.0

# Watermark / disclaimer text
_DISCLAIMER_LINES = [
    "⚠  PRELIMINARY SCHEME ONLY — NOT ENGINEERED",
    "Max span: {max_span_m:.1f} m  |  Slab: {slab_mm} mm  |  System: {system}",
    "MUST BE REVIEWED BY A STRUCTURAL ENGINEER BEFORE USE",
]

_FULL_DISCLAIMER = (
    "⚠  PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION\n"
    "This column layout was generated algorithmically from span/depth rules of thumb.\n"
    "It has NOT been designed or verified by a structural engineer.\n"
    "It MUST be reviewed, checked, and approved by a registered structural engineer\n"
    "before use in any design documentation or construction.\n"
    "Punching shear, lateral stability, transfer structures, and serviceability\n"
    "have NOT been checked. Column sizes are indicative only."
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_output_dir() -> Path:
    out = Path("output")
    out.mkdir(exist_ok=True)
    return out


def _column_annotation_contents(col: dict) -> str:
    D = col.get("D_mm", 500)
    B = col.get("B_mm", 500)
    fc = 50
    chain_id = col.get("id", "C1")
    return f"D={D} B={B} fc={fc} chain={chain_id}"


def _add_circle_annotation(
    page: fitz.Page,
    x_pts: float,
    y_pts: float,
    radius: float,
    colour: tuple,
    fill: tuple | None,
    contents: str,
    subject: str = "column",
    opacity: float = 0.8,
) -> None:
    """Draw a circle annotation at (x_pts, y_pts) in PDF-point coordinates."""
    # fitz uses top-left origin; y_pts is already in top-left coords at call site
    rect = fitz.Rect(
        x_pts - radius, y_pts - radius,
        x_pts + radius, y_pts + radius,
    )
    annot = page.add_circle_annot(rect)
    annot.set_colors(stroke=colour, fill=fill or colour)
    annot.set_info(subject=subject, content=contents)
    annot.set_opacity(opacity)
    annot.set_border(width=1.5)
    annot.update()


def _add_watermark(
    page: fitz.Page,
    max_span_mm: float,
    slab_mm: int,
    system: str,
    scheme_name: str = "",
) -> None:
    """Add a semi-transparent watermark text block to the page."""
    max_span_m = max_span_mm / 1000
    line2 = _DISCLAIMER_LINES[1].format(
        max_span_m=max_span_m, slab_mm=slab_mm, system=system
    )
    text = (
        f"{scheme_name}   " if scheme_name else ""
    ) + _DISCLAIMER_LINES[0] + "\n" + line2 + "\n" + _DISCLAIMER_LINES[2]

    # Place watermark near top of page
    rect = fitz.Rect(20, 10, page.rect.width - 20, 60)
    page.insert_textbox(
        rect,
        text,
        fontsize=7,
        color=(0.8, 0.0, 0.0),
        align=fitz.TEXT_ALIGN_CENTER,
    )


def _add_full_disclaimer_annotation(page: fitz.Page) -> None:
    """Add a text annotation in the bottom-left corner with the full disclaimer."""
    x0, y0 = 10, page.rect.height - 80
    rect = fitz.Rect(x0, y0, x0 + 300, page.rect.height - 10)
    annot = page.add_freetext_annot(
        rect,
        _FULL_DISCLAIMER,
        fontsize=5,
        text_color=(0.7, 0.0, 0.0),
        fill_color=(1.0, 0.98, 0.85),
        border_color=(0.8, 0.0, 0.0),
    )
    annot.set_border(width=0.5)
    annot.update()


def _add_legend(
    page: fitz.Page,
    scheme_colours: list[tuple],
    scheme_names: list[str],
) -> None:
    """Add a colour legend in the top-right corner."""
    x0 = page.rect.width - 150
    y0 = 10
    lines = ["LEGEND"]
    for col, name in zip(scheme_colours, scheme_names):
        hex_col = "#{:02X}{:02X}{:02X}".format(
            int(col[0] * 255), int(col[1] * 255), int(col[2] * 255)
        )
        lines.append(f"  {name}: ●")

    rect = fitz.Rect(x0, y0, page.rect.width - 5, y0 + len(lines) * 10 + 5)
    page.insert_textbox(rect, "\n".join(lines), fontsize=6.5, color=(0.1, 0.1, 0.1))


def _pdf_y(y_pts_bottom_origin: float, page_height: float) -> float:
    """
    Convert y from bottom-left origin (PDF logical) to top-left origin (fitz/screen).
    """
    return page_height - y_pts_bottom_origin


def _draw_polygon_outline(
    page: fitz.Page,
    polygon_pts: list[dict],
    page_height: float,
    colour: tuple,
    width: float = 1.0,
    dashed: bool = False,
) -> None:
    """Draw a polygon outline using fitz drawing primitives."""
    if len(polygon_pts) < 2:
        return
    coords = [
        (p["x_pts"], _pdf_y(p["y_pts"], page_height))
        for p in polygon_pts
    ]
    shape = page.new_shape()
    shape.draw_polyline(coords)
    # Close the polygon
    shape.draw_line(coords[-1], coords[0])
    shape.finish(color=colour, fill=None, width=width, dashes="[4 2] 0" if dashed else None)
    shape.commit()


# ---------------------------------------------------------------------------
# Per-scheme PDF writer
# ---------------------------------------------------------------------------

def write_scheme_pdf(
    scheme: dict,
    analysis: dict,
    level: dict,
    config: dict,
    span_result: dict,
    scheme_index: int = 0,
) -> str:
    """
    Write one annotated PDF for a single scheme.

    Args:
        scheme:       Scheme dict from grid_generator (columns, n_columns, etc.)
        analysis:     Vision analysis dict (floor_plate, voids, etc.)
        level:        Level dict from config (page_index, level_name)
        config:       Full tool config.
        span_result:  Output of span_rules.get_max_span().
        scheme_index: 0-based index (controls colour and filename).

    Returns:
        Path to written file.
    """
    out_dir = _ensure_output_dir()
    out_path = out_dir / f"scheme_{scheme_index + 1}.pdf"

    colour = SCHEME_COLOURS[scheme_index % len(SCHEME_COLOURS)]
    slab_mm = config["structural"]["slab_thickness_mm"]
    system = config["structural"]["slab_system"]
    max_span_mm = span_result["max_span_mm"]

    doc = fitz.open(config["pdf_path"])
    page = doc[level["page_index"]]
    ph = page.rect.height  # page height in pts (top-left origin conversion)

    # ------------------------------------------------------------------
    # Floor plate boundary
    # ------------------------------------------------------------------
    _draw_polygon_outline(
        page, analysis.get("floor_plate", []), ph, PLATE_COLOUR, width=1.5
    )

    # ------------------------------------------------------------------
    # Void polygons
    # ------------------------------------------------------------------
    for v in analysis.get("voids", []):
        _draw_polygon_outline(
            page, v.get("polygon", []), ph, VOID_COLOUR, width=1.0, dashed=True
        )

    # ------------------------------------------------------------------
    # Core walls
    # ------------------------------------------------------------------
    for cw in analysis.get("core_walls", []):
        _draw_polygon_outline(
            page, cw.get("polygon", []), ph, (0.4, 0.4, 0.4), width=1.0
        )

    # ------------------------------------------------------------------
    # Façade line
    # ------------------------------------------------------------------
    facade = analysis.get("facade_line", [])
    if len(facade) >= 2:
        _draw_polygon_outline(page, facade, ph, FACADE_COLOUR, width=0.8, dashed=True)

    # ------------------------------------------------------------------
    # Column circles
    # ------------------------------------------------------------------
    for col in scheme["columns"]:
        cx = col["x_pts"]
        cy = _pdf_y(col["y_pts"], ph)
        is_forced = col.get("type") == "forced"
        col_colour = FORCED_COLOUR if is_forced else colour
        radius = FORCED_RADIUS_PT if is_forced else COLUMN_RADIUS_PT
        contents = _column_annotation_contents(col)
        _add_circle_annotation(
            page, cx, cy, radius, col_colour, None, contents, opacity=0.85
        )

    # ------------------------------------------------------------------
    # Watermark & disclaimer
    # ------------------------------------------------------------------
    _add_watermark(page, max_span_mm, slab_mm, system, scheme["scheme_name"])
    _add_full_disclaimer_annotation(page)
    _add_legend(page, [colour], [scheme["scheme_name"]])

    doc.save(str(out_path))
    doc.close()
    print(f"  Scheme PDF written → {out_path}")
    return str(out_path)


# ---------------------------------------------------------------------------
# Comparison PDF (all schemes on one page)
# ---------------------------------------------------------------------------

def write_comparison_pdf(
    schemes: list[dict],
    analysis: dict,
    level: dict,
    config: dict,
    span_result: dict | None = None,
) -> str:
    """
    Write a comparison PDF with all schemes overlaid in different colours.

    Returns path to written file.
    """
    out_dir = _ensure_output_dir()
    out_path = out_dir / "comparison.pdf"

    doc = fitz.open(config["pdf_path"])
    page = doc[level["page_index"]]
    ph = page.rect.height

    slab_mm = config["structural"]["slab_thickness_mm"]
    system = config["structural"]["slab_system"]
    max_span_mm = span_result["max_span_mm"] if span_result else 0

    # Floor plate
    _draw_polygon_outline(
        page, analysis.get("floor_plate", []), ph, PLATE_COLOUR, width=1.5
    )
    # Voids
    for v in analysis.get("voids", []):
        _draw_polygon_outline(
            page, v.get("polygon", []), ph, VOID_COLOUR, width=1.0, dashed=True
        )
    # Core walls
    for cw in analysis.get("core_walls", []):
        _draw_polygon_outline(page, cw.get("polygon", []), ph, (0.4, 0.4, 0.4), width=1.0)

    # Columns per scheme
    for idx, scheme in enumerate(schemes):
        colour = SCHEME_COLOURS[idx % len(SCHEME_COLOURS)]
        for col in scheme["columns"]:
            cx = col["x_pts"]
            cy = _pdf_y(col["y_pts"], ph)
            is_forced = col.get("type") == "forced"
            col_colour = FORCED_COLOUR if is_forced else colour
            radius = (FORCED_RADIUS_PT if is_forced else COLUMN_RADIUS_PT) + idx * 1.5
            contents = f"{scheme['scheme_name']} — {_column_annotation_contents(col)}"
            _add_circle_annotation(
                page, cx, cy, radius, col_colour, None, contents,
                opacity=0.6 + idx * 0.05,
            )

    # Watermark
    _add_watermark(page, max_span_mm, slab_mm, system, "ALL SCHEMES — COMPARISON")
    _add_full_disclaimer_annotation(page)
    _add_legend(
        page,
        [SCHEME_COLOURS[i % len(SCHEME_COLOURS)] for i in range(len(schemes))],
        [s["scheme_name"] for s in schemes],
    )

    doc.save(str(out_path))
    doc.close()
    print(f"  Comparison PDF written → {out_path}")
    return str(out_path)


# ---------------------------------------------------------------------------
# Tribli Python script writer
# ---------------------------------------------------------------------------

_TRIBLI_TEMPLATE = '''"""
{scheme_name} — Tribli Python Script
Generated by Structural Scheme Generator (preliminary tool)

⚠️  PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION
This column layout was generated algorithmically from span/depth rules of thumb.
It has NOT been designed or verified by a structural engineer.
It MUST be reviewed, checked, and approved by a registered structural engineer
before use in any design documentation or construction.
Punching shear, lateral stability, transfer structures, and serviceability
have NOT been checked. Column sizes are indicative only.
"""

# ===========================================================================
# Tribli API — {scheme_name}
# Grid spacing:  {grid_spacing_mm} mm
# Max span:      {max_span_mm} mm
# Slab system:   {system}
# Load type:     {load_type}
# Columns:       {n_columns}
# ===========================================================================

DISCLAIMER = (
    "⚠  PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION\\n"
    "This column layout was generated algorithmically. "
    "Requires engineer review before use."
)
print(DISCLAIMER)

# ---------------------------------------------------------------------------
# Column definitions
# Each entry: (id, x_mm, y_mm, D_mm, B_mm, type)
# Coordinates are real-world millimetres from drawing origin.
# ---------------------------------------------------------------------------
columns = [
{column_rows}]

# ---------------------------------------------------------------------------
# Create columns in Tribli model
# ---------------------------------------------------------------------------
for col_id, x_mm, y_mm, D_mm, B_mm, col_type in columns:
    tribli.add_column(
        label=col_id,
        x=x_mm / 1000,     # convert mm → m for Tribli API
        y=y_mm / 1000,
        D=D_mm,
        B=B_mm,
        fc=50,
        comment=f"{{col_type}} — PRELIMINARY SCHEME",
    )

print(f"Added {{len(columns)}} columns to model.")
print(f"Grid: {grid_spacing_mm} mm  |  Max span: {max_span_mm} mm")
print()
print("NEXT STEPS (engineer to perform):")
print("  1. Review column positions visually against architectural plan")
print("  2. Run: Calculate > Tributary Areas")
print("  3. Run: Calculate > Column Loads")
print("  4. Check 3D view for sanity and adjust any positions")
print("  5. Verify punching shear at each slab-column connection")
print()

# ---------------------------------------------------------------------------
# Load calculations — commented out until engineer has reviewed geometry
# ---------------------------------------------------------------------------
# UNCOMMENT the lines below only after the engineer has reviewed and approved
# the column layout above.
#
# tribli.calculate_loads()
# loads = tribli.get_axial_loads()
# for col_id, N_kN in loads.items():
#     print(f"  {{col_id}}: N* = {{N_kN:.0f}} kN")
'''


def write_scheme_tribli_script(
    scheme: dict,
    analysis: dict,
    level: dict,
    config: dict,
    span_result: dict,
    scheme_index: int = 0,
) -> str:
    """
    Write a Tribli Python script for a single scheme.
    Returns the path to the written file.
    """
    out_dir = _ensure_output_dir()
    out_path = out_dir / f"scheme_{scheme_index + 1}_tribli.py"

    drawing_scale = config["drawing_scale"]
    scale_denom = int(drawing_scale.split(":")[1])
    # PDF points → real-world mm
    pts_to_mm_factor = scale_denom * 25.4 / 72.0

    rows = []
    for col in scheme["columns"]:
        x_mm = round(col["x_pts"] * pts_to_mm_factor, 1)
        y_mm = round(col["y_pts"] * pts_to_mm_factor, 1)
        D = col.get("D_mm", 500)
        B = col.get("B_mm", 500)
        col_type = col.get("type", "grid")
        rows.append(
            f'    ("{col["id"]}", {x_mm}, {y_mm}, {D}, {B}, "{col_type}"),'
        )

    script = _TRIBLI_TEMPLATE.format(
        scheme_name=scheme["scheme_name"],
        grid_spacing_mm=scheme["grid_spacing_mm"],
        max_span_mm=span_result["max_span_mm"],
        system=config["structural"]["slab_system"],
        load_type=config["structural"]["load_type"],
        n_columns=scheme["n_columns"],
        column_rows="\n".join(rows) + "\n",
    )

    out_path.write_text(script)
    print(f"  Tribli script written → {out_path}")
    return str(out_path)
