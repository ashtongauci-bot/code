# photo_analyzer.py - Uses Claude vision to describe photos and assign ratings

import anthropic
import base64
import io
import json
from pathlib import Path
from PIL import Image
from config import ANTHROPIC_API_KEY, PHOTO_WORKERS

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ─── COUNCIL ASSETS PROMPT ─────────────────────────────────────

COUNCIL_RATING_GUIDE = """
Rate the pavement/kerb/footpath on a scale of 1-7:
1 - Extremely Poor: Structural failure, unsafe
2 - Very Poor: Severe deterioration, large sections missing or displaced
3 - Poor: Significant cracking, ravelling, aggregate loss, root heave
4 - Fair (lower): Moderate cracking, longitudinal/transverse cracks, some ravelling
5 - Fair (upper): Minor cracking, light ravelling, surface wear consistent with age
6 - Good: Minor surface wear only, very limited distress
7 - Good (excellent): No visible defects, new or near-new condition
"""

COUNCIL_PROMPT = """You are inspecting council assets (roads, footpaths, kerbs, gutters) for a pre-construction dilapidation report in Australia.

Analyse this photo and write a single description sentence in this exact style:
"[Surface type] [location/context] showing [defect description and observed features]. Rating [X] ([Condition])."

Rules:
- Surface types: Asphalt footpath, Concrete footpath, Asphalt road carriageway, Concrete kerb, Concrete kerb/gutter, etc.
- Describe what you actually see: cracking types (longitudinal, transverse, diagonal), ravelling, aggregate loss, surface wear, root heave, spalling, moss/algae growth, utility pits, displacement
- Condition label: use "Good" for ratings 6-7, "Fair" for ratings 4-5, "Poor" for ratings 1-3
- Keep it factual and professional (engineering report style)
- One sentence only, ending with the rating

Rating guide:
""" + COUNCIL_RATING_GUIDE + """

Respond with JSON only, in this format:
{
  "description": "Asphalt footpath alongside brick wall showing...",
  "rating": 5,
  "condition": "Fair",
  "category": ""
}"""

# ─── BUILDING PROMPT ───────────────────────────────────────────

BUILDING_CATEGORY_GUIDE = """
Assign a category based on AS2870 crack classification:
Cat 1 (Negligible): Hairline cracks, no structural concern
Cat 2 (Slight): Fine cracks, minor cosmetic damage
Cat 3 (Moderate): Cracks requiring repair, some structural concern
Cat 4 (Severe): Significant cracking, structural damage likely
Cat 5 (Very Severe): Major structural failure, urgent action required
"""

BUILDING_PROMPT = """You are inspecting a residential or commercial building for a pre-construction dilapidation report in Australia.

Analyse this photo and write a single description sentence in this exact style:
"[Element type] [location/context] showing [defect description and observed features]. [Condition]."

Rules:
- Element types: External brick wall, Rendered facade, Concrete driveway, Timber floor, Internal wall, Ceiling, Window frame, Door frame, Roof tile, Gutter, Downpipe, Paving, Retaining wall, Garden bed, etc.
- Describe what you actually see: cracking (hairline, diagonal, horizontal, vertical), spalling, render loss, water staining, efflorescence, rust staining, rot, settlement, displacement, paint peeling
- Keep it factual and professional (engineering report style)
- One sentence only

Category guide:
""" + BUILDING_CATEGORY_GUIDE + """

Respond with JSON only, in this format:
{
  "description": "External brick wall to east facade showing diagonal cracking...",
  "rating": 3,
  "condition": "Fair",
  "category": "Cat 2 (Slight)"
}"""


def encode_image(image_path: Path) -> tuple[str, str]:
    media_type = "image/jpeg"
    max_bytes = 4 * 1024 * 1024  # 4MB to stay safely under the 5MB limit

    with Image.open(image_path) as img:
        # Convert to RGB (handles PNGs with transparency etc.)
        img = img.convert("RGB")

        # Resize if image is very large (max 2000px on longest side)
        max_dim = 2000
        if max(img.width, img.height) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        # Compress until under size limit
        quality = 85
        while quality >= 40:
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=quality)
            if buffer.tell() <= max_bytes:
                break
            quality -= 10

        buffer.seek(0)
        data = base64.standard_b64encode(buffer.read()).decode("utf-8")

    return data, media_type


def analyze_photo(image_path: Path, report_type: str = "council_assets") -> dict:
    """Send a photo to Claude and get a description + rating back."""
    image_data, media_type = encode_image(image_path)
    prompt = BUILDING_PROMPT if report_type == "building" else COUNCIL_PROMPT

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    result = json.loads(raw.strip())
    return result


def analyze_section(section_folder: Path, section_name: str, start_number: int = 1,
                    max_workers: int = PHOTO_WORKERS, report_type: str = "council_assets",
                    appendix: str = "", facade: str = "") -> list[dict]:
    """Analyze all photos in a section folder in parallel and return list of photo records."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    photos = sorted([p for p in section_folder.iterdir() if p.suffix.lower() in image_extensions])

    def process(args):
        i, photo_path = args
        try:
            analysis = analyze_photo(photo_path, report_type=report_type)
            label = analysis.get("category") or f"Rating {analysis['rating']} ({analysis['condition']})"
            print(f"  ✓ Photo {i}: {photo_path.name} -> {label}")
            return {
                "number": i,
                "path": str(photo_path),
                "filename": photo_path.name,
                "section": section_name,
                "appendix": appendix,
                "facade": facade,
                "description": analysis["description"],
                "rating": analysis["rating"],
                "condition": analysis["condition"],
                "category": analysis.get("category", ""),
            }
        except Exception as e:
            print(f"  ✗ Photo {i}: {photo_path.name} -> ERROR: {e}")
            return {
                "number": i,
                "path": str(photo_path),
                "filename": photo_path.name,
                "section": section_name,
                "description": f"[Could not analyze photo: {photo_path.name}]",
                "rating": 0,
                "condition": "Unknown",
            }

    indexed = list(enumerate(photos, start=start_number))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process, item): item for item in indexed}
        raw_results = [f.result() for f in as_completed(futures)]

    # Sort back into original order
    raw_results.sort(key=lambda x: x["number"])
    return raw_results
