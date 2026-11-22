"""
Airport diagram renderer for TRMNL ePaper.

Builds a crisp, recognizable airport diagram (runways with designators, taxiways,
aprons, terminals, surrounding water/coastline) from OpenStreetMap data (Overpass API)
plus an ESRI World Topo water mask, rendered in 4 ePaper shades.
"""

import base64
import io
import json
import math
import os
import re

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
WATER_TILE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
)
EARTH_R = 6378137.0

# ePaper shades
BLACK, DARK, LIGHT, WHITE = 0, 85, 170, 255

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "pixel-airports-trmnl/1.0"})


# --------------------------------------------------------------------------- #
# Projection helpers
# --------------------------------------------------------------------------- #
def to_merc(lat, lon):
    """Projects lat/lon to Web Mercator meters."""
    x = math.radians(lon) * EARTH_R
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * EARTH_R
    return x, y


def merc_to_global_px(x, y, zoom):
    """Converts Web Mercator meters to global tile-pixel coordinates at a zoom level."""
    world = 256 * (2 ** zoom)
    gx = (x + math.pi * EARTH_R) / (2 * math.pi * EARTH_R) * world
    gy = (math.pi * EARTH_R - y) / (2 * math.pi * EARTH_R) * world
    return gx, gy


# --------------------------------------------------------------------------- #
# Data fetching (with permanent disk cache - airport layouts rarely change)
# --------------------------------------------------------------------------- #
def _cache_path(iata, suffix):
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{iata.upper()}{suffix}")


def is_cached(iata):
    """Returns True if both OSM features and the water mask are cached for this airport."""
    return os.path.exists(_cache_path(iata, ".json")) and os.path.exists(_cache_path(iata, "_water.png"))


def fetch_airport_features(iata, lat, lon, radius_m=7000):
    """Fetches runways, taxiways, aprons, terminals around an airport from Overpass (cached)."""
    path = _cache_path(iata, ".json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    query = (
        "[out:json][timeout:60];("
        f'way["aeroway"~"^(runway|taxiway|apron|terminal)$"](around:{radius_m},{lat},{lon});'
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
        raise RuntimeError(f"Overpass failed for {iata}: {last_exc}")

    features = []
    for el in elements:
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        tags = el.get("tags", {})
        coords = [[round(p["lat"], 6), round(p["lon"], 6)] for p in geom]
        features.append(
            {
                "type": tags.get("aeroway"),
                "ref": tags.get("ref", ""),
                "width": tags.get("width", ""),
                "area": tags.get("area", "") == "yes",
                "closed": coords[0] == coords[-1],
                "coords": coords,
            }
        )

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(features, fh)
    return features


def compute_bbox(features, center_lat, center_lon, aspect=4 / 3, pad=0.14, min_span_m=2200):
    """Computes a padded Web Mercator bbox framing all runways/terminals at the given aspect."""
    pts = [
        to_merc(c[0], c[1])
        for f in features
        if f["type"] in ("runway", "terminal")
        for c in f["coords"]
    ]
    if not pts:
        pts = [to_merc(center_lat, center_lon)]

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2

    # Mercator meters are stretched by 1/cos(lat); convert min span accordingly
    scale = 1 / math.cos(math.radians(center_lat))
    w = max(maxx - minx, min_span_m * scale) * (1 + pad * 2)
    h = max(maxy - miny, min_span_m * scale) * (1 + pad * 2)
    if w / h > aspect:
        h = w / aspect
    else:
        w = h * aspect
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def fetch_water_mask(iata, bbox, width, height):
    """Builds a boolean water mask image (L mode, 255 = water) for the bbox from ESRI topo tiles."""
    path = _cache_path(iata, "_water.png")
    if os.path.exists(path):
        mask = Image.open(path).convert("L")
        if mask.size == (width, height):
            return mask

    minx, miny, maxx, maxy = bbox
    # Choose a zoom where the bbox spans roughly 1.5-3x the output width in tile pixels
    zoom = 10
    for z in range(10, 17):
        gx0, _ = merc_to_global_px(minx, maxy, z)
        gx1, _ = merc_to_global_px(maxx, miny, z)
        if gx1 - gx0 > width * 1.5:
            zoom = z
            break
        zoom = z

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
        (
            int(gx0 - tx0 * 256),
            int(gy0 - ty0 * 256),
            int(gx1 - tx0 * 256),
            int(gy1 - ty0 * 256),
        )
    )
    # ESRI World Topo water is a distinct light blue (~204, 237, 255)
    px = crop.load()
    w0, h0 = crop.size
    mask = Image.new("L", (w0, h0), 0)
    mp = mask.load()
    for y in range(h0):
        for x in range(w0):
            rr, gg, bb = px[x, y]
            if bb >= 240 and (bb - rr) >= 30 and gg >= 220:
                mp[x, y] = 255

    # Remove label specks and small noise, then scale to output size
    mask = mask.filter(ImageFilter.MedianFilter(size=5))
    mask = mask.resize((width, height), Image.Resampling.BILINEAR).point(lambda v: 255 if v >= 128 else 0)
    mask.save(path)
    return mask


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #
def _parse_width(raw, default):
    match = re.search(r"[\d.]+", str(raw or ""))
    try:
        return float(match.group()) if match else default
    except ValueError:
        return default


