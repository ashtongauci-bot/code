# report_builder_building.py - Builds building dilapidation reports

from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from pathlib import Path
from config import PROJECT

TNR = "Times New Roman"


def set_run(run, size=None, bold=False, italic=False, underline=False, font_name=TNR):
    run.font.name = font_name
    if size:
        run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.underline = underline


def add_body(doc, text, size=12, bold=False, italic=False, align=WD_ALIGN_PARAGRAPH.LEFT):
    p = doc.add_paragraph()
    p.alignment = align
    run = p.add_run(text)
    set_run(run, size=size, bold=bold, italic=italic)
    return p


def add_section_heading(doc, text):
    """Heading 1 - e.g. '1.0 PREAMBLE'"""
    p = doc.add_paragraph(style="Heading 1")
    run = p.add_run(text)
    set_run(run, size=18, bold=True)
    run.font.color.rgb = RGBColor(0, 0, 0)
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
        run.add_picture(str(photo_to_use), width=Inches(6.0))
    else:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("[Cover photo – auto-generated or place cover.jpg in photos folder]")
        run.italic = True
        set_run(run, size=11)

    doc.add_paragraph()

    # Metadata
    for label, value in [
        ("Prepared By:", PROJECT["inspector_name"]),
        ("Date:", PROJECT["report_date"]),
        ("Ref:", PROJECT["ref"]),
    ]:
        p = doc.add_paragraph()
        run = p.add_run(f"{label}\t{value}")
        set_run(run, size=12)

    doc.add_page_break()


def add_report_metadata(doc):
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
    doc.add_paragraph()


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
    add_body(doc, (
        f"This pre-construction dilapidation report is based on visual inspection only. "
        f"The purpose of this report is to provide a photographic record of the condition of "
        f"the property at {PROJECT['address']} prior to construction works at the neighbouring "
        f"development at {PROJECT.get('development_address', PROJECT['address'])}."
    ))
    add_body(doc, (
        f"This report gives a brief descriptive record of any defects noted on the date of our "
        f"inspection. The inspection included all site features and accessible areas as photographed "
        f"and identified within this report."
    ))
    add_body(doc, (
        f"A total of {PROJECT['total_photos']} photos was taken during our inspection "
        f"({PROJECT['inspection_date']}). A full set of photos can be downloaded via the "
        f"following link: {PROJECT['photo_link']}"
    ))
    add_body(doc, (
        "This report is not a structural or civil engineering report. It is the property owner's "
        "responsibility to seek further structural engineering advice on any defective elements "
        "noted in this report."
    ))
    doc.add_paragraph()


def add_introduction(doc, map_paths: dict = None):
    map_paths = map_paths or {}
    add_section_heading(doc, "2.0 INTRODUCTION")
    add_body(doc, (
        f"The inspection focused on the existing conditions of the property at {PROJECT['address']}. "
        f"The extent of the inspection area is highlighted in Figure 1 below."
    ))
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
        "The areas inspected include all accessible external facades and internal areas of the "
        "property. Specifically, the inspection covered:"
    ))

    for item in ["External Facades", "Internal Areas"]:
        p = doc.add_paragraph()
        run = p.add_run(f"•\t{item}")
        set_run(run, size=12)

    doc.add_paragraph()
    add_body(doc, "Description of terms in the report (based on visual observations) are:")

    for term, definition in [
        ("Good -", "Items do not appear to have any defects and are in good condition."),
        ("Fair -", "Item is in reasonable condition for its age and may have some minor defect(s)."),
        ("Poor -", "Indicates generally that a defect is beyond minor and further structural advice may be required."),
    ]:
        p = doc.add_paragraph()
        r1 = p.add_run(f"{term}    ")
        set_run(r1, size=12, bold=True)
        r2 = p.add_run(definition)
        set_run(r2, size=12)

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

    # Figures 3 & 4 - AS2870 rating tables (always included as Word tables)
    add_as2870_table_c1(doc, fig_number=3)
    add_table_3_02(doc, fig_number=4)

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


