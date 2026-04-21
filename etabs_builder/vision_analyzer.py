"""
vision_analyzer.py — Claude vision analysis of marked-up architectural plans.

Sends each floor plan page to Claude claude-sonnet-4-6 and extracts:
  • Column locations and sizes (from markup annotations or inferred geometry)
  • Core wall outlines (lift cores, stair cores, service risers)
  • Slab / floor plate boundary
  • Floor usage zones (if labelled)
  • Grid reference lines and dimensions

The plans are assumed to have structural elements MARKED ON THEM (column
squares, core hatching, size annotations like "600×600" or "750Ø").

All coordinates are returned in PDF POINTS (bottom-left origin) and must be
converted to real-world metres via the drawing scale.

⚠️  PRELIMINARY — output requires structural engineer review.
"""

from __future__ import annotations

import base64
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

import anthropic
import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# PDF → base-64 PNG
# ---------------------------------------------------------------------------

def page_to_base64(
    pdf_path: str,
    page_index: int,
    render_scale: float = 3.0,
) -> tuple[str, dict]:
    """
    Render a PDF page to a base-64-encoded PNG.

    Returns (b64_string, dims) where dims contains:
      width_pts, height_pts, render_scale, width_px, height_px
    """
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    rect = page.rect

    mat = fitz.Matrix(render_scale, render_scale)
    pix = page.get_pixmap(matrix=mat, alpha=False)

    buf = io.BytesIO(pix.tobytes("png"))
    b64 = base64.standard_b64encode(buf.getvalue()).decode()

    dims = {
        "width_pts": rect.width,
        "height_pts": rect.height,
        "render_scale": render_scale,
        "width_px": pix.width,
        "height_px": pix.height,
    }
    doc.close()
    return b64, dims


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_etabs_prompt(dims: dict, config: dict, level_cfg: dict) -> str:
    drawing_scale = config.get("drawing_scale", "1:100")
    floor_usage = level_cfg.get("floor_usage", "office")
    level_name = level_cfg.get("name", "Typical Floor")
    slab_thk = config.get("structural", {}).get("slab_thickness_mm", 250)

    return f"""You are an experienced structural engineer reviewing a marked-up architectural floor plan.
The plan has structural elements annotated on it — column positions (shown as solid squares or circles),
core walls (shown as hatched/shaded rectangular outlines), and possibly size annotations.

Your task is to extract all structural geometry so it can be imported into an ETABS structural model.

Drawing information:
- Level: {level_name}
- Floor usage: {floor_usage}
- Drawing scale: {drawing_scale}
- Slab thickness (from config): {slab_thk} mm
- Page size: {dims['width_pts']:.1f} pt × {dims['height_pts']:.1f} pt
- Render scale: {dims['render_scale']}× (1 PDF point = {dims['render_scale']} pixels in the image)

COORDINATE SYSTEM:
Return ALL coordinates in PDF POINTS with BOTTOM-LEFT ORIGIN.
Convert from image pixel coordinates:
  pdf_x = pixel_x / {dims['render_scale']}
  pdf_y = {dims['height_pts']:.1f} - (pixel_y / {dims['render_scale']})

═══════════════════════════════════════════════════════
WHAT TO EXTRACT:
═══════════════════════════════════════════════════════

1. COLUMNS
   - Look for: solid filled squares, solid filled circles, cross-hatched squares,
     or small rectangles — these are column cross-sections shown in plan view.
   - Also look for annotation labels such as "600×600", "500×500", "750Ø", "C1", "C2".
   - For each column, return:
       • Centre position (x_pts, y_pts)
       • Detected size (width_mm × depth_mm), or null if not labelled
       • Shape: "rectangular" or "circular"
       • Confidence: "high" (clearly drawn + labelled), "medium" (drawn, no label),
         "low" (inferred from geometry)

2. CORE WALLS
   - Look for: thick solid lines forming closed rectangles or L-shapes,
     hatched regions, or areas labelled "LIFT", "STAIR", "CORE", "RISER".
   - Each core has a closed polygon boundary. Decompose L-shaped cores into
     their constituent rectangle(s) if needed.
   - For each core, return the FULL OUTER POLYGON of the core boundary.
   - Also return a list of individual wall CENTRELINE segments (start/end points)
     forming each side of the core, with an estimated wall thickness.
   - Wall type: "lift", "stair", "service", "shear" — infer from context.

3. SLAB / FLOOR PLATE BOUNDARY
   - The outer edge of the concrete slab. Trace the full perimeter as a polygon.
   - If the plate has re-entrant corners or steps, include them.
   - Exclude any voids (lift shafts, stair voids, atria) from this polygon —
     return them separately in the voids list.

4. SLAB VOIDS
   - Openings through the slab (lift shafts, stairs, atria, plant voids).
   - Return each void as a polygon.

5. FLOOR USAGE ZONES (if identifiable)
   - If different areas of the floor have different uses (office, retail, lobby,
     plant, carpark), return them as labelled polygons.
   - Otherwise return the whole plate as a single zone with the floor usage
     specified in the drawing information above.

6. DIMENSION ANNOTATIONS (if present)
   - Any dimension strings visible on the plan (e.g. "8500", "7.2m", "3600").
   - Return up to 10 key dimensions with start/end points to help calibrate
     the coordinate scale.

7. STRUCTURAL GRID LINES (if shown)
   - Any grid bubbles or grid lines (A, B, C or 1, 2, 3).
   - Return as named lines with start/end points.

═══════════════════════════════════════════════════════
OUTPUT FORMAT (return ONLY this JSON, no markdown):
═══════════════════════════════════════════════════════

{{
  "columns": [
    {{
      "id": "C1",
      "x_pts": 0,
      "y_pts": 0,
      "width_mm": 600,
      "depth_mm": 600,
      "shape": "rectangular",
      "label": "600x600",
      "confidence": "high",
      "notes": ""
    }}
  ],
  "core_walls": [
    {{
      "id": "CORE1",
      "type": "lift",
      "outer_polygon": [{{"x_pts": 0, "y_pts": 0}}],
      "wall_segments": [
        {{
          "id": "W1",
          "x1_pts": 0, "y1_pts": 0,
          "x2_pts": 0, "y2_pts": 0,
          "thickness_mm": 250
        }}
      ],
      "notes": ""
    }}
  ],
  "floor_plate": [{{"x_pts": 0, "y_pts": 0}}],
  "slab_voids": [
    {{
      "id": "V1",
      "type": "lift_shaft",
      "polygon": [{{"x_pts": 0, "y_pts": 0}}]
    }}
  ],
  "usage_zones": [
    {{
      "id": "Z1",
      "usage": "office",
      "polygon": [{{"x_pts": 0, "y_pts": 0}}]
    }}
  ],
  "dimension_annotations": [
    {{
      "value_mm": 8500,
      "x1_pts": 0, "y1_pts": 0,
      "x2_pts": 0, "y2_pts": 0
    }}
  ],
  "grid_lines": [
    {{
      "label": "A",
      "x1_pts": 0, "y1_pts": 0,
      "x2_pts": 0, "y2_pts": 0
    }}
  ],
  "warnings": [],
  "general_notes": ""
}}"""


