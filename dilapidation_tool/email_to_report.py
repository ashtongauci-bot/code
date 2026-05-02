#!/usr/bin/env python3
"""
email_to_report.py

Paste a client email → Claude extracts project details → fills any gaps
interactively → updates config.py → runs the report generator.

Usage:  python email_to_report.py
"""

import json
import re
import subprocess
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).parent
sys.path.insert(0, str(TOOL_DIR))

import config as cfg  # noqa: E402 — must come after sys.path update

# ── Field definitions ────────────────────────────────────────────────────────

REQUIRED_FIELDS = [
    ("address",         "Subject property address"),
    ("client",          "Client / company name"),
    ("inspection_date", "Inspection date (e.g. Wednesday 25th of April 2026)"),
    ("report_date",     "Report date (DD/MM/YYYY)"),
    ("ref",             "Reference number (e.g. RS2401-D06[A])"),
]

OPTIONAL_FIELDS = [
    ("total_photos", "Total number of photos (leave blank to auto-count)"),
    ("photo_link",   "Photo download link (leave blank to skip)"),
]

CONDITIONAL_FIELDS = {
    "council_assets": [
        ("streets_inspected", "Streets inspected (e.g. Mary Street, Campbell Street)"),
    ],
    "building": [
        ("development_address", "Neighbouring development address"),
    ],
}

EXTRACT_PROMPT = """\
Extract project details from this client email for a pre-construction dilapidation report.

Return ONLY a JSON object with these fields (use null for anything not mentioned):
{
  "report_type": "council_assets" or "building"
               (council_assets = roads/footpaths/council assets; building = property/building),
  "address": "full subject property address",
  "client": "client company or person name",
  "inspection_date": "formatted as 'DayName DDth/st/nd/rd of Month YYYY'",
  "report_date": "DD/MM/YYYY",
  "ref": "reference or job number if mentioned",
  "total_photos": integer or null,
  "photo_link": "URL or file path if mentioned, else null",
  "streets_inspected": "comma-separated street names (council assets only, else null)",
  "development_address": "neighbouring development address (building only, else null)"
}

Email:
"""

# ── Helpers ──────────────────────────────────────────────────────────────────

def _ask(prompt: str, required: bool = True) -> str:
    """Prompt the user for input, re-asking if required and blank."""
    while True:
        val = input(f"  {prompt}: ").strip()
        if val or not required:
            return val
        print("  (this field is required)")


def _count_photos() -> int:
    """Count image files across the photos directory."""
    photos_dir = TOOL_DIR / "photos"
    if not photos_dir.exists():
        return 0
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    return sum(1 for p in photos_dir.rglob("*") if p.suffix.lower() in exts)


def _ordinal(n: int) -> str:
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    return f"{n}{suffix}"


# ── Email input ──────────────────────────────────────────────────────────────

def get_email_text() -> str:
    print("=" * 60)
    print("DILAPIDATION REPORT – EMAIL PARSER")
    print("=" * 60)
    print()
    print("Paste the client email below.")
    print("When finished, type  ---END---  on its own line and press Enter.")
    print()
    lines = []
    while True:
        line = input()
        if line.strip() == "---END---":
            break
        lines.append(line)
    return "\n".join(lines)


# ── Claude extraction ────────────────────────────────────────────────────────

def extract_fields(email_text: str) -> dict:
    try:
        import anthropic
    except ImportError:
        print("  (anthropic package not installed – skipping AI extraction)")
        return {}

    print("\nExtracting details with Claude...")
    client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": EXTRACT_PROMPT + email_text
                       + "\n\nRespond with ONLY the JSON object, no markdown or explanation.",
        }],
    )
    raw = msg.content[0].text.strip()
    # Strip any accidental code fences
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  Warning: Could not parse Claude response ({e}). Entering manually.")
        return {}


# ── Interactive gap-fill ─────────────────────────────────────────────────────

