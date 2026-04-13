"""
review_scheme.py - Interactive scheme review UI (Flask / browser).

Opens at http://localhost:5051 and lets the engineer:
  - See all generated schemes drawn over the floor plan (colour-coded)
  - Toggle individual scheme visibility
  - See max-span halos around each column
  - Click to add columns, right-click to remove
  - Approve scheme(s) to proceed to output

WARNING: PRELIMINARY STRUCTURAL SCHEME - NOT FOR CONSTRUCTION
"""

from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path

import fitz
from flask import Flask, Response, jsonify, render_template_string, request

_state = {}

SCHEME_HEX = ["#FF9900", "#8B00CC", "#00BFDB"]

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Structural Scheme Review - PRELIMINARY</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: monospace; font-size: 12px; background: #1a1a2e; color: #eee; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }

#disclaimer {
    background: #b30000; color: #fff; text-align: center;
    padding: 6px 10px; font-size: 11px; font-weight: bold; flex-shrink: 0;
}

#main { display: flex; flex: 1; overflow: hidden; }

#sidebar {
    width: 280px; min-width: 280px; background: #16213e;
    border-right: 1px solid #333; padding: 10px;
    display: flex; flex-direction: column; gap: 10px; overflow-y: auto;
}
#sidebar h2 { font-size: 12px; color: #aad4f5; border-bottom: 1px solid #333; padding-bottom: 4px; }

