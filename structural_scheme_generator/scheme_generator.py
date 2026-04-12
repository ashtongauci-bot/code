"""
scheme_generator.py — Main CLI for the Structural Scheme Generator.

Usage:
  python scheme_generator.py                       # uses config.json
  python scheme_generator.py --config my.json      # specify config file
  python scheme_generator.py --schemes 3           # max schemes (default 3)
  python scheme_generator.py --no-review           # skip browser review UI
  python scheme_generator.py --reuse-analysis      # skip Claude call, reuse output/analysis_page*.json

⚠️  PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION
This column layout was generated algorithmically from span/depth rules of thumb.
It has NOT been designed or verified by a structural engineer.
It MUST be reviewed, checked, and approved by a registered structural engineer
before use in any design documentation or construction.
Punching shear, lateral stability, transfer structures, and serviceability
have NOT been checked. Column sizes are indicative only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Disclaimer — printed unconditionally at startup
# ---------------------------------------------------------------------------
_DISCLAIMER_BOX = """
=============================================================
⚠  PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION
This column layout was generated algorithmically from
span/depth rules of thumb.
It has NOT been designed or verified by a structural engineer.
It MUST be reviewed, checked, and approved by a registered
structural engineer before use in any design documentation
or construction.
Punching shear, lateral stability, transfer structures, and
serviceability have NOT been checked.
Column sizes are indicative only.
=============================================================
"""

_WHAT_NEXT = """
=============================================================
WHAT HAPPENS NEXT
=============================================================
1. Open the scheme PDF(s) in Tribli:
   File > Open PDF > select output/scheme_1.pdf
   Enter scale {drawing_scale} when prompted

2. OR run the Python script inside Tribli:
   File > Python Interpreter > open scheme_1_tribli.py

3. In Tribli:
   - Review all column positions visually
   - Run: Calculate > Tributary Areas
   - Run: Calculate > Column Loads
   - Check 3D view for sanity
   - Adjust any columns that don't work architecturally

4. CRITICAL ENGINEER CHECKS (not done by this tool):
   ✗ Punching shear at each column
   ✗ Lateral stability (shear walls / cores)
   ✗ Transfer structures
   ✗ Foundation scheme
   ✗ Actual deflection calculations (use RAPT or RAM Concept)
   ✗ Column design (biaxial bending, slenderness)
   ✗ Edge and facade columns
   ✗ Slab reinforcement

