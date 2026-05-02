# report_builder.py - Builds the Word document matching the IIE template format

from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches, Twips
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from pathlib import Path
from config import PROJECT
from generate_rating_images import ensure_rating_images

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


def add_cover_page(doc, cover_photo: str = None):
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

    # "Surrounding Council Assets"
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Surrounding Council Assets")
    set_run(run, size=18, bold=True)

    # "Due to development at:"
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Due to development at:")
    set_run(run, size=12)

    # Address
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(PROJECT["address"])
    set_run(run, size=18, bold=True)

    doc.add_paragraph()

    # Prepared For
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f"Prepared For: {PROJECT['client']}")
    set_run(run, size=12, bold=True)

    doc.add_paragraph()

    # Cover photo - use Street View if available, otherwise placeholder
    if cover_photo and Path(cover_photo).exists():
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run.add_picture(str(cover_photo), width=Inches(6.0))
    else:
        doc.add_paragraph()
        doc.add_paragraph()

    doc.add_paragraph()

    # Metadata block (bottom of cover)
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
    """Second page - report name, inspection date, client."""
    for label, value in [
        ("Name:", f"Pre-Construction Dilapidation Report – {PROJECT['address']} – Council Assets Surrounding"),
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
    # "CONTENTS" heading
    p = doc.add_paragraph()
    try:
        p.style = doc.styles["TOC Heading"]
    except KeyError:
        pass
    run = p.add_run("CONTENTS")
    set_run(run, size=12, bold=True)

    # TOC entries
    for entry in [
        "1.0 PREAMBLE",
        "2.0 INTRODUCTION",
        "3.0 EXISTING CONDITIONS",
        "4.0 CONCLUSION",
    ]:
        p = doc.add_paragraph()
        run = p.add_run(entry)
        set_run(run, size=12, italic=True)

    doc.add_page_break()


def add_section_heading(doc, text):
    """e.g. '1.0 PREAMBLE' - uses Heading 1 style."""
    p = doc.add_paragraph(style="Heading 1")
    run = p.add_run(text)
    set_run(run, bold=True)
    run.font.color.rgb = RGBColor(0, 0, 0)
    return p


def add_sub_label(doc, text):
    """e.g. 'NORTHERN END', 'SURROUNDING ROAD AND PATHWAYS' - 9pt bold."""
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run(run, size=9, bold=True)
    return p


def add_body(doc, text):
    """Standard body paragraph - Times New Roman 12pt."""
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run(run, size=12)
    return p


def add_bullet(doc, text):
    """Bullet point paragraph."""
    p = doc.add_paragraph()
    run = p.add_run(f"•\t{text}")
    set_run(run, size=12)
    return p


def add_preamble(doc):
    add_section_heading(doc, "1.0 PREAMBLE")
    add_body(doc, (
        f"This pre-construction dilapidation report is based on visual inspection only. "
        f"The purpose of this report is to provide a photographic record of the Council Assets along "
        f"{PROJECT['streets_inspected']}. The council assets include roads and footpaths within the zone of "
        f"influence of the proposed construction site at {PROJECT['address']}."
    ))
    add_body(doc, (
        f"This report also gives a brief descriptive record of any defects noted on the date of our inspection. "
        f"The inspection included all site features and accessible areas of the council assets as photographed "
        f"and identified within this report. Photos show items of note, such as cracks, as well as some overviews."
    ))
    add_body(doc, (
        f"A total of {PROJECT['total_photos']} photos was taken during our inspection ({PROJECT['inspection_date']}). "
        f"A full set of photos can be downloaded via the following link: {PROJECT['photo_link']}"
    ))
    add_body(doc, (
        "This report is not a structural or civil engineering report. It is the property owner's responsibility "
        "to seek further structural engineering advice on any defective elements which have been noted in this report."
    ))
    doc.add_paragraph()


def add_map_figure(doc, image_path: str, caption: str):
    """Insert a map image with caption."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    try:
        run.add_picture(image_path, width=Inches(6.0))
    except Exception:
        p.add_run(f"[Map image not found: {image_path}]")
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = cap.add_run(caption)
    set_run(run, size=12, bold=True, italic=True)


def add_introduction(doc, map_paths: dict = None):
    map_paths = map_paths or {}
    ensure_rating_images(Path(__file__).parent)
    add_section_heading(doc, "2.0 INTRODUCTION")
    add_body(doc, (
        f"The inspection focused conditions to the council assets that surround {PROJECT['address']}. "
        f"The locality of the site is shown in Figure 1 below. The 50m inspection corridor extending "
        f"either side of the subject address is illustrated in Figure 3."
    ))
    doc.add_paragraph()

    # Figure 1 - Locality Plan
    if map_paths.get("figure1"):
        add_map_figure(doc, map_paths["figure1"], "Figure 1 – Site Locality Plan (Not to Scale)")
    else:
        p = doc.add_paragraph()
        run = p.add_run("Figure 1 – Site Locality Plan (Not to Scale)")
        set_run(run, size=12, bold=True, italic=True)

    doc.add_paragraph()
    add_body(doc, (
        "The areas inspected include all road pavement surfaces, pathways, stairs, concrete footpaths, "
        "grass, kerb and gutters, vehicular crossings, in-ground service pits, street trees and signs within "
        "the vicinity of the subject development. Specifically, when discussing the council assets herein, "
        "we discuss them in the following sub-categories:"
    ))

    add_bullet(doc, "Surrounding Roads and Pathways (Building Side)")
    add_bullet(doc, "Surrounding Roads and Pathways (Opposite Side)")

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
        add_map_figure(doc, map_paths["figure2"], "Figure 2 – Site Property Map (Not to Scale)")
    else:
        p = doc.add_paragraph()
        run = p.add_run("Figure 2 – Site Property Map (Not to Scale)")
        set_run(run, size=12, bold=True, italic=True)

    doc.add_paragraph()

    # Figure 3 - 50m Inspection Corridor
    if map_paths.get("figure3"):
        add_map_figure(doc, map_paths["figure3"], "Figure 3 – 50m Inspection Corridor (Not to Scale)")
    else:
        p = doc.add_paragraph()
        run = p.add_run("Figure 3 – 50m Inspection Corridor (Not to Scale)")
        set_run(run, size=12, bold=True, italic=True)

    doc.add_paragraph()

    # Figure 4 - Pavement Rating Graph
    rating_graph = Path(__file__).parent / "rating_graph.png"
    if rating_graph.exists():
        add_map_figure(doc, str(rating_graph), "Figure 4 – Graph Depicting Pavement Rating System")
    else:
        p = doc.add_paragraph()
        run = p.add_run("Figure 4 – Graph Depicting Pavement Rating System")
        set_run(run, size=12, bold=True, italic=True)

    doc.add_paragraph()

    # Figure 5 - Pavement Rating Table
    rating_table = Path(__file__).parent / "rating_table.png"
    if rating_table.exists():
        add_map_figure(doc, str(rating_table), "Figure 5 – Table Describing Pavement Rating System in More Detail")
    else:
        p = doc.add_paragraph()
        run = p.add_run("Figure 5 – Table Describing Pavement Rating System in More Detail")
        set_run(run, size=12, bold=True, italic=True)

    doc.add_page_break()


def add_existing_conditions_intro(doc):
    add_section_heading(doc, "3.0 EXISTING CONDITIONS")
    add_body(doc, (
        f"The inspection covered all council-managed roads and footpaths along {PROJECT['streets_inspected']} "
        f"within the zone of influence of the proposed development at {PROJECT['address']}. "
        f"The roads and pathways were found to be in fair to poor condition with some cracks present "
        f"typical for the age of the infrastructure. Photos and description of condition can be found overleaf."
    ))
    doc.add_paragraph()
    add_sub_label(doc, "SURROUNDING ROAD AND PATHWAYS")
    doc.add_paragraph()


def add_photo_table_entry(doc, photo: dict):
    """Add photo + caption as a single-column table row matching template format."""
    photo_path = Path(photo["path"])

    # Create single-column table (no borders)
    table = doc.add_table(rows=1, cols=1)
    table.style = "Normal Table"
    cell = table.cell(0, 0)

    # Remove all borders
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for border_name in ["top", "left", "bottom", "right", "insideH", "insideV"]:
        border = OxmlElement(f"w:{border_name}")
        border.set(qn("w:val"), "none")
        tcBorders.append(border)
    tcPr.append(tcBorders)

    # Set cell width (~120mm)
    tcW = OxmlElement("w:tcW")
    tcW.set(qn("w:w"), "6810")
    tcW.set(qn("w:type"), "dxa")
    tcPr.append(tcW)

    # Add photo
    photo_para = cell.paragraphs[0]
    photo_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = photo_para.add_run()
    if photo_path.exists():
        try:
            run.add_picture(str(photo_path), width=Inches(4.73))
        except Exception:
            run.add_run(f"[Photo: {photo_path.name}]")
    else:
        photo_para.add_run(f"[Photo not found: {photo_path.name}]")

    # Add caption paragraph in same cell
    cap_para = cell.add_paragraph()
    cap_para.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # "Photograph N:" — underlined + bold
    r1 = cap_para.add_run(f"Photograph {photo['number']}:")
    set_run(r1, size=9, bold=True, underline=True)

    # Description — bold + italic
    r2 = cap_para.add_run(f" {photo['description']}")
    set_run(r2, size=9, bold=True, italic=True)

    doc.add_paragraph()


def add_direction_heading(doc, section_name: str):
    """e.g. 'NORTHERN END' - 9pt bold, centred."""
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(section_name)
    set_run(run, size=9, bold=True)
    doc.add_paragraph()


def add_conclusion(doc):
    doc.add_page_break()
    add_section_heading(doc, "4.0 CONCLUSION")
    add_body(doc, (
        f"The inspection covered all council-managed roads and footpaths along {PROJECT['streets_inspected']} "
        f"within the zone of influence of the proposed development at {PROJECT['address']}. "
        f"The roads and pathways were found to be in reasonable to poor condition with some cracks present "
        f"typical for the age of the infrastructure. No signs of significant structural distress were observed."
    ))
    add_body(doc, (
        "The roads and footpaths were inspected on both sides of the roads. Across the road and footpaths there "
        "was cracking present which showed typical wear of council assets. These items have been documented in "
        "the photographic record above for future reference."
    ))
    add_body(doc, (
        f"A total of {PROJECT['total_photos']} photos was taken during our inspection ({PROJECT['inspection_date']}). "
        f"A full set of photos can be downloaded via the following link: {PROJECT['photo_link']}"
    ))
    add_body(doc, (
        "I am an appropriately qualified and person competent in this area. I possess indemnity insurance to "
        "the satisfaction of the client. We trust that this dilapidation report meets your requirements."
    ))

    doc.add_paragraph()
    doc.add_paragraph()

    # Signature block
    p = doc.add_paragraph()
    r1 = p.add_run("Yours faithfully,")
    set_run(r1, size=12)

    doc.add_paragraph()
    doc.add_paragraph()

    p = doc.add_paragraph()
    r1 = p.add_run(PROJECT["inspector_name"])
    set_run(r1, size=12, bold=True)

    p = doc.add_paragraph()
    r1 = p.add_run(PROJECT["inspector_quals"])
    set_run(r1, size=12, italic=True)

    p = doc.add_paragraph()
    r1 = p.add_run(f"For, and on behalf of, {PROJECT['company']}.")
    set_run(r1, size=12)


def build_report(all_photos: list[dict], output_path: str, template_path: str = None, map_paths: dict = None):
    if template_path and Path(template_path).exists():
        doc = Document(template_path)
        # Clear all body content but preserve the sectPr (section/page layout)
        body = doc.element.body
        sectPr = body.find(qn("w:sectPr"))
        for child in list(body):
            body.remove(child)
        # Re-attach sectPr so page layout/margins/headers are preserved
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

    sections_seen = []
    for photo in all_photos:
        section = photo["section"]
        if not sections_seen or sections_seen[-1] != section:
            sections_seen.append(section)
            add_direction_heading(doc, section)
        add_photo_table_entry(doc, photo)

    add_conclusion(doc)

    doc.save(output_path)
    print(f"\nReport saved to: {output_path}")
