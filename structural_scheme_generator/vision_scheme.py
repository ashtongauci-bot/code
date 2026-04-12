"""
vision_scheme.py — Claude vision analysis of an architectural floor plan.

Sends each floor plan page image to Claude claude-sonnet-4-6 and extracts:
  • Floor plate boundary
  • Voids and exclusion zones
  • Forced column locations
  • Detected architectural grid module
  • Column-sensitive zones
  • Core walls
  • Façade line

⚠️  PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION
This module was generated algorithmically from span/depth rules of thumb.
It has NOT been designed or verified by a structural engineer.
It MUST be reviewed, checked, and approved by a registered structural engineer
before use in any design documentation or construction.
Punching shear, lateral stability, transfer structures, and serviceability
have NOT been checked. Column sizes are indicative only.
"""

from __future__ import annotations

import base64
import io
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import anthropic
import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# PDF → base-64 image helper
# ---------------------------------------------------------------------------

def page_to_base64(
    pdf_path: str,
    page_index: int,
    render_scale: float = 3.0,
) -> tuple[str, dict]:
    """
    Render a PDF page to a base-64-encoded PNG and return metadata.

    Returns:
        (b64_string, dims_dict)
        dims_dict keys: width_pts, height_pts, render_scale, width_px, height_px
    """
    MAX_PX = 7800  # Claude's hard limit is 8000px; stay under it

    doc = fitz.open(pdf_path)
    page = doc[page_index]
    rect = page.rect  # PDF units (points)

    # Auto-reduce render_scale if it would produce an image larger than MAX_PX
    max_dim_pts = max(rect.width, rect.height)
    effective_scale = render_scale
    if max_dim_pts * effective_scale > MAX_PX:
        effective_scale = MAX_PX / max_dim_pts
        print(
            f"  render_scale reduced from {render_scale} → {effective_scale:.2f} "
            f"to stay within Claude's {MAX_PX}px image limit."
        )

    mat = fitz.Matrix(effective_scale, effective_scale)
    pix = page.get_pixmap(matrix=mat, alpha=False)

    buf = io.BytesIO(pix.tobytes("png"))
    b64 = base64.standard_b64encode(buf.getvalue()).decode()

    dims = {
        "width_pts": rect.width,
        "height_pts": rect.height,
        "render_scale": effective_scale,
        "width_px": pix.width,
        "height_px": pix.height,
    }
    doc.close()
    return b64, dims


# ---------------------------------------------------------------------------
# Vision prompt builder
# ---------------------------------------------------------------------------

def _build_vision_prompt(dims: dict, config: dict, span_result: dict) -> str:
    drawing_scale = config["drawing_scale"]
    slab_mm = config["structural"]["slab_thickness_mm"]
    system = config["structural"]["slab_system"]
    load_type = config["structural"]["load_type"]
    max_span_mm = span_result["max_span_mm"]
    max_span_m = max_span_mm / 1000

    return f"""You are an experienced structural engineer performing a preliminary structural scheme study on an architectural floor plan. There are NO structural elements drawn on this plan — your job is to understand the architectural geometry and constraints so a column grid can be proposed.

Drawing information:
- Scale: {drawing_scale}
- Page dimensions: {dims['width_pts']:.1f}pt × {dims['height_pts']:.1f}pt
- Render scale: {dims['render_scale']}x (1 PDF point = {dims['render_scale']} pixels)
- Maximum allowable column spacing: {max_span_mm}mm ({max_span_m:.1f}m)
  (derived from slab thickness {slab_mm}mm, system: {system}, loads: {load_type})

COORDINATE SYSTEM: Return ALL coordinates in PDF POINTS (bottom-left origin).
Convert from image pixels:
  pdf_x = pixel_x / render_scale
  pdf_y = page_height_pts - (pixel_y / render_scale)
where page_height_pts = {dims['height_pts']:.1f}

ANALYSE THE PLAN AND RETURN:

1. FLOOR PLATE BOUNDARY
   The outer edge of the concrete slab. Trace the full perimeter as a polygon.

2. VOIDS AND EXCLUSIONS
   Areas where NO column should be placed:
   - Lift shafts, stair voids (structure goes around them)
   - Open plan areas flagged as column-free by architect (if labelled)
   - Carpark areas with clear span requirements
   - Areas outside the floor plate
   Return each as a polygon with a reason.

3. FORCED COLUMN ZONES
   Locations where a column IS required or strongly preferred:
   - Lift/stair core corners (columns typically at or near core walls)
   - Re-entrant corners of the floor plate
   - End of cantilevers
   - Mid-points of very long facade spans
   Return each as a point with a reason.

4. ARCHITECTURAL GRID
   Does the plan show a repeating module? (e.g. apartment layouts, office bays,
   carpark stalls). If yes, estimate the likely grid dimension in mm.
   Look for: repeated room widths, window spacing, structural grid lines already shown.

5. COLUMN-SENSITIVE ZONES
   Areas where columns would be architecturally disruptive:
   - Main entry lobbies
   - Large open plan office areas
   - Retail floor plates
   - Pool or recreation areas
   Return each as a polygon with a note. (These are not excluded, but the column
   grid should try to avoid them or minimise columns within them.)

6. CORE WALLS
   Any lift core, stair core, or service core shown. Return as polygons.
   These provide lateral stability and columns should be coordinated with them.

7. FACADE LINE
   The outer building facade as a polyline. Columns typically sit 0-500mm
   inside the facade or on the facade line in column-free facade systems.

Return ONLY this JSON (no other text, no markdown fences):
{{
  "floor_plate": [{{"x_pts": 0, "y_pts": 0}}],
  "voids": [
    {{"id": "V1", "reason": "lift shaft", "polygon": [{{"x_pts": 0, "y_pts": 0}}], "confidence": "high"}}
  ],
  "forced_columns": [
    {{"id": "FC1", "reason": "core corner", "x_pts": 0, "y_pts": 0, "confidence": "high"}}
  ],
  "architectural_grid_mm": null,
  "architectural_grid_confidence": "low",
  "architectural_grid_note": "",
  "column_sensitive_zones": [
    {{"id": "S1", "type": "lobby", "polygon": [{{"x_pts": 0, "y_pts": 0}}], "note": "Main entry — minimise columns"}}
  ],
  "core_walls": [
    {{"id": "CW1", "type": "lift", "polygon": [{{"x_pts": 0, "y_pts": 0}}]}}
  ],
  "facade_line": [{{"x_pts": 0, "y_pts": 0}}],
  "warnings": [],
  "general_notes": ""
}}"""


