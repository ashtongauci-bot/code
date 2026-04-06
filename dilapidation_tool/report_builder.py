# report_builder.py - Builds the Word document in the correct report format

from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from pathlib import Path
from config import PROJECT


def set_font(run, bold=False, size=11, color=None):
    run.bold = bold
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor(*color)


def add_heading(doc, text, level=1, size=14, bold=True, align=WD_ALIGN_PARAGRAPH.LEFT):
    p = doc.add_paragraph()
    p.alignment = align
    run = p.add_run(text)
    set_font(run, bold=bold, size=size)
    return p


def add_body(doc, text, size=11):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_font(run, size=size)
    return p


def add_cover_page(doc):
    doc.add_paragraph()
    doc.add_paragraph()

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("PRE-CONSTRUCTION DILAPIDATION REPORT")
    set_font(run, bold=True, size=16)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run("At\nSurrounding Council Assets\nDue to development at:")
    set_font(run, size=12)

    addr = doc.add_paragraph()
    addr.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = addr.add_run(PROJECT["address"])
    set_font(run, bold=True, size=13)

    doc.add_paragraph()

    prep = doc.add_paragraph()
    prep.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = prep.add_run(f"Prepared For: {PROJECT['client']}")
    set_font(run, size=12)

    doc.add_paragraph()
    doc.add_paragraph()

    for label, value in [
        ("Prepared By:", PROJECT["inspector_name"]),
        ("Date:", PROJECT["report_date"]),
        ("Ref:", PROJECT["ref"]),
    ]:
        row = doc.add_paragraph()
        r1 = row.add_run(f"{label:<20}")
        set_font(r1, bold=True, size=11)
        r2 = row.add_run(value)
        set_font(r2, size=11)

    doc.add_page_break()


def add_contents(doc):
    add_heading(doc, "CONTENTS", size=14)
    doc.add_paragraph()
    for section, page in [("1.0 PREAMBLE", "3"), ("2.0 INTRODUCTION", "3"), ("3.0 EXISTING CONDITIONS", "6"), ("4.0 CONCLUSION", "")]:
        p = doc.add_paragraph()
        run = p.add_run(f"{section}")
        set_font(run, size=11)
    doc.add_page_break()


def add_preamble(doc):
    add_heading(doc, "1.0 PREAMBLE", size=13)
    text = (
        f"This pre-construction dilapidation report is based on visual inspection only. "
        f"The purpose of this report is to provide a photographic record of the Council Assets along "
        f"{PROJECT['streets_inspected']}. The council assets include roads and footpaths within the zone of "
        f"influence of the proposed construction site at {PROJECT['address']}.\n\n"
        f"This report also gives a brief descriptive record of any defects noted on the date of our inspection. "
        f"The inspection included all site features and accessible areas of the council assets as photographed "
        f"and identified within this report. Photos show items of note, such as cracks, as well as some overviews.\n\n"
        f"A total of {PROJECT['total_photos']} photos was taken during our inspection ({PROJECT['inspection_date']}). "
        f"A full set of photos can be downloaded via the following link: {PROJECT['photo_link']}\n\n"
        f"This report is not a structural or civil engineering report. It is the property owner's responsibility "
        f"to seek further structural engineering advice on any defective elements which have been noted in this report."
    )
    add_body(doc, text)
    doc.add_paragraph()


def add_introduction(doc):
    add_heading(doc, "2.0 INTRODUCTION", size=13)
    text = (
        f"The inspection focused conditions to the council assets that surround {PROJECT['address']}. "
        f"The extent of which is highlighted in Figure 1 below."
    )
    add_body(doc, text)
    doc.add_paragraph()

    # Placeholder for Figure 1
    fig1 = doc.add_paragraph()
    fig1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = fig1.add_run("[Figure 1 – Site Locality Plan (Not to Scale) – Insert map here]")
    run.italic = True
    set_font(run, size=10)

    doc.add_paragraph()
    add_body(doc, (
        "The areas inspected include all road pavement surfaces, pathways, stairs, concrete footpaths, "
        "grass, kerb and gutters, vehicular crossings, in-ground service pits, street trees and signs within "
        "the vicinity of the subject development. Specifically, when discussing the council assets herein, "
        "we discuss them in the following sub-categories:"
    ))

    for item in ["Surrounding Roads and Pathways (Building Side)", "Surrounding Roads and Pathways (Opposite Side)"]:
        p = doc.add_paragraph(style="List Bullet")
        run = p.add_run(item)
        set_font(run, size=11)

    doc.add_paragraph()
    add_body(doc, "Description of terms in the report (based on visual observations) are:")

    for term, definition in [
        ("Good -", "Items do not appear to have any defects and are in good condition."),
        ("Fair -", "Item is in reasonable condition for its age and may have some minor defect(s)."),
        ("Poor -", "Indicates generally that a defect is beyond minor and further structural advice may be required."),
    ]:
        p = doc.add_paragraph()
        r1 = p.add_run(f"{term}    ")
        set_font(r1, bold=True, size=11)
        r2 = p.add_run(definition)
        set_font(r2, size=11)

    doc.add_paragraph()
    fig2 = doc.add_paragraph()
    fig2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = fig2.add_run("[Figure 2 – Pavement Rating Graph – Insert here]")
    run.italic = True
    set_font(run, size=10)

    doc.add_paragraph()
    fig3 = doc.add_paragraph()
    fig3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = fig3.add_run("[Figure 3 – Pavement Rating Table – Insert here]")
    run.italic = True
    set_font(run, size=10)

    doc.add_page_break()


