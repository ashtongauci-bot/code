# map_generator.py - Auto-generates site locality and inspection zone maps from photo GPS data

import io
import math
import requests
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from config import PROJECT, GOOGLE_MAPS_API_KEY

# Map output size
MAP_WIDTH = 1200
MAP_HEIGHT = 900


# ─── GPS EXTRACTION ────────────────────────────────────────────────────────────

def get_exif_gps(image_path: Path) -> tuple[float, float] | None:
    """Extract (lat, lon) from a photo's EXIF data. Returns None if not found."""
    try:
        from PIL.ExifTags import TAGS, GPSTAGS
        img = Image.open(image_path)
        exif_data = img._getexif()
        if not exif_data:
            return None

        gps_info = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo":
                for gps_tag_id, gps_value in value.items():
                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps_info[gps_tag] = gps_value

        if not gps_info:
            return None

        def dms_to_decimal(dms, ref):
            degrees = float(dms[0])
            minutes = float(dms[1])
            seconds = float(dms[2])
            decimal = degrees + minutes / 60 + seconds / 3600
            if ref in ("S", "W"):
                decimal = -decimal
            return decimal

        lat = dms_to_decimal(gps_info["GPSLatitude"], gps_info["GPSLatitudeRef"])
        lon = dms_to_decimal(gps_info["GPSLongitude"], gps_info["GPSLongitudeRef"])
        return lat, lon

    except Exception:
        return None


def extract_all_gps(photos_dir: Path) -> list[tuple[float, float]]:
    """Extract GPS coords from all photos across all section folders."""
    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    coords = []

    for photo_path in photos_dir.rglob("*"):
        if photo_path.suffix.lower() in image_extensions:
            coord = get_exif_gps(photo_path)
            if coord:
                coords.append(coord)

    print(f"  Found GPS data in {len(coords)} photos")
    return coords


# ─── GEOCODING ─────────────────────────────────────────────────────────────────

def geocode_address(address: str) -> tuple[float, float]:
    """Convert address to (lat, lon) using Google Geocoding API."""
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": GOOGLE_MAPS_API_KEY}
    response = requests.get(url, params=params)
    data = response.json()

    if data["status"] != "OK":
        raise ValueError(f"Geocoding failed for '{address}': {data['status']}")

    location = data["results"][0]["geometry"]["location"]
    return location["lat"], location["lng"]


# ─── GOOGLE MAPS STATIC IMAGE ──────────────────────────────────────────────────

