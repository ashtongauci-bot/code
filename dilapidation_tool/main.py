# main.py - Run this to generate your dilapidation report

import json
from pathlib import Path
import config
from config import PROJECT, GOOGLE_MAPS_API_KEY
from photo_analyzer import analyze_section
from report_builder import build_report
from report_builder_building import build_building_report
from map_generator import generate_maps

REPORT_TYPE = config.REPORT_TYPE

PHOTOS_DIR = Path(__file__).parent / "photos"
OUTPUT_DIR = Path(__file__).parent / "output"
TEMPLATE_PATH = Path(__file__).parent / "26066 - Council Assets (Surrounding 81-85 Campell Street, SURRYHILLS, NSW) - Pre-Construction Dilapidation Report.docx"
CACHE_FILE = Path(__file__).parent / "output" / "photo_cache.json"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def load_cache() -> list[dict]:
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return json.load(f)
    return []


def save_cache(photos: list[dict]):
    with open(CACHE_FILE, "w") as f:
        json.dump(photos, f, indent=2)


def folder_label(folder: Path) -> str:
    """Convert folder name to a display label e.g. 'east_facade' -> 'East Facade'"""
    return folder.name.replace("_", " ").replace("-", " ").title()


def scan_photos_dir(photos_dir: Path) -> list[dict]:
    """
    Auto-scan the photos directory and return a list of section entries.
    Supports both flat and nested structures:
      Flat:   photos/Northern End/          -> section_label="Northern End"
      Nested: photos/Appendix A/East Facade -> appendix="Appendix A", facade="East Facade"
    """
    sections = []

    if not photos_dir.exists():
        return sections

    top_folders = sorted([f for f in photos_dir.iterdir() if f.is_dir()])

    for top_folder in top_folders:
        # Check if this folder has photos directly in it
        direct_photos = [f for f in top_folder.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS]

        # Check if this folder has subfolders
        subfolders = sorted([f for f in top_folder.iterdir() if f.is_dir()])

        if direct_photos:
            # Flat section - use folder name as section label
            sections.append({
                "folder": top_folder,
                "section_label": folder_label(top_folder),
                "appendix": "",
                "facade": "",
            })
        elif subfolders:
            # Nested - top folder is appendix, subfolders are facades
            appendix_label = folder_label(top_folder)
            for subfolder in subfolders:
                sub_photos = [f for f in subfolder.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS]
                if sub_photos:
                    sections.append({
                        "folder": subfolder,
                        "section_label": folder_label(subfolder),
                        "appendix": appendix_label,
                        "facade": folder_label(subfolder),
                    })

    return sections


def process_sections(sections, cached):
    """Process all sections, return all_photos list."""
    cached_files = {p["filename"] for p in cached}
    all_photos = []
    photo_number = 1

    for section in sections:
        folder = section["folder"]
        section_label = section["section_label"]
        appendix = section["appendix"]
        facade = section["facade"]

        photos_in_section = sorted([
            p for p in folder.iterdir()
            if p.suffix.lower() in IMAGE_EXTENSIONS
        ])

        if not photos_in_section:
            continue

        print(f"\n[{section_label}] - {len(photos_in_section)} photos")

        new_photos = [p for p in photos_in_section if p.name not in cached_files]
        already_cached = [p for p in photos_in_section if p.name in cached_files]

        if already_cached:
            print(f"  Using cached results for {len(already_cached)} photos")

        if new_photos:
            print(f"  Analyzing {len(new_photos)} new photos with Claude vision...")
            new_results = analyze_section(
                section_folder=folder,
                section_name=section_label,
                start_number=photo_number,
                report_type=REPORT_TYPE,
                appendix=appendix,
                facade=facade,
            )
            cached.extend(new_results)
            cached_files.update(r["filename"] for r in new_results)
            save_cache(cached)

        for photo_path in photos_in_section:
            match = next((p for p in cached if p["filename"] == photo_path.name), None)
            if match:
                entry = dict(match)
                entry["number"] = photo_number
                entry["section"] = section_label
                entry["appendix"] = appendix
                entry["facade"] = facade
                all_photos.append(entry)
                photo_number += 1

    return all_photos


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("=" * 60)
    print(f"DILAPIDATION REPORT GENERATOR [{REPORT_TYPE.upper()}]")
    print("=" * 60)
    print(f"Project: {PROJECT['address']}")
    print(f"Client:  {PROJECT['client']}")
    print()

    # Auto-scan photos folder
    sections = scan_photos_dir(PHOTOS_DIR)

    if not sections:
        print(f"\nNo photo folders found in: {PHOTOS_DIR}")
        print("Create subfolders inside the photos/ folder and add your photos there.")
        return

    print(f"Found {len(sections)} section(s):")
    for s in sections:
        prefix = f"  {s['appendix']} > " if s["appendix"] else "  "
        print(f"{prefix}{s['section_label']} ({s['folder']})")

    cached = load_cache()
    all_photos = process_sections(sections, cached)

    if not all_photos:
        print("\nNo photos found in any section folders.")
        return

    print(f"\nTotal photos processed: {len(all_photos)}")

    # Generate site maps
    map_paths = {}
    if GOOGLE_MAPS_API_KEY and GOOGLE_MAPS_API_KEY != "your-google-maps-api-key-here":
        try:
            map_paths = generate_maps(PHOTOS_DIR, OUTPUT_DIR)
        except Exception as e:
            print(f"  Warning: Map generation failed: {e}")
            print("  Continuing without maps...")
    else:
        print("\nSkipping map generation (no Google Maps API key in config.py)")

    print("\nBuilding Word document...")

    ref_clean = PROJECT["ref"].replace("/", "-").replace("[", "").replace("]", "")
    output_filename = f"Dilapidation_Report_{ref_clean}.docx"
    output_path = OUTPUT_DIR / output_filename

    if REPORT_TYPE == "building":
        build_building_report(all_photos, str(output_path),
                              template_path=str(TEMPLATE_PATH), map_paths=map_paths)
    else:
        build_report(all_photos, str(output_path),
                     template_path=str(TEMPLATE_PATH), map_paths=map_paths)

    print("\nDone!")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()