def add_photo_table_entry(doc, photo: dict):
    """Add photo + caption in a borderless single-column table."""
    photo_path = Path(photo["path"])

    table = doc.add_table(rows=1, cols=1)
    table.style = "Normal Table"
    cell = table.cell(0, 0)

    # Remove borders
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for side in ["top", "left", "bottom", "right", "insideH", "insideV"]:
        border = OxmlElement(f"w:{side}")
        border.set(qn("w:val"), "none")
        tcBorders.append(border)
    tcPr.append(tcBorders)

    # Set cell width
    tcW = OxmlElement("w:tcW")
    tcW.set(qn("w:w"), "6803")
    tcW.set(qn("w:type"), "dxa")
    tcPr.append(tcW)

    # Photo
    photo_para = cell.paragraphs[0]
    photo_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = photo_para.add_run()
    if photo_path.exists():
        try:
            run.add_picture(str(photo_path), width=Inches(4.724))
        except Exception:
            photo_para.add_run(f"[Photo: {photo_path.name}]")
    else:
        photo_para.add_run(f"[Photo not found: {photo_path.name}]")

    # Caption: "Photograph N" underlined + ": description -- Cat X (Severity)"
    cap = cell.add_paragraph()
    r1 = cap.add_run(f"Photograph {photo['number']}")
    set_run(r1, size=12, underline=True)
    r2 = cap.add_run(f": {photo['description']} -- {photo.get('category', '')}")
    set_run(r2, size=12)

    doc.add_paragraph()


def _set_table_borders(table):
    """Apply visible single borders to all cells in a table."""
    for row in table.rows:
        for cell in row.cells:
            tc = cell._tc
            tcPr = tc.get_or_add_tcPr()
            tcBorders = OxmlElement("w:tcBorders")
            for side in ["top", "left", "bottom", "right"]:
                border = OxmlElement(f"w:{side}")
                border.set(qn("w:val"), "single")
                border.set(qn("w:sz"), "4")
                border.set(qn("w:color"), "000000")
                tcBorders.append(border)
            tcPr.append(tcBorders)