def _designator_heading(part):
    match = re.match(r"\s*(\d{1,2})", part)
    return int(match.group(1)) * 10 if match else None


def _bearing(p_from, p_to):
    """Bearing (degrees from north) between two pixel points (y grows downward)."""
    dx = p_to[0] - p_from[0]
    dy = p_from[1] - p_to[1]
    return math.degrees(math.atan2(dx, dy)) % 360


def _angle_diff(a, b):
    return abs((a - b + 180) % 360 - 180)


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _draw_label(draw, text, center, font, canvas_size):
    """Draws a small boxed label centered at `center`, clamped inside the canvas."""
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    tw, th = r - l, b - t
    pad = 2
    w, h = canvas_size
    x = min(max(center[0] - tw / 2, pad + 1), w - tw - pad - 2)
    y = min(max(center[1] - th / 2, pad + 1), h - th - pad - 2)
    draw.rectangle([x - pad, y - pad, x + tw + pad, y + th + pad], fill=WHITE, outline=BLACK)
    draw.text((x - l, y - t), text, fill=BLACK, font=font)


def _hatch_water(img, mask):
    """Fills water areas with a crisp diagonal hatch pattern and outlines the coastline."""
    w, h = img.size
    ip = img.load()
    mp = mask.load()
    for y in range(h):
        for x in range(w):
            if mp[x, y]:
                ip[x, y] = DARK if (x + y) % 4 == 0 else WHITE

    # Coastline: water pixel adjacent to land -> black
    edges = mask.filter(ImageFilter.FIND_EDGES)
    ep = edges.load()
    for y in range(h):
        for x in range(w):
            if ep[x, y] and mp[x, y]:
                ip[x, y] = BLACK


def _nice_scale_length(meters_per_px, target_px):
    target_m = meters_per_px * target_px
    for nice in (100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000):
        if nice >= target_m * 0.7:
            return nice
    return 10000


