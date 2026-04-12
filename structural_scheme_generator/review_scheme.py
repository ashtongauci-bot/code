"""
review_scheme.py — Interactive scheme review UI (Flask / browser).

Opens at http://localhost:5051 and lets the engineer:
  • See all generated schemes overlaid on the floor plan (colour-coded)
  • Toggle individual scheme visibility
  • See the max-span halo around each column (visual coverage check)
  • See floor plate boundary and void zones
  • Compare scheme statistics (column count, grid spacing, avg trib area)
  • Click to add / remove columns from the selected scheme
  • Drag columns to adjust positions
  • "Approve" selected scheme(s) to proceed to PDF/Tribli output

The review result is returned to the main CLI via a shared state dict.

⚠️  PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION
This UI is a review aid only. All column positions must be verified by a
registered structural engineer before use in any design documentation.
"""

from __future__ import annotations

import base64
import io
import json
import threading
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from flask import Flask, jsonify, render_template_string, request

# ---------------------------------------------------------------------------
# Shared state (set before starting the server, read after shutdown)
# ---------------------------------------------------------------------------
_state: dict = {}


# ---------------------------------------------------------------------------
# Colour palette (hex, for JS)
# ---------------------------------------------------------------------------
SCHEME_HEX = ["#FF9900", "#8B00CC", "#00BFDB"]
FORCED_HEX = "#FF3333"
VOID_HEX = "#CC0000"
PLATE_HEX = "#0066CC"
FACADE_HEX = "#339933"


# ---------------------------------------------------------------------------
# HTML / JS template
# ---------------------------------------------------------------------------
_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Structural Scheme Review — PRELIMINARY</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: monospace; font-size: 12px; background: #1a1a2e; color: #eee; display: flex; height: 100vh; overflow: hidden; }

  /* ── Disclaimer banner ── */
  #disclaimer {
    position: fixed; top: 0; left: 0; right: 0; z-index: 999;
    background: #b30000; color: #fff; text-align: center;
    padding: 6px 10px; font-size: 11px; font-weight: bold;
  }

  /* ── Left sidebar ── */
  #sidebar {
    width: 280px; min-width: 280px; background: #16213e;
    border-right: 1px solid #333; padding: 54px 10px 10px;
    display: flex; flex-direction: column; gap: 12px; overflow-y: auto;
  }
  #sidebar h2 { font-size: 13px; color: #aad4f5; border-bottom: 1px solid #333; padding-bottom: 6px; }

  .scheme-card {
    background: #0f3460; border-radius: 6px; padding: 10px;
    border: 2px solid transparent; cursor: pointer; transition: border .15s;
  }
  .scheme-card.active { border-color: #aad4f5; }
  .scheme-card h3 { font-size: 12px; display: flex; align-items: center; gap: 8px; }
  .scheme-card .swatch { width: 14px; height: 14px; border-radius: 50%; display: inline-block; }
  .scheme-card table { width: 100%; border-collapse: collapse; margin-top: 6px; }
  .scheme-card td { padding: 2px 4px; font-size: 11px; }
  .scheme-card td:first-child { color: #aad4f5; }
  .scheme-card .toggle-btn {
    margin-top: 6px; width: 100%; padding: 4px; border: none; border-radius: 4px;
    cursor: pointer; font-size: 11px; font-family: monospace;
  }

  #controls { display: flex; flex-direction: column; gap: 6px; }
  #controls button {
    padding: 8px; border: none; border-radius: 4px; cursor: pointer;
    font-family: monospace; font-size: 12px; font-weight: bold;
  }
  #btn-approve { background: #00853f; color: #fff; }
  #btn-approve:hover { background: #00a84e; }
  #btn-approve:disabled { background: #555; cursor: not-allowed; }
  #btn-halo { background: #333; color: #eee; }
  #btn-halo.active { background: #444; border: 1px solid #aad4f5; }

  #mode-info { font-size: 10px; color: #888; text-align: center; }

  /* ── Main canvas area ── */
  #canvas-wrap {
    flex: 1; overflow: auto; background: #0d0d0d;
    padding-top: 40px; display: flex; align-items: flex-start; justify-content: center;
  }
  #canvas-wrap canvas { cursor: crosshair; display: block; }