def _shade_cell(cell, hex_color="D9D9D9"):
    """Apply background shading to a table cell."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def add_as2870_table_c1(doc, fig_number=3):
    """Build AS2870 Appendix C Table C1 as a Word table (always included)."""
    p = doc.add_paragraph()
    r1 = p.add_run("Also, when categorising cracking in this report, we rely on the definitions defined in ")
    set_run(r1, size=11)
    r2 = p.add_run("AS2870-2011, Appendix C (Page 72), Table C1")
    set_run(r2, size=11, italic=True)
    r3 = p.add_run(
        " and the NSW Guide to Standards and Tolerances, 2017 (NSWGST) as per extracts below. "
        "Cracks in this report are therefore categorised as follows:"
    )
    set_run(r3, size=11)
    doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(p.add_run("TABLE C1"), size=11, bold=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(p.add_run("CLASSIFICATION OF DAMAGE WITH REFERENCE TO WALLS"), size=11, bold=True)

    table = doc.add_table(rows=6, cols=3)
    table.style = "Normal Table"
    _set_table_borders(table)

    for col, text in enumerate([
        "Description of typical damage and required repair",
        "Approximate crack width limit (see Note 1)",
        "Damage category",
    ]):
        cell = table.cell(0, col)
        _shade_cell(cell)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run(p.add_run(text), size=10, bold=True)

    for row_idx, (desc, width, cat) in enumerate([
        ("Hairline cracks", "<0.1 mm", "Negligible"),
        ("Fine cracks that do not need repair", "<1 mm", "1\nVery slight"),
        ("Cracks noticeable but easily filled.\nDoors and windows stick slightly", "<5 mm", "2\nSlight"),
        (
            "Cracks can be repaired and possibly a small amount of wall will need to be replaced. "
            "Doors and windows stick. Service pipes can fracture. Weather tightness often impaired",
            "5 mm to 15 mm\n(or a number of cracks 3 mm or more in one group)",
            "3\nModerate",
        ),
        (
            "Extensive repair work involving breaking out and replacing sections of walls, especially "
            "over doors and windows. Window frames and door frames distort. Walls lean or bulge "
            "noticeably, some loss of bearing in beams. Service pipes disrupted",
            "15 mm to 25 mm\nbut also depends on number of cracks",
            "4\nSevere",
        ),
    ], start=1):
        p = table.cell(row_idx, 0).paragraphs[0]
        set_run(p.add_run(desc), size=10)
        p = table.cell(row_idx, 1).paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run(p.add_run(width), size=10)
        p = table.cell(row_idx, 2).paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run(p.add_run(cat), size=10)

    doc.add_paragraph()
    set_run(doc.add_paragraph().add_run("NOTES:"), size=9, bold=True)
    for i, note in enumerate([
        "Where the cracking occurs in easily repaired plasterboard or similar clad-framed partitions, "
        "the crack width limits may be increased by 50% for each damage category.",
        "Crack width is the main factor by which damage to walls is categorized. The width may be "
        "supplemented by other factors, including serviceability, in assessing category of damage.",
        "In assessing the degree of damage, account shall be taken of the location in the building "
        "or structure where it occurs, and also of the function of the building or structure.",
    ], start=1):
        p = doc.add_paragraph()
        set_run(p.add_run(f"{i}    "), size=9)
        set_run(p.add_run(note), size=9)

    doc.add_paragraph()
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(cap.add_run(
        f"Figure {fig_number} – AS2870-2011 Appendix C, Table C1 – "
        "Classification of Damage with Reference to Walls"
    ), size=11, bold=True, italic=True)
    doc.add_paragraph()


def add_table_3_02(doc, fig_number=4):
    """Build NSW Guide to Standards and Tolerances Table 3.02 as a Word table (always included)."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(p.add_run(
        "TABLE 3.02  DAMAGE TO WALLS CAUSED BY MOVEMENT OF SLABS AND FOOTINGS AND OTHER CAUSES"
    ), size=11, bold=True)

    table = doc.add_table(rows=6, cols=3)
    table.style = "Normal Table"
    _set_table_borders(table)

    for col, text in enumerate([
        "Description of typical damage\nand required repair",
        "Crack width limit",
        "Damage Category",
    ]):
        cell = table.cell(0, col)
        _shade_cell(cell)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run(p.add_run(text), size=10, bold=True)

    for row_idx, (desc, width, cat) in enumerate([
        ("Hairline cracks", "< 0.1 mm", "0 Negligible"),
        ("Fine cracks that do not need repair", "< 1 mm", "1 Very slight"),
        ("Cracks noticeable but easily filled.\nDoors and windows stick slightly", "< 5 mm", "2 Slight"),
        (
            "Cracks can be repaired and possibly a small amount of wall will need to be replaced. "
            "Doors and windows stick. Service pipes can fracture. Weather tightness often impaired",
            "5 mm to 15 mm\n(or a number of cracks 3 mm or more in one group)",
            "3 Moderate",
        ),
        (
            "Extensive repair work involving breaking out and replacing sections of walls, especially "
            "over doors and windows. Window and doorframes distort. Walls lean or bulge noticeably. "
            "Some loss of bearing in beams. Service pipes disrupted",
            "15 mm to 25 mm\nbut also depends on number of cracks",
            "4 Severe",
        ),
    ], start=1):
        p = table.cell(row_idx, 0).paragraphs[0]
        set_run(p.add_run(desc), size=10)
        p = table.cell(row_idx, 1).paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run(p.add_run(width), size=10)
        p = table.cell(row_idx, 2).paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run(p.add_run(cat), size=10)

    doc.add_paragraph()
    p = doc.add_paragraph()
    set_run(p.add_run(
        "Taken from AS2870: Residential slabs and footings – Construction, Table C1. "
        "Classification of damage with reference to walls. Reproduced with permission from "
        "SAI Global Ltd under Licence 1407-c122."
    ), size=9, italic=True)
    doc.add_paragraph()
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(cap.add_run(
        f"Figure {fig_number} – NSW Guide to Standards and Tolerances, 2017 (NSWGST) Table 3.02"
    ), size=11, bold=True, italic=True)
    doc.add_paragraph()


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

    p = doc.add_paragraph()
    set_run(p.add_run("Yours faithfully,"), size=12)
    doc.add_paragraph()
    doc.add_paragraph()

    p = doc.add_paragraph()
    set_run(p.add_run(PROJECT["inspector_name"]), size=12, bold=True)
    p = doc.add_paragraph()
    set_run(p.add_run(PROJECT["inspector_quals"]), size=12, italic=True)
    p = doc.add_paragraph()
    set_run(p.add_run(f"For, and on behalf of, {PROJECT['company']}."), size=12)


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

    add_cover_page(doc, cover_photo=map_paths.get("cover") if map_paths else None)
    add_report_metadata(doc)
    add_contents(doc)
    add_preamble(doc)
    add_introduction(doc, map_paths=map_paths)
    add_existing_conditions_intro(doc)
    add_conclusion(doc)

    # Appendix sections - group by appendix then facade
    doc.add_page_break()

    appendices_seen = []
    facades_seen = []

    for photo in all_photos:
        appendix = photo.get("appendix", photo["section"])
        facade = photo.get("facade", "")

        if appendix not in appendices_seen:
            appendices_seen.append(appendix)
            add_appendix_label(doc, appendix)
            doc.add_paragraph()

        if facade and (not facades_seen or facades_seen[-1] != facade):
            facades_seen.append(facade)
            add_facade_label(doc, facade)
            doc.add_paragraph()

        add_photo_table_entry(doc, photo)

    doc.save(output_path)
    print(f"\nReport saved to: {output_path}")
