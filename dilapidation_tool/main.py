# main.py - Run this to generate your dilapidation report

import json
from pathlib import Path
from config import PROJECT, PHOTO_SECTIONS
from photo_analyzer import analyze_section
from report_builder import build_report

PHOTOS_DIR = Path(__file__).parent / "photos"
OUTPUT_DIR = Path(__file__).parent / "output"
CACHE_FILE = Path(__file__).parent / "output" / "photo_cache.json"


def load_cache() -> list[dict]:
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return json.load(f)
    return []


def save_cache(photos: list[dict]):
    with open(CACHE_FILE, "w") as f:
        json.dump(photos, f, indent=2)


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("=" * 60)
    print("DILAPIDATION REPORT GENERATOR")
    print("=" * 60)
    print(f"Project: {PROJECT['address']}")
    print(f"Client:  {PROJECT['client']}")
    print()

    # Check if we have cached results (avoids re-analyzing photos)
    cached = load_cache()
    cached_files = {p["filename"] for p in cached}

    all_photos = []
    photo_number = 1

    for folder_name, section_label in PHOTO_SECTIONS:
        section_folder = PHOTOS_DIR / folder_name
        if not section_folder.exists():
            print(f"  Skipping {section_label} - folder not found: {section_folder}")
            continue

        image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
        photos_in_section = sorted([
            p for p in section_folder.iterdir()
            if p.suffix.lower() in image_extensions
        ])

        if not photos_in_section:
            print(f"  Skipping {section_label} - no photos found")
            continue

        print(f"\n[{section_label}] - {len(photos_in_section)} photos")

        # Separate cached vs new photos
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
            )
            # Update cache
            cached.extend(new_results)
            save_cache(cached)

        # Rebuild section in order with correct numbering
        for photo_path in photos_in_section:
            match = next((p for p in cached if p["filename"] == photo_path.name), None)
            if match:
                entry = dict(match)
                entry["number"] = photo_number
                entry["section"] = section_label
                all_photos.append(entry)
                photo_number += 1

    if not all_photos:
        print("\nNo photos found. Add photos to the folders under /photos/ and run again.")
        print("Expected folders:")
        for folder_name, label in PHOTO_SECTIONS:
            print(f"  photos/{folder_name}/   ({label})")
        return

    print(f"\nTotal photos processed: {len(all_photos)}")
    print("\nBuilding Word document...")

    ref_clean = PROJECT["ref"].replace("/", "-").replace("[", "").replace("]", "")
    output_filename = f"Dilapidation_Report_{ref_clean}.docx"
    output_path = OUTPUT_DIR / output_filename

    build_report(all_photos, str(output_path))

    print("\nDone!")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
