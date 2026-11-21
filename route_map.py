"""Lightweight 1-bit / 2-bit SVG great-circle flight route map generator."""

import math

# Simplified coastlines & Great Lakes (lon, lat)
COASTLINES = [
    # North America (detailed US/Mexico/Canada coastline for instant recognition)
    [
        (-168, 65), (-162, 60), (-152, 60), (-140, 60), (-130, 54), (-124.7, 48.4),
        (-124.5, 42.0), (-123.8, 39.0), (-122.4, 37.8), (-120.6, 34.5), (-117.1, 32.5),
        (-114.5, 31.5), (-110.0, 24.0), (-105.5, 20.5), (-96.0, 16.0), (-87.0, 14.0),
        (-83.5, 10.0), (-78.0, 9.0), (-84.0, 11.0), (-88.0, 16.0), (-90.4, 21.2),
        (-90.5, 19.8), (-96.1, 19.2), (-97.8, 22.3), (-97.2, 26.0), (-96.8, 28.0),
        (-94.8, 29.3), (-89.4, 29.1), (-87.2, 30.3), (-84.2, 30.0), (-82.8, 28.0),
        (-81.8, 26.0), (-80.2, 25.2), (-80.0, 27.0), (-81.2, 30.5), (-79.9, 32.8),
        (-75.5, 35.2), (-76.0, 37.0), (-74.8, 39.0), (-74.0, 40.5), (-71.4, 41.3),
        (-70.0, 41.8), (-70.8, 42.8), (-67.0, 45.0), (-64.0, 45.5), (-60.0, 46.5),
        (-53.0, 47.0), (-56.0, 52.0), (-64.0, 58.0), (-78.0, 62.0), (-94.0, 60.0),
        (-90.0, 66.0), (-110.0, 69.0), (-135.0, 70.0), (-156.0, 71.0), (-166.0, 68.0),
        (-168.0, 65.0),
    ],
    # South America
    [
        (-78, 9), (-72, 12), (-62, 10), (-50, 1), (-35, -6), (-38, -13),
        (-40, -22), (-48, -28), (-53, -34), (-62, -41), (-67, -50), (-68, -55),
        (-74, -52), (-73, -42), (-71, -30), (-70, -18), (-77, -12), (-81, -5),
        (-79, 2), (-78, 9),
    ],
    # Great Britain & Ireland
    [(-6, 50), (-5, 55), (-3, 58), (-2, 57), (1, 52), (-2, 50), (-6, 50)],
    [(-10, 52), (-9, 55), (-6, 54), (-7, 52), (-10, 52)],
    # Continental Europe & Scandinavia
    [
        (-9, 37), (-9, 43), (-2, 43), (-4, 48), (2, 51), (8, 54), (10, 58),
        (5, 61), (14, 68), (28, 71), (32, 69), (24, 65), (20, 60), (28, 60),
        (21, 55), (14, 54), (24, 46), (29, 41), (24, 38), (18, 40), (16, 38),
        (12, 42), (9, 44), (5, 43), (0, 39), (-5, 36), (-9, 37),
    ],
    # Africa
    [
        (-6, 36), (10, 37), (12, 33), (25, 32), (33, 31), (43, 12), (51, 12),
        (45, 2), (40, -10), (35, -24), (28, -33), (18, -34), (14, -22),
        (12, -6), (9, 4), (2, 6), (-8, 5), (-17, 15), (-15, 24), (-6, 36),
    ],
    # Asia
    [
        (29, 41), (40, 42), (50, 40), (60, 45), (72, 20), (80, 8), (90, 22),
        (100, 13), (104, 2), (109, 12), (114, 22), (121, 31), (122, 39),
        (129, 35), (135, 44), (142, 54), (160, 60), (175, 66), (130, 72),
        (80, 73), (60, 69), (45, 66), (32, 69), (29, 41),
    ],
    # Japan & Australia
    [(130, 31), (135, 34), (140, 36), (145, 44), (141, 45), (138, 38), (130, 31)],
    [(114, -22), (122, -17), (131, -12), (137, -14), (142, -11), (153, -27), (150, -37), (138, -35), (129, -32), (115, -34), (114, -22)],
]

