"""Daily IQ Challenge: Deterministic 3x3 Raven's-style 1-bit SVG visual puzzles."""

from datetime import date, timedelta
import random


def _shape_svg(shape: str, fill_mode: str, angle: int = 0) -> str:
    """Renders a centered shape on an 80x80 tile (center 40,40)."""
    fill = "#000" if fill_mode == "solid" else "#fff"
    stroke = "#000"
    sw = "2.5"
    inner = ""
    if shape == "triangle":
        inner = f'<polygon points="40,14 64,58 16,58" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round" />'
    elif shape == "square":
        inner = f'<rect x="18" y="18" width="44" height="44" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" />'
    elif shape == "diamond":
        inner = f'<polygon points="40,13 67,40 40,67 13,40" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round" />'
    elif shape == "arrow":
        inner = f'<path d="M 40,14 L 58,34 L 47,34 L 47,64 L 33,64 L 33,34 L 22,34 Z" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round" />'
    elif shape == "semicircle":
        inner = f'<path d="M 16,48 A 24,24 0 0 1 64,48 Z" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" />'
    else:
        inner = f'<circle cx="40" cy="40" r="22" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" />'

    if fill_mode == "striped":
        inner += '<line x1="26" y1="40" x2="54" y2="40" stroke="#000" stroke-width="2" /><line x1="40" y1="26" x2="40" y2="54" stroke="#000" stroke-width="2" />'

    if angle:
        return f'<g transform="rotate({angle} 40 40)">{inner}</g>'
    return inner


def _pip_svg(count: int, hollow: bool = False) -> str:
    """Renders 1..9 crisp pips in a 3x3 subgrid on an 80x80 tile."""
    coords = [
        (20, 20), (40, 20), (60, 20),
        (20, 40), (40, 40), (60, 40),
        (20, 60), (40, 60), (60, 60),
    ]
    layouts = {
        1: [4],
        2: [0, 8],
        3: [0, 4, 8],
        4: [0, 2, 6, 8],
        5: [0, 2, 4, 6, 8],
        6: [0, 2, 3, 5, 6, 8],
        7: [0, 2, 3, 4, 5, 6, 8],
        8: [0, 1, 2, 3, 5, 6, 7, 8],
        9: [0, 1, 2, 3, 4, 5, 6, 7, 8],
    }
    fill = "#fff" if hollow else "#000"
    parts = []
    for idx in layouts.get(max(1, min(9, count)), [4]):
        cx, cy = coords[idx]
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="5.5" fill="{fill}" stroke="#000" stroke-width="2" />')
    return "".join(parts)


def _xor_svg(mask: int) -> str:
    """Renders a 6-segment geometric glyph from a 6-bit mask on an 80x80 tile."""
    # Bits: 0=top, 1=bottom, 2=left, 3=right, 4=diag1, 5=diag2
    segs = [
        '<line x1="16" y1="16" x2="64" y2="16" stroke="#000" stroke-width="4" stroke-linecap="round" />',
        '<line x1="16" y1="64" x2="64" y2="64" stroke="#000" stroke-width="4" stroke-linecap="round" />',
        '<line x1="16" y1="16" x2="16" y2="64" stroke="#000" stroke-width="4" stroke-linecap="round" />',
        '<line x1="64" y1="16" x2="64" y2="64" stroke="#000" stroke-width="4" stroke-linecap="round" />',
        '<line x1="16" y1="16" x2="64" y2="64" stroke="#000" stroke-width="4" stroke-linecap="round" />',
        '<line x1="64" y1="16" x2="16" y2="64" stroke="#000" stroke-width="4" stroke-linecap="round" />',
    ]
    center = '<circle cx="40" cy="40" r="3" fill="#000" />'
    return center + "".join(segs[i] for i in range(6) if mask & (1 << i))


def _rings_svg(rings: int, outer_shape: str, dot_pos: str, dashed: bool = False) -> str:
    """Renders 1..3 concentric shapes + a corner marker dot."""
    parts = []
    dash_attr = ' stroke-dasharray="4 3"' if dashed else ""
    for k in range(rings):
        pad = 12 + k * 8
        size = 80 - 2 * pad
        if outer_shape == "circle":
            parts.append(f'<circle cx="40" cy="40" r="{size // 2}" fill="none" stroke="#000" stroke-width="2.2"{dash_attr} />')
        elif outer_shape == "diamond":
            r = size // 2
            parts.append(f'<polygon points="40,{40 - r} {40 + r},40 40,{40 + r} {40 - r},40" fill="none" stroke="#000" stroke-width="2.2"{dash_attr} />')
        else:
            parts.append(f'<rect x="{pad}" y="{pad}" width="{size}" height="{size}" fill="none" stroke="#000" stroke-width="2.2"{dash_attr} />')
    dot_coords = {"TL": (12, 12), "TR": (68, 12), "BR": (68, 68), "BL": (12, 68)}
    dx, dy = dot_coords[dot_pos]
    parts.append(f'<circle cx="{dx}" cy="{dy}" r="4.5" fill="#000" />')
    return "".join(parts)


