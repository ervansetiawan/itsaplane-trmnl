"""Random-location 1-bit pixel art map generator for TRMNL."""

import base64
import io
import math
import random

import requests
from PIL import Image

LOCATIONS = [
    ("Tokyo, Japan", 35.6762, 139.6503, 12),
    ("Venice, Italy", 45.4408, 12.3155, 13),
    ("Manhattan, New York", 40.7831, -73.9712, 12),
    ("Reykjavik, Iceland", 64.1466, -21.9426, 12),
    ("Cape Town, South Africa", -33.9249, 18.4241, 12),
    ("Rio de Janeiro, Brazil", -22.9068, -43.1729, 12),
    ("Santorini, Greece", 36.3932, 25.4615, 12),
    ("San Francisco, USA", 37.7749, -122.4194, 12),
    ("Paris, France", 48.8566, 2.3522, 12),
    ("Sydney, Australia", -33.8688, 151.2093, 12),
    ("Cairo, Egypt", 30.0444, 31.2357, 12),
    ("Istanbul, Turkey", 41.0082, 28.9784, 12),
    ("Amsterdam, Netherlands", 52.3676, 4.9041, 13),
    ("Hong Kong", 22.3193, 114.1694, 12),
    ("Tromsø, Norway", 69.6492, 18.9553, 12),
    ("Marrakesh, Morocco", 31.6295, -7.9811, 12),
    ("Bora Bora, French Polynesia", -16.5004, -151.7415, 12),
    ("Kathmandu, Nepal", 27.7172, 85.3240, 12),
    ("Stockholm, Sweden", 59.3293, 18.0686, 12),
    ("Havana, Cuba", 23.1136, -82.3666, 12),
    ("Singapore", 1.3521, 103.8198, 12),
    ("Lisbon, Portugal", 38.7223, -9.1393, 12),
    ("Kyoto, Japan", 35.0116, 135.7681, 12),
    ("Buenos Aires, Argentina", -34.6037, -58.3816, 12),
]


def _deg2num(lat_deg: float, lon_deg: float, zoom: int) -> tuple[int, int]:
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


def generate_pixel_map() -> dict:
    name, lat, lon, zoom = random.choice(LOCATIONS)
    # Slight random offset so every load frames a fresh slice
    lat += random.uniform(-0.02, 0.02)
    lon += random.uniform(-0.02, 0.02)

    x, y = _deg2num(lat, lon, zoom)
    tile_url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"

    resp = requests.get(
        tile_url,
        headers={"User-Agent": "itsaplane-trmnl/1.0 (https://github.com/ervansetiawan/itsaplane-trmnl)"},
        timeout=10,
    )
    resp.raise_for_status()

    img = Image.open(io.BytesIO(resp.content)).convert("L")
    # Downsample to chunky pixel-art grid, dither to 1-bit, then scale up crisp
    pixel_w, pixel_h = 96, 54
    small = img.resize((pixel_w, pixel_h), Image.Resampling.BILINEAR)
    dithered = small.convert("1")
    crisp = dithered.resize((768, 432), Image.Resampling.NEAREST)

    buf = io.BytesIO()
    crisp.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    return {
        "name": name,
        "coords": f"{lat:.3f}, {lon:.3f}",
        "zoom": zoom,
        "image_url": f"data:image/png;base64,{b64}",
    }