def fetch_satellite_image(centre_lat: float, centre_lon: float, zoom: int) -> Image.Image:
    """Fetch a satellite image from Google Maps Static API."""
    url = "https://maps.googleapis.com/maps/api/staticmap"
    params = {
        "center": f"{centre_lat},{centre_lon}",
        "zoom": zoom,
        "size": f"{MAP_WIDTH}x{MAP_HEIGHT}",
        "maptype": "satellite",
        "key": GOOGLE_MAPS_API_KEY,
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        raise ValueError(f"Map fetch failed: {response.status_code}")
    return Image.open(io.BytesIO(response.content)).convert("RGB")


# ─── MAP MATH ──────────────────────────────────────────────────────────────────

def lat_lon_to_pixel(lat, lon, centre_lat, centre_lon, zoom, img_width, img_height):
    """Convert a lat/lon to pixel coordinates on the static map image."""
    def lat_to_mercator_y(lat_deg):
        lat_rad = math.radians(lat_deg)
        return math.log(math.tan(math.pi / 4 + lat_rad / 2))

    scale = (256 * (2 ** zoom)) / (2 * math.pi)

    cx = (centre_lon + 180) / 360 * 256 * (2 ** zoom)
    cy = (math.pi - lat_to_mercator_y(centre_lat)) * scale

    px = (lon + 180) / 360 * 256 * (2 ** zoom)
    py = (math.pi - lat_to_mercator_y(lat)) * scale

    x = img_width / 2 + (px - cx)
    y = img_height / 2 + (py - cy)
    return int(x), int(y)


def metres_per_pixel(lat: float, zoom: int) -> float:
    """Calculate metres per pixel at a given latitude and zoom level."""
    return 156543.03392 * math.cos(math.radians(lat)) / (2 ** zoom)


# ─── DRAWING HELPERS ───────────────────────────────────────────────────────────

def draw_north_arrow(draw: ImageDraw, x: int, y: int, size: int = 50):
    """Draw a north arrow at (x, y)."""
    # Arrow shaft
    draw.line([(x, y + size // 2), (x, y - size // 2)], fill="white", width=3)
    # Arrowhead
    draw.polygon([
        (x, y - size // 2),
        (x - size // 6, y - size // 6),
        (x + size // 6, y - size // 6),
    ], fill="white")
    # "N" label
    try:
        font = ImageFont.truetype("arial.ttf", size // 2)
    except Exception:
        font = ImageFont.load_default()
    draw.text((x - size // 6, y + size // 2 + 4), "N", fill="white", font=font)


def draw_scale_bar(draw: ImageDraw, img: Image.Image, lat: float, zoom: int):
    """Draw a scale bar in the bottom-left corner."""
    mpp = metres_per_pixel(lat, zoom)
    bar_metres = 50 if zoom >= 18 else 100 if zoom >= 16 else 200 if zoom >= 14 else 500
    bar_pixels = int(bar_metres / mpp)

    x1 = 60
    x2 = x1 + bar_pixels
    y = img.height - 50

    draw.rectangle([x1, y - 6, x2, y + 6], fill="white")
    draw.rectangle([x1, y - 6, x1 + bar_pixels // 2, y + 6], fill="black")

    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()

    draw.text((x1, y + 10), "0", fill="white", font=font)
    draw.text((x2 - 10, y + 10), f"{bar_metres}m", fill="white", font=font)


def draw_boundary(draw: ImageDraw, points: list[tuple[int, int]], colour=(255, 0, 0), width=3):
    """Draw a convex hull boundary around a set of pixel points."""
    if len(points) < 3:
        return
    hull = convex_hull(points)
    for i in range(len(hull)):
        draw.line([hull[i], hull[(i + 1) % len(hull)]], fill=colour, width=width)


def convex_hull(points):
    """Simple convex hull (gift wrapping algorithm)."""
    points = list(set(points))
    if len(points) < 3:
        return points

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    points.sort()
    lower = []
    for p in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def draw_title_box(draw: ImageDraw, img: Image.Image, title: str, subtitle: str):
    """Draw a title box in the top-left corner."""
    try:
        font_title = ImageFont.truetype("arial.ttf", 20)
        font_sub = ImageFont.truetype("arial.ttf", 15)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = font_title

    padding = 10
    draw.rectangle([10, 10, 500, 70], fill=(0, 0, 0, 180))
    draw.text((10 + padding, 10 + padding), title, fill="white", font=font_title)
    draw.text((10 + padding, 40 + padding), subtitle, fill="white", font=font_sub)


# ─── STREET VIEW COVER PHOTO ───────────────────────────────────────────────────

def fetch_street_view(address: str, output_dir: Path) -> str | None:
    """
    Fetch a Google Street View image of the site address for use as cover photo.
    Returns path to saved image, or None if unavailable.
    """
    cover_path = str(output_dir / "cover_street_view.jpg")

    # First check if Street View is available at this location
    meta_url = "https://maps.googleapis.com/maps/api/streetview/metadata"
    meta_params = {"location": address, "key": GOOGLE_MAPS_API_KEY}
    meta_response = requests.get(meta_url, params=meta_params)
    meta = meta_response.json()

    if meta.get("status") != "OK":
        print(f"  Street View not available for this address (status: {meta.get('status')})")
        return None

    # Fetch the Street View image
    url = "https://maps.googleapis.com/maps/api/streetview"
    params = {
        "size": "1280x720",
        "location": address,
        "fov": 90,
        "pitch": 5,
        "key": GOOGLE_MAPS_API_KEY,
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"  Street View fetch failed: {response.status_code}")
        return None

    with open(cover_path, "wb") as f:
        f.write(response.content)

    print(f"  Street View cover photo saved: {cover_path}")
    return cover_path


# ─── MAIN MAP GENERATION ───────────────────────────────────────────────────────

def generate_maps(photos_dir: Path, output_dir: Path) -> dict[str, str]:
    """
    Generate Figure 1 (locality) and Figure 2 (inspection zone) maps.
    Returns dict with paths to the saved images.
    """
    output_dir.mkdir(exist_ok=True)
    print("\nGenerating site maps...")

    # Step 1: Geocode the site address
    print(f"  Geocoding: {PROJECT['address']}")
    site_lat, site_lon = geocode_address(PROJECT["address"])
    print(f"  Site coordinates: {site_lat:.6f}, {site_lon:.6f}")

    # Step 2: Extract GPS from photos
    print("  Extracting GPS from photos...")
    coords = extract_all_gps(photos_dir)

    # Fall back to site coords if no GPS in photos
    if not coords:
        print("  No GPS data found in photos - using site address only")
        coords = [(site_lat, site_lon)]

    # Step 3: Fetch Street View cover photo
    print("  Fetching Street View cover photo...")
    cover_path = fetch_street_view(PROJECT["address"], output_dir)

    # Step 4: Generate Figure 1 - Locality Plan (zoomed out)
    print("  Generating Figure 1 - Locality Plan...")
    fig1_path = _generate_locality_map(site_lat, site_lon, coords, output_dir)

    # Step 5: Generate Figure 2 - Inspection Zone (zoomed in)
    print("  Generating Figure 2 - Inspection Zone Map...")
    fig2_path = _generate_inspection_map(site_lat, site_lon, coords, output_dir)

    print(f"  Maps saved to: {output_dir}")
    return {"figure1": fig1_path, "figure2": fig2_path, "cover": cover_path}


def _generate_locality_map(site_lat, site_lon, coords, output_dir):
    zoom = 15
    img = fetch_satellite_image(site_lat, site_lon, zoom)
    draw = ImageDraw.Draw(img)

    # Mark the site with a red dot
    sx, sy = lat_lon_to_pixel(site_lat, site_lon, site_lat, site_lon, zoom, img.width, img.height)
    draw.ellipse([sx - 10, sy - 10, sx + 10, sy + 10], fill="red", outline="white", width=2)

    # Draw inspection boundary from GPS points
    if len(coords) >= 3:
        pixels = [
            lat_lon_to_pixel(lat, lon, site_lat, site_lon, zoom, img.width, img.height)
            for lat, lon in coords
        ]
        draw_boundary(draw, pixels, colour=(255, 0, 0), width=3)

    draw_north_arrow(draw, img.width - 70, 80)
    draw_scale_bar(draw, img, site_lat, zoom)
    draw_title_box(draw, img,
                   f"Figure 1 – Site Locality Plan",
                   f"{PROJECT['address']} (Not to Scale)")

    path = str(output_dir / "figure1_locality.png")
    img.save(path)
    return path


def _generate_inspection_map(site_lat, site_lon, coords, output_dir):
    zoom = 18
    img = fetch_satellite_image(site_lat, site_lon, zoom)
    draw = ImageDraw.Draw(img)

    # Plot all photo GPS points as small dots
    pixels = []
    for lat, lon in coords:
        px, py = lat_lon_to_pixel(lat, lon, site_lat, site_lon, zoom, img.width, img.height)
        draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill="yellow", outline="white", width=1)
        pixels.append((px, py))

    # Draw boundary around all photo locations
    if len(pixels) >= 3:
        draw_boundary(draw, pixels, colour=(255, 0, 0), width=3)

    # Mark site centre
    sx, sy = lat_lon_to_pixel(site_lat, site_lon, site_lat, site_lon, zoom, img.width, img.height)
    draw.ellipse([sx - 8, sy - 8, sx + 8, sy + 8], fill="red", outline="white", width=2)

    draw_north_arrow(draw, img.width - 70, 80)
    draw_scale_bar(draw, img, site_lat, zoom)
    draw_title_box(draw, img,
                   "Figure 2 – Inspection Zone",
                   f"Zone of Influence – {PROJECT['address']} (Not to Scale)")

    path = str(output_dir / "figure2_inspection_zone.png")
    img.save(path)
    return path
