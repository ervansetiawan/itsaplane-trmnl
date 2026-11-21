"""Yesterday's NBA Game Story: Win-Probability Curve, Linescore & MVP."""

from datetime import date, timedelta
import random
import time
import requests

NBA_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
NBA_SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"

_SCOREBOARD_CACHE: dict[str, tuple[float, date, list[dict]]] = {}
_STORY_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_CACHE_TTL_SECONDS = 1800


def _team_leader(summary: dict, team_abbr: str) -> dict | None:
    best = None
    for tb in summary.get("boxscore", {}).get("players", []):
        if tb.get("team", {}).get("abbreviation") != team_abbr:
            continue
        for sg in tb.get("statistics", []):
            names = sg.get("names", [])
            if "PTS" not in names:
                continue
            pts_i = names.index("PTS")
            reb_i = names.index("REB") if "REB" in names else None
            ast_i = names.index("AST") if "AST" in names else None
            fg_i = names.index("FG") if "FG" in names else None
            tp_i = names.index("3PT") if "3PT" in names else None
            pm_i = names.index("+/-") if "+/-" in names else None
            for ath in sg.get("athletes", []):
                st = ath.get("stats", [])
                if len(st) <= pts_i:
                    continue
                try:
                    pts = int(st[pts_i])
                except (ValueError, TypeError):
                    continue
                if best is None or pts > best["pts"]:
                    best = {
                        "name": ath.get("athlete", {}).get("shortName", ""),
                        "team": team_abbr,
                        "pts": pts,
                        "reb": st[reb_i] if reb_i is not None and len(st) > reb_i else "0",
                        "ast": st[ast_i] if ast_i is not None and len(st) > ast_i else "0",
                        "fg": st[fg_i] if fg_i is not None and len(st) > fg_i else "",
                        "three_pt": st[tp_i] if tp_i is not None and len(st) > tp_i else "",
                        "plus_minus": st[pm_i] if pm_i is not None and len(st) > pm_i else "",
                    }
    return best


def _team_stats_map(summary: dict, team_abbr: str) -> dict[str, str]:
    for tb in summary.get("boxscore", {}).get("teams", []):
        if tb.get("team", {}).get("abbreviation") == team_abbr:
            return {
                s.get("name"): str(s.get("displayValue", ""))
                for s in tb.get("statistics", [])
                if s.get("name")
            }
    return {}


def _team_shooting(summary: dict, team_abbr: str) -> str:
    stats = _team_stats_map(summary, team_abbr)
    if not stats:
        return ""
    fg_pct = stats.get("fieldGoalPct")
    tp = stats.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted")
    tp_pct = stats.get("threePointFieldGoalPct")
    parts = []
    if fg_pct:
        parts.append(f"{fg_pct}% FG")
    if tp:
        parts.append(f"{tp} 3PT" + (f" ({tp_pct}%)" if tp_pct else ""))
    return " · ".join(parts)


def _build_team_compare(summary: dict, away_abbr: str, home_abbr: str) -> list[dict]:
    a_stats = _team_stats_map(summary, away_abbr)
    h_stats = _team_stats_map(summary, home_abbr)
    if not a_stats or not h_stats:
        return []
    specs = [
        ("FG%", "fieldGoalPct", "%"),
        ("3P%", "threePointFieldGoalPct", "%"),
        ("REB", "totalRebounds", ""),
        ("AST", "assists", ""),
    ]
    rows = []
    for label, key, suffix in specs:
        try:
            a_val = float(a_stats.get(key, 0) or 0)
            h_val = float(h_stats.get(key, 0) or 0)
        except (ValueError, TypeError):
            continue
        total = a_val + h_val
        if total <= 0:
            continue
        a_pct = max(12, min(88, round(a_val / total * 100)))
        a_disp = f"{int(round(a_val))}{suffix}"
        h_disp = f"{int(round(h_val))}{suffix}"
        rows.append(
            {
                "label": label,
                "away_val": a_disp,
                "home_val": h_disp,
                "away_pct": a_pct,
                "home_pct": 100 - a_pct,
            }
        )
    return rows


