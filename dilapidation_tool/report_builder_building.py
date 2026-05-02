# report_builder_building.py - Builds building dilapidation reports

from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from pathlib import Path
from config import PROJECT

TNR = "Times New Roman"


def set_run(run, size=None, bold=None, italic=None, underline=None, font_name=TNR):
    """Apply run formatting. Pass None (default) to leave a property unset so
    the paragraph style can define it. Pass True/False to override explicitly."""
    if font_name:
        run.font.name = font_name
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if underline is not None:
        run.underline = underline


def add_body(doc, text, size=12, bold=None, italic=None, align=WD_ALIGN_PARAGRAPH.LEFT):
    p = doc.add_paragraph()
    p.alignment = align
    run = p.add_run(text)
    set_run(run, size=size, bold=bold, italic=italic)
    return p


def add_section_heading(doc, text):
    """Heading 1 with explicit bold + underline stamped on the run so they
    cannot be overridden by differing style definitions across templates."""
    p = doc.add_paragraph(style="Heading 1")
    run = p.add_run(text)
    rPr = run._r.get_or_add_rPr()
    for tag, attrs in [
        ("w:rFonts", {"w:ascii": TNR, "w:hAnsi": TNR, "w:cs": TNR}),
        ("w:b",      {}),
        ("w:color",  {"w:val": "000000"}),
        ("w:sz",     {"w:val": "24"}),
        ("w:u",      {"w:val": "single"}),
    ]:
        el = OxmlElement(tag)
        for k, v in attrs.items():
            el.set(qn(k), v)
        rPr.append(el)
    return p


def add_heading2(doc, text):
    """Heading 2 - e.g. '3.1 External Areas'"""
    p = doc.add_paragraph(style="Heading 2")
    run = p.add_run(text)
    set_run(run, size=16)
    return p


def add_appendix_label(doc, text):
    """e.g. 'APPENDIX A- EXTERNAL FACADES' - bold, 12pt"""
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run(run, size=12, bold=True)
    return p


def add_facade_label(doc, text):
    """e.g. 'EAST FAÇADE – FRONT OF PROPERTY' - bold, 12pt"""
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run(run, size=12, bold=True)
    return p


def add_cover_page(doc, cover_photo: str = None):
    doc.add_paragraph()

    # Title
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("PRE-CONSTRUCTION DILAPIDATION REPORT")
    set_run(run, size=18, bold=True, underline=True)

    # "At"
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("At")
    set_run(run, size=12)

    # Subject address
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(PROJECT["address"])
    set_run(run, size=18, bold=True)

    # "Due to development at:"
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Due to development at:")
    set_run(run, size=12)

    # Development address
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(PROJECT.get("development_address", PROJECT["address"]))
    set_run(run, size=18, bold=True)

    # Prepared For
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f"Prepared For: {PROJECT['client']}")
    set_run(run, size=12, bold=True)

    doc.add_paragraph()

    # Cover photo - use Street View or manual cover.jpg
    manual_cover = Path(__file__).parent / "photos" / "cover.jpg"
    photo_to_use = cover_photo or (str(manual_cover) if manual_cover.exists() else None)

    if photo_to_use and Path(photo_to_use).exists():
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run.add_picture(str(photo_to_use), width=Inches(7.09), height=Inches(5.10))
    else:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("[Cover photo – auto-generated or place cover.jpg in photos folder]")
        run.italic = True
        set_run(run, size=11)

    doc.add_paragraph()

    # Prepared By / Date / Ref block
    for label, value in [
        ("Prepared By:", PROJECT["inspector_name"]),
        ("Date:", PROJECT["report_date"]),
        ("Ref:", PROJECT["ref"]),
    ]:
        p = doc.add_paragraph()
        run = p.add_run(f"{label}\t{value}")
        set_run(run, size=12)

    # 14 spacer paragraphs push the info block toward the bottom of the cover page
    for _ in range(14):
        doc.add_paragraph()

    # Report info block (bottom of cover page)
    for label, value in [
        ("Name:", f"Pre-Construction Dilapidation Report – {PROJECT['address']}"),
        ("Date of Inspection:", PROJECT["inspection_date"]),
        ("To:", PROJECT["client"]),
    ]:
        p = doc.add_paragraph()
        r1 = p.add_run(f"{label}\t")
        set_run(r1, size=12, bold=True)
        r2 = p.add_run(value)
        set_run(r2, size=12)

    doc.add_page_break()