This tool provides a STARTING POINT for structural scheme
development. It does not replace structural engineering
judgement.
=============================================================
"""


def print_disclaimer() -> None:
    print(_DISCLAIMER_BOX)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(path: str) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        sys.exit(f"ERROR: Config file not found: {path}")
    with open(config_path) as f:
        return json.load(f)


def _resolve_api_key(config: dict) -> str:
    """Return API key from config or ANTHROPIC_API_KEY env var."""
    key = config.get("anthropic_api_key", "")
    if not key or key.startswith("your-"):
        key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        sys.exit(
            "ERROR: No Anthropic API key found.\n"
            "  Set ANTHROPIC_API_KEY env var or add it to config.json."
        )
    return key


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate preliminary column grid schemes from an architectural floor plan PDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "⚠  All output is PRELIMINARY and requires review by a structural engineer."
        ),
    )
    parser.add_argument(
        "--config", default="config.json",
        help="Path to config JSON file (default: config.json)"
    )
    parser.add_argument(
        "--schemes", type=int, default=3,
        help="Maximum number of schemes to generate (default: 3)"
    )
    parser.add_argument(
        "--no-review", action="store_true",
        help="Skip the browser review UI and write output immediately"
    )
    parser.add_argument(
        "--reuse-analysis", action="store_true",
        help="Skip Claude API call and reuse saved output/analysis_page*.json"
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()
    print_disclaimer()

    # ── 1. Load config ──────────────────────────────────────────────────
    config = load_config(args.config)
    config["anthropic_api_key"] = _resolve_api_key(config)

    structural = config["structural"]
    drawing_scale = config["drawing_scale"]

    # ── 2. Span analysis ────────────────────────────────────────────────
    from span_rules import get_max_span, suggest_column_size

    span_result = get_max_span(
        structural["slab_thickness_mm"],
        structural["slab_system"],
        structural["load_type"],
    )

    print("\nSLAB SPAN ANALYSIS")
    print(f"  Slab thickness:      {structural['slab_thickness_mm']} mm")
    print(f"  System:              {span_result['system_label']}")
    print(f"  Load type:           {span_result['load_label']}")
    print(f"  Effective depth:     {span_result['effective_depth_mm']} mm")
    print(f"  Span/depth ratio:    {span_result['span_depth_ratio_used']}")
    print(f"  Load factor:         {span_result['load_factor_applied']:.2f}")
    print(f"  MAX COLUMN SPACING:  {span_result['max_span_mm']} mm  "
          f"({span_result['max_span_mm'] / 1000:.1f} m)")

    if span_result["punching_warning"]:
        print(f"\n  ⚠  {span_result['punching_warning']}")

    if span_result["max_span_mm"] < 4000:
        print(
            f"\n⚠  WARNING: Calculated max span of {span_result['max_span_mm']} mm is very small.\n"
            f"   This slab thickness ({structural['slab_thickness_mm']} mm) may not be appropriate\n"
            f"   for the chosen system. Consider:\n"
            f"     • Increasing slab thickness\n"
            f"     • Switching to PT flat plate\n"
            f"     • Using band beams"
        )

    # ── 3. Per-level analysis & output ──────────────────────────────────
    from vision_scheme import analyse_for_scheme, page_to_base64, save_analysis_json, load_analysis_json
    from grid_generator import generate_column_grid, check_span_coverage
    from pdf_writer import write_scheme_pdf, write_scheme_tribli_script, write_comparison_pdf
    from report import write_scheme_report

    levels = config.get("levels", [{"page_index": 0, "level_name": "Typical Floor"}])

    for level in levels:
        page_idx = level.get("page_index", 0)
        level_name = level.get("level_name", f"Page {page_idx}")
        print(f"\n{'='*60}")
        print(f"LEVEL: {level_name}  (page {page_idx})")
        print(f"{'='*60}")

        # ------ Vision analysis ----------------------------------------
        analysis_path = f"output/analysis_page{page_idx}.json"

        if args.reuse_analysis and Path(analysis_path).exists():
            print(f"\nReusing saved analysis → {analysis_path}")
            analysis = load_analysis_json(analysis_path)
        else:
            print(f"\nAnalysing floor plan with Claude vision…")
            b64, dims = page_to_base64(
                config["pdf_path"], page_idx, config.get("render_scale", 3)
            )
            analysis = analyse_for_scheme(b64, dims, config, span_result)
            save_analysis_json(analysis, analysis_path)

        print(f"  Floor plate area:    {analysis.get('floor_plate_area_m2', '?'):.0f} m²")
        print(f"  Forced columns:      {len(analysis.get('forced_columns', []))}")
        print(f"  Void zones:          {len(analysis.get('voids', []))}")
        arch_grid = analysis.get("architectural_grid_mm")
        if arch_grid:
            print(
                f"  Architectural grid:  {arch_grid / 1000:.1f} m  "
                f"({analysis.get('architectural_grid_confidence', '?')} confidence)"
            )
        if analysis.get("warnings"):
            for w in analysis["warnings"]:
                print(f"  ⚠  {w}")

        # ------ Grid generation ----------------------------------------
        print(f"\nGenerating column grid schemes…")
        grid_result = generate_column_grid(
            analysis["floor_plate"],
            analysis.get("voids", []),
            analysis.get("forced_columns", []),
            span_result["max_span_mm"],
            analysis.get("architectural_grid_mm"),
            config,
        )

        # Limit to requested number of schemes
        grid_result["schemes"] = grid_result["schemes"][: args.schemes]

        # ------ Coverage check & column sizing -------------------------
        for scheme in grid_result["schemes"]:
            coverage = check_span_coverage(
                scheme["columns"],
                analysis["floor_plate"],
                span_result["max_span_mm"],
                grid_result["mm_to_pts_factor"],
            )
            scheme["coverage"] = coverage

            # Add indicative column sizes to every column
            for col in scheme["columns"]:
                size = suggest_column_size(
                    scheme["avg_tributary_m2"],
                    structural.get("num_floors", 1),
                    structural["load_type"],
                    structural.get("fc_column_MPa", 50),
                )
                col["D_mm"] = size["D_mm"]
                col["B_mm"] = size["B_mm"]
                col["estimated_N_star_kN"] = size["estimated_N_star_kN"]

            ok_str = (
                "✅ OK"
                if coverage["coverage_ok"]
                else f"⚠  {coverage['n_uncovered']} zones exceed max span"
            )
            print(
                f"\n  {scheme['scheme_name']}:\n"
                f"    Columns:       {scheme['n_columns']}\n"
                f"    Grid spacing:  {scheme['grid_spacing_mm'] / 1000:.1f} m\n"
                f"    Avg trib:      {scheme['avg_tributary_m2']:.1f} m²\n"
                f"    Coverage:      {ok_str}"
            )

        # ------ Optional review UI ------------------------------------
        if config.get("review_before_output", True) and not args.no_review:
            from review_scheme import run_scheme_review
            print(f"\nLaunching scheme review UI at http://localhost:5051 …")
            grid_result = run_scheme_review(grid_result, analysis, config)

        # ------ Write outputs -----------------------------------------
        print(f"\nWriting output files…")
        for idx, scheme in enumerate(grid_result["schemes"]):
            write_scheme_pdf(scheme, analysis, level, config, span_result, idx)
            write_scheme_tribli_script(scheme, analysis, level, config, span_result, idx)

        write_comparison_pdf(grid_result["schemes"], analysis, level, config, span_result)
        write_scheme_report(grid_result, analysis, config, span_result)

    # ── 4. Final summary ────────────────────────────────────────────────
    n = len(grid_result["schemes"])
    print(f"\n{'='*60}")
    print(f"OUTPUT FILES:")
    for i in range(1, n + 1):
        print(f"  output/scheme_{i}.pdf")
    print(f"  output/comparison.pdf  (all schemes overlaid)")
    for i in range(1, n + 1):
        print(f"  output/scheme_{i}_tribli.py")
    print(f"  output/scheme_report.txt")
    for level in levels:
        print(f"  output/analysis_page{level.get('page_index', 0)}.json")
    print(f"\n⚠  REMINDER: ALL SCHEMES ARE PRELIMINARY AND REQUIRE")
    print(f"   REVIEW BY A REGISTERED STRUCTURAL ENGINEER.")
    print(f"{'='*60}")
    print(_WHAT_NEXT.format(drawing_scale=drawing_scale))


if __name__ == "__main__":
    main()
