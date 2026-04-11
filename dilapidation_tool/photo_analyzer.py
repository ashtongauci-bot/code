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
Use AS2870-2011 Table C1 damage categories for walls:

Cat 0 (Negligible): Hairline cracks <0.1mm, no action required
Cat 1 (Very Slight): Fine cracks <1mm, do not need repair
Cat 2 (Slight): Cracks noticeable but easily filled <5mm, doors/windows may stick slightly
Cat 3 (Moderate): Cracks 5-15mm (or multiple cracks 3mm+), doors/windows stick, some wall sections may need replacing
Cat 4 (Severe): Cracks 15-25mm, extensive repair needed, walls lean or bulge, doors/windows distorted
"""

BUILDING_PROMPT = """You are a structural engineer inspecting a residential or commercial building for a pre-construction dilapidation report in Australia.

Analyse this photo and write a single professional description sentence focusing ONLY on the building fabric and structure.

IMPORTANT:
- IGNORE any personal belongings, furniture, shoes, clothing, vehicles, plants or people in the photo
- ONLY describe the building elements: walls, floors, ceilings, windows, doors, roof, gutters, downpipes, paving, steps, balustrades, retaining walls, rendered surfaces, brickwork, timber framing, etc.
- If no building defects are visible, describe the element and its condition as good/sound
- Describe what you see: crack type (hairline, diagonal, horizontal, vertical), crack width if estimable, spalling, render loss, water staining, efflorescence, rust staining, rot, settlement, displacement, paint peeling

Description format:
"[Element type] to [location] showing [defect description and observed features]. Cat [X] ([Label])."

Example outputs:
"Brick wall to east facade showing diagonal cracking approximately 2mm wide at window corner, consistent with minor differential settlement. Cat 2 (Slight)."
"Rendered external wall to north facade in good condition with no visible cracking or defects noted. Cat 0 (Negligible)."
"Internal plasterboard wall to ground floor hallway showing hairline cracking at ceiling junction. Cat 1 (Very Slight)."

Category guide:
""" + BUILDING_CATEGORY_GUIDE + """

Respond with JSON only:
{
  "description": "Brick wall to east facade showing...",
  "rating": 2,
  "condition": "Slight",
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