.scheme-card {
    background: #0f3460; border-radius: 5px; padding: 8px;
    border: 2px solid transparent; cursor: pointer;
}
.scheme-card.active { border-color: #aad4f5; }
.scheme-card h3 { font-size: 11px; display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.swatch { width: 12px; height: 12px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
.scheme-card table { width: 100%; font-size: 10px; border-collapse: collapse; }
.scheme-card td { padding: 1px 3px; }
.scheme-card td:first-child { color: #aad4f5; }
.toggle-btn { margin-top: 5px; width: 100%; padding: 3px; border: none; border-radius: 3px; cursor: pointer; font-size: 10px; font-family: monospace; }

#controls { display: flex; flex-direction: column; gap: 5px; }
#controls button { padding: 7px; border: none; border-radius: 4px; cursor: pointer; font-family: monospace; font-size: 11px; font-weight: bold; }
#btn-approve { background: #00853f; color: #fff; }
#btn-approve:hover { background: #00a84e; }
#btn-approve:disabled { background: #555; cursor: not-allowed; }
#btn-halo { background: #333; color: #eee; border: 1px solid #555; }
#mode-info { font-size: 10px; color: #888; text-align: center; line-height: 1.4; }

#canvas-wrap { flex: 1; overflow: auto; background: #111; display: flex; align-items: flex-start; justify-content: flex-start; }
canvas { cursor: crosshair; display: block; }

#status { font-size: 10px; color: #aaa; margin-top: 4px; min-height: 16px; }
</style>
</head>
<body>
<div id="disclaimer">
  &#9888; PRELIMINARY STRUCTURAL SCHEME &mdash; NOT FOR CONSTRUCTION &nbsp;|&nbsp;
  All column positions MUST be reviewed by a registered structural engineer before use.
</div>
<div id="main">
  <div id="sidebar">
    <h2>Scheme Selector</h2>
    <div id="scheme-cards"><p style="font-size:10px;color:#888">Loading...</p></div>
    <h2>Controls</h2>
    <div id="controls">
      <div id="mode-info">Click canvas: add column<br>Right-click column: remove it</div>
      <button id="btn-halo" onclick="toggleHalo()">Toggle coverage halos</button>
      <button id="btn-approve" onclick="approveSchemes()">Approve Selected Scheme(s)</button>
      <div id="status"></div>
    </div>
  </div>
  <div id="canvas-wrap">
    <canvas id="cvs"></canvas>
  </div>
</div>

<script>
var RAW    = SCHEMES_JSON;
var PAGE_H = PAGE_HEIGHT;
var SCALE  = RENDER_SCALE;
var MAX_SPAN_PTS = MAX_SPAN;
var COLOURS = SCHEME_COLOURS_JSON;

var schemes  = JSON.parse(JSON.stringify(RAW.schemes));
var analysis = RAW.analysis;
var visible  = schemes.map(function() { return true; });
var selected = 0;
var showHalos = false;

var cvs = document.getElementById("cvs");
var ctx = cvs.getContext("2d");
var bgImg = new Image();

function status(msg) { document.getElementById("status").textContent = msg; }

bgImg.onload = function() {
    cvs.width  = bgImg.width;
    cvs.height = bgImg.height;
    status("Plan loaded. " + cvs.width + " x " + cvs.height + "px");
    buildCards();
    renderAll();
};
bgImg.onerror = function() { status("ERROR: background image failed to load"); };
bgImg.src = "/bg.png";

function toCanvas(x_pts, y_pts) {
    return { x: x_pts * SCALE, y: (PAGE_H - y_pts) * SCALE };
}

function renderAll() {
    ctx.clearRect(0, 0, cvs.width, cvs.height);
    if (bgImg.complete && bgImg.naturalWidth > 0) {
        ctx.drawImage(bgImg, 0, 0);
    }

    // Floor plate
    drawPoly(analysis.floor_plate, "#0066CC", 1.5 * SCALE, false);

    // Voids
    (analysis.voids || []).forEach(function(v) {
        drawPoly(v.polygon, "#CC0000", 1.0 * SCALE, true);
    });

    // Core walls
    (analysis.core_walls || []).forEach(function(c) {
        drawPoly(c.polygon, "#666666", 1.0 * SCALE, false);
    });

    // Schemes - draw non-selected first, selected on top
    var order = [];
    for (var i = 0; i < schemes.length; i++) { if (i !== selected) order.push(i); }
    order.push(selected);

    order.forEach(function(i) {
        if (!visible[i]) return;
        var colour = COLOURS[i % COLOURS.length];
        var isSel = (i === selected);

        schemes[i].columns.forEach(function(col) {
            var pos = toCanvas(col.x_pts, col.y_pts);
            var r = (col.type === "forced" ? 9 : 6) * SCALE;
            var c = col.type === "forced" ? "#FF3333" : colour;

            if (showHalos && isSel) {
                ctx.beginPath();
                ctx.arc(pos.x, pos.y, MAX_SPAN_PTS * SCALE, 0, 2 * Math.PI);
                ctx.strokeStyle = colour + "22";
                ctx.lineWidth = 0.5 * SCALE;
                ctx.stroke();
            }

            ctx.beginPath();
            ctx.arc(pos.x, pos.y, r, 0, 2 * Math.PI);
            ctx.strokeStyle = c;
            ctx.lineWidth = isSel ? 2 * SCALE : 1 * SCALE;
            ctx.globalAlpha = isSel ? 0.9 : 0.45;
            ctx.stroke();
            ctx.fillStyle = c + "44";
            ctx.fill();
            ctx.globalAlpha = 1.0;
        });
    });
}

function drawPoly(pts, stroke, lw, dashed) {
    if (!pts || pts.length < 2) return;
    ctx.beginPath();
    var p0 = toCanvas(pts[0].x_pts, pts[0].y_pts);
    ctx.moveTo(p0.x, p0.y);
    for (var i = 1; i < pts.length; i++) {
        var p = toCanvas(pts[i].x_pts, pts[i].y_pts);
        ctx.lineTo(p.x, p.y);
    }
    ctx.closePath();
    if (dashed) ctx.setLineDash([4 * SCALE, 2 * SCALE]);
    ctx.strokeStyle = stroke;
    ctx.lineWidth = lw;
    ctx.stroke();
    ctx.setLineDash([]);
}

function buildCards() {
    var container = document.getElementById("scheme-cards");
    container.innerHTML = "";
    schemes.forEach(function(s, i) {
        var col = COLOURS[i % COLOURS.length];
        var cov = s.coverage || {};
        var covText = cov.coverage_ok === false
            ? "<span style='color:#ff9966'>&#9888; " + cov.n_uncovered + " zones</span>"
            : "<span style='color:#66ff99'>&#10003; OK</span>";

        var card = document.createElement("div");
        card.className = "scheme-card" + (i === selected ? " active" : "");
        card.innerHTML =
            "<h3><span class='swatch' style='background:" + col + "'></span>" + s.scheme_name + "</h3>" +
            "<table>" +
            "<tr><td>Columns</td><td>" + s.n_columns + "</td></tr>" +
            "<tr><td>Grid</td><td>" + s.grid_spacing_mm + " mm</td></tr>" +
            "<tr><td>Avg trib</td><td>" + s.avg_tributary_m2 + " m&#178;</td></tr>" +
            "<tr><td>Coverage</td><td>" + covText + "</td></tr>" +
            "</table>" +
            "<button class='toggle-btn' style='background:" + (visible[i] ? col + "88" : "#333") + ";color:#fff'" +
            " onclick='toggleVisible(" + i + ", event)'>" +
            (visible[i] ? "&#9679; Visible" : "&#9675; Hidden") + "</button>";
        card.addEventListener("click", function(idx) {
            return function() { selectScheme(idx); };
        }(i));
        container.appendChild(card);
    });
}

function selectScheme(i) { selected = i; buildCards(); renderAll(); }

function toggleVisible(i, event) {
    event.stopPropagation();
    visible[i] = !visible[i];
    buildCards();
    renderAll();
}

function toggleHalo() {
    showHalos = !showHalos;
    var btn = document.getElementById("btn-halo");
    btn.style.background = showHalos ? "#555" : "#333";
    renderAll();
}

cvs.addEventListener("click", function(e) {
    var rect = cvs.getBoundingClientRect();
    var scaleX = cvs.width / rect.width;
    var scaleY = cvs.height / rect.height;
    var px = (e.clientX - rect.left) * scaleX;
    var py = (e.clientY - rect.top) * scaleY;
    var x_pts = px / SCALE;
    var y_pts = PAGE_H - (py / SCALE);

    var scheme = schemes[selected];
    var newId = "U" + (scheme.columns.length + 1);
    scheme.columns.push({ id: newId, x_pts: x_pts, y_pts: y_pts, type: "user", reason: "manually added", D_mm: 500, B_mm: 500 });
    scheme.n_columns = scheme.columns.length;
    buildCards();
    renderAll();
    status("Added column " + newId);
});

cvs.addEventListener("contextmenu", function(e) {
    e.preventDefault();
    var rect = cvs.getBoundingClientRect();
    var scaleX = cvs.width / rect.width;
    var scaleY = cvs.height / rect.height;
    var px = (e.clientX - rect.left) * scaleX;
    var py = (e.clientY - rect.top) * scaleY;

    var scheme = schemes[selected];
    var threshold = 12 * SCALE;
    var found = -1;
    for (var i = 0; i < scheme.columns.length; i++) {
        var pos = toCanvas(scheme.columns[i].x_pts, scheme.columns[i].y_pts);
        if (Math.sqrt(Math.pow(pos.x - px, 2) + Math.pow(pos.y - py, 2)) < threshold) {
            found = i; break;
        }
    }
    if (found >= 0) {
        var removed = scheme.columns.splice(found, 1)[0];
        scheme.n_columns = scheme.columns.length;
        buildCards(); renderAll();
        status("Removed column " + removed.id);
    }
});

function approveSchemes() {
    var btn = document.getElementById("btn-approve");
    btn.disabled = true;
    btn.textContent = "Saving...";
    status("Sending approval...");
    fetch("/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ schemes: schemes })
    }).then(function(r) { return r.json(); }).then(function(d) {
        if (d.ok) {
            btn.textContent = "Approved - close this tab";
            btn.style.background = "#004d24";
            status("Approved. Output files are being written...");
        } else {
            btn.textContent = "Error - check terminal";
            btn.disabled = false;
        }
    }).catch(function(err) {
        status("Error: " + err);
        btn.disabled = false;
        btn.textContent = "Approve Selected Scheme(s)";
    });
}
</script>
</body>
</html>"""


def _render_page_png(pdf_path, page_index, render_scale):
    doc = fitz.open(pdf_path)
    page = doc[page_index]

    MAX_PX = 7800
    rect = page.rect
    effective_scale = render_scale
    if max(rect.width, rect.height) * effective_scale > MAX_PX:
        effective_scale = MAX_PX / max(rect.width, rect.height)

    mat = fitz.Matrix(effective_scale, effective_scale)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    png_bytes = pix.tobytes("png")
    page_height = rect.height
    doc.close()
    return png_bytes, page_height, effective_scale


def run_scheme_review(grid_result, analysis, config, port=5051):
    app = Flask(__name__)
    _state["done"] = False
    _state["result"] = grid_result

    render_scale = config.get("render_scale", 3)
    level = config.get("levels", [{"page_index": 0}])[0]
    page_index = level.get("page_index", 0)

    png_bytes, page_height, effective_scale = _render_page_png(
        config["pdf_path"], page_index, render_scale
    )
    _state["png_bytes"] = png_bytes

    from grid_generator import mm_to_pts as _mm_to_pts
    max_span_mm = grid_result.get("max_span_mm", 8000)
    drawing_scale = config.get("drawing_scale", "1:100")
    max_span_pts = _mm_to_pts(max_span_mm, drawing_scale)

    data_for_js = {
        "schemes": grid_result["schemes"],
        "analysis": {
            "floor_plate": analysis.get("floor_plate", []),
            "voids": analysis.get("voids", []),
            "core_walls": analysis.get("core_walls", []),
            "facade_line": analysis.get("facade_line", []),
        },
    }

    # Build the HTML by substituting values directly (avoids Jinja conflicts)
    html = _HTML
    html = html.replace("SCHEMES_JSON",        json.dumps(data_for_js))
    html = html.replace("PAGE_HEIGHT",         str(page_height))
    html = html.replace("RENDER_SCALE",        str(round(effective_scale, 4)))
    html = html.replace("MAX_SPAN",            str(round(max_span_pts, 2)))
    html = html.replace("SCHEME_COLOURS_JSON", json.dumps(SCHEME_HEX))

    @app.route("/")
    def index():
        return html

    @app.route("/bg.png")
    def background():
        return Response(_state["png_bytes"], mimetype="image/png")

    @app.route("/approve", methods=["POST"])
    def approve():
        payload = request.get_json(force=True)
        updated = payload.get("schemes", grid_result["schemes"])
        _state["result"] = dict(grid_result, schemes=updated)
        _state["done"] = True
        return jsonify({"ok": True})

    server_thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    server_thread.start()

    print("\n  Review UI running at http://localhost:" + str(port))
    print("  Approve your scheme(s) in the browser to continue...")

    while not _state["done"]:
        time.sleep(0.5)

    print("  Schemes approved - continuing with output generation.")
    return _state["result"]
