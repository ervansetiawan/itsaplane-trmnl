"""Deterministic Daily Pen-Plotter Generative Art for TRMNL."""

from datetime import date
import math
import random


def _hypotrochoid(rng: random.Random) -> tuple[str, str, str, list[str]]:
    R = rng.choice([120, 126, 130, 135])
    r = rng.choice([24, 30, 35, 42, 45, 50, 54])
    d = rng.randint(55, 115)
    steps = 720
    # LCM-like revolution count
    g = math.gcd(R, r)
    turns = r // g
    turns = min(turns, 12)
    pts = []
    for i in range(steps * turns + 1):
        t = (2 * math.pi * i) / steps
        x = (R - r) * math.cos(t) + d * math.cos(((R - r) / r) * t)
        y = (R - r) * math.sin(t) - d * math.sin(((R - r) / r) * t)
        px = 180 + x * 0.72
        py = 180 + y * 0.72
        pts.append(f"{px:.1f},{py:.1f}")
    path_d = "M " + " L ".join(pts)
    return (
        "Hypotrochoid",
        f"R={R} · r={r} · d={d}",
        "Epicycle",
        [path_d],
    )


def _lissajous(rng: random.Random) -> tuple[str, str, str, list[str]]:
    fx = rng.choice([3, 4, 5, 6, 7])
    fy = rng.choice([2, 3, 4, 5, 7])
    if fx == fy:
        fy += 1
    delta = round(rng.uniform(0.25, 1.4), 2)
    paths = []
    for layer in range(3):
        scale = 148 - layer * 14
        pts = []
        steps = 480
        for i in range(steps + 1):
            t = (2 * math.pi * i) / steps
            x = 180 + scale * math.sin(fx * t + delta + layer * 0.12)
            y = 180 + scale * math.sin(fy * t)
            pts.append(f"{x:.1f},{y:.1f}")
        paths.append("M " + " L ".join(pts))
    return (
        "Lissajous Knot",
        f"fx={fx} · fy={fy} · δ={delta} rad",
        "Harmonic",
        paths,
    )


def _molnar_grid(rng: random.Random) -> tuple[str, str, str, list[str]]:
    n = 9
    cell = 34
    offset = (360 - n * cell) / 2
    jitter_max = rng.uniform(4.0, 9.0)
    paths = []
    for row in range(n):
        for col in range(n):
            dist = math.hypot(row - 4, col - 4) / 5.6
            j = jitter_max * (0.2 + 0.8 * dist)
            cx = offset + col * cell + cell / 2
            cy = offset + row * cell + cell / 2
            for ring in (13, 8):
                pts = []
                for dx, dy in [(-ring, -ring), (ring, -ring), (ring, ring), (-ring, ring)]:
                    px = cx + dx + rng.uniform(-j, j)
                    py = cy + dy + rng.uniform(-j, j)
                    pts.append(f"{px:.1f},{py:.1f}")
                paths.append("M " + " L ".join(pts) + " Z")
    return (
        "Vera Molnár Grid",
        f"{n}×{n} · 2 rings · σ={jitter_max:.1f}px",
        "Des Ordres",
        paths,
    )


def _truchet_maze(rng: random.Random) -> tuple[str, str, str, list[str]]:
    n = 12
    cell = 28
    offset = (360 - n * cell) / 2
    r = cell / 2
    paths = []
    for row in range(n):
        for col in range(n):
            x0 = offset + col * cell
            y0 = offset + row * cell
            x1 = x0 + cell
            y1 = y0 + cell
            if rng.random() < 0.5:
                # Top-left & bottom-right quarter arcs
                paths.append(f"M {x0 + r:.1f},{y0:.1f} A {r:.1f},{r:.1f} 0 0 1 {x0:.1f},{y0 + r:.1f}")
                paths.append(f"M {x1 - r:.1f},{y1:.1f} A {r:.1f},{r:.1f} 0 0 1 {x1:.1f},{y1 - r:.1f}")
            else:
                # Top-right & bottom-left quarter arcs
                paths.append(f"M {x0 + r:.1f},{y0:.1f} A {r:.1f},{r:.1f} 0 0 0 {x1:.1f},{y0 + r:.1f}")
                paths.append(f"M {x0:.1f},{y1 - r:.1f} A {r:.1f},{r:.1f} 0 0 0 {x0 + r:.1f},{y1:.1f}")
    return (
        "Truchet Quarter-Arcs",
        f"{n}×{n} tiles · r={int(r)}px",
        "Labyrinth",
        paths,
    )


