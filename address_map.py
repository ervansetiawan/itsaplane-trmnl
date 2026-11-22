"""
Street-level landmark map renderer for TRMNL ePaper.

Builds a crisp 4-shade map (streets, parks, buildings, water/coastline,
and a highlighted target pin) from OpenStreetMap (Overpass API) + ESRI World Topo.
"""

import base64
import io
import json
import math
import os

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "addresses")
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
WATER_TILE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
)
EARTH_R = 6378137.0

BLACK, DARK, LIGHT, WHITE = 0, 85, 170, 255

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "daily-famous-address-trmnl/1.0"})


def to_merc(lat, lon):
    """Projects lat/lon to Web Mercator meters."""
    x = math.radians(lon) * EARTH_R
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * EARTH_R
    return x, y


def merc_to_global_px(x, y, zoom):
    """Converts Web Mercator meters to global tile-pixel coordinates at zoom."""
    world = 256 * (2 ** zoom)
    gx = (x + math.pi * EARTH_R) / (2 * math.pi * EARTH_R) * world
    gy = (math.pi * EARTH_R - y) / (2 * math.pi * EARTH_R) * world
    return gx, gy


def _cache_path(slug, suffix):
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{slug}{suffix}")


def is_cached(slug):
    """Returns True if both OSM features and water mask are cached for this address."""
    return os.path.exists(_cache_path(slug, ".json")) and os.path.exists(
        _cache_path(slug, "_water.png")
    )


def fetch_address_features(slug, lat, lon, radius_m=420):
    """Fetches streets, buildings, and parks around an address from Overpass (cached)."""
    path = _cache_path(slug, ".json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    query = (
        "[out:json][timeout:60];("
        f'way["highway"](around:{radius_m},{lat},{lon});'
        f'way["building"](around:{radius_m},{lat},{lon});'
        f'way["leisure"~"^(park|garden)$"](around:{radius_m},{lat},{lon});'
        ");out geom;"
    )
    last_exc = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            resp = _SESSION.post(endpoint, data={"data": query}, timeout=90)
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            break
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
    else:
        raise RuntimeError(f"Overpass failed for {slug}: {last_exc}")

    features = []
    for el in elements:
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        tags = el.get("tags", {})
        coords = [[round(p["lat"], 6), round(p["lon"], 6)] for p in geom]
        if "building" in tags:
            ftype = "building"
        elif "leisure" in tags:
            ftype = "park"
        else:
            ftype = "road"
        features.append(
            {
                "type": ftype,
                "highway": tags.get("highway", ""),
                "closed": coords[0] == coords[-1],
                "coords": coords,
            }
        )

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(features, fh)
    return features


def compute_bbox(center_lat, center_lon, span_m=520, aspect=4 / 3):
    """Computes a Web Mercator bbox centered on (center_lat, center_lon)."""
    cx, cy = to_merc(center_lat, center_lon)
    scale = 1 / math.cos(math.radians(center_lat))
    w = span_m * scale
    h = w / aspect
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def fetch_water_mask(slug, bbox, width, height):
    """Builds a boolean water mask image (255 = water) from ESRI World Topo."""
    path = _cache_path(slug, "_water.png")
    if os.path.exists(path):
        mask = Image.open(path).convert("L")
        if mask.size == (width, height):
            return mask

    minx, miny, maxx, maxy = bbox
    zoom = 16
    gx0, gy0 = merc_to_global_px(minx, maxy, zoom)
    gx1, gy1 = merc_to_global_px(maxx, miny, zoom)
    tx0, ty0 = int(gx0 // 256), int(gy0 // 256)
    tx1, ty1 = int(gx1 // 256), int(gy1 // 256)

    mosaic = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256), (255, 255, 255))
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            try:
                resp = _SESSION.get(WATER_TILE_URL.format(z=zoom, x=tx, y=ty), timeout=10)
                resp.raise_for_status()
                tile = Image.open(io.BytesIO(resp.content)).convert("RGB")
                mosaic.paste(tile, ((tx - tx0) * 256, (ty - ty0) * 256))
            except (requests.RequestException, OSError):
                continue

    crop = mosaic.crop(
        (int(gx0 - tx0 * 256), int(gy0 - ty0 * 256), int(gx1 - tx0 * 256), int(gy1 - ty0 * 256))
    )
    px = crop.load()
    w0, h0 = crop.size
    mask = Image.new("L", (w0, h0), 0)
    mp = mask.load()
    for y in range(h0):
        for x in range(w0):
            rr, gg, bb = px[x, y]
            if bb >= 240 and (bb - rr) >= 30 and gg >= 220:
                mp[x, y] = 255

    mask = mask.filter(ImageFilter.MedianFilter(size=5))
    mask = mask.resize((width, height), Image.Resampling.BILINEAR).point(
        lambda v: 255 if v >= 128 else 0
    )
    mask.save(path)
    return mask