def fill_missing(fields: dict) -> dict:
    # ── Report type ───────────────────────────────────────────────────────────
    rt = fields.get("report_type") or ""
    while rt not in ("council_assets", "building"):
        print()
        rt = _ask("Report type — enter 'council_assets' or 'building'")
    fields["report_type"] = rt

    print()
    print("── Extracted fields " + "─" * 40)
    for k, v in fields.items():
        if v is not None:
            print(f"  {k}: {v}")
    print("─" * 60)

    # ── Required fields ───────────────────────────────────────────────────────
    print("\nFilling in any missing required fields...")
    for field, label in REQUIRED_FIELDS:
        if not fields.get(field):
            fields[field] = _ask(label, required=True)

    # ── Conditional fields (report-type specific) ─────────────────────────────
    for field, label in CONDITIONAL_FIELDS.get(rt, []):
        if not fields.get(field):
            fields[field] = _ask(label, required=True)

    # ── Optional fields ───────────────────────────────────────────────────────
    print()
    for field, label in OPTIONAL_FIELDS:
        if not fields.get(field):
            val = _ask(label, required=False)
            if val:
                fields[field] = val

    # ── total_photos: auto-count if blank ─────────────────────────────────────
    if not fields.get("total_photos"):
        counted = _count_photos()
        if counted:
            print(f"  total_photos: auto-counted {counted} photos from photos/ folder")
            fields["total_photos"] = counted
        else:
            fields["total_photos"] = int(_ask("Total number of photos", required=True))
    else:
        try:
            fields["total_photos"] = int(fields["total_photos"])
        except (TypeError, ValueError):
            fields["total_photos"] = int(_ask("Total number of photos (enter a number)", required=True))

    # ── photo_link default ────────────────────────────────────────────────────
    if not fields.get("photo_link"):
        fields["photo_link"] = "Insert photo link here"

    return fields


# ── Config writer ─────────────────────────────────────────────────────────────

def write_config(fields: dict):
    """Overwrite config.py with updated values, preserving API keys and settings."""
    p = dict(cfg.PROJECT)

    # Apply extracted / user-supplied values
    for key in [
        "address", "client", "inspection_date", "report_date", "ref",
        "total_photos", "photo_link", "streets_inspected", "development_address",
    ]:
        if fields.get(key) is not None:
            p[key] = fields[key]

    # Keep inspector / reviewer / company from existing config unchanged
    report_type = fields["report_type"]

    def fmt_val(v):
        if isinstance(v, int):
            return str(v)
        return repr(v)

    project_block = "PROJECT = {\n"
    for k, v in p.items():
        project_block += f'    "{k}": {fmt_val(v)},\n'
    project_block += "}"

    photo_sections_block = (
        "PHOTO_SECTIONS = [\n"
        + "".join(f'    {repr(s)},\n' for s in cfg.PHOTO_SECTIONS)
        + "]"
    )

    building_sections_block = (
        "BUILDING_SECTIONS = [\n"
        + "".join(f'    {repr(s)},\n' for s in cfg.BUILDING_SECTIONS)
        + "]"
    )

    photo_workers = getattr(cfg, "PHOTO_WORKERS", 5)
    max_photos    = getattr(cfg, "MAX_PHOTOS_PER_SECTION", 0)
    max_line      = f"\nMAX_PHOTOS_PER_SECTION = {max_photos}\n" if max_photos else ""

    content = f'''\
# config.py - Edit these details before running

# ─── REPORT TYPE ───────────────────────────────────────────────
# Options: "council_assets" or "building"
REPORT_TYPE = "{report_type}"

{project_block}

# Your Anthropic API key
ANTHROPIC_API_KEY = {repr(cfg.ANTHROPIC_API_KEY)}

# Your Google Maps API key (needs Maps Static API + Geocoding API enabled)
GOOGLE_MAPS_API_KEY = {repr(cfg.GOOGLE_MAPS_API_KEY)}

# Number of photos to analyze simultaneously (higher = faster but more API load)
# Recommended: 5-10. Max: 20
PHOTO_WORKERS = {photo_workers}
{max_line}
# ─── COUNCIL ASSETS PHOTO SECTIONS ─────────────────────────────
# Used when REPORT_TYPE = "council_assets"
{photo_sections_block}

# ─── BUILDING PHOTO SECTIONS ────────────────────────────────────
# Used when REPORT_TYPE = "building"
# Each entry: (folder_name, appendix_label, facade_label)
{building_sections_block}
'''

    config_path = TOOL_DIR / "config.py"
    config_path.write_text(content)
    print(f"\nconfig.py updated.")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    email_text = get_email_text()

    if not email_text.strip():
        print("No email text provided. Exiting.")
        return

    fields = extract_fields(email_text)
    fields = fill_missing(fields)

    print()
    print("── Final project details " + "─" * 36)
    for k, v in fields.items():
        if v is not None:
            print(f"  {k}: {v}")
    print("─" * 60)

    confirm = input("\nLook good? Press Enter to generate report, or 'n' to cancel: ").strip()
    if confirm.lower() == "n":
        print("Cancelled — config.py was NOT changed.")
        return

    write_config(fields)

    print("\nRunning report generator...")
    print("=" * 60)
    result = subprocess.run(
        [sys.executable, str(TOOL_DIR / "main.py")],
        cwd=str(TOOL_DIR),
    )
    if result.returncode != 0:
        print("\nReport generation encountered an error (see above).")
    else:
        print("\nAll done!")


if __name__ == "__main__":
    main()
