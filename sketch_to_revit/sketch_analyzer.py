"""
sketch_analyzer.py — Analyze a hand-drawn structural sketch with Claude vision.

Accepts a sketch image (PNG, JPG, PDF page) and returns a structured JSON
description of all structural elements: columns, beams, slabs, and floors.

The returned data drives revit_generator.py to produce a pyRevit script.

⚠️  PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION
All output must be reviewed and verified by a registered structural engineer
before use in any design documentation or construction.
"""

from __future__ import annotations

import base64
import io
import json
import re
import sys
from pathlib import Path


def image_to_base64(image_path: str) -> tuple[str, str]:
    """
    Load an image file and return (base64_string, media_type).
    Supports PNG, JPG/JPEG, GIF, WEBP.
    For PDFs, renders page 0 to PNG first (requires PyMuPDF).
    """
    path = Path(image_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        try:
            import fitz
        except ImportError:
            raise ImportError(
                "PyMuPDF (fitz) is required to read PDF sketches.\n"
                "Install it with: pip install pymupdf"
            )
        doc = fitz.open(image_path)
        page = doc[0]
        mat = fitz.Matrix(3.0, 3.0)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        buf = io.BytesIO(pix.tobytes("png"))
        doc.close()
        b64 = base64.standard_b64encode(buf.getvalue()).decode()
        return b64, "image/png"

    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    if suffix not in media_types:
        raise ValueError(
            f"Unsupported image format: {suffix}\n"
            "Supported: PNG, JPG, JPEG, GIF, WEBP, PDF"
        )

    with open(image_path, "rb") as f:
        b64 = base64.standard_b64encode(f.read()).decode()
    return b64, media_types[suffix]


_ANALYSIS_PROMPT = """You are an expert structural engineer analyzing a hand-drawn sketch.
Your job is to identify all structural elements and return their positions and properties as structured JSON.

SKETCH CONTEXT:
The sketch may show a plan view (top-down), a 3D perspective, an elevation, or a combination.
It may have dimension annotations, grid labels, or be purely freehand.

YOUR TASK:
1. Identify the SKETCH TYPE (plan, 3d_perspective, elevation, section, mixed)
2. Find any DIMENSION ANNOTATIONS on the sketch and use them as ground truth for scale
3. If no dimensions are annotated, infer typical structural bay sizes (usually 5–9m for concrete frames)
4. Extract all structural elements:
   - COLUMNS: locations on a grid, section sizes if shown
   - BEAMS: which columns they connect, sizes if shown
   - SLABS / FLOORS: thickness and boundaries if shown
5. Identify the NUMBER OF FLOORS visible or implied

COORDINATE SYSTEM:
- Use a simple grid with column labels (A, B, C...) in one direction and row numbers (1, 2, 3...) in the other
- Report all x/y positions in REAL-WORLD METRES from the bottom-left/front-left origin
- If dimensions are shown, use them directly; otherwise make a reasonable engineering assumption and flag it

RETURN ONLY this JSON object (no markdown fences, no other text):
{
  "sketch_type": "plan",
  "dimensions_annotated": true,
  "scale_notes": "dimensions shown on sketch: 6m bays",
  "floor_to_floor_height_m": 3.5,
  "num_floors": 1,
  "grid": {
    "x_labels": ["A", "B", "C"],
    "y_labels": ["1", "2"],
    "x_spacing_m": [6.0, 6.0],
    "y_spacing_m": [6.0]
  },
  "columns": [
    {
      "id": "C_A1",
      "grid_x": "A",
      "grid_y": "1",
      "x_m": 0.0,
      "y_m": 0.0,
      "section_width_mm": 500,
      "section_depth_mm": 500,
      "floors": "all"
    }
  ],
  "beams": [
    {
      "id": "B1",
      "from_col": "C_A1",
      "to_col": "C_B1",
      "width_mm": 400,
      "depth_mm": 600,
      "floor": "all"
    }
  ],
  "slabs": [
    {
      "id": "SL1",
      "floor": 1,
      "thickness_mm": 250,
      "boundary_cols": ["C_A1", "C_B1", "C_B2", "C_A2"]
    }
  ],
  "warnings": ["No dimensions annotated — assumed 6m typical bay"],
  "confidence": "medium",
  "general_notes": ""
}

IMPORTANT RULES:
- Every column must have a unique id (e.g. "C_A1" for column at grid A-1)
- Every beam's from_col and to_col must match a column id exactly
- Every slab's boundary_cols must list column ids in order (clockwise or anticlockwise)
- section sizes: if not shown, assume 500×500mm columns and 400×600mm beams
- floor_to_floor_height_m: if not shown, assume 3.5m
- num_floors: count storeys visible or implied in sketch
- confidence: "high" if dimensions annotated, "medium" if inferred from sketch geometry, "low" if very rough guess
"""


def analyse_sketch(image_path: str, api_key: str = "") -> dict:
    """
    Send a sketch image to Claude and return the structured analysis dict.

    Args:
        image_path: Path to the sketch image (PNG, JPG, PDF).
        api_key:    Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.

    Returns:
        Parsed analysis dict.
    """
    import os
    import anthropic

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError(
            "No Anthropic API key provided.\n"
            "  Set ANTHROPIC_API_KEY env var, or pass --api-key on the command line."
        )

    b64, media_type = image_to_base64(image_path)

    client = anthropic.Anthropic(api_key=key)
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
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": _ANALYSIS_PROMPT,
                    },
                ],
            }
        ],
    )

    raw = message.content[0].text
    return _extract_json(raw)


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Claude response is not valid JSON.\nRaw response:\n{text[:2000]}"
        ) from exc


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python sketch_analyzer.py <image_path>")
        sys.exit(1)
    result = analyse_sketch(sys.argv[1])
    print(json.dumps(result, indent=2))