ALGORITHMS = [_hypotrochoid, _lissajous, _molnar_grid, _truchet_maze]

ALGORITHM_META = {
    "Hypotrochoid": {
        "short": "Epicycle",
        "formula": "x = (R-r)cos(t) + d*cos((R-r)t/r)",
        "note": "Traced by a point attached to a circle rolling inside a fixed outer ring.",
    },
    "Lissajous Knot": {
        "short": "Harmonic",
        "formula": "x = A*sin(fx*t + d),  y = A*sin(fy*t)",
        "note": "Harmonic oscilloscope curves studied by Jules Antoine Lissajous (1857).",
    },
    "Vera Molnár Grid": {
        "short": "Des Ordres",
        "formula": "9x9 nested squares · radial jitter",
        "note": "Homage to Vera Molnar's Des Ordres (1974), balancing grid order and noise.",
    },
    "Truchet Quarter-Arcs": {
        "short": "Labyrinth",
        "formula": "12x12 tiles · quarter-arcs (p = 0.5)",
        "note": "Sebastien Truchet's 1704 tiling; two arc orientations form a continuous maze.",
    },
}

CYCLE_LABELS = ["Epicycle", "Harmonic", "Des Ordres", "Labyrinth"]


def _compute_plotter_stats(paths: list[str]) -> tuple[int, int]:
    """Computes total vertex count and approximate pen travel distance across SVG paths."""
    vertices = 0
    travel = 0.0
    for d in paths:
        tokens = d.replace("M ", "").replace(" Z", "").split()
        prev = None
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok == "L":
                i += 1
                continue
            if tok == "A" and i + 6 < len(tokens):
                try:
                    rx = float(tokens[i + 1].split(",")[0])
                    travel += 0.5 * math.pi * rx
                    end_parts = tokens[i + 6].split(",")
                    prev = (float(end_parts[0]), float(end_parts[1]))
                    vertices += 1
                except (ValueError, IndexError):
                    pass
                i += 7
                continue
            if "," in tok:
                try:
                    x_s, y_s = tok.split(",", 1)
                    pt = (float(x_s), float(y_s))
                    if prev is not None:
                        travel += math.hypot(pt[0] - prev[0], pt[1] - prev[1])
                    prev = pt
                    vertices += 1
                except ValueError:
                    pass
            i += 1
    return vertices, int(round(travel))


def generate_daily_plotter(target_date: date | None = None) -> dict:
    d = target_date or date.today()
    seed = d.toordinal()
    rng = random.Random(seed)
    idx = seed % len(ALGORITHMS)
    algo_fn = ALGORITHMS[idx]
    algo_name, params, prefix, paths = algo_fn(rng)
    meta = ALGORITHM_META.get(algo_name, {})
    vertices, pen_travel = _compute_plotter_stats(paths)
    next_label = CYCLE_LABELS[(idx + 1) % len(CYCLE_LABELS)]
    cycle = [
        {"label": lbl, "active": i == idx}
        for i, lbl in enumerate(CYCLE_LABELS)
    ]

    return {
        "title": "Daily Pen-Plotter",
        "piece_title": f"{prefix} #{d.timetuple().tm_yday}",
        "algorithm": algo_name,
        "formula": meta.get("formula", ""),
        "note": meta.get("note", ""),
        "cycle": cycle,
        "next_algorithm": next_label,
        "params": params,
        "seed": seed,
        "stroke_count": len(paths),
        "vertex_count": vertices,
        "pen_travel": pen_travel,
        "paths": paths,
        "date": d.strftime("%b %d, %Y").upper(),
    }
