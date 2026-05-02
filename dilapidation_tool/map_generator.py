# map_generator.py - Auto-generates site locality and inspection zone maps from photo GPS data

import io
import math
import requests
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from config import PROJECT, GOOGLE_MAPS_API_KEY, REPORT_TYPE

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
    """Simple north arrow (used for council assets maps)."""
    draw.line([(x, y + size // 2), (x, y - size // 2)], fill="white", width=3)
    draw.polygon([
        (x, y - size // 2),
        (x - size // 6, y - size // 6),
        (x + size // 6, y - size // 6),
    ], fill="white")
    try:
        font = ImageFont.truetype("arial.ttf", size // 2)
    except Exception:
        font = ImageFont.load_default()
    draw.text((x - size // 6, y + size // 2 + 4), "N", fill="white", font=font)


def draw_north_arrow_compass(draw: ImageDraw, img: Image.Image, x: int, y: int, size: int = 55):
    """
    Compass-style north indicator: red north diamond, white south diamond, 'N' label.
    Matches the style shown in the building report template image.
    """
    half_w = size // 3
    north_tip = (x, y - int(size * 0.65))
    south_tip = (x, y + int(size * 0.35))
    left = (x - half_w, y)
    right = (x + half_w, y)
    centre = (x, y)

    # White circle background
    r = size // 2 + 8
    bg_overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg_overlay)
    bg_draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 220))
    merged = Image.alpha_composite(img.convert("RGBA"), bg_overlay)
    img.paste(merged.convert("RGB"))
    draw = ImageDraw.Draw(img)

    # Red north half
    draw.polygon([north_tip, right, centre, left], fill=(210, 30, 30), outline=(0, 0, 0), width=1)
    # White south half
    draw.polygon([centre, right, south_tip, left], fill=(255, 255, 255), outline=(0, 0, 0), width=1)

    # "N" label above north tip
    try:
        font = ImageFont.truetype("arialbd.ttf", size // 3)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", size // 3)
        except Exception:
            font = ImageFont.load_default()
    nw = size // 3
    draw.text((x - nw // 2, north_tip[1] - nw - 4), "N", fill=(0, 0, 0), font=font)

    return draw


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


def _offset_lat_lon(lat: float, lon: float, distance_m: float, bearing_deg: float) -> tuple[float, float]:
    """Offset a lat/lon by distance_m metres at bearing_deg degrees from north."""
    R = 6378137.0
    bearing_rad = math.radians(bearing_deg)
    new_lat = math.asin(
        math.sin(math.radians(lat)) * math.cos(distance_m / R)
        + math.cos(math.radians(lat)) * math.sin(distance_m / R) * math.cos(bearing_rad)
    )
    new_lon = math.radians(lon) + math.atan2(
        math.sin(bearing_rad) * math.sin(distance_m / R) * math.cos(math.radians(lat)),
        math.cos(distance_m / R) - math.sin(math.radians(lat)) * math.sin(new_lat),
    )
    return math.degrees(new_lat), math.degrees(new_lon)


def _calculate_street_bearing(coords: list[tuple[float, float]]) -> float:
    """
    Estimate the primary street bearing (degrees from north) from a list of GPS coords.
    Returns a value in [0, 180) — we don't distinguish direction, only orientation.
    """
    if len(coords) < 2:
        return 90.0  # default east-west

    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    lat_spread = max(lats) - min(lats)
    # Scale lon spread by cos(lat) so it's comparable in metres
    lon_spread = (max(lons) - min(lons)) * math.cos(math.radians(sum(lats) / len(lats)))

    if lon_spread >= lat_spread:
        return 90.0   # wider east-west → street runs E-W
    return 0.0        # taller north-south → street runs N-S


def _draw_dashed_line(draw: ImageDraw, start: tuple, end: tuple, fill, width: int = 2,
                      dash: int = 12, gap: int = 6):
    """Draw a dashed line between two pixel points."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return
    ux, uy = dx / length, dy / length
    pos = 0.0
    while pos < length:
        end_pos = min(pos + dash, length)
        draw.line(
            [(int(start[0] + ux * pos), int(start[1] + uy * pos)),
             (int(start[0] + ux * end_pos), int(start[1] + uy * end_pos))],
            fill=fill, width=width,
        )
        pos += dash + gap


def draw_property_overlay(draw: ImageDraw, img: Image.Image, centre_lat: float, centre_lon: float,
                          prop_lat: float, prop_lon: float, zoom: int,
                          colour_fill, colour_border, label: str, address: str):
    """Draw a semi-transparent property rectangle and label on the map."""
    mpp = metres_per_pixel(centre_lat, zoom)

    # Approximate property as a rectangle ~25m x 40m
    half_w = int(25 / mpp)
    half_h = int(20 / mpp)

    px, py = lat_lon_to_pixel(prop_lat, prop_lon, centre_lat, centre_lon, zoom, img.width, img.height)

    # Draw semi-transparent fill using a separate RGBA image
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.rectangle([px - half_w, py - half_h, px + half_w, py + half_h],
                      fill=colour_fill, outline=colour_border, width=3)
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))

    # Redraw border cleanly
    draw = ImageDraw.Draw(img)
    draw.rectangle([px - half_w, py - half_h, px + half_w, py + half_h],
                   outline=colour_border, width=3)

    # Label box
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    label_x = px - half_w + 5
    label_y = py - half_h + 5
    draw.rectangle([label_x - 2, label_y - 2, label_x + len(label) * 8 + 2, label_y + 18],
                   fill=(0, 0, 0, 180))
    draw.text((label_x, label_y), label, fill="white", font=font)

    # Address label below
    addr_y = py + half_h - 22
    draw.rectangle([px - half_w + 3, addr_y - 2, px + half_w - 3, addr_y + 18],
                   fill=(0, 0, 0, 160))
    draw.text((px - half_w + 5, addr_y), address, fill="white", font=font)

    return draw


# ─── CORRIDOR MAP ──────────────────────────────────────────────────────────────

def _generate_corridor_map(site_lat: float, site_lon: float,
                           coords: list[tuple[float, float]], output_dir: Path) -> str:
    """
    Generate a corridor map showing a 50m-each-direction inspection zone along the street.
    The corridor is a semi-transparent orange band centred on the site address.
    """
    zoom = 18
    img = fetch_satellite_image(site_lat, site_lon, zoom)

    street_bearing = _calculate_street_bearing(coords)
    perp_bearing = (street_bearing + 90) % 360
    half_width_m = 20   # metres each side of street centreline (covers road + footpaths)
    reach_m = 50        # metres each direction along the street

    # Four corners of the corridor polygon
    # (+along, +perp), (+along, -perp), (-along, -perp), (-along, +perp)
    corner_offsets = [
        (reach_m,  half_width_m),
        (reach_m,  -half_width_m),
        (-reach_m, -half_width_m),
        (-reach_m,  half_width_m),
    ]
    corners_px = []
    for along, perp in corner_offsets:
        lat1, lon1 = _offset_lat_lon(site_lat, site_lon, along, street_bearing)
        lat2, lon2 = _offset_lat_lon(lat1, lon1, perp, perp_bearing)
        corners_px.append(lat_lon_to_pixel(lat2, lon2, site_lat, site_lon, zoom, img.width, img.height))

    # Semi-transparent orange corridor fill
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.polygon(corners_px, fill=(255, 165, 0, 90))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Corridor outline
    for i in range(4):
        draw.line([corners_px[i], corners_px[(i + 1) % 4]], fill=(255, 165, 0), width=3)

    # Dashed centreline along the street
    end_a_px = lat_lon_to_pixel(
        *_offset_lat_lon(site_lat, site_lon, reach_m, street_bearing),
        site_lat, site_lon, zoom, img.width, img.height,
    )
    end_b_px = lat_lon_to_pixel(
        *_offset_lat_lon(site_lat, site_lon, -reach_m, street_bearing),
        site_lat, site_lon, zoom, img.width, img.height,
    )
    _draw_dashed_line(draw, end_b_px, end_a_px, fill=(255, 255, 255), width=2)

    # Site centre pin (red circle)
    sx, sy = lat_lon_to_pixel(site_lat, site_lon, site_lat, site_lon, zoom, img.width, img.height)
    draw.ellipse([sx - 10, sy - 10, sx + 10, sy + 10], fill="red", outline="white", width=3)

    try:
        font = ImageFont.truetype("arial.ttf", 16)
        font_sm = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font = ImageFont.load_default()
        font_sm = font

    # "50m" labels at each end of the corridor centreline
    for end_px, side_label in [(end_a_px, "50m"), (end_b_px, "50m")]:
        lx, ly = end_px[0] - 22, end_px[1] - 22
        draw.rectangle([lx - 3, ly - 3, lx + 50, ly + 22], fill=(0, 0, 0, 180))
        draw.text((lx, ly), f"← {side_label} →", fill="white", font=font_sm)

    # Dimension line showing full 100m span
    mid_top = ((corners_px[0][0] + corners_px[3][0]) // 2, min(corners_px[0][1], corners_px[3][1]) - 18)
    dim_lx = mid_top[0] - 50
    draw.rectangle([dim_lx - 4, mid_top[1] - 4, dim_lx + 100 + 4, mid_top[1] + 20], fill=(0, 0, 0, 180))
    draw.text((dim_lx, mid_top[1]), f"← 100m total corridor →", fill=(255, 165, 0), font=font_sm)

    draw_north_arrow(draw, img.width - 70, 80)
    draw_scale_bar(draw, img, site_lat, zoom)
    draw_title_box(draw, img,
                   "Figure 3 – 50m Inspection Corridor",
                   f"{PROJECT['address']} (Not to Scale)")

    path = str(output_dir / "figure3_corridor.png")
    img.save(path)
    return path


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

    # Geocode development address if provided
    dev_lat, dev_lon = None, None
    dev_address = PROJECT.get("development_address", "")
    if dev_address:
        try:
            print(f"  Geocoding development address: {dev_address}")
            dev_lat, dev_lon = geocode_address(dev_address)
        except Exception as e:
            print(f"  Warning: Could not geocode development address: {e}")

    # Step 4: Generate Figure 1 - Locality Plan (zoomed out)
    print("  Generating Figure 1 - Locality Plan...")
    fig1_path = _generate_locality_map(site_lat, site_lon, coords, output_dir)

    # Step 5: Generate Figure 2 - Property Site Map (zoomed in with overlays)
    print("  Generating Figure 2 - Property Site Map...")
    if REPORT_TYPE == "building":
        fig2_path = _generate_building_property_map(site_lat, site_lon, dev_lat, dev_lon, output_dir)
    else:
        fig2_path = _generate_property_map(site_lat, site_lon, dev_lat, dev_lon, output_dir)

    # Step 6: Generate Figure 3 - 50m Corridor Map
    print("  Generating Figure 3 - 50m Inspection Corridor Map...")
    fig3_path = _generate_corridor_map(site_lat, site_lon, coords, output_dir)

    print(f"  Maps saved to: {output_dir}")
    return {"figure1": fig1_path, "figure2": fig2_path, "figure3": fig3_path, "cover": cover_path}


def _draw_lot_rectangle(img: Image.Image, centre_lat: float, centre_lon: float,
                        prop_lat: float, prop_lon: float, zoom: int,
                        half_w_m: float, half_h_m: float,
                        fill_rgba: tuple, border_rgb: tuple,
                        label: str, address: str):
    """
    Draw a semi-transparent lot rectangle with white-background text labels
    matching the building report template style (label left, address right).
    Returns the updated draw handle.
    """
    mpp = metres_per_pixel(centre_lat, zoom)
    hw = int(half_w_m / mpp)
    hh = int(half_h_m / mpp)
    px, py = lat_lon_to_pixel(prop_lat, prop_lon, centre_lat, centre_lon, zoom, img.width, img.height)

    # Semi-transparent fill
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.rectangle([px - hw, py - hh, px + hw, py + hh], fill=fill_rgba)
    merged = Image.alpha_composite(img.convert("RGBA"), overlay)
    img.paste(merged.convert("RGB"))

    draw = ImageDraw.Draw(img)
    # Clean border
    draw.rectangle([px - hw, py - hh, px + hw, py + hh], outline=border_rgb, width=3)

    try:
        font = ImageFont.truetype("arial.ttf", 15)
    except Exception:
        font = ImageFont.load_default()

    pad = 6
    # Category label — white bg, left side of rectangle
    lw = int(len(label) * 8.5) + pad * 2
    lh = 22
    lx = px - hw + 6
    ly = py - hh // 2 - lh // 2
    draw.rectangle([lx - pad, ly - pad // 2, lx + lw, ly + lh], fill=(255, 255, 255, 230))
    draw.text((lx, ly), label, fill=(0, 0, 0), font=font)

    # Address label — white bg, right side of rectangle
    aw = int(len(address) * 8.5) + pad * 2
    ax = px + hw - aw - 6
    ay = py - hh // 2 - lh // 2
    draw.rectangle([ax - pad, ay - pad // 2, ax + aw, ay + lh], fill=(255, 255, 255, 230))
    draw.text((ax, ay), address, fill=(0, 0, 0), font=font)

    return draw


def _generate_building_property_map(site_lat, site_lon, dev_lat, dev_lon, output_dir):
    """
    Building-report property map: close satellite view, compass north arrow,
    labelled lot rectangles, no title box — matching the template image style.
    """
    zoom = 19
    img = fetch_satellite_image(site_lat, site_lon, zoom)

    # Subject property — grey overlay
    _draw_lot_rectangle(
        img, site_lat, site_lon, site_lat, site_lon, zoom,
        half_w_m=15, half_h_m=22,
        fill_rgba=(180, 180, 180, 110),
        border_rgb=(100, 100, 100),
        label="Subject to Dilapidation",
        address=PROJECT["address"].split(",")[0],
    )

    # Development property — green overlay
    if dev_lat and dev_lon:
        _draw_lot_rectangle(
            img, site_lat, site_lon, dev_lat, dev_lon, zoom,
            half_w_m=15, half_h_m=22,
            fill_rgba=(0, 180, 0, 110),
            border_rgb=(0, 150, 0),
            label="Proposed development",
            address=PROJECT.get("development_address", "").split(",")[0],
        )

    draw = ImageDraw.Draw(img)
    # Compass north arrow — bottom right
    draw_north_arrow_compass(draw, img, img.width - 80, img.height - 90)

    path = str(output_dir / "figure2_building_property.png")
    img.save(path)
    return path


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


def _generate_property_map(site_lat, site_lon, dev_lat, dev_lon, output_dir):
    """Generate a zoomed-in satellite map showing both properties with coloured overlays."""
    zoom = 19
    img = fetch_satellite_image(site_lat, site_lon, zoom)
    draw = ImageDraw.Draw(img)

    # Draw subject property - grey overlay
    draw = draw_property_overlay(
        draw, img, site_lat, site_lon,
        site_lat, site_lon, zoom,
        colour_fill=(180, 180, 180, 100),
        colour_border=(200, 200, 200),
        label="Subject to Dilapidation",
        address=PROJECT["address"],
    )

    # Draw development property - green overlay
    if dev_lat and dev_lon:
        draw = draw_property_overlay(
            draw, img, site_lat, site_lon,
            dev_lat, dev_lon, zoom,
            colour_fill=(0, 180, 0, 100),
            colour_border=(0, 200, 0),
            label="Proposed Development",
            address=PROJECT.get("development_address", ""),
        )

    draw_north_arrow(draw, img.width - 70, 80)
    draw_scale_bar(draw, img, site_lat, zoom)
    draw_title_box(draw, img,
                   "Figure 2 – Site Property Map",
                   "Subject to Dilapidation & Proposed Development (Not to Scale)")

    path = str(output_dir / "figure2_property_map.png")
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
                   "Figure 3 – Inspection Zone",
                   f"Zone of Influence – {PROJECT['address']} (Not to Scale)")

    path = str(output_dir / "figure3_inspection_zone.png")
    img.save(path)
    return path