def add_contents(doc):
    p = doc.add_paragraph()
    run = p.add_run("CONTENTS")
    set_run(run, size=12, bold=True)

    for entry in [
        "1.0 PREAMBLE",
        "2.0 INTRODUCTION",
        "3.0 EXISTING CONDITIONS",
        "4.0 CONCLUSION",
        "APPENDIX A – EXTERNAL FACADES",
        "APPENDIX B – INTERNAL AREAS",
    ]:
        p = doc.add_paragraph()
        run = p.add_run(entry)
        set_run(run, size=12, italic=True)

    doc.add_page_break()


def add_preamble(doc):
    add_section_heading(doc, "1.0 PREAMBLE")

    # Paragraph 1 – subject address bold, optional property description, dev address bold
    p = doc.add_paragraph()
    set_run(p.add_run(
        "This pre-construction dilapidation report is based on visual inspection only. "
        "The purpose of this report is to provide a photographic record of the "
        "existing internal and external conditions of "
    ), size=12)
    set_run(p.add_run(f"{PROJECT['address']}."), size=12, bold=True)

    prop_desc = PROJECT.get("property_description", "")
    if prop_desc:
        set_run(p.add_run(f" {prop_desc}"), size=12)

    dev_addr = PROJECT.get("development_address", "")
    if dev_addr:
        set_run(p.add_run(" This property is located adjacent to the proposed development at "), size=12)
        set_run(p.add_run(f"{dev_addr}."), size=12, bold=True)

    set_run(p.add_run(
        " This report also gives a brief descriptive record of any defects noted on the "
        "date of our inspection. The inspection included all site features and accessible "
        "areas of the property as photographed and identified within this report. "
        "Photos show items of note, such as cracks, as well as some overviews."
    ), size=12)

    # Paragraph 2 – photos available on request
    p2 = doc.add_paragraph()
    set_run(p2.add_run(
        f"A full set of photos taken during our inspection ({PROJECT['inspection_date']}) "
        "can be provided upon request."
    ), size=12)

    # Paragraph 3 – non-structural disclaimer
    add_body(doc, (
        "This report is not a structural or civil engineering report. It is the property owner's "
        "responsibility to seek further structural engineering advice on any defective elements "
        "which have been noted in this report."
    ))
    doc.add_paragraph()