</style>
</head>
<body>

<div id="disclaimer">
  ⚠ PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION &nbsp;|&nbsp;
  All column positions MUST be reviewed by a registered structural engineer before use.
</div>

<div id="sidebar">
  <h2>Scheme Selector</h2>
  <div id="scheme-cards"></div>

  <h2>Controls</h2>
  <div id="controls">
    <div id="mode-info">Click canvas to add column to selected scheme.<br>Right-click a column to remove it.</div>
    <button id="btn-halo" onclick="toggleHalo()">Toggle coverage halos</button>
    <button id="btn-approve" onclick="approveSchemes()">Approve Selected Scheme(s)</button>
  </div>
</div>

<div id="canvas-wrap">
  <canvas id="cvs"></canvas>
</div>

<script>
const DATA     = {{ data_json }};
const BG_SRC   = "data:image/png;base64,{{ bg_b64 }}";
const MAX_SPAN_PTS = {{ max_span_pts }};
const SCHEME_COLOURS = {{ scheme_colours_json }};
const PAGE_H = {{ page_height }};

let bgImg = new Image();
bgImg.src = BG_SRC;

let schemes       = JSON.parse(JSON.stringify(DATA.schemes));  // deep copy
let visible       = schemes.map(() => true);
let selected      = 0;           // active scheme index for add/remove
let showHalos     = true;
let approved      = [];

// ── canvas setup ──────────────────────────────────────────────────────────
const cvs = document.getElementById("cvs");
const ctx = cvs.getContext("2d");
const RENDER_SCALE = DATA.render_scale || 1;

bgImg.onload = function() {
  cvs.width  = bgImg.width;
  cvs.height = bgImg.height;
  renderAll();
};

// ── coordinate conversion ──────────────────────────────────────────────────
function ptsToCanvas(x_pts, y_pts) {
  return { x: x_pts * RENDER_SCALE, y: (PAGE_H - y_pts) * RENDER_SCALE };
}

// ── render ─────────────────────────────────────────────────────────────────
function renderAll() {
  ctx.clearRect(0, 0, cvs.width, cvs.height);
  ctx.drawImage(bgImg, 0, 0);

  // Floor plate
  drawPoly(DATA.floor_plate, "#0066CC", null, 1.5 * RENDER_SCALE);

  // Voids
  (DATA.voids || []).forEach(v => drawPoly(v.polygon, "#CC0000", null, 1 * RENDER_SCALE, true));

  // Core walls
  (DATA.core_walls || []).forEach(c => drawPoly(c.polygon, "#666", null, 1 * RENDER_SCALE));

  // Facade
  if ((DATA.facade_line || []).length > 1) {
    drawPolyLine(DATA.facade_line, "#339933", 0.8 * RENDER_SCALE, true);
  }

  // Schemes (back to front so selected is on top)
  [...schemes.keys()].reverse().forEach(i => {
    if (!visible[i]) return;
    const colour = SCHEME_COLOURS[i % SCHEME_COLOURS.length];
    const isSelected = (i === selected);

    schemes[i].columns.forEach(col => {
      const pos = ptsToCanvas(col.x_pts, col.y_pts);
      const r = (col.type === "forced" ? 8 : 6) * RENDER_SCALE;
      const c = col.type === "forced" ? "#FF3333" : colour;

      // Halo
      if (showHalos && isSelected) {
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, MAX_SPAN_PTS * RENDER_SCALE, 0, 2 * Math.PI);
        ctx.strokeStyle = colour + "33";
        ctx.lineWidth = 0.5 * RENDER_SCALE;
        ctx.stroke();
      }

      // Circle
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, r, 0, 2 * Math.PI);
      ctx.strokeStyle = c;
      ctx.lineWidth = isSelected ? 2 * RENDER_SCALE : 1 * RENDER_SCALE;
      ctx.globalAlpha = isSelected ? 0.9 : 0.5;
      ctx.stroke();
      ctx.fillStyle = c + "55";
      ctx.fill();
      ctx.globalAlpha = 1.0;
    });
  });
}