# ---------------------------------------------------------------------------
# API call + JSON extraction
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """Extract JSON from Claude response, tolerating markdown fences."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Claude response is not valid JSON.\nRaw:\n{text[:3000]}"
        ) from exc


def analyse_plan_page(
    b64_image: str,
    dims: dict,
    config: dict,
    level_cfg: dict,
    api_key: str = "",
) -> dict:
    """
    Send one floor plan page image to Claude and return the structured analysis.

    Args:
        b64_image:  Base-64 PNG of the floor plan page.
        dims:       Page dimension metadata from page_to_base64().
        config:     Full tool config dict.
        level_cfg:  Config for this specific level (name, floor_usage, etc.).
        api_key:    Anthropic API key (falls back to ANTHROPIC_API_KEY env var).

    Returns:
        Parsed analysis dict with added coordinate conversion metadata.
    """
    client = anthropic.Anthropic(api_key=api_key or None)
    prompt = _build_etabs_prompt(dims, config, level_cfg)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64_image,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    )

    raw = message.content[0].text
    analysis = _extract_json(raw)

    # Attach conversion metadata so callers can convert pts → metres
    scale_str = config.get("drawing_scale", "1:100")
    try:
        scale = int(scale_str.split(":")[1])
    except (IndexError, ValueError):
        scale = 100
    analysis["_meta"] = {
        "drawing_scale": scale_str,
        "scale_denominator": scale,
        "mm_per_pt": scale * 25.4 / 72.0,
        "page_height_pts": dims["height_pts"],
        "level_name": level_cfg.get("name", ""),
    }

    return analysis


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------

def pts_to_m(value_pts: float, mm_per_pt: float) -> float:
    return value_pts * mm_per_pt / 1000.0


def polygon_pts_to_m(polygon: list[dict], mm_per_pt: float) -> list[tuple[float, float]]:
    """Convert a list of {x_pts, y_pts} dicts to a list of (x_m, y_m) tuples."""
    return [(pts_to_m(p["x_pts"], mm_per_pt), pts_to_m(p["y_pts"], mm_per_pt)) for p in polygon]


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def save_analysis(analysis: dict, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"  Analysis saved → {path}")


def load_analysis(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# CLI self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python vision_analyzer.py <pdf> <config.json> <page_index>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    cfg_path = sys.argv[2]
    page_idx = int(sys.argv[3])

    with open(cfg_path) as f:
        cfg = json.load(f)

    level_cfg = cfg["levels"][page_idx] if page_idx < len(cfg["levels"]) else {}
    b64, dims = page_to_base64(pdf_path, page_idx, cfg.get("render_scale", 3))
    analysis = analyse_plan_page(b64, dims, cfg, level_cfg, cfg.get("anthropic_api_key", ""))
    save_analysis(analysis, f"output/analysis_page{page_idx}.json")

    print(f"Columns found:    {len(analysis.get('columns', []))}")
    print(f"Core walls found: {len(analysis.get('core_walls', []))}")
    print(f"Warnings:         {analysis.get('warnings', [])}")