# --------------------------------------------------------------------------- #
# Main render
# --------------------------------------------------------------------------- #
def render_airport_diagram(iata, lat, lon, width=432, height=324, wind_from_deg=None):
    """
    Renders a recognizable 4-shade airport diagram.

    Returns (data_uri, info) where info contains runway designators,
    longest runway length and the runway best aligned with the current wind.
    """
    features = fetch_airport_features(iata, lat, lon)
    bbox = compute_bbox(features, lat, lon, aspect=width / height)
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

    # 1) Water + coastline
    try:
        mask = fetch_water_mask(iata, bbox, width, height)
        _hatch_water(img, mask)
    except (requests.RequestException, OSError):
        pass

    draw = ImageDraw.Draw(img)

    # 2) Aprons (light gray fill)
    for f in features:
        if f["type"] == "apron" and f["closed"] and len(f["coords"]) >= 4:
            draw.polygon(project(f["coords"]), fill=LIGHT)

    # 3) Taxiways (dark gray lines scaled by real width)
    taxi_w = max(1, round(_parse_width("", 23) / meters_per_px))
    for f in features:
        if f["type"] == "taxiway":
            pts = project(f["coords"])
            if f["closed"] and f["area"]:
                draw.polygon(pts, fill=DARK)
            else:
                draw.line(pts, fill=DARK, width=min(taxi_w, 3), joint="curve")

    # 4) Terminals (solid black)
    for f in features:
        if f["type"] == "terminal" and f["closed"] and len(f["coords"]) >= 4:
            draw.polygon(project(f["coords"]), fill=BLACK)

    # 5) Runways (thick black with dashed white centerline + designators)
    runway_lines = []
    seen_refs = set()
    for f in features:
        if f["type"] != "runway":
            continue
        pts = project(f["coords"])
        if f["closed"] and (f["area"] or len(pts) > 4):
            draw.polygon(pts, fill=BLACK)
            continue
        ref_key = f["ref"] or str(f["coords"][0])
        if ref_key in seen_refs:
            continue
        seen_refs.add(ref_key)
        runway_lines.append((f, pts))

    longest_m = 0.0
    designators = []
    font = _font(11)
    label_jobs = []

    for f, pts in runway_lines:
        rw_px = max(5, round(_parse_width(f["width"], 45) / meters_per_px * 1.3))
        draw.line(pts, fill=BLACK, width=rw_px, joint="curve")

        a, b = pts[0], pts[-1]
        length_px = math.hypot(b[0] - a[0], b[1] - a[1])
        longest_m = max(longest_m, length_px * meters_per_px)

        # Dashed centerline
        if rw_px >= 5 and length_px > 20:
            ux, uy = (b[0] - a[0]) / length_px, (b[1] - a[1]) / length_px
            dash, gap, inset = 6, 5, 6
            pos = inset
            while pos + dash < length_px - inset:
                p1 = (a[0] + ux * pos, a[1] + uy * pos)
                p2 = (a[0] + ux * (pos + dash), a[1] + uy * (pos + dash))
                draw.line([p1, p2], fill=WHITE, width=1)
                pos += dash + gap

        # Threshold designators at each end
        parts = [p.strip() for p in (f["ref"] or "").split("/") if p.strip()]
        if parts:
            designators.append("/".join(parts))
            if length_px > 0:
                ux, uy = (b[0] - a[0]) / length_px, (b[1] - a[1]) / length_px
                for end, other, sign in ((a, b, -1), (b, a, 1)):
                    heading = _bearing(end, other)
                    best = min(
                        parts,
                        key=lambda p, h=heading: _angle_diff(_designator_heading(p) or 0, h),
                    )
                    offset = rw_px / 2 + 9
                    label_pos = (end[0] + sign * ux * offset, end[1] + sign * uy * offset)
                    label_jobs.append((best, label_pos))

    for text, pos in label_jobs:
        _draw_label(draw, text, pos, font, (width, height))

    # 6) North arrow (top-right)
    nx, ny = width - 16, 10
    draw.polygon([(nx, ny), (nx - 6, ny + 14), (nx, ny + 10), (nx + 6, ny + 14)], fill=BLACK)
    small_font = _font(10)
    l, t, r, _ = draw.textbbox((0, 0), "N", font=small_font)
    draw.text((nx - (r - l) / 2 - l, ny + 16 - t), "N", fill=BLACK, font=small_font)

    # 7) Scale bar (bottom-left)
    bar_m = _nice_scale_length(meters_per_px, width * 0.22)
    bar_px = bar_m / meters_per_px
    bx, by = 10, height - 12
    draw.rectangle([bx - 3, by - 14, bx + bar_px + 3, by + 5], fill=WHITE)
    draw.rectangle([bx, by, bx + bar_px, by + 3], fill=BLACK)
    draw.line([(bx, by - 3), (bx, by + 3)], fill=BLACK, width=1)
    draw.line([(bx + bar_px, by - 3), (bx + bar_px, by + 3)], fill=BLACK, width=1)
    scale_txt = f"{bar_m // 1000} km" if bar_m >= 1000 and bar_m % 1000 == 0 else f"{bar_m} m"
    draw.text((bx, by - 13), scale_txt, fill=BLACK, font=small_font)

    # 8) Frame
    draw.rectangle([0, 0, width - 1, height - 1], outline=BLACK, width=2)

    # Active runway: designator whose heading best matches the wind direction (land into wind)
    active = None
    if wind_from_deg is not None:
        all_parts = [p for d in designators for p in d.split("/")]
        scored = [(p, _designator_heading(p)) for p in all_parts if _designator_heading(p) is not None]
        if scored:
            active = min(scored, key=lambda ph: _angle_diff(ph[1], float(wind_from_deg)))[0]

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    data_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    unique_designators = sorted(set(designators), key=lambda d: (_designator_heading(d) or 0, d))
    return data_uri, {
        "runways": unique_designators,
        "runway_count": len(unique_designators),
        "longest_runway_m": int(round(longest_m, -1)),
        "active_runway": active,
    }
