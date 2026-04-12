"""
report.py — Plain-text engineering summary report generator.

Writes output/scheme_report.txt containing:
  • Project inputs
  • Engineering basis (AS3600 span/depth)
  • Per-scheme summary (columns, grid, trib area, coverage, output files)
  • Engineer checklist

⚠️  PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION
This column layout was generated algorithmically from span/depth rules of thumb.
It has NOT been designed or verified by a structural engineer.
It MUST be reviewed, checked, and approved by a registered structural engineer
before use in any design documentation or construction.
Punching shear, lateral stability, transfer structures, and serviceability
have NOT been checked. Column sizes are indicative only.
"""

from __future__ import annotations

import textwrap
from datetime import datetime
from pathlib import Path


_DIVIDER = "=" * 65
_SUBDIV = "-" * 65


def _w(text: str, indent: int = 0) -> str:
    """Wrap a text block at 65 characters with optional indent."""
    prefix = " " * indent
    return textwrap.fill(text, width=65, initial_indent=prefix, subsequent_indent=prefix)


def write_scheme_report(
    grid_result: dict,
    analysis: dict,
    config: dict,
    span_result: dict,
) -> str:
    """
    Generate and write the plain-text scheme report.

    Args:
        grid_result:  Output of grid_generator.generate_column_grid()
                      (with coverage and column size data already merged in).
        analysis:     Vision analysis dict from vision_scheme.py.
        config:       Full tool config dict.
        span_result:  Output of span_rules.get_max_span().

    Returns:
        Path to the written report file.
    """
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "scheme_report.txt"

    lines = _build_report_lines(grid_result, analysis, config, span_result)
    text = "\n".join(lines)

    out_path.write_text(text, encoding="utf-8")
    print(f"  Scheme report written → {out_path}")
    return str(out_path)


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def _build_report_lines(
    grid_result: dict,
    analysis: dict,
    config: dict,
    span_result: dict,
) -> list[str]:
    lines: list[str] = []
    structural = config.get("structural", {})
    slab_mm = structural.get("slab_thickness_mm", "?")
    system = span_result.get("system_label", structural.get("slab_system", "?"))
    load_type = span_result.get("load_label", structural.get("load_type", "?"))
    max_span_mm = span_result["max_span_mm"]
    max_span_m = max_span_mm / 1000
    eff_depth = span_result["effective_depth_mm"]
    ratio = span_result["span_depth_ratio_used"]
    load_factor = span_result["load_factor_applied"]
    panel_pos = span_result.get("panel_position", "interior")
    system_notes = span_result.get("notes", "")
    punching_warn = span_result.get("punching_warning", "")

    plate_area = analysis.get("floor_plate_area_m2", 0)
    n_floors = structural.get("num_floors", 1)
    drawing_scale = config.get("drawing_scale", "1:100")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    lines += [
        _DIVIDER,
        "PRELIMINARY STRUCTURAL SCHEME REPORT",
        f"Generated: {now}",
        "⚠️  NOT FOR CONSTRUCTION — REQUIRES ENGINEER REVIEW",
        _DIVIDER,
        "",
    ]

    # ------------------------------------------------------------------
    # Project inputs
    # ------------------------------------------------------------------
    lines += [
        "PROJECT INPUT",
        _SUBDIV,
        f"Floor plate area:        {plate_area:.0f} m²",
        f"Drawing scale:           {drawing_scale}",
        f"Slab system:             {system}",
        f"Slab thickness:          {slab_mm} mm",
        f"Load type:               {load_type}",
        f"Max allowable span:      {max_span_m:.1f} m  (from L/d = {ratio})",
        f"Effective depth assumed: {eff_depth} mm",
        f"Number of floors:        {n_floors}",
    ]
    if punching_warn:
        lines += [f"", f"⚠️  {punching_warn}"]
    lines.append("")

    # ------------------------------------------------------------------
    # Engineering basis
    # ------------------------------------------------------------------
    lines += [
        "ENGINEERING BASIS",
        _SUBDIV,
        _w(
            "Span limit derived from AS3600:2018 deemed-to-comply "
            "span/depth approach (Clause 9.4.4)."
        ),
        f"L/d = {ratio} used for {panel_pos} panels.",
        f"Load adjustment factor: {load_factor:.2f} (for {load_type}).",
        _w(system_notes),
        "",
        _w(span_result.get("preliminary_disclaimer", "")),
        "",
    ]

    # ------------------------------------------------------------------
    # Architectural analysis summary
    # ------------------------------------------------------------------
    n_forced = len(analysis.get("forced_columns", []))
    n_voids = len(analysis.get("voids", []))
    arch_grid = analysis.get("architectural_grid_mm")
    arch_grid_conf = analysis.get("architectural_grid_confidence", "unknown")
    arch_grid_note = analysis.get("architectural_grid_note", "")
    general_notes = analysis.get("general_notes", "")

    lines += [
        "ARCHITECTURAL ANALYSIS (from Claude vision)",
        _SUBDIV,
        f"Forced column locations: {n_forced}",
        f"Void / exclusion zones:  {n_voids}",
    ]
    if arch_grid:
        lines.append(
            f"Detected grid module:    {arch_grid / 1000:.1f} m  "
            f"({arch_grid_conf} confidence)"
        )
        if arch_grid_note:
            lines.append(f"  Note: {arch_grid_note}")
    else:
        lines.append("Detected grid module:    None detected")

    if analysis.get("warnings"):
        lines.append("")
        lines.append("Warnings from vision analysis:")
        for w in analysis["warnings"]:
            lines.append(f"  • {w}")

    if general_notes:
        lines += ["", _w(f"General notes: {general_notes}")]

    lines.append("")

    # ------------------------------------------------------------------
    # Per-scheme summary
    # ------------------------------------------------------------------
    lines += [
        "SCHEMES GENERATED",
        _SUBDIV,
    ]

    for scheme in grid_result.get("schemes", []):
        name = scheme.get("scheme_name", "Scheme ?")
        label = scheme.get("label", "")
        n_cols = scheme.get("n_columns", "?")
        grid_mm = scheme.get("grid_spacing_mm", "?")
        avg_trib = scheme.get("avg_tributary_m2", "?")
        coverage = scheme.get("coverage", {})
        coverage_ok = coverage.get("coverage_ok", True)
        n_uncov = coverage.get("n_uncovered", 0)
        max_obs = coverage.get("max_actual_span_mm", 0)

        idx = int(name.split()[-1]) if name[-1].isdigit() else 1

        # Pick first column for size info (all same avg)
        first_col = scheme["columns"][0] if scheme.get("columns") else {}
        D = first_col.get("D_mm", "?")
        B = first_col.get("B_mm", "?")
        N_star = first_col.get("estimated_N_star_kN", "?")

        coverage_str = (
            "✓ OK"
            if coverage_ok
            else f"⚠ {n_uncov} zones exceed max span (worst: {max_obs} mm)"
        )

        lines += [
            f"{name}: {label}",
            f"  Columns:              {n_cols}",
            f"  Grid spacing:         {grid_mm} mm × {grid_mm} mm",
            f"  Avg tributary area:   {avg_trib} m² per column",
            f"  Indicative col size:  {D}×{B} mm  (N*≈{N_star} kN at base)",
            f"  Span coverage:        {coverage_str}",
            f"  Output PDF:           output/scheme_{idx}.pdf",
            f"  Tribli script:        output/scheme_{idx}_tribli.py",
            "",
        ]

    # ------------------------------------------------------------------
    # Engineer checklist
    # ------------------------------------------------------------------
    lines += [
        "WHAT THE ENGINEER SHOULD CHECK",
        _SUBDIV,
        "□  Column positions are architecturally acceptable",
        "□  Punching shear at slab-column connection",
        "    (critical for flat plates — use RAPT, RAM Concept, or SAFE)",
        "□  Lateral stability scheme",
        "    (shear walls / cores NOT included in this model)",
        "□  Transfer structures",
        "    (any columns that do not stack vertically between floors)",
        "□  Edge and corner column spans",
        "    (use more conservative span/depth ratios for these panels)",
        "□  Façade support",
        "    (perimeter columns or façade system — not addressed here)",
        "□  Column sizes",
        "    (indicative only — biaxial bending, slenderness not checked)",
        "□  Slab thickness",
        "    (verify with full deflection calculation)",
        "□  Footing scheme — not addressed in this tool",
        "",
        _w(
            "⚠️  THIS IS A STARTING POINT ONLY. THE GRID WILL NEED "
            "REFINEMENT BY A STRUCTURAL ENGINEER."
        ),
        _DIVIDER,
        "",
    ]

    return lines