def add_existing_conditions_intro(doc):
    add_heading(doc, "3.0 EXISTING CONDITIONS", size=13)
    text = (
        f"The inspection covered all council-managed roads and footpaths along {PROJECT['streets_inspected']} "
        f"within the zone of influence of the proposed development at {PROJECT['address']}. "
        f"The roads and pathways were found to be in fair to poor condition with some cracks present "
        f"typical for the age of the infrastructure. Photos and description of condition can be found overleaf."
    )
    add_body(doc, text)
    doc.add_paragraph()
    add_heading(doc, "SURROUNDING ROAD AND PATHWAYS", size=12)
    doc.add_paragraph()


def add_photo_entry(doc, photo: dict):
    """Add a single photo + caption to the document."""
    photo_path = Path(photo["path"])

    if photo_path.exists():
        try:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run()
            run.add_picture(str(photo_path), width=Cm(14))
        except Exception:
            p = doc.add_paragraph()
            run = p.add_run(f"[Photo: {photo_path.name}]")
            run.italic = True
    else:
        p = doc.add_paragraph()
        run = p.add_run(f"[Photo not found: {photo_path.name}]")
        run.italic = True

    caption = doc.add_paragraph()
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = caption.add_run(f"Photograph {photo['number']}: {photo['description']}")
    set_font(run, size=10)

    doc.add_paragraph()


def add_section_heading(doc, section_name: str):
    doc.add_paragraph()
    p = add_heading(doc, section_name, size=12, bold=True)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()


def add_conclusion(doc):
    doc.add_page_break()
    add_heading(doc, "4.0 CONCLUSION", size=13)
    text = (
        f"The inspection covered all council-managed roads and footpaths along {PROJECT['streets_inspected']} "
        f"within the zone of influence of the proposed development at {PROJECT['address']}. "
        f"The roads and pathways were found to be in reasonable to poor condition with some cracks present "
        f"typical for the age of the infrastructure. No signs of significant structural distress were observed.\n\n"
        f"The roads and footpaths were inspected on both sides of the roads. Across the road and footpaths there "
        f"was cracking present which showed typical wear of council assets. These items have been documented in "
        f"the photographic record above for future reference.\n\n"
        f"A total of {PROJECT['total_photos']} photos was taken during our inspection ({PROJECT['inspection_date']}). "
        f"A full set of photos can be downloaded via the following link: {PROJECT['photo_link']}\n\n"
        f"I am an appropriately qualified and person competent in this area. I possess indemnity insurance to "
        f"the satisfaction of the client. We trust that this dilapidation report meets your requirements."
    )
    add_body(doc, text)

    doc.add_paragraph()
    doc.add_paragraph()

    sig = doc.add_paragraph()
    r1 = sig.add_run(f"Yours faithfully,\n\n\n{PROJECT['inspector_name']}\n{PROJECT['inspector_quals']}\nFor, and on behalf of, {PROJECT['company']}.")
    set_font(r1, size=11)


def build_report(all_photos: list[dict], output_path: str, template_path: str = None):
    if template_path and Path(template_path).exists():
        doc = Document(template_path)
        # Clear all existing content but keep styles, headers, footers
        body = doc.element.body
        for child in list(body):
            body.remove(child)
        print(f"Using template: {Path(template_path).name}")
    else:
        doc = Document()
        # Page margins
        for section in doc.sections:
            section.top_margin = Cm(2)
            section.bottom_margin = Cm(2)
            section.left_margin = Cm(2.5)
            section.right_margin = Cm(2.5)

    add_cover_page(doc)
    add_contents(doc)
    add_preamble(doc)
    add_introduction(doc)
    add_existing_conditions_intro(doc)

    # Group photos by section
    from itertools import groupby
    sections_seen = []
    for photo in all_photos:
        section = photo["section"]
        if not sections_seen or sections_seen[-1] != section:
            sections_seen.append(section)
            add_section_heading(doc, section)
        add_photo_entry(doc, photo)

    add_conclusion(doc)

    doc.save(output_path)
    print(f"\nReport saved to: {output_path}")