def _hatch_water(img, mask):
    """Fills water areas with diagonal hatch lines and outlines coastlines."""
    w, h = img.size
    ip = img.load()
    mp = mask.load()
    for y in range(h):
        for x in range(w):
            if mp[x, y]:
                ip[x, y] = DARK if (x + y) % 4 == 0 else WHITE

    edges = mask.filter(ImageFilter.FIND_EDGES)
    ep = edges.load()
    for y in range(h):
        for x in range(w):
            if ep[x, y] and mp[x, y]:
                ip[x, y] = BLACK


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _road_width(highway):
    if highway in ("motorway", "trunk", "primary"):
        return 5
    if highway in ("secondary", "tertiary"):
        return 4
    if highway in ("residential", "unclassified", "pedestrian", "living_street"):
        return 2
    return 1


def render_address_map(slug, lat, lon, width=432, height=324):
    """Renders a 4-shade street-level map centered on (lat, lon) as a PNG data URI."""
    features = fetch_address_features(slug, lat, lon)
    bbox = compute_bbox(lat, lon, span_m=520, aspect=width / height)
    minx, miny, maxx, maxy = bbox
    sx = width / (maxx - minx)
    sy = height / (maxy - miny)
    meters_per_px = (maxx - minx) * math.cos(math.radians(lat)) / width

    def project(coords):
        out = []
        for c in coords:
            x, y = to_merc(c[0], c[1])
            out.append(((x - minx) * sx, (maxy - y) * sy))
        return out

    img = Image.new("L", (width, height), WHITE)

    try:
        mask = fetch_water_mask(slug, bbox, width, height)
        _hatch_water(img, mask)
    except (requests.RequestException, OSError):
        pass

    draw = ImageDraw.Draw(img)

    # 1) Parks / gardens (light gray)
    for f in features:
        if f["type"] == "park" and f["closed"] and len(f["coords"]) >= 4:
            draw.polygon(project(f["coords"]), fill=LIGHT)

    # 2) Buildings (light gray with dark outline); highlight building closest to center
    cx_px, cy_px = width / 2.0, height / 2.0
    buildings = [
        (f, project(f["coords"]))
        for f in features
        if f["type"] == "building" and f["closed"] and len(f["coords"]) >= 4
    ]
    target_idx = None
    best_dist = 32.0
    for idx, (_, pts) in enumerate(buildings):
        bx = sum(p[0] for p in pts) / len(pts)
        by = sum(p[1] for p in pts) / len(pts)
        dist = math.hypot(bx - cx_px, by - cy_px)
        if dist < best_dist:
            best_dist = dist
            target_idx = idx

    for idx, (_, pts) in enumerate(buildings):
        if idx == target_idx:
            draw.polygon(pts, fill=BLACK)
        else:
            draw.polygon(pts, fill=LIGHT, outline=DARK)

    # 3) Roads (dark gray / black)
    for f in features:
        if f["type"] == "road":
            rw = _road_width(f["highway"])
            color = BLACK if rw >= 4 else DARK
            draw.line(project(f["coords"]), fill=color, width=rw, joint="curve")

    # 4) Target crosshair pin at exact (lat, lon)
    cx, cy = int(round(cx_px)), int(round(cy_px))
    draw.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=WHITE, outline=BLACK, width=2)
    draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=BLACK)
    draw.line([(cx - 15, cy), (cx - 11, cy)], fill=BLACK, width=2)
    draw.line([(cx + 11, cy), (cx + 15, cy)], fill=BLACK, width=2)
    draw.line([(cx, cy - 15), (cx, cy - 11)], fill=BLACK, width=2)
    draw.line([(cx, cy + 11), (cx, cy + 15)], fill=BLACK, width=2)

    # 5) North arrow (top-right)
    nx, ny = width - 16, 10
    draw.polygon([(nx, ny), (nx - 6, ny + 14), (nx, ny + 10), (nx + 6, ny + 14)], fill=BLACK)
    small_font = _font(10)
    l, t, r, _ = draw.textbbox((0, 0), "N", font=small_font)
    draw.text((nx - (r - l) / 2 - l, ny + 16 - t), "N", fill=BLACK, font=small_font)

    # 6) Scale bar (bottom-left, 100 m)
    bar_m = 100
    bar_px = bar_m / meters_per_px
    bx, by = 10, height - 12
    draw.rectangle([bx - 3, by - 14, bx + bar_px + 3, by + 5], fill=WHITE)
    draw.rectangle([bx, by, bx + bar_px, by + 3], fill=BLACK)
    draw.line([(bx, by - 3), (bx, by + 3)], fill=BLACK, width=1)
    draw.line([(bx + bar_px, by - 3), (bx + bar_px, by + 3)], fill=BLACK, width=1)
    draw.text((bx, by - 13), "100 m", fill=BLACK, font=small_font)

    # 7) Frame
    draw.rectangle([0, 0, width - 1, height - 1], outline=BLACK, width=2)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