def add_introduction(doc, map_paths: dict = None):
    map_paths = map_paths or {}
    add_section_heading(doc, "2.0 INTRODUCTION")

    # Lead-in with bold subject address
    p = doc.add_paragraph()
    set_run(p.add_run("The inspection focused on the internal and external conditions to "), size=12)
    set_run(p.add_run(f"{PROJECT['address']}."), size=12, bold=True)
    set_run(p.add_run(" The extent of which is highlighted in Figure 1 below."), size=12)
    doc.add_paragraph()

    # Figure 1 - Locality Map
    if map_paths.get("figure1"):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run.add_picture(map_paths["figure1"], width=Inches(6.0))
        cap = doc.add_paragraph()
        run = cap.add_run("Figure 1 – Site Locality Plan (Not to Scale)")
        set_run(run, size=12, bold=True, italic=True)
    else:
        add_body(doc, "Figure 1 – Site Locality Plan (Not to Scale)", bold=True, italic=True)

    doc.add_paragraph()
    add_body(doc, (
        "The areas inspected at this property include all external building facades and external "
        "site features. The internals for the property were also inspected as access was provided. "
        "Specifically, when discussing the pre-construction condition of the building in this report, "
        "we have structured this report in the following sub-categories:"
    ))

    # Bullet list
    for item in ["External Facades", "Internals"]:
        try:
            p = doc.add_paragraph(style="List Bullet")
        except Exception:
            p = doc.add_paragraph()
            p.add_run("• ")
        run = p.add_run(item)
        set_run(run, size=12)

    doc.add_paragraph()
    add_body(doc, (
        "When describing the condition of an element in this report (Good, Fair or Poor), these are "
        "visual observation-based opinions and are based on the following definitions:"
    ))

    for term, definition in [
        ("Good –", "Items do not appear to have any defects and are in good condition."),
        ("Fair –", "Item is in reasonable condition for its age and may have some minor defect(s)."),
        ("Poor –", "Indicates generally that a defect is beyond minor and further structural advice is required."),
    ]:
        p = doc.add_paragraph()
        r1 = p.add_run(f"{term}    ")
        set_run(r1, size=12, bold=True)
        r2 = p.add_run(definition)
        set_run(r2, size=12)

    doc.add_paragraph()

    # AS2870 categorisation paragraph (exact template wording)
    p = doc.add_paragraph()
    set_run(p.add_run("Also, when categorising cracking in this report, we rely on the definitions defined in "), size=12)
    set_run(p.add_run("AS2870-2011, Appendix C (Page 72), Table C1 and the NSW Guide to Standards and Tolerances, 2017 (NSWGST)"), size=12, italic=True)
    set_run(p.add_run(
        " as per extracts in Figures 3 & 4 below. Although, this extract classifies damage due to "
        "foundation movements (particularly cracking with reference to walls) we still believe it to "
        "be useful in categorizing all cracking defects identified at our dilapidation survey inspection. "
        "Cracks in this report are therefore categorised as follows:"
    ), size=12)

    doc.add_paragraph()

    # Figure 2 - Property Site Map (subject + development overlays)
    if map_paths.get("figure2"):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run.add_picture(map_paths["figure2"], width=Inches(6.0))
        cap = doc.add_paragraph()
        run = cap.add_run("Figure 2 – Site Property Map (Not to Scale)")
        set_run(run, size=12, bold=True, italic=True)
    else:
        p = doc.add_paragraph()
        run = p.add_run("Figure 2 – Site Property Map (Not to Scale)")
        set_run(run, size=12, bold=True, italic=True)

    doc.add_paragraph()

    # Figure 3 - AS2870 Crack Classification Table
    fig3 = Path(__file__).parent / "rating_graph.png"
    if fig3.exists():
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run.add_picture(str(fig3), width=Inches(5.49))
        cap = doc.add_paragraph()
        run = cap.add_run("Figure 3 – AS2870 Classification of Damage Due to Foundation Movements")
        set_run(run, size=12, bold=True, italic=True)
        doc.add_paragraph()
    else:
        print("  Warning: rating_graph.png not found – Figure 3 skipped")

    # Figure 4 - Damage Rating Table
    fig4 = Path(__file__).parent / "rating_table.png"
    if fig4.exists():
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run.add_picture(str(fig4), width=Inches(5.49))
        cap = doc.add_paragraph()
        run = cap.add_run("Figure 4 – Table 3.02 Damage to Walls Caused by Movement of Slabs and Footings")
        set_run(run, size=12, bold=True, italic=True)
    else:
        print("  Warning: rating_table.png not found – Figure 4 skipped")

    # Bridging text + Figure 5 - NSWGST Extract
    doc.add_paragraph()
    add_body(doc, (
        "As AS2870 and the NSWGST extracts suggest, Category 3 cracking is considered structural, "
        "and therefore further structural engineering advice on such defects should be sourced. "
        "Figure 5 is another extract from the NSWGST which further validates this opinion:"
    ))
    doc.add_paragraph()

    fig5 = Path(__file__).parent / "rating_extract.png"
    if fig5.exists():
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run.add_picture(str(fig5), width=Inches(5.49))
        cap = doc.add_paragraph()
        run = cap.add_run("Figure 5 – NSW Guide to Standards and Tolerances, 2017 (NSWGST) Extract")
        set_run(run, size=12, bold=True, italic=True)
    else:
        print("  Warning: rating_extract.png not found – Figure 5 skipped")

    doc.add_page_break()


def add_existing_conditions_intro(doc):
    add_section_heading(doc, "3.0 EXISTING CONDITIONS")
    add_body(doc, (
        f"The inspection covered all accessible external facades and internal areas of the property "
        f"at {PROJECT['address']}. The property was found to be in generally fair condition with "
        f"some defects present typical for the age of the structure. Photos and descriptions of "
        f"condition can be found in the appendices overleaf."
    ))
    doc.add_paragraph()


# ─── PHOTO TABLE HELPERS ──────────────────────────────────────────────────────

