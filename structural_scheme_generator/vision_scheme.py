"""
vision_scheme.py - Claude vision analysis of an architectural floor plan.

Sends each floor plan page image to Claude claude-sonnet-4-6 and extracts:
  - Floor plate boundary
  - Voids and exclusion zones
  - Forced column locations
  - Detected architectural grid module
  - Column-sensitive zones
  - Core walls
  - Facade line

WARNING: PRELIMINARY STRUCTURAL SCHEME - NOT FOR CONSTRUCTION
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
import re
import sys
from pathlib import Path

import anthropic
import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# PDF to base-64 image helper
# ---------------------------------------------------------------------------

def page_to_base64(pdf_path, page_index, render_scale=3.0):
    MAX_PX = 7800

    doc = fitz.open(pdf_path)
    page = doc[page_index]
    rect = page.rect

    max_dim_pts = max(rect.width, rect.height)
    effective_scale = render_scale
    if max_dim_pts * effective_scale > MAX_PX:
        effective_scale = MAX_PX / max_dim_pts
        print(
            "  render_scale reduced from " + str(render_scale) +
            " to " + str(round(effective_scale, 2)) +
            " to stay within Claude's " + str(MAX_PX) + "px image limit."
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

def _build_vision_prompt(dims, config, span_result):
    drawing_scale = config["drawing_scale"]
    slab_mm = config["structural"]["slab_thickness_mm"]
    system = config["structural"]["slab_system"]
    load_type = config["structural"]["load_type"]
    max_span_mm = span_result["max_span_mm"]
    max_span_m = max_span_mm / 1000

    return (
        "You are an experienced structural engineer performing a preliminary structural scheme study "
        "on an architectural floor plan. There are NO structural elements drawn on this plan - "
        "your job is to understand the architectural geometry and constraints so a column grid can be proposed.\n\n"
        "Drawing information:\n"
        "- Scale: " + drawing_scale + "\n"
        "- Page dimensions: " + str(round(dims["width_pts"], 1)) + "pt x " + str(round(dims["height_pts"], 1)) + "pt\n"
        "- Render scale: " + str(round(dims["render_scale"], 2)) + "x\n"
        "- Maximum allowable column spacing: " + str(max_span_mm) + "mm (" + str(round(max_span_m, 1)) + "m)\n"
        "  (derived from slab thickness " + str(slab_mm) + "mm, system: " + system + ", loads: " + load_type + ")\n\n"
        "COORDINATE SYSTEM: Return ALL coordinates in PDF POINTS (bottom-left origin).\n"
        "Convert from image pixels:\n"
        "  pdf_x = pixel_x / render_scale\n"
        "  pdf_y = page_height_pts - (pixel_y / render_scale)\n"
        "where page_height_pts = " + str(round(dims["height_pts"], 1)) + "\n\n"
        "IMPORTANT: Keep ALL polygon point counts very low to avoid response truncation.\n\n"
        "Return ONLY a JSON object (no other text, no markdown fences) with these keys:\n"
        "  floor_plate: array of {x_pts, y_pts} - MAX 16 POINTS, simplified outline only\n"
        "  voids: array of {id, reason, polygon, confidence} - polygon MAX 6 points each\n"
        "  forced_columns: array of {id, reason, x_pts, y_pts, confidence}\n"
        "  architectural_grid_mm: number or null\n"
        "  architectural_grid_confidence: 'high', 'medium', or 'low'\n"
        "  architectural_grid_note: string under 100 chars\n"
        "  column_sensitive_zones: array of {id, type, polygon, note} - polygon MAX 6 points\n"
        "  core_walls: array of {id, type, polygon} - polygon MAX 6 points each\n"
        "  facade_line: array of {x_pts, y_pts} - MAX 16 POINTS\n"
        "  warnings: array of strings, each under 80 chars, max 5 warnings\n"
        "  general_notes: string under 150 chars\n\n"
        "Return ONLY the JSON object. No explanation before or after. No markdown."
    )


# ---------------------------------------------------------------------------
# JSON extraction - robust to LLM formatting quirks
# ---------------------------------------------------------------------------

# Minimum keys required in a valid analysis response
_REQUIRED_KEYS = [
    "floor_plate", "voids", "forced_columns", "architectural_grid_mm",
    "architectural_grid_confidence", "architectural_grid_note",
    "column_sensitive_zones", "core_walls", "facade_line",
    "warnings", "general_notes",
]

_ANALYSIS_DEFAULTS = {
    "floor_plate": [],
    "voids": [],
    "forced_columns": [],
    "architectural_grid_mm": None,
    "architectural_grid_confidence": "low",
    "architectural_grid_note": "",
    "column_sensitive_zones": [],
    "core_walls": [],
    "facade_line": [],
    "warnings": ["JSON parse failed - analysis incomplete, re-run recommended"],
    "general_notes": "Automatic analysis partially failed.",
}


def _sanitize(text):
    """Replace common problematic Unicode and fix trailing commas."""
    # Replace characters that look like JSON syntax but aren't
    text = text.replace("\u2018", "'").replace("\u2019", "'")   # curly single quotes
    text = text.replace("\u201c", '\\"').replace("\u201d", '\\"')  # curly double → escaped
    text = text.replace("\u2014", "-").replace("\u2013", "-")    # em/en dash
    text = text.replace("\u00a0", " ")                           # non-breaking space
    # Remove trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text


def _close_open_brackets(json_str):
    """Walk the string tracking bracket depth and append any missing closers."""
    stack = []
    in_string = False
    escape_next = False
    for ch in json_str:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch in ("{", "["):
                stack.append(ch)
            elif ch == "}" and stack and stack[-1] == "{":
                stack.pop()
            elif ch == "]" and stack and stack[-1] == "[":
                stack.pop()
    closing = "".join("}" if c == "{" else "]" for c in reversed(stack))
    return json_str + closing


def _progressive_parse(json_str):
    """
    Try parsing the string, then progressively trim from the end at each
    closing bracket until we get something json.loads accepts.
    Handles both truncation and mid-string syntax errors.
    """
    # Collect positions of all } and ] (outside strings) as trim points
    trim_positions = []
    in_string = False
    escape_next = False
    for i, ch in enumerate(json_str):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string and ch in ("}", "]"):
            trim_positions.append(i)

    # Try from longest to shortest
    for pos in reversed(trim_positions):
        candidate = json_str[:pos + 1]
        candidate = re.sub(r",\s*$", "", candidate.rstrip())
        candidate = _close_open_brackets(candidate)
        try:
            result = json.loads(candidate)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            continue

    return None


def _extract_json(text):
    """
    Extract and parse a JSON object from the model response.
    Handles: prose before/after, markdown fences, trailing commas,
    Unicode quirks, truncated responses, and mid-string syntax errors.
    Falls back to partial defaults rather than crashing.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        print("  WARNING: No JSON object found in Claude response. Using defaults.")
        return dict(_ANALYSIS_DEFAULTS)

    raw = _sanitize(text[start:end + 1])

    # Attempt 1: direct parse after sanitization
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Attempt 2: progressive trim from end
    result = _progressive_parse(raw)
    if result is not None:
        print("  NOTE: Claude response was partially malformed — recovered what we could.")
        # Fill in any missing keys with defaults
        for key, default in _ANALYSIS_DEFAULTS.items():
            if key not in result:
                result[key] = default
        return result

    # Attempt 3: give up gracefully — return defaults so tool doesn't crash
    print("  WARNING: Could not parse Claude response JSON. Using empty defaults.")
    print("  Recommend re-running — the column grid will use bounding-box fallback.")
    return dict(_ANALYSIS_DEFAULTS)