# Great Lakes water cutouts (rendered white inside North America)
LAKES = [
    # Lake Superior
    [(-92.1, 46.8), (-89.5, 48.2), (-86.5, 48.8), (-84.6, 46.5), (-87.5, 46.5), (-90.8, 46.7), (-92.1, 46.8)],
    # Lake Michigan
    [(-87.9, 41.6), (-87.8, 44.0), (-86.8, 45.8), (-85.1, 45.9), (-86.2, 43.5), (-86.6, 41.8), (-87.9, 41.6)],
    # Lake Huron
    [(-84.7, 45.9), (-82.5, 46.2), (-80.0, 45.0), (-82.4, 43.0), (-83.9, 43.7), (-84.7, 45.9)],
    # Lake Erie & Ontario
    [(-83.4, 41.6), (-81.2, 42.6), (-78.9, 42.9), (-80.5, 41.8), (-83.4, 41.6)],
    [(-79.8, 43.3), (-77.5, 44.0), (-76.1, 44.1), (-76.5, 43.5), (-79.2, 43.2), (-79.8, 43.3)],
]

US_BORDERS = [
    # US-Canada 49th parallel & Great Lakes/Northeast border
    [(-124.7, 48.4), (-123.0, 49.0), (-95.1, 49.0), (-92.1, 48.1), (-89.5, 48.0), (-84.6, 46.5), (-82.4, 43.0), (-78.9, 42.9), (-76.1, 44.1), (-74.8, 45.0), (-71.5, 45.0), (-69.2, 47.4), (-67.0, 45.0)],
    # US-Mexico border
    [(-117.1, 32.5), (-114.8, 32.5), (-111.1, 31.3), (-108.2, 31.3), (-106.5, 31.8), (-104.5, 30.0), (-103.0, 29.0), (-101.0, 29.5), (-99.5, 27.5), (-97.2, 26.0)],
]


def _slerp_points(lat1: float, lon1: float, lat2: float, lon2: float, steps: int = 24) -> list[tuple[float, float]]:
    phi1, lam1 = math.radians(lat1), math.radians(lon1)
    phi2, lam2 = math.radians(lat2), math.radians(lon2)
    x1, y1, z1 = math.cos(phi1) * math.cos(lam1), math.cos(phi1) * math.sin(lam1), math.sin(phi1)
    x2, y2, z2 = math.cos(phi2) * math.cos(lam2), math.cos(phi2) * math.sin(lam2), math.sin(phi2)
    dot = max(-1.0, min(1.0, x1 * x2 + y1 * y2 + z1 * z2))
    omega = math.acos(dot)
    pts = []
    for i in range(steps + 1):
        t = i / steps
        if omega < 1e-6:
            x, y, z = x1 + t * (x2 - x1), y1 + t * (y2 - y1), z1 + t * (z2 - z1)
        else:
            sin_o = math.sin(omega)
            a = math.sin((1 - t) * omega) / sin_o
            b = math.sin(t * omega) / sin_o
            x, y, z = a * x1 + b * x2, a * y1 + b * y2, a * z1 + b * z2
        lat = math.degrees(math.atan2(z, math.hypot(x, y)))
        lon = math.degrees(math.atan2(y, x))
        pts.append((lon, lat))
    return pts


