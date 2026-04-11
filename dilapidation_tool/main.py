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