# ---------------------------------------------------------------------------
# API call + JSON extraction
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """
    Extract a JSON object from the model response.

    Robust to:
    - Leading/trailing prose
    - Markdown fences (``` or ''')
    - Any text before the opening { or after the closing }
    - Trailing commas before } or ] (common LLM output issue)
    """
    # Find the first { and last } — everything in between is the JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(
            f"No JSON object found in Claude response.\nRaw response:\n{text[:2000]}"
        )
    json_str = text[start : end + 1]

    # Remove trailing commas before } or ] — strict JSON forbids them
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Claude response is not valid JSON.\nExtracted:\n{json_str[:2000]}"
        ) from exc


def analyse_for_scheme(
    b64_image: str,
    dims: dict,
    config: dict,
    span_result: dict,
) -> dict:
    """
    Send the floor plan image to Claude and return the structured analysis dict.

    Args:
        b64_image:   Base-64-encoded PNG of the floor plan page.
        dims:        Page dimension metadata from page_to_base64().
        config:      Full tool config dict.
        span_result: Output of span_rules.get_max_span().

    Returns:
        Parsed analysis dict with an additional 'floor_plate_area_m2' key.
    """
    api_key = config.get("anthropic_api_key") or ""
    client = anthropic.Anthropic(api_key=api_key)

    prompt = _build_vision_prompt(dims, config, span_result)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
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

    # Compute floor plate area in m²
    analysis["floor_plate_area_m2"] = _polygon_area_m2(
        analysis.get("floor_plate", []),
        config["drawing_scale"],
    )

    return analysis


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _scale_factor(drawing_scale: str) -> int:
    """Return the numeric scale denominator, e.g. '1:100' → 100."""
    try:
        return int(drawing_scale.split(":")[1])
    except (IndexError, ValueError):
        return 100


def _polygon_area_m2(polygon_pts: list[dict], drawing_scale: str) -> float:
    """
    Compute the area of a polygon (given as list of {x_pts, y_pts} dicts)
    in real-world square metres, using the Shoelace formula.

    PDF points → mm: 1 pt = 25.4/72 mm at scale 1:1.
    At drawing scale 1:S, each pt represents S × 25.4/72 mm in reality.
    """
    if len(polygon_pts) < 3:
        return 0.0

    scale = _scale_factor(drawing_scale)
    pts_to_mm = scale * 25.4 / 72.0  # mm per PDF point (real world)

    xs = [p["x_pts"] * pts_to_mm for p in polygon_pts]
    ys = [p["y_pts"] * pts_to_mm for p in polygon_pts]
    n = len(xs)

    area_mm2 = abs(
        sum(xs[i] * ys[(i + 1) % n] - xs[(i + 1) % n] * ys[i] for i in range(n))
    ) / 2.0

    return area_mm2 / 1_000_000  # mm² → m²


# ---------------------------------------------------------------------------
# Diagnostic / debug helpers
# ---------------------------------------------------------------------------

def save_analysis_json(analysis: dict, output_path: str) -> None:
    """Persist raw Claude analysis to a JSON file for debugging."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as fh:
        json.dump(analysis, fh, indent=2)
    print(f"  Analysis JSON saved → {output_path}")


def load_analysis_json(path: str) -> dict:
    """Load a previously saved analysis JSON (for re-running without re-calling Claude)."""
    with open(path) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# CLI self-test (requires a real PDF and API key)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python vision_scheme.py <pdf_path> <config_json>")
        sys.exit(1)

    import json as _json
    with open(sys.argv[2]) as f:
        _config = _json.load(f)

    from span_rules import get_max_span

    _span = get_max_span(
        _config["structural"]["slab_thickness_mm"],
        _config["structural"]["slab_system"],
        _config["structural"]["load_type"],
    )

    _b64, _dims = page_to_base64(sys.argv[1], 0, _config.get("render_scale", 3))
    _analysis = analyse_for_scheme(_b64, _dims, _config, _span)
    save_analysis_json(_analysis, "output/analysis_page0.json")
    print(f"Floor plate area: {_analysis.get('floor_plate_area_m2', '?'):.0f} m²")
    print(f"Forced columns:   {len(_analysis.get('forced_columns', []))}")
    print(f"Voids:            {len(_analysis.get('voids', []))}")