function drawPoly(pts, stroke, fill, lw, dashed) {
  if (!pts || pts.length < 2) return;
  ctx.beginPath();
  const p0 = ptsToCanvas(pts[0].x_pts, pts[0].y_pts);
  ctx.moveTo(p0.x, p0.y);
  pts.slice(1).forEach(p => { const c = ptsToCanvas(p.x_pts, p.y_pts); ctx.lineTo(c.x, c.y); });
  ctx.closePath();
  if (dashed) ctx.setLineDash([4 * RENDER_SCALE, 2 * RENDER_SCALE]);
  ctx.strokeStyle = stroke; ctx.lineWidth = lw; ctx.stroke();
  if (fill) { ctx.fillStyle = fill; ctx.fill(); }
  ctx.setLineDash([]);
}

function drawPolyLine(pts, stroke, lw, dashed) {
  if (!pts || pts.length < 2) return;
  ctx.beginPath();
  const p0 = ptsToCanvas(pts[0].x_pts, pts[0].y_pts);
  ctx.moveTo(p0.x, p0.y);
  pts.slice(1).forEach(p => { const c = ptsToCanvas(p.x_pts, p.y_pts); ctx.lineTo(c.x, c.y); });
  if (dashed) ctx.setLineDash([4 * RENDER_SCALE, 2 * RENDER_SCALE]);
  ctx.strokeStyle = stroke; ctx.lineWidth = lw; ctx.stroke();
  ctx.setLineDash([]);
}

// ── sidebar cards ──────────────────────────────────────────────────────────
function buildCards() {
  const container = document.getElementById("scheme-cards");
  container.innerHTML = "";
  schemes.forEach((s, i) => {
    const col = SCHEME_COLOURS[i % SCHEME_COLOURS.length];
    const cov = s.coverage || {};
    const covText = cov.coverage_ok === false
      ? `<span style="color:#ff6666">⚠ ${cov.n_uncovered} zones exceed span</span>`
      : '<span style="color:#66ff99">✓ OK</span>';

    const card = document.createElement("div");
    card.className = "scheme-card" + (i === selected ? " active" : "");
    card.innerHTML = `
      <h3><span class="swatch" style="background:${col}"></span>${s.scheme_name}</h3>
      <table>
        <tr><td>Columns</td><td>${s.n_columns}</td></tr>
        <tr><td>Grid</td><td>${s.grid_spacing_mm} mm</td></tr>
        <tr><td>Avg trib</td><td>${s.avg_tributary_m2} m²</td></tr>
        <tr><td>Coverage</td><td>${covText}</td></tr>
      </table>
      <button class="toggle-btn" style="background:${visible[i] ? col+'88' : '#333'};color:#fff"
        onclick="toggleVisible(${i}, event)">
        ${visible[i] ? "● Visible" : "○ Hidden"}
      </button>`;
    card.addEventListener("click", () => selectScheme(i));
    container.appendChild(card);
  });
}

function selectScheme(i) {
  selected = i;
  buildCards();
  renderAll();
}

function toggleVisible(i, event) {
  event.stopPropagation();
  visible[i] = !visible[i];
  buildCards();
  renderAll();
}

function toggleHalo() {
  showHalos = !showHalos;
  document.getElementById("btn-halo").classList.toggle("active", showHalos);
  renderAll();
}

// ── add / remove columns ───────────────────────────────────────────────────
cvs.addEventListener("click", function(e) {
  const rect = cvs.getBoundingClientRect();
  const px = (e.clientX - rect.left) * (cvs.width / rect.width);
  const py = (e.clientY - rect.top)  * (cvs.height / rect.height);
  const x_pts = px / RENDER_SCALE;
  const y_pts = PAGE_H - (py / RENDER_SCALE);

  const scheme = schemes[selected];
  const newId  = "U" + (scheme.columns.length + 1);
  scheme.columns.push({ id: newId, x_pts, y_pts, type: "user", reason: "manually added", confidence: "high", D_mm: 500, B_mm: 500 });
  scheme.n_columns = scheme.columns.length;
  buildCards();
  renderAll();
});