def load_cache() -> list[dict]:
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return json.load(f)
    return []


def save_cache(photos: list[dict]):
    with open(CACHE_FILE, "w") as f:
        json.dump(photos, f, indent=2)


def process_sections(sections, cached, photo_number):
    """Process a list of sections, return all_photos and updated photo_number."""
    cached_files = {p["filename"] for p in cached}
    all_photos = []
    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}

    for section_entry in sections:
        if len(section_entry) == 2:
            # Council assets: (folder_name, section_label)
            folder_name, section_label = section_entry
            appendix, facade = "", ""
        else:
            # Building: (folder_name, appendix_label, facade_label)
            folder_name, appendix, facade = section_entry
            section_label = facade

        section_folder = PHOTOS_DIR / folder_name
        if not section_folder.exists():
            print(f"  Skipping {section_label} - folder not found: {section_folder}")
            continue

        photos_in_section = sorted([
            p for p in section_folder.iterdir()
            if p.suffix.lower() in image_extensions
        ])

        if not photos_in_section:
            print(f"  Skipping {section_label} - no photos found")
            continue

        print(f"\n[{section_label}] - {len(photos_in_section)} photos")

        new_photos = [p for p in photos_in_section if p.name not in cached_files]
        already_cached = [p for p in photos_in_section if p.name in cached_files]

        if already_cached:
            print(f"  Using cached results for {len(already_cached)} photos")

        if new_photos:
            print(f"  Analyzing {len(new_photos)} new photos with Claude vision...")
            new_results = analyze_section(
                section_folder=section_folder,
                section_name=section_label,
                start_number=photo_number,
                report_type=REPORT_TYPE,
                appendix=appendix,
                facade=facade,
            )
            cached.extend(new_results)
            cached_files.update(r["filename"] for r in new_results)
            save_cache(cached)

        for photo_path in photos_in_section:
            match = next((p for p in cached if p["filename"] == photo_path.name), None)
            if match:
                entry = dict(match)
                entry["number"] = photo_number
                entry["section"] = section_label
                entry["appendix"] = appendix
                entry["facade"] = facade
                all_photos.append(entry)
                photo_number += 1

    return all_photos, photo_number


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("=" * 60)
    print(f"DILAPIDATION REPORT GENERATOR [{REPORT_TYPE.upper()}]")
    print("=" * 60)
    print(f"Project: {PROJECT['address']}")
    print(f"Client:  {PROJECT['client']}")
    print()

    cached = load_cache()

    # Select sections based on report type
    if REPORT_TYPE == "building":
        sections = config.BUILDING_SECTIONS
    else:
        sections = config.PHOTO_SECTIONS

    all_photos, _ = process_sections(sections, cached, photo_number=1)

    if not all_photos:
        print("\nNo photos found. Add photos to the correct folders and run again.")
        return

    print(f"\nTotal photos processed: {len(all_photos)}")

    # Generate site maps
    map_paths = {}
    if GOOGLE_MAPS_API_KEY and GOOGLE_MAPS_API_KEY != "your-google-maps-api-key-here":
        try:
            map_paths = generate_maps(PHOTOS_DIR, OUTPUT_DIR)
        except Exception as e:
            print(f"  Warning: Map generation failed: {e}")
            print("  Continuing without maps...")
    else:
        print("\nSkipping map generation (no Google Maps API key in config.py)")

    print("\nBuilding Word document...")

    ref_clean = PROJECT["ref"].replace("/", "-").replace("[", "").replace("]", "")
    output_filename = f"Dilapidation_Report_{ref_clean}.docx"
    output_path = OUTPUT_DIR / output_filename

    if REPORT_TYPE == "building":
        build_building_report(all_photos, str(output_path),
                              template_path=str(TEMPLATE_PATH), map_paths=map_paths)
    else:
        build_report(all_photos, str(output_path),
                     template_path=str(TEMPLATE_PATH), map_paths=map_paths)

    print("\nDone!")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
