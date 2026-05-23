"""
main.py — CLI for sketch_to_revit.

Usage:
  python main.py sketch.png
  python main.py sketch.jpg --output my_model.py
  python main.py sketch.pdf --save-analysis
  python main.py --reuse-analysis analysis.json

⚠️  PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION
All generated scripts must be reviewed by a registered structural engineer.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


_DISCLAIMER = """
=============================================================
⚠  PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION
This model was generated algorithmically from a hand-drawn sketch.
It has NOT been designed or verified by a structural engineer.
It MUST be reviewed and approved by a registered structural engineer
before use in any design documentation or construction.
Column sizes, beam sizes, and slab thicknesses are indicative only.
=============================================================
"""

_WHAT_NEXT = """
=============================================================
WHAT TO DO WITH THE GENERATED SCRIPT
=============================================================
1. Open Revit with a structural or architectural project template.

2. Load structural families if not already in the project:
     Structural Columns:
       Insert > Load Family > Structural > Columns > Concrete
       (e.g. "Concrete-Rectangular-Column.rfa")
     Structural Framing:
       Insert > Load Family > Structural > Framing > Concrete
       (e.g. "Concrete-Rectangular Beam.rfa")

3. Make sure at least one Level exists in the project
   (View > Plan Views — check for Level 1, Level 2, etc.)

4. Open pyRevit Shell or Revit Python Shell.

5. Open {script_path} in the shell and click Run.

6. REVIEW the model with your structural engineer:
   • Check all column and beam positions in the 3D view
   • Resize sections to suit the actual design
   • Verify slab boundaries and thickness
   • Run a proper structural analysis before construction

=============================================================
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a hand-drawn structural sketch to a Revit pyRevit script.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="⚠  All output is PRELIMINARY and requires structural engineer review.",
    )
    parser.add_argument(
        "sketch",
        nargs="?",
        help="Path to the sketch image (PNG, JPG, JPEG, GIF, WEBP, PDF).",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output path for the Revit script (default: output/model_revit.py).",
    )
    parser.add_argument(
        "--save-analysis",
        action="store_true",
        help="Save the raw Claude analysis JSON to output/analysis.json.",
    )
    parser.add_argument(
        "--reuse-analysis",
        metavar="ANALYSIS_JSON",
        default=None,
        help="Skip the Claude API call and reuse a previously saved analysis JSON.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Anthropic API key (overrides ANTHROPIC_API_KEY env var).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(_DISCLAIMER)

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    # ── 1. Get analysis ──────────────────────────────────────────────────
    if args.reuse_analysis:
        analysis_path = Path(args.reuse_analysis)
        if not analysis_path.exists():
            sys.exit(f"ERROR: Analysis file not found: {args.reuse_analysis}")
        print(f"Reusing saved analysis → {analysis_path}")
        with open(analysis_path) as f:
            analysis = json.load(f)

    else:
        if not args.sketch:
            sys.exit(
                "ERROR: Provide a sketch image path.\n"
                "  python main.py my_sketch.png\n"
                "  python main.py --help"
            )
        sketch_path = Path(args.sketch)
        if not sketch_path.exists():
            sys.exit(f"ERROR: Sketch file not found: {args.sketch}")

        if not api_key:
            sys.exit(
                "ERROR: No Anthropic API key found.\n"
                "  Set the ANTHROPIC_API_KEY environment variable, or use --api-key."
            )

        print(f"Analysing sketch: {sketch_path.name}")
        print("Sending to Claude vision…")

        from sketch_analyzer import analyse_sketch
        analysis = analyse_sketch(str(sketch_path), api_key=api_key)

    # ── 2. Print analysis summary ────────────────────────────────────────
    print()
    print("SKETCH ANALYSIS RESULT")
    print(f"  Sketch type:        {analysis.get('sketch_type', '?')}")
    print(f"  Confidence:         {analysis.get('confidence', '?')}")
    print(f"  Floors:             {analysis.get('num_floors', '?')}")
    print(f"  Floor-to-floor:     {analysis.get('floor_to_floor_height_m', '?')} m")
    print(f"  Columns extracted:  {len(analysis.get('columns', []))}")
    print(f"  Beams extracted:    {len(analysis.get('beams', []))}")
    print(f"  Slabs extracted:    {len(analysis.get('slabs', []))}")
    if analysis.get("scale_notes"):
        print(f"  Scale notes:        {analysis['scale_notes']}")
    for w in analysis.get("warnings", []):
        print(f"  ⚠  {w}")

    # ── 3. Optionally save analysis JSON ─────────────────────────────────
    if args.save_analysis or args.reuse_analysis:
        analysis_out = Path("output") / "analysis.json"
        analysis_out.parent.mkdir(parents=True, exist_ok=True)
        with open(analysis_out, "w") as f:
            json.dump(analysis, f, indent=2)
        print(f"\nAnalysis JSON saved → {analysis_out}")

    # ── 4. Generate Revit script ─────────────────────────────────────────
    from revit_generator import write_revit_script
    script_path = write_revit_script(analysis, output_path=args.output)
    print(f"\nRevit script written → {script_path}")

    print(_WHAT_NEXT.format(script_path=script_path))


if __name__ == "__main__":
    main()
