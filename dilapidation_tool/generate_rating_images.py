# generate_rating_images.py
"""Auto-generates pavement rating reference images for the council assets report."""

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def _font(name: str, size: int) -> ImageFont.ImageFont:
    for candidate in [f"{name}.ttf", f"{name}bd.ttf", "arial.ttf", "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            pass
    return ImageFont.load_default()


def generate_rating_graph(path: str):
    """
    Generate the pavement condition decay curve with maintenance recommendation table.
    Saved as rating_graph.png → Figure 4 in the council assets report.
    """
    W, H = 960, 600
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    DARK = (50, 50, 50)
    LGREY = (220, 220, 220)

    img = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)

    # Outer border
    draw.rectangle([4, 4, W - 5, H - 5], outline=BLACK, width=2)

    # ── Graph axes ────────────────────────────────────────────
    GX1, GY1 = 145, 25
    GX2, GY2 = 840, 310

    def r_to_y(r):
        return int(GY2 - (r - 1) / 9 * (GY2 - GY1))

    draw.line([(GX1, GY1), (GX1, GY2), (GX2, GY2)], fill=BLACK, width=2)
    # Arrow on x-axis
    draw.polygon([(GX2 + 10, GY2), (GX2 - 5, GY2 - 6), (GX2 - 5, GY2 + 6)], fill=BLACK)

    fn_sm = _font("arial", 13)
    fn_bd = _font("arialbd", 13)
    fn_ax = _font("arialbd", 14)

    # Y-axis tick labels
    for rating, line1, line2 in [
        (10, "RATING 10", "Excellent"),
        (6,  "RATING 6",  "Good"),
        (4,  "RATING 4",  "Fair"),
        (2,  "RATING 2",  "Poor"),
    ]:
        y = r_to_y(rating)
        draw.line([(GX1 - 6, y), (GX1, y)], fill=BLACK, width=1)
        draw.text((GX1 - 130, y - 20), line1, fill=DARK,  font=fn_sm)
        draw.text((GX1 - 100, y + 1),  line2, fill=BLACK, font=fn_bd)

    # Rotated y-axis title
    lbl_img = Image.new("RGB", (280, 20), WHITE)
    lbl_draw = ImageDraw.Draw(lbl_img)
    lbl_draw.text((0, 0), "PAVEMENT CONDITION", fill=BLACK, font=fn_ax)
    lbl_rot = lbl_img.rotate(90, expand=True)
    img.paste(lbl_rot, (8, GY1 + (GY2 - GY1) // 2 - 140))
    draw = ImageDraw.Draw(img)

    # X-axis title
    draw.text((GX1 + (GX2 - GX1) // 2 - 80, GY2 + 12), "PAVEMENT AGE", fill=BLACK, font=fn_ax)

    # Decay S-curve  (high rating when new, drops off with age)
    pts = []
    for i in range(201):
        x_n = i / 200
        r = 1.5 + 8.5 / (1 + math.exp(6 * (x_n - 0.55)))
        pts.append((int(GX1 + x_n * (GX2 - GX1)), r_to_y(r)))
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i + 1]], fill=BLACK, width=2)

    # ── Bottom section: paragraph left, table right ───────────
    fn_para = _font("arial", 12)

    para = (
        "In addition to indicating the\n"
        "surface condition of a road,\n"
        "a given rating also includes a\n"
        "recommendation for needed\n"
        "maintenance or repair. This\n"
        "feature of the rating system\n"
        "facilitates its use and enhances\n"
        "its value as a tool in ongoing\n"
        "road maintenance."
    )
    draw.multiline_text((30, 342), para, fill=DARK, font=fn_para, spacing=3)

    # Maintenance table
    TX, TY = 290, 328
    RH = 34
    TW = W - 44 - TX
    col2_x = TX + 160

    # Header
    draw.rectangle([TX, TY, TX + TW, TY + 28], fill=(50, 50, 50))
    draw.text((TX + 6, TY + 7),
              "RATINGS ARE RELATED TO NEEDED MAINTENANCE OR REPAIR",
              fill=WHITE, font=_font("arialbd", 12))

    maint_rows = [
        ("Rating 9 & 10", "No maintenance required"),
        ("Rating 8",       "Little or no maintenance"),
        ("Rating 7",       "Routine maintenance, cracksealing and minor patching"),
        ("Rating 5 & 6",   "Preservative treatments (sealcoating)"),
        ("Rating 3 & 4",   "Structural improvement and leveling (overlay or recycling)"),
        ("Rating 1 & 2",   "Reconstruction"),
    ]
    for i, (c1, c2) in enumerate(maint_rows):
        ry = TY + 28 + i * RH
        draw.rectangle([TX, ry, TX + TW, ry + RH], fill=LGREY if i % 2 == 0 else WHITE)
        draw.line([(TX, ry + RH), (TX + TW, ry + RH)], fill=LGREY, width=1)
        draw.line([(col2_x, ry), (col2_x, ry + RH)], fill=LGREY, width=1)
        draw.text((TX + 5, ry + 8), c1, fill=BLACK, font=_font("arialbd", 12))
        draw.text((col2_x + 5, ry + 8), c2, fill=BLACK, font=fn_para)

    img.save(path, dpi=(150, 150))
    print(f"  Generated {Path(path).name}")


def generate_rating_table(path: str):
    """
    Generate the detailed pavement rating system table (ratings 10→1).
    Saved as rating_table.png → Figure 5 in the council assets report.
    """
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    HDR_BG = (80, 80, 80)
    HDR_FG = (255, 255, 255)
    ROW_ALT = (242, 242, 242)
    LGREY = (200, 200, 200)

    table_rows = [
        (10, "Excellent",
         "None.",
         "New construction."),
        (9, "Excellent",
         "None.",
         "Recent overlay. Like new."),
        (8, "Very Good",
         "No longitudinal cracks except reflection of paving joints.\n"
         "Occasional transverse cracks, widely spaced (40' or greater).\n"
         "All cracks sealed or tight (open less than ¼\").",
         "Recent sealcoat or new cold mix.\nLittle or no maintenance\nrequired."),
        (7, "Good",
         "Very slight or no raveling, surface shows some traffic wear.\n"
         "Longitudinal cracks (open ¼\") due to reflection or paving joints.\n"
         "Transverse cracks spaced 10' or more apart, little or slight\n"
         "crack raveling. No patching or very few patches in excellent condition.",
         "First signs of aging. Maintain\nwith routine crack filling."),
        (6, "Good",
         "Slight raveling (loss of fines) and traffic wear.\n"
         "Longitudinal cracks (open ¼\"–½\"), some spaced less than 10'.\n"
         "First sign of block cracking. Sight to moderate flushing or polishing.\n"
         "Occasional patching in good condition.",
         "Shows signs of aging. Sound\nstructural condition. Could\nextend life with sealcoat."),
        (5, "Fair",
         "Moderate to severe raveling (loss of fine and coarse aggregate).\n"
         "Longitudinal and transverse cracks (open ½\") show first signs of\n"
         "slight raveling and secondary cracks. First signs of longitudinal cracks\n"
         "near pavement edge. Block cracking up to 50% of surface. Extensive\n"
         "to severe flushing or polishing. Some patching or edge wedging in\n"
         "good condition.",
         "Surface aging. Sound structural\ncondition. Needs sealcoat or\nthin non-structural overlay (less\nthan 2\")"),
        (4, "Fair",
         "Severe surface raveling. Multiple longitudinal and transverse cracking\n"
         "with slight raveling. Longitudinal cracking in wheel path. Block\n"
         "cracking (over 50% of surface). Patching in fair condition.\n"
         "Slight rutting or distortions (½\" deep or less).",
         "Significant aging and first signs\nof need for strengthening. Would\nbenefit from a structural overlay\n(2\" or more)."),
        (3, "Poor",
         "Closely spaced longitudinal and transverse cracks often showing\n"
         "raveling and crack erosion. Severe block cracking. Some alligator\n"
         "cracking (less than 25% of surface). Patches in fair to poor condition.\n"
         "Moderate rutting or distortion (1\" or 2\" deep). Occasional potholes.",
         "Needs patching and repair prior\nto major overlay. Milling and\nremoval of deterioration extends\nthe life of overlay."),
        (2, "Very Poor",
         "Alligator cracking (over 25% of surface).\n"
         "Severe distortions (over 2\" deep)\n"
         "Extensive patching in poor condition.\n"
         "Potholes.",
         "Severe deterioration. Needs\nreconstruction with extensive\nbase repair. Pulverization of old\npavement is effective."),
        (1, "Failed",
         "Severe distress with extensive loss of surface integrity.",
         "Failed. Needs total\nreconstruction."),
    ]

    fn_num  = _font("arialbd", 30)
    fn_cond = _font("arial", 13)
    fn_hdr  = _font("arialbd", 14)
    fn_body = _font("arial", 13)
    fn_title = _font("arialbd", 20)

    W = 900
    COL1 = 110
    COL2 = 490
    COL3 = W - COL1 - COL2

    LINE_H = 17
    PAD = 10

    def row_h(distress: str, treatment: str) -> int:
        n = max(distress.count("\n") + 1, treatment.count("\n") + 1)
        return max(n * LINE_H + PAD * 2, 68)

    row_heights = [row_h(d, t) for _, _, d, t in table_rows]

    TITLE_H = 38
    HDR_H = 40
    H = TITLE_H + HDR_H + sum(row_heights) + 6

    img = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)

    # Title
    draw.text((10, 8), "Rating system", fill=BLACK, font=fn_title)

    # Header
    hy = TITLE_H
    draw.rectangle([0, hy, W, hy + HDR_H], fill=HDR_BG)
    draw.text((COL1 // 2 - 38, hy + 12), "Surface rating",       fill=HDR_FG, font=fn_hdr)
    draw.text((COL1 + 8,       hy + 12), "Visible distress*",    fill=HDR_FG, font=fn_hdr)
    draw.text((COL1 + COL2 + 8, hy + 4),
              "General condition/\ntreatment measures",           fill=HDR_FG, font=fn_hdr)

    # Data rows
    y = TITLE_H + HDR_H
    for idx, (rating, cond, distress, treatment) in enumerate(table_rows):
        rh = row_heights[idx]
        draw.rectangle([0, y, W, y + rh], fill=ROW_ALT if idx % 2 == 0 else WHITE)

        # Column dividers
        draw.line([(COL1, y), (COL1, y + rh)],           fill=LGREY, width=1)
        draw.line([(COL1 + COL2, y), (COL1 + COL2, y + rh)], fill=LGREY, width=1)

        # Rating number (large, centred in col 1)
        num_w = fn_num.getlength(str(rating)) if hasattr(fn_num, "getlength") else len(str(rating)) * 18
        draw.text((COL1 // 2 - int(num_w // 2), y + 6), str(rating), fill=BLACK, font=fn_num)
        cond_w = fn_cond.getlength(cond) if hasattr(fn_cond, "getlength") else len(cond) * 7
        draw.text((COL1 // 2 - int(cond_w // 2), y + 42), cond, fill=BLACK, font=fn_cond)

        # Visible distress (col 2)
        draw.multiline_text((COL1 + 8, y + PAD), distress, fill=BLACK, font=fn_body, spacing=2)

        # Treatment measures (col 3)
        draw.multiline_text((COL1 + COL2 + 8, y + PAD), treatment, fill=BLACK, font=fn_body, spacing=2)

        # Row bottom border
        draw.line([(0, y + rh), (W, y + rh)], fill=LGREY, width=1)
        y += rh

    img.save(path, dpi=(150, 150))
    print(f"  Generated {Path(path).name}")


def ensure_rating_images(base_dir: Path):
    """Generate rating images in base_dir if they don't already exist."""
    graph_path = base_dir / "rating_graph.png"
    table_path = base_dir / "rating_table.png"
    if not graph_path.exists():
        generate_rating_graph(str(graph_path))
    if not table_path.exists():
        generate_rating_table(str(table_path))