def fetch_nba_game_story(target_date: date | None = None, pick_random: bool = True) -> dict:
    # Default to yesterday's slate
    requested_date = target_date or (date.today() - timedelta(days=1))
    sb_key = requested_date.isoformat()
    now = time.time()

    if sb_key in _SCOREBOARD_CACHE and (now - _SCOREBOARD_CACHE[sb_key][0]) < _CACHE_TTL_SECONDS:
        _, game_date, events = _SCOREBOARD_CACHE[sb_key]
    else:
        events = []
        game_date = requested_date
        for back in range(3):
            d_try = requested_date - timedelta(days=back)
            sb = requests.get(NBA_SCOREBOARD_URL, params={"dates": d_try.strftime("%Y%m%d")}, timeout=8).json()
            done = [e for e in sb.get("events", []) if e.get("status", {}).get("type", {}).get("state") == "post"]
            if done:
                events = done
                game_date = d_try
                break
        if events:
            _SCOREBOARD_CACHE[sb_key] = (now, game_date, events)

    if not events:
        raise ValueError("No completed NBA games found recently")

    def margin(ev: dict) -> int:
        comps = ev["competitions"][0]["competitors"]
        try:
            return abs(int(comps[0]["score"]) - int(comps[1]["score"]))
        except (ValueError, TypeError, KeyError):
            return 999

    featured_ev = random.choice(events) if pick_random else min(events, key=margin)
    story_key = (game_date.isoformat(), str(featured_ev["id"]))
    if story_key in _STORY_CACHE and (now - _STORY_CACHE[story_key][0]) < _CACHE_TTL_SECONDS:
        return _STORY_CACHE[story_key][1]
    comp = featured_ev["competitions"][0]
    competitors = comp["competitors"]
    home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
    away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[-1])

    home_abbr = home["team"]["abbreviation"]
    away_abbr = away["team"]["abbreviation"]
    home_logo = home["team"].get("logo") or f"https://a.espncdn.com/i/teamlogos/nba/500/{home_abbr.lower()}.png"
    away_logo = away["team"].get("logo") or f"https://a.espncdn.com/i/teamlogos/nba/500/{away_abbr.lower()}.png"
    home_score = int(home.get("score") or 0)
    away_score = int(away.get("score") or 0)
    winner_abbr = home_abbr if home_score >= away_score else away_abbr
    loser_abbr = away_abbr if winner_abbr == home_abbr else home_abbr

    summary = requests.get(NBA_SUMMARY_URL, params={"event": featured_ev["id"]}, timeout=8).json()

    # Downsample winprobability to ~75 points on viewBox 0..300 x 0..100
    wp_raw = summary.get("winprobability", [])
    wp_pts = []
    lead_changes = 0
    prev_fav = None
    min_winner_wp = 100

    for pt in wp_raw:
        h_wp = float(pt.get("homeWinPercentage", 0.5))
        fav = "H" if h_wp >= 0.5 else "A"
        if prev_fav and fav != prev_fav:
            lead_changes += 1
        prev_fav = fav
        w_wp = h_wp if winner_abbr == home_abbr else (1.0 - h_wp)
        min_winner_wp = min(min_winner_wp, round(w_wp * 100))

    if len(wp_raw) >= 2:
        step = max(1, len(wp_raw) // 75)
        sampled = wp_raw[::step]
        if sampled[-1] is not wp_raw[-1]:
            sampled.append(wp_raw[-1])
        n = len(sampled)
        for i, pt in enumerate(sampled):
            h_wp = max(0.0, min(1.0, float(pt.get("homeWinPercentage", 0.5))))
            x = round((i / (n - 1)) * 296 + 2, 1)
            y = round(96 - (h_wp * 92), 1)
            wp_pts.append(f"{x},{y}")

    # Quarter + OT linescores
    away_q = [str(int(q.get("value", 0))) for q in away.get("linescores", [])]
    home_q = [str(int(q.get("value", 0))) for q in home.get("linescores", [])]
    ot_count = max(0, max(len(away_q), len(home_q)) - 4)
    ot_label = "" if ot_count == 0 else ("OT" if ot_count == 1 else f"{ot_count}OT")

    mvp = _team_leader(summary, winner_abbr)
    runner_up = _team_leader(summary, loser_abbr)
    away_shooting = _team_shooting(summary, away_abbr)
    home_shooting = _team_shooting(summary, home_abbr)
    team_compare = _build_team_compare(summary, away_abbr, home_abbr)

    all_q = [int(q) for q in away_q + home_q] or [30]
    max_q = max(all_q) or 30
    quarter_bars = []
    for idx in range(max(len(away_q), len(home_q))):
        a_pts = int(away_q[idx]) if idx < len(away_q) else 0
        h_pts = int(home_q[idx]) if idx < len(home_q) else 0
        q_lbl = f"Q{idx + 1}" if idx < 4 else ("OT" if idx == 4 else f"OT{idx - 3}")
        quarter_bars.append(
            {
                "label": q_lbl,
                "away": a_pts,
                "home": h_pts,
                "away_h": max(3, round(a_pts / max_q * 28)),
                "home_h": max(3, round(h_pts / max_q * 28)),
            }
        )

    wp_polygon = f"2.0,50 {' '.join(wp_pts)} 298.0,50" if wp_pts else ""

    other_finals = []
    for ev in events:
        if ev["id"] == featured_ev["id"]:
            continue
        cs = ev["competitions"][0]["competitors"]
        a = next((c for c in cs if c.get("homeAway") == "away"), cs[-1])
        h = next((c for c in cs if c.get("homeAway") == "home"), cs[0])
        other_finals.append(f"{a['team']['abbreviation']} {a.get('score')} - {h.get('score')} {h['team']['abbreviation']}")

    diff = abs(home_score - away_score)
    if diff <= 5:
        reason = f"THRILLER · {diff}-PT MARGIN"
    else:
        reason = f"{diff}-PT MARGIN"

    result = {
        "title": "NBA Final Whistle",
        "date": game_date.strftime("%b %d, %Y").upper(),
        "reason": reason,
        "matchup": f"{away_abbr} @ {home_abbr}",
        "away_abbr": away_abbr,
        "away_logo": away_logo,
        "away_score": away_score,
        "away_record": (away.get("records") or [{}])[0].get("summary", ""),
        "home_abbr": home_abbr,
        "home_logo": home_logo,
        "home_score": home_score,
        "home_record": (home.get("records") or [{}])[0].get("summary", ""),
        "winner": winner_abbr,
        "away_q": away_q,
        "home_q": home_q,
        "quarter_bars": quarter_bars,
        "ot_label": ot_label,
        "away_shooting": away_shooting,
        "home_shooting": home_shooting,
        "team_compare": team_compare,
        "wp_polyline": " ".join(wp_pts),
        "wp_polygon": wp_polygon,
        "lead_changes": lead_changes,
        "min_winner_wp": min_winner_wp if wp_raw else 50,
        "mvp": mvp,
        "runner_up": runner_up,
        "other_finals": other_finals[:3],
    }
    _STORY_CACHE[story_key] = (now, result)
    return result