cvs.addEventListener("contextmenu", function(e) {
  e.preventDefault();
  const rect = cvs.getBoundingClientRect();
  const px = (e.clientX - rect.left) * (cvs.width / rect.width);
  const py = (e.clientY - rect.top)  * (cvs.height / rect.height);
  const x_pts = px / RENDER_SCALE;
  const y_pts = PAGE_H - (py / RENDER_SCALE);

  const scheme = schemes[selected];
  const threshold = 10 * RENDER_SCALE;

  const idx = scheme.columns.findIndex(c => {
    const pos = ptsToCanvas(c.x_pts, c.y_pts);
    return Math.hypot(pos.x - px, pos.y - py) < threshold;
  });
  if (idx >= 0) {
    scheme.columns.splice(idx, 1);
    scheme.n_columns = scheme.columns.length;
    buildCards();
    renderAll();
  }
});

// ── approve ────────────────────────────────────────────────────────────────
function approveSchemes() {
  const btn = document.getElementById("btn-approve");
  btn.disabled = true;
  btn.textContent = "Saving…";

  fetch("/approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ schemes: schemes })
  }).then(r => r.json()).then(d => {
    if (d.ok) {
      btn.textContent = "✓ Approved — you can close this tab";
      btn.style.background = "#004d24";
    } else {
      btn.textContent = "Error — check terminal";
      btn.disabled = false;
    }
  });
}

// ── init ───────────────────────────────────────────────────────────────────
buildCards();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

def _render_page_b64(pdf_path: str, page_index: int, render_scale: float) -> str:
    """Render a PDF page as base-64 PNG (for the canvas background)."""
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    mat = fitz.Matrix(render_scale, render_scale)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    buf = io.BytesIO(pix.tobytes("png"))
    b64 = base64.standard_b64encode(buf.getvalue()).decode()
    doc.close()
    return b64


def run_scheme_review(
    grid_result: dict,
    analysis: dict,
    config: dict,
    port: int = 5051,
) -> dict:
    """
    Launch the Flask review UI and block until the engineer approves.

    Returns the (potentially edited) grid_result with updated schemes.
    """
    app = Flask(__name__)
    _state["done"] = False
    _state["result"] = grid_result

    render_scale = config.get("render_scale", 3)
    level = config.get("levels", [{"page_index": 0}])[0]
    page_index = level.get("page_index", 0)

    bg_b64 = _render_page_b64(config["pdf_path"], page_index, render_scale)

    # Page height for coordinate conversion
    doc = fitz.open(config["pdf_path"])
    page_height = doc[page_index].rect.height
    doc.close()

    # max span in pts
    from grid_generator import mm_to_pts as _mm_to_pts
    max_span_mm = grid_result.get("max_span_mm", 8000)
    drawing_scale = config.get("drawing_scale", "1:100")
    max_span_pts = _mm_to_pts(max_span_mm, drawing_scale)

    data_for_js = {
        "schemes": grid_result["schemes"],
        "floor_plate": analysis.get("floor_plate", []),
        "voids": analysis.get("voids", []),
        "core_walls": analysis.get("core_walls", []),
        "facade_line": analysis.get("facade_line", []),
        "render_scale": render_scale,
    }

    @app.route("/")
    def index():
        return render_template_string(
            _HTML,
            data_json=json.dumps(data_for_js),
            bg_b64=bg_b64,
            max_span_pts=max_span_pts,
            page_height=page_height,
            scheme_colours_json=json.dumps(SCHEME_HEX),
        )

    @app.route("/approve", methods=["POST"])
    def approve():
        payload = request.get_json(force=True)
        updated_schemes = payload.get("schemes", grid_result["schemes"])
        _state["result"] = dict(grid_result, schemes=updated_schemes)
        _state["done"] = True
        # Trigger server shutdown after responding
        shutdown = request.environ.get("werkzeug.server.shutdown")
        if shutdown:
            shutdown()
        return jsonify({"ok": True})

    # Run Flask in a daemon thread so we can poll _state["done"]
    server_thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    server_thread.start()

    print(f"\n  Review UI running at http://localhost:{port}")
    print("  Approve your scheme(s) in the browser to continue…")

    # Block main thread until approval
    while not _state["done"]:
        import time
        time.sleep(0.5)

    print("  Schemes approved — continuing with output generation.")
    return _state["result"]