# ---------------------------------------------------------------------------
# Main API call
# ---------------------------------------------------------------------------

def analyse_for_scheme(b64_image, dims, config, span_result):
    """Send the floor plan image to Claude and return the structured analysis dict."""
    api_key = config.get("anthropic_api_key") or ""
    client = anthropic.Anthropic(api_key=api_key)

    prompt = _build_vision_prompt(dims, config, span_result)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
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

    # If floor_plate is empty (parse failed), fall back to full page bounding box
    if not analysis.get("floor_plate"):
        print("  WARNING: floor_plate empty — using page bounding box as fallback.")
        w, h = dims["width_pts"], dims["height_pts"]
        margin = min(w, h) * 0.03
        analysis["floor_plate"] = [
            {"x_pts": margin,     "y_pts": margin},
            {"x_pts": w - margin, "y_pts": margin},
            {"x_pts": w - margin, "y_pts": h - margin},
            {"x_pts": margin,     "y_pts": h - margin},
        ]

    analysis["floor_plate_area_m2"] = _polygon_area_m2(
        analysis.get("floor_plate", []),
        config["drawing_scale"],
    )

    return analysis


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _scale_factor(drawing_scale):
    try:
        return int(drawing_scale.split(":")[1])
    except (IndexError, ValueError):
        return 100


def _polygon_area_m2(polygon_pts, drawing_scale):
    if len(polygon_pts) < 3:
        return 0.0

    scale = _scale_factor(drawing_scale)
    pts_to_mm = scale * 25.4 / 72.0

    xs = [p["x_pts"] * pts_to_mm for p in polygon_pts]
    ys = [p["y_pts"] * pts_to_mm for p in polygon_pts]
    n = len(xs)

    area_mm2 = abs(
        sum(xs[i] * ys[(i + 1) % n] - xs[(i + 1) % n] * ys[i] for i in range(n))
    ) / 2.0

    return area_mm2 / 1000000


# ---------------------------------------------------------------------------
# Save / load helpers
# ---------------------------------------------------------------------------

def save_analysis_json(analysis, output_path):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as fh:
        json.dump(analysis, fh, indent=2)
    print("  Analysis JSON saved -> " + output_path)


def load_analysis_json(path):
    with open(path) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# CLI self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python vision_scheme.py <pdf_path> <config_json>")
        sys.exit(1)

    with open(sys.argv[2]) as f:
        _config = json.load(f)

    from span_rules import get_max_span

    _span = get_max_span(
        _config["structural"]["slab_thickness_mm"],
        _config["structural"]["slab_system"],
        _config["structural"]["load_type"],
    )

    _b64, _dims = page_to_base64(sys.argv[1], 0, _config.get("render_scale", 3))
    _analysis = analyse_for_scheme(_b64, _dims, _config, _span)
    save_analysis_json(_analysis, "output/analysis_page0.json")
    print("Floor plate area: " + str(round(_analysis.get("floor_plate_area_m2", 0))) + " m2")
    print("Forced columns:   " + str(len(_analysis.get("forced_columns", []))))
    print("Voids:            " + str(len(_analysis.get("voids", []))))