def _reflect_svg(quads: tuple[int, int, int, int], style: str = "square") -> str:
    """Renders an asymmetric 2x2 quadrant glyph for reflection/symmetry puzzles."""
    coords = [(16, 16), (44, 16), (16, 44), (44, 44)]
    parts = ['<line x1="40" y1="12" x2="40" y2="68" stroke="#ccc" stroke-width="1" /><line x1="12" y1="40" x2="68" y2="40" stroke="#ccc" stroke-width="1" />']
    for idx, active in enumerate(quads):
        x, y = coords[idx]
        if active:
            if style == "circle":
                parts.append(f'<circle cx="{x + 10}" cy="{y + 10}" r="9" fill="#000" />')
            else:
                parts.append(f'<rect x="{x}" y="{y}" width="20" height="20" rx="2" fill="#000" />')
        else:
            if style == "circle":
                parts.append(f'<circle cx="{x + 10}" cy="{y + 10}" r="9" fill="#fff" stroke="#000" stroke-width="1.5" />')
            else:
                parts.append(f'<rect x="{x}" y="{y}" width="20" height="20" rx="2" fill="#fff" stroke="#000" stroke-width="1.5" />')
    return "".join(parts)


def _gen_rotation_matrix(rng: random.Random) -> dict:
    shapes = rng.sample(["arrow", "semicircle", "triangle", "diamond"], 3)
    fills = rng.sample(["outline", "solid", "striped"], 3)
    step = rng.choice([90, -90, 45])
    base_angle = rng.choice([0, 45, 90])

    tiles = []
    for r in range(3):
        for c in range(3):
            sh = shapes[(r + c) % 3]
            fl = fills[(r + 2 * c) % 3]
            ang = (base_angle + (r + c) * step) % 360
            tiles.append(_shape_svg(sh, fl, ang))

    ans = tiles[8]
    distractors = [
        _shape_svg(shapes[1], fills[2], (base_angle + 4 * step + 90) % 360),
        _shape_svg(shapes[(2 + 2) % 3], fills[0], (base_angle + 4 * step) % 360),
        _shape_svg(shapes[(2 + 2) % 3], fills[2], (base_angle + 4 * step + 180) % 360),
    ]
    return {
        "category": "Spatial Rotation",
        "difficulty": "Standard",
        "tiles": tiles[:8],
        "answer_svg": ans,
        "distractors": distractors,
        "explanation": f"Each step shifts shape, fill, and rotates by {step:+d}°.",
    }