def build_route_map(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    ac_lat: float,
    ac_lon: float,
    track_deg: float = 0.0,
    progress_pct: float = 0.0,
    width: int = 360,
    height: int = 96,
) -> dict | None:
    """Projects coastlines, lakes, great-circle arc, airports, and aircraft into an SVG map."""
    try:
        lats = [float(origin_lat), float(dest_lat), float(ac_lat)]
        lons = [float(origin_lon), float(dest_lon), float(ac_lon)]
    except (ValueError, TypeError):
        return None

    in_conus = all(23.0 <= la <= 51.0 and -127.0 <= lo <= -65.0 for la, lo in zip(lats, lons))
    if in_conus:
        # Frame the contiguous US so geography is immediately recognizable
        min_lat, max_lat = 23.5, 50.5
        min_lon, max_lon = -126.5, -65.5
    else:
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

    mid_lat = (min_lat + max_lat) / 2.0
    cos_lat = max(0.25, math.cos(math.radians(mid_lat)))

    span_lat = max(18.0, (max_lat - min_lat) * (1.06 if in_conus else 1.4))
    span_lon = max(36.0, (max_lon - min_lon) * (1.04 if in_conus else 1.35))

    target_ratio = width / height
    geo_ratio = (span_lon * cos_lat) / span_lat
    if geo_ratio < target_ratio:
        span_lon = (span_lat * target_ratio) / cos_lat
    else:
        span_lat = (span_lon * cos_lat) / target_ratio

    c_lat = (min_lat + max_lat) / 2.0
    c_lon = (min_lon + max_lon) / 2.0
    lon0, lon1 = c_lon - span_lon / 2.0, c_lon + span_lon / 2.0
    lat0, lat1 = c_lat - span_lat / 2.0, c_lat + span_lat / 2.0

    def proj(lon: float, lat: float) -> tuple[float, float]:
        x = (lon - lon0) / (lon1 - lon0) * width
        y = (1.0 - (lat - lat0) / (lat1 - lat0)) * height
        return round(x, 1), round(y, 1)

    def poly_paths(polys: list[list[tuple[float, float]]]) -> list[str]:
        out = []
        for poly in polys:
            p_lons = [p[0] for p in poly]
            p_lats = [p[1] for p in poly]
            if max(p_lons) < lon0 - 5 or min(p_lons) > lon1 + 5 or max(p_lats) < lat0 - 5 or min(p_lats) > lat1 + 5:
                continue
            pts = [proj(lon, lat) for lon, lat in poly]
            out.append("M " + " L ".join(f"{x},{y}" for x, y in pts) + " Z")
        return out

    land_paths = poly_paths(COASTLINES)
    lake_paths = poly_paths(LAKES)
    border_paths = []
    if in_conus:
        for line in US_BORDERS:
            pts = [proj(lon, lat) for lon, lat in line]
            border_paths.append("M " + " L ".join(f"{x},{y}" for x, y in pts))

    arc_geo = _slerp_points(float(origin_lat), float(origin_lon), float(dest_lat), float(dest_lon), steps=24)
    split_idx = max(0, min(len(arc_geo) - 1, round((max(0.0, min(100.0, progress_pct)) / 100.0) * (len(arc_geo) - 1))))
    flown_pts = [proj(lon, lat) for lon, lat in arc_geo[: split_idx + 1]]
    rem_pts = [proj(lon, lat) for lon, lat in arc_geo[split_idx:]]

    ox, oy = proj(float(origin_lon), float(origin_lat))
    dx, dy = proj(float(dest_lon), float(dest_lat))
    px, py = proj(float(ac_lon), float(ac_lat))

    if abs(dx - ox) < 38 and abs(dy - oy) < 28:
        ox_lbl = max(18.0, ox - 8.0) if ox <= dx else min(width - 18.0, ox + 8.0)
        dx_lbl = min(width - 18.0, dx + 8.0) if ox <= dx else max(18.0, dx - 8.0)
        ox_anchor = "end" if ox <= dx else "start"
        dx_anchor = "start" if ox <= dx else "end"
        oy_lbl = oy + 3.0
        dy_lbl = dy + 3.0
    else:
        ox_lbl = max(24.0, min(width - 24.0, ox))
        dx_lbl = max(24.0, min(width - 24.0, dx))
        ox_anchor = "middle"
        dx_anchor = "middle"
        oy_lbl = oy - 7 if oy > 18 else oy + 13
        dy_lbl = dy - 7 if dy > 18 else dy + 13

    try:
        angle = round(float(track_deg) - 90.0, 1)
    except (ValueError, TypeError):
        angle = 0.0

    return {
        "land_paths": land_paths,
        "lake_paths": lake_paths,
        "border_paths": border_paths,
        "flown_path": ("M " + " L ".join(f"{x},{y}" for x, y in flown_pts)) if len(flown_pts) >= 2 else "",
        "rem_path": ("M " + " L ".join(f"{x},{y}" for x, y in rem_pts)) if len(rem_pts) >= 2 else "",
        "ox": ox,
        "oy": oy,
        "dx": dx,
        "dy": dy,
        "px": px,
        "py": py,
        "ox_lbl": round(ox_lbl, 1),
        "oy_lbl": round(oy_lbl, 1),
        "ox_anchor": ox_anchor,
        "dx_lbl": round(dx_lbl, 1),
        "dy_lbl": round(dy_lbl, 1),
        "dx_anchor": dx_anchor,
        "plane_angle": angle,
    }