def _remove_cell_borders(cell):
    """Remove all visible borders from a table cell."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for side in ["top", "left", "bottom", "right", "insideH", "insideV"]:
        border = OxmlElement(f"w:{side}")
        border.set(qn("w:val"), "none")
        tcBorders.append(border)
    tcPr.append(tcBorders)
    tcW = OxmlElement("w:tcW")
    tcW.set(qn("w:w"), "6803")
    tcW.set(qn("w:type"), "dxa")
    tcPr.append(tcW)


def _make_run_elem(rpr_specs: list, text: str = None, fld_type: str = None, instr: str = None):
    """Build a <w:r> element with the given run properties and content."""
    r = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    for tag, attrs in rpr_specs:
        el = OxmlElement(tag)
        for k, v in attrs.items():
            el.set(qn(k), v)
        rPr.append(el)
    r.append(rPr)

    if fld_type is not None:
        fc = OxmlElement("w:fldChar")
        fc.set(qn("w:fldCharType"), fld_type)
        r.append(fc)
    elif instr is not None:
        it = OxmlElement("w:instrText")
        it.set(qn("xml:space"), "preserve")
        it.text = instr
        r.append(it)
    elif text is not None:
        t = OxmlElement("w:t")
        t.set(qn("xml:space"), "preserve")
        t.text = text
        r.append(t)
    return r


def _build_caption_para(para, photo_number: int, description: str, category: str):
    """
    Populate a paragraph with a Caption-style photo caption using a SEQ field.

    Format: "Photograph [SEQ]: description -- category"
    - "Photograph " prefix: 12pt, TNR, underline, color 000000
    - SEQ field: auto-increments in Word on open
    - Description text: 11pt, Calibri, color 44546A
    """
    # Apply Caption paragraph style
    try:
        para.style = "Caption"
    except Exception:
        pass

    # Paragraph-level rPr (cursor default formatting)
    pPr = para._p.get_or_add_pPr()
    p_rPr = OxmlElement("w:rPr")
    for tag, attrs in [
        ("w:b",     {"w:val": "0"}),
        ("w:i",     {"w:val": "0"}),
        ("w:color", {"w:val": "000000"}),
        ("w:sz",    {"w:val": "24"}),
        ("w:u",     {"w:val": "single"}),
    ]:
        el = OxmlElement(tag)
        for k, v in attrs.items():
            el.set(qn(k), v)
        p_rPr.append(el)
    pPr.append(p_rPr)

    # Standard run properties for "Photograph " prefix + SEQ field runs
    std = [
        ("w:i",     {"w:val": "0"}),
        ("w:color", {"w:val": "000000"}),
        ("w:sz",    {"w:val": "24"}),
        ("w:u",     {"w:val": "single"}),
    ]
    std_with_b0 = [("w:b", {"w:val": "0"})] + std

    # "Photograph " prefix
    para._p.append(_make_run_elem(std, text="Photograph "))

    # SEQ field: begin → instrText → separate → cached value → end
    para._p.append(_make_run_elem(std_with_b0, fld_type="begin"))
    para._p.append(_make_run_elem(std, instr=" SEQ Photograph \\* ARABIC "))
    para._p.append(_make_run_elem(std_with_b0, fld_type="separate"))
    # Cached display value (Word auto-updates on open)
    cached_rpr = std + [("w:noProof", {})]
    para._p.append(_make_run_elem(cached_rpr, text=str(photo_number)))
    para._p.append(_make_run_elem(std_with_b0, fld_type="end"))

    # Description run: Calibri 11pt, steel-blue colour, no underline
    desc_text = f": {description}"
    if category:
        desc_text += f" -- {category}"
    desc_rpr = [
        ("w:rFonts", {"w:ascii": "Calibri", "w:hAnsi": "Calibri"}),
        ("w:color",  {"w:val": "44546A"}),
        ("w:sz",     {"w:val": "22"}),
    ]
    para._p.append(_make_run_elem(desc_rpr, text=desc_text))


def add_photo_section_table(doc, photos: list[dict]):
    """
    All photos for one section in a single borderless table.
    Row layout: image row, caption row, image row, caption row …
    """
    n = len(photos)
    table = doc.add_table(rows=n * 2, cols=1)
    table.style = "Normal Table"

    # Centre the table on the page
    tbl = table._tbl
    tblPr = tbl.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "center")
    tblPr.append(jc)

    for i, photo in enumerate(photos):
        photo_path = Path(photo["path"])
        img_row = i * 2
        cap_row = i * 2 + 1

        # ── image cell ────────────────────────────────────────────
        img_cell = table.cell(img_row, 0)
        _remove_cell_borders(img_cell)
        img_para = img_cell.paragraphs[0]
        img_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        img_run = img_para.add_run()
        if photo_path.exists():
            try:
                img_run.add_picture(str(photo_path), width=Inches(4.724))
            except Exception:
                img_para.add_run(f"[Photo: {photo_path.name}]")
        else:
            img_para.add_run(f"[Photo not found: {photo_path.name}]")

        # ── caption cell ─────────────────────────────────────────
        cap_cell = table.cell(cap_row, 0)
        _remove_cell_borders(cap_cell)
        _build_caption_para(
            cap_cell.paragraphs[0],
            photo["number"],
            photo["description"],
            photo.get("category", ""),
        )

    doc.add_paragraph()


# ─── CONCLUSION ───────────────────────────────────────────────────────────────

def _add_signature_table(doc):
    """Two-column signature block: Yours faithfully (left) / Reviewed by (right)."""
    from report_builder import _add_signature_table as _shared_sig
    _shared_sig(doc)


def add_conclusion(doc):
    doc.add_page_break()
    add_section_heading(doc, "4.0 CONCLUSION")
    add_body(doc, (
        f"The inspection covered all accessible external facades and internal areas of the property "
        f"at {PROJECT['address']}. The property was found to be in generally fair to good condition "
        f"with some defects present typical for the age of the structure. No signs of significant "
        f"structural distress attributable to the neighbouring development were observed."
    ))
    add_body(doc, (
        f"A total of {PROJECT['total_photos']} photos was taken during our inspection "
        f"({PROJECT['inspection_date']}). A full set of photos can be downloaded via the "
        f"following link: {PROJECT['photo_link']}"
    ))
    add_body(doc, (
        "I am an appropriately qualified person competent in this area. I possess indemnity "
        "insurance to the satisfaction of the client. We trust that this dilapidation report "
        "meets your requirements."
    ))

    doc.add_paragraph()
    doc.add_paragraph()
    _add_signature_table(doc)


# ─── MAIN BUILD ───────────────────────────────────────────────────────────────

def build_building_report(all_photos: list[dict], output_path: str,
                          template_path: str = None, map_paths: dict = None):
    if template_path and Path(template_path).exists():
        doc = Document(template_path)
        body = doc.element.body
        sectPr = body.find(qn("w:sectPr"))
        for child in list(body):
            body.remove(child)
        if sectPr is not None:
            body.append(sectPr)
        print(f"Using template: {Path(template_path).name}")
    else:
        doc = Document()
        for section in doc.sections:
            section.top_margin = Cm(2.0)
            section.bottom_margin = Cm(2.0)
            section.left_margin = Cm(1.5)
            section.right_margin = Cm(1.5)

    # cover page now includes the Name/Date of Inspection/To block at the bottom
    add_cover_page(doc, cover_photo=map_paths.get("cover") if map_paths else None)
    add_contents(doc)
    add_preamble(doc)
    add_introduction(doc, map_paths=map_paths)
    add_existing_conditions_intro(doc)
    add_conclusion(doc)

    # ── Appendix photo sections ───────────────────────────────────────────────
    # Group photos so all photos in the same appendix+facade share one table.
    doc.add_page_break()

    current_appendix = None
    current_facade = None
    section_photos: list[dict] = []

    for photo in all_photos:
        appendix = photo.get("appendix", photo["section"])
        facade = photo.get("facade", "")

        # Flush accumulated photos when the section changes
        if appendix != current_appendix or facade != current_facade:
            if section_photos:
                add_photo_section_table(doc, section_photos)
                section_photos = []

            # New appendix label
            if appendix != current_appendix:
                current_appendix = appendix
                current_facade = None          # reset so facade label fires below
                add_appendix_label(doc, appendix)
                doc.add_paragraph()

            # New facade label
            if facade and facade != current_facade:
                current_facade = facade
                add_facade_label(doc, facade)
                doc.add_paragraph()

        section_photos.append(photo)

    # Flush the final section
    if section_photos:
        add_photo_section_table(doc, section_photos)

    doc.save(output_path)
    print(f"\nReport saved to: {output_path}")