def _gen_pip_arithmetic(rng: random.Random) -> dict:
    # Row 3 = Row 1 + Row 2 (or Col 3 = Col 1 + Col 2)
    r1 = [rng.randint(1, 4), rng.randint(1, 4), rng.randint(1, 4)]
    r2 = [rng.randint(1, 5 - v + 4) for v in r1]
    r2 = [min(5, max(1, 9 - r1[i] - rng.randint(0, 2))) for i in range(3)]
    r3 = [min(9, r1[i] + r2[i]) for i in range(3)]
    hollow_row = rng.choice([False, True])

    vals = [r1[0], r1[1], r1[2], r2[0], r2[1], r2[2], r3[0], r3[1], r3[2]]
    tiles = [
        _pip_svg(vals[i], hollow=(hollow_row and i // 3 == 1))
        for i in range(9)
    ]
    ans_val = vals[8]
    cand_vals = [v for v in (ans_val - 1, ans_val + 1, max(1, ans_val - 2)) if v != ans_val]
    while len(cand_vals) < 3:
        cand_vals.append((ans_val + len(cand_vals) + 2) % 9 + 1)
    distractors = [_pip_svg(v, hollow=False) for v in cand_vals[:3]]

    return {
        "category": "Pip Arithmetic",
        "difficulty": "Standard",
        "tiles": tiles[:8],
        "answer_svg": tiles[8],
        "distractors": distractors,
        "explanation": f"Bottom row equals Row 1 + Row 2 ({r1[2]} + {r2[2]} = {ans_val}).",
    }


def _gen_xor_matrix(rng: random.Random) -> dict:
    # Col 3 = Col 1 XOR Col 2
    masks = []
    for _ in range(3):
        m1 = rng.randint(3, 62)
        m2 = rng.randint(3, 62)
        while m1 == m2 or (m1 ^ m2) == 0:
            m2 = rng.randint(3, 62)
        masks.extend([m1, m2, m1 ^ m2])

    tiles = [_xor_svg(m) for m in masks]
    ans_m = masks[8]
    distractors = [
        _xor_svg(masks[6] | masks[7]),
        _xor_svg(ans_m ^ 1 if (ans_m ^ 1) != 0 else ans_m ^ 2),
        _xor_svg(ans_m ^ 16 if (ans_m ^ 16) != 0 else ans_m ^ 4),
    ]
    return {
        "category": "Visual XOR",
        "difficulty": "Mensa-Grade",
        "tiles": tiles[:8],
        "answer_svg": tiles[8],
        "distractors": distractors,
        "explanation": "Col 3 keeps only segments present in Col 1 OR Col 2 (XOR).",
    }


def _gen_rings_matrix(rng: random.Random) -> dict:
    corners = ["TL", "TR", "BR", "BL"]
    start_c = rng.randint(0, 3)
    dot_dir = rng.choice([1, -1])
    shapes = rng.sample(["circle", "square", "diamond"], 3)
    dashed_row = rng.choice([True, False])
    tiles = []
    for r in range(3):
        for c in range(3):
            rings = ((r + c) % 3) + 1
            dot = corners[(start_c + dot_dir * (r + c)) % 4]
            sh = shapes[(r + 2 * c) % 3]
            tiles.append(_rings_svg(rings, sh, dot, dashed=(dashed_row and r == 1)))

    ans_rings = ((2 + 2) % 3) + 1
    ans_dot = corners[(start_c + dot_dir * 4) % 4]
    ans_shape = shapes[(2 + 4) % 3]
    dir_lbl = "clockwise" if dot_dir == 1 else "counter-clockwise"
    distractors = [
        _rings_svg((ans_rings % 3) + 1, ans_shape, ans_dot),
        _rings_svg(ans_rings, ans_shape, corners[(start_c + dot_dir * 5) % 4]),
        _rings_svg(ans_rings, shapes[1], ans_dot),
    ]
    return {
        "category": "Nested Geometry",
        "difficulty": "Challenging",
        "tiles": tiles[:8],
        "answer_svg": tiles[8],
        "distractors": distractors,
        "explanation": f"{ans_rings} {ans_shape} rings with corner dot moving {dir_lbl} to {ans_dot}.",
    }


def _gen_reflection_matrix(rng: random.Random) -> dict:
    # Col 2 = horizontal flip of Col 1; Col 3 = vertical flip of Col 2
    style = rng.choice(["square", "circle"])
    patterns = []
    for _ in range(3):
        q = (rng.randint(0, 1), rng.randint(0, 1), rng.randint(0, 1), rng.randint(0, 1))
        while sum(q) in (0, 4) or (q[0] == q[1] and q[2] == q[3]):
            q = (rng.randint(0, 1), rng.randint(0, 1), rng.randint(0, 1), rng.randint(0, 1))
        h_flip = (q[1], q[0], q[3], q[2])
        v_flip = (h_flip[2], h_flip[3], h_flip[0], h_flip[1])
        patterns.extend([q, h_flip, v_flip])

    tiles = [_reflect_svg(p, style) for p in patterns]
    ans_q = patterns[8]
    cands = [
        (patterns[6][2], patterns[6][3], patterns[6][0], patterns[6][1]),
        patterns[7],
        (1 - ans_q[0], ans_q[1], ans_q[2], ans_q[3]),
    ]
    distractors = [_reflect_svg(c, style) for c in cands]
    return {
        "category": "Spatial Symmetry",
        "difficulty": "Challenging",
        "tiles": tiles[:8],
        "answer_svg": tiles[8],
        "distractors": distractors,
        "explanation": "Col 2 flips Col 1 horizontally; Col 3 flips Col 2 vertically.",
    }


GENERATORS = [_gen_rotation_matrix, _gen_pip_arithmetic, _gen_xor_matrix, _gen_rings_matrix, _gen_reflection_matrix]


def _build_for_seed(seed: int) -> dict:
    rng = random.Random(seed)
    gen = GENERATORS[seed % len(GENERATORS)]
    raw = gen(rng)

    # Deduplicate distractors and shuffle A/B/C/D deterministically
    options_raw = [raw["answer_svg"]]
    for d_svg in raw["distractors"]:
        if d_svg not in options_raw:
            options_raw.append(d_svg)
    while len(options_raw) < 4:
        options_raw.append(_pip_svg(len(options_raw) + 2))

    indices = [0, 1, 2, 3]
    rng.shuffle(indices)
    labels = ["A", "B", "C", "D"]
    choices = []
    correct_label = "A"
    for pos, orig_idx in enumerate(indices):
        if orig_idx == 0:
            correct_label = labels[pos]
        choices.append({"label": labels[pos], "svg": options_raw[orig_idx]})

    return {
        "category": raw["category"],
        "difficulty": raw["difficulty"],
        "tiles": raw["tiles"],
        "choices": choices,
        "correct_label": correct_label,
        "explanation": raw["explanation"],
    }


def generate_daily_iq(target_date: date | None = None) -> dict:
    """Returns today's deterministic 3x3 visual IQ matrix puzzle + yesterday's answer."""
    d = target_date or date.today()
    today_puzzle = _build_for_seed(d.toordinal())
    yest_puzzle = _build_for_seed((d - timedelta(days=1)).toordinal())

    return {
        "title": "Daily IQ Challenge",
        "date": d.strftime("%b %d, %Y").upper(),
        "puzzle_num": d.timetuple().tm_yday,
        "category": today_puzzle["category"],
        "difficulty": today_puzzle["difficulty"],
        "tiles": today_puzzle["tiles"],
        "choices": today_puzzle["choices"],
        "yesterday": {
            "answer": yest_puzzle["correct_label"],
            "category": yest_puzzle["category"],
            "explanation": yest_puzzle["explanation"],
        },
    }
