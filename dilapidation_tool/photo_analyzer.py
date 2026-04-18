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
Rate pavement/kerb/footpath using this system (1-10 scale):

Rating 10 - Excellent: No distress, new construction
Rating 9  - Excellent: No distress, recent overlay, like new
Rating 8  - Very Good: No longitudinal cracks except paving joint reflection. Occasional transverse cracks widely spaced (>40'). All cracks sealed/tight (<1/4"). Little or no maintenance required.
Rating 7  - Good: Very slight/no raveling, minor traffic wear. Longitudinal cracks (open 1/4") from joints. Transverse cracks spaced >10' apart, slight raveling. No patching or few patches in excellent condition. Routine maintenance, cracksealing and minor patching.
Rating 6  - Good: Slight raveling (loss of fines) and traffic wear. Longitudinal cracks (1/4"-1/2"), some <10' apart. First sign of block cracking. Slight to moderate flushing/polishing. Occasional patching in good condition. Preservative treatments needed.
Rating 5  - Fair: Moderate to severe raveling (loss of fine and coarse aggregate). Longitudinal and transverse cracks (open 1/2"), slight raveling and secondary cracks. Longitudinal cracks near edge. Block cracking up to 50%. Extensive flushing/polishing. Some patching or edge wedging. Needs sealcoat or thin non-structural overlay.
Rating 4  - Fair: Severe surface raveling. Multiple longitudinal and transverse cracking with slight raveling. Longitudinal cracking in wheel path. Block cracking over 50%. Patching in fair condition. Slight rutting or distortions (1/2" deep or less). Needs structural overlay 2"+.
Rating 3  - Poor: Closely spaced longitudinal and transverse cracks with raveling and crack erosion. Severe block cracking. Some alligator cracking (<25%). Patches in fair to poor condition. Moderate rutting or distortion (1-2" deep). Occasional potholes. Needs patching and major overlay.
Rating 2  - Very Poor: Alligator cracking (>25%). Severe distortions (>2" deep). Extensive patching in poor condition. Potholes. Needs reconstruction with extensive base repair.
Rating 1  - Failed: Severe distress with extensive loss of surface integrity. Needs total reconstruction.
"""

COUNCIL_PROMPT = """You are a civil engineer inspecting council assets (roads, footpaths, kerbs, gutters) for a pre-construction dilapidation report in Australia.

Analyse this photo and write a single professional description sentence focusing ONLY on the council infrastructure visible.

IMPORTANT:
- IGNORE any vehicles, people, personal belongings, buildings or vegetation unless they are directly causing damage to the pavement (e.g. tree root heave)
- ONLY describe council assets: asphalt/concrete footpaths, road carriageways, kerb and gutter, utility pits, driveways, stormwater infrastructure
- Focus on visible distress: crack types (longitudinal, transverse, diagonal, block, alligator), crack width/spacing, ravelling, aggregate loss, surface wear, root heave, spalling, moss/algae growth, displacement, potholing, rutting, patching
- Keep the description to a MAXIMUM of 28 words (not counting the Rating label at the end)

Description format:
"[Surface type] [location/context] showing [defect description and observed features]. Rating [X] ([Condition])."

Example outputs:
"Asphalt footpath alongside brick building showing moderate surface cracking with open longitudinal and transverse cracks and surface ravelling. Rating 5 (Fair)."
"Concrete kerb and gutter at intersection showing longitudinal cracking along the kerb face with slight displacement. Rating 4 (Fair)."
"Asphalt road carriageway showing generally sound surface with minor transverse cracking and light surface ravelling consistent with normal ageing. Rating 7 (Good)."

Rating guide:
""" + COUNCIL_RATING_GUIDE + """

Respond with JSON only:
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
- Keep the description to a MAXIMUM of 28 words (not counting the Category label at the end)

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
                    appendix: str = "", facade: str = "",
                    photo_paths: list = None) -> list[dict]:
    """Analyze photos in parallel. Pass photo_paths to analyze a specific subset."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    if photo_paths is not None:
        photos = sorted(photo_paths)
    else:
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
