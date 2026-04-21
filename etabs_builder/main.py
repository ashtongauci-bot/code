"""
main.py — CLI entry point for the ETABS Builder.

Usage:
  python main.py [options]

Options:
  --config PATH          Path to config.json (default: config.json)
  --pdf PATH             Override PDF path from config
  --reuse-analysis       Load cached analysis JSONs from output/ instead of
                         re-calling Claude (saves API cost on re-runs)
  --no-e2k               Skip E2K file output
  --no-api-script        Skip ETABS API Python script output
  --output DIR           Output directory (default: output)

Output files:
  output/build_etabs_model.py  — Python script for ETABS COM API (Windows)
  output/<project>.e2k         — E2K text file (ETABS import)
  output/analysis_page*.json   — Cached vision analysis (one per PDF page)
  output/model_report.txt      — Human-readable summary

⚠️  PRELIMINARY STRUCTURAL TOOL — NOT FOR CONSTRUCTION
All generated element sizes are indicative only. This tool does not perform
structural design. All output must be reviewed by a registered structural
engineer before use in any design documentation or construction.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from vision_analyzer import page_to_base64, analyse_plan_page, save_analysis, load_analysis
from model_builder import build_model
from etabs_api_script import write_script
from e2k_writer import write_e2k
from load_definitions import get_loads


DISCLAIMER = """\
╔══════════════════════════════════════════════════════════════════════════╗
║  ⚠️   PRELIMINARY STRUCTURAL MODEL — NOT FOR CONSTRUCTION               ║
║                                                                          ║
║  All element sizes, positions, and loads are indicative only.            ║
║  This tool does not perform structural design.                           ║
║  Output MUST be reviewed by a registered structural engineer             ║
║  before use in any design, documentation, or construction.               ║
╚══════════════════════════════════════════════════════════════════════════╝"""


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        cfg = json.load(f)
    return cfg


def resolve_pdf_path(config: dict, override: str | None) -> str:
    path = override or config.get("pdf_path", "")
    if not path:
        raise ValueError("No PDF path specified (set 'pdf_path' in config.json or use --pdf)")
    if not Path(path).exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    return path


def get_api_key(config: dict) -> str:
    return (
        config.get("anthropic_api_key", "")
        or os.environ.get("ANTHROPIC_API_KEY", "")
    )


# ---------------------------------------------------------------------------
# Vision analysis
# ---------------------------------------------------------------------------

def run_vision_analysis(
    pdf_path: str,
    config: dict,
    output_dir: str,
    reuse: bool,
) -> dict[int, dict]:
    """
    Run Claude vision analysis on each unique page_index in the config.
    Returns dict mapping page_index → analysis dict.
    """
    api_key = get_api_key(config)
    render_scale = config.get("render_scale", 3)

    # Collect unique pages needed
    pages_needed: dict[int, dict] = {}   # page_index → first level cfg that uses it
    for lv in config.get("levels", []):
        pi = lv.get("page_index", 0)
        if pi not in pages_needed:
            pages_needed[pi] = lv

    analyses: dict[int, dict] = {}

    for page_idx, level_cfg in sorted(pages_needed.items()):
        cache_path = Path(output_dir) / f"analysis_page{page_idx}.json"

        if reuse and cache_path.exists():
            print(f"  [page {page_idx}] Loading cached analysis: {cache_path}")
            analyses[page_idx] = load_analysis(str(cache_path))
            continue

        if not api_key:
            raise ValueError(
                "Anthropic API key required for vision analysis. "
                "Set 'anthropic_api_key' in config.json or ANTHROPIC_API_KEY env var."
            )

        print(f"  [page {page_idx}] Running vision analysis (Claude claude-sonnet-4-6)...")
        b64, dims = page_to_base64(pdf_path, page_idx, render_scale)
        analysis = analyse_plan_page(b64, dims, config, level_cfg, api_key)
        save_analysis(analysis, str(cache_path))
        analyses[page_idx] = analysis

        n_cols = len(analysis.get("columns", []))
        n_cores = len(analysis.get("core_walls", []))
        warnings = analysis.get("warnings", [])
        print(f"    → {n_cols} columns, {n_cores} cores detected")
        if warnings:
            for w in warnings:
                print(f"    ⚠ {w}")

    return analyses


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_report(model, config: dict, output_dir: str) -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    report_path = Path(output_dir) / "model_report.txt"

    lines = [
        "=" * 72,
        f"  ETABS MODEL REPORT — {model.project_name}",
        "=" * 72,
        "",
        DISCLAIMER,
        "",
        "PROJECT",
        f"  Name:          {model.project_name}",
        f"  Base RL:       {model.base_rl_m:.3f} m",
        f"  Stories:       {len(model.levels)}",
        "",
        "LEVELS",
    ]

    for lv in model.levels:
        loads = get_loads(lv.floor_usage)
        lines.append(
            f"  {lv.name:<20}  RL {lv.rl_m:.3f} m  "
            f"H={lv.height_m:.1f} m  "
            f"{lv.floor_usage:<20}  "
            f"SDL={loads['sdl_kpa']:.1f} + LL={loads['ll_kpa']:.1f} kPa"
        )

    lines += ["", "MATERIALS"]
    for mat in model.materials:
        lines.append(
            f"  {mat.label:<10}  fc'={mat.fc_mpa:.0f} MPa  "
            f"Ec={mat.E_mpa/1000:.0f} GPa  "
            f"γ={mat.unit_weight_kn_m3:.0f} kN/m³"
        )

    lines += ["", "COLUMN SECTIONS"]
    for cs in model.column_sections:
        lines.append(
            f"  {cs.label:<18}  {cs.depth_mm:.0f}×{cs.width_mm:.0f} mm  "
            f"fc'={cs.material}"
        )

    lines += ["", "WALL SECTIONS"]
    for ws in model.wall_sections:
        lines.append(f"  {ws.label:<18}  {ws.thickness_mm:.0f} mm  fc'={ws.material}")

    lines += ["", "SLAB SECTIONS"]
    for ss in model.slab_sections:
        lines.append(f"  {ss.label:<18}  {ss.thickness_mm:.0f} mm  fc'={ss.material}")

    lines += [
        "",
        "ELEMENT COUNTS",
        f"  Columns:  {len(model.columns)} instances "
        f"({len(model.column_sections)} unique sections)",
        f"  Walls:    {len(model.walls)} panel segments",
        f"  Slabs:    {len(model.slabs)} panels",
        "",
        "LOAD PATTERNS",
    ]
    for lp in model.load_patterns:
        lines.append(f"  {lp.name:<30}  type: {lp.pattern_type}")

    lines += [
        "",
        "ENGINEER CHECKLIST",
        "  [ ] Verify column positions match structural intent",
        "  [ ] Check column sizes against hand calculation",
        "  [ ] Verify core wall positions and thicknesses",
        "  [ ] Confirm slab extents and any openings",
        "  [ ] Check load intensities for each usage type",
        "  [ ] Add lateral load cases (wind, seismic) per AS1170.2 / AS1170.4",
        "  [ ] Add transfer structures if required",
        "  [ ] Check punching shear at columns (AS3600 S9.3)",
        "  [ ] Check wall stability and slenderness (AS3600 S11)",
        "  [ ] Verify model with hand reactions before design",
        "",
        "=" * 72,
        "PRELIMINARY ONLY — NOT FOR CONSTRUCTION",
        "Generated by etabs_builder. All output requires engineer review.",
        "=" * 72,
    ]

    text = "\n".join(lines)
    report_path.write_text(text, encoding="utf-8")
    print(f"  Report → {report_path}")
    return str(report_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="ETABS Builder — build ETABS models from marked-up architectural plans",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="⚠️  PRELIMINARY TOOL — all output requires structural engineer review.",
    )
    p.add_argument("--config", default="config.json", help="Path to config.json")
    p.add_argument("--pdf", default=None, help="Override PDF path from config")
    p.add_argument(
        "--reuse-analysis", action="store_true",
        help="Load cached Claude analysis from output/ (avoid re-running vision API)"
    )
    p.add_argument("--no-e2k", action="store_true", help="Skip E2K file generation")
    p.add_argument("--no-api-script", action="store_true", help="Skip ETABS API script generation")
    p.add_argument("--output", default="output", help="Output directory (default: output)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    print()
    print(DISCLAIMER)
    print()

    # Load config
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"ERROR: Config not found: {args.config}")
        print("       Copy config.json.example to config.json and fill in your details.")
        return 1

    # Resolve PDF
    try:
        pdf_path = resolve_pdf_path(config, args.pdf)
    except (ValueError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        return 1

    output_dir = args.output
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    print(f"Project: {config.get('project', {}).get('name', 'Unnamed')}")
    print(f"PDF:     {pdf_path}")
    print(f"Levels:  {len(config.get('levels', []))}")
    print(f"Scale:   {config.get('drawing_scale', '1:100')}")
    print()

    # --- Vision analysis ---
    print("STEP 1 — Vision analysis")
    try:
        analyses = run_vision_analysis(pdf_path, config, output_dir, args.reuse_analysis)
    except (ValueError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        return 1

    if not analyses:
        print("ERROR: No analysis results. Check PDF path and page_index values in config.")
        return 1

    # --- Build model ---
    print()
    print("STEP 2 — Building structural model")
    model = build_model(analyses, config)
    print(f"  Columns:  {len(model.columns)}")
    print(f"  Walls:    {len(model.walls)}")
    print(f"  Slabs:    {len(model.slabs)}")

    # --- Write outputs ---
    print()
    print("STEP 3 — Writing output files")

    if not args.no_api_script:
        write_script(model, output_dir)

    if not args.no_e2k:
        write_e2k(model, output_dir)

    write_report(model, config, output_dir)

    print()
    print("Done.")
    print()
    print("NEXT STEPS:")
    print("  Windows (ETABS API):  pip install comtypes && python output/build_etabs_model.py")
    print("  Any machine (E2K):    File → Import → ETABS Text File → output/*.e2k")
    print()
    print("⚠️  All output is preliminary. Review with a registered structural engineer.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
