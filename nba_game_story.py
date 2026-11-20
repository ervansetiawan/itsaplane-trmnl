"""Yesterday's NBA Game Story: Win-Probability Curve, Linescore & MVP."""

from datetime import date, timedelta
import time
import requests

NBA_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
NBA_SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL_SECONDS = 900


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
                    }
    return best


def fetch_nba_game_story(target_date: date | None = None) -> dict:
    # Default to yesterday's slate
    game_date = target_date or (date.today() - timedelta(days=1))
    cache_key = game_date.isoformat()
    now = time.time()
    if cache_key in _CACHE and (now - _CACHE[cache_key][0]) < _CACHE_TTL_SECONDS:
        return _CACHE[cache_key][1]

    events = []
    for back in range(3):
        d_try = game_date - timedelta(days=back)
        sb = requests.get(NBA_SCOREBOARD_URL, params={"dates": d_try.strftime("%Y%m%d")}, timeout=8).json()
        done = [e for e in sb.get("events", []) if e.get("status", {}).get("type", {}).get("state") == "post"]
        if done:
            events = done
            game_date = d_try
            break

    if not events:
        raise ValueError("No completed NBA games found recently")

    # Pick closest margin game as featured story
    def margin(ev: dict) -> int:
        comps = ev["competitions"][0]["competitors"]
        try:
            return abs(int(comps[0]["score"]) - int(comps[1]["score"]))
        except (ValueError, TypeError, KeyError):
            return 999

    featured_ev = min(events, key=margin)
    comp = featured_ev["competitions"][0]
    competitors = comp["competitors"]
    home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
    away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[-1])

    home_abbr = home["team"]["abbreviation"]
    away_abbr = away["team"]["abbreviation"]
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

    # Quarter linescores
    away_q = [str(int(q.get("value", 0))) for q in away.get("linescores", [])][:4]
    home_q = [str(int(q.get("value", 0))) for q in home.get("linescores", [])][:4]

    mvp = _team_leader(summary, winner_abbr)
    runner_up = _team_leader(summary, loser_abbr)

    other_finals = []
    for ev in events:
        if ev["id"] == featured_ev["id"]:
            continue
        cs = ev["competitions"][0]["competitors"]
        a = next((c for c in cs if c.get("homeAway") == "away"), cs[-1])
        h = next((c for c in cs if c.get("homeAway") == "home"), cs[0])
        other_finals.append(f"{a['team']['abbreviation']} {a.get('score')} - {h.get('score')} {h['team']['abbreviation']}")

    result = {
        "title": "NBA Game Story",
        "date": game_date.strftime("%b %d, %Y").upper(),
        "matchup": f"{away_abbr} @ {home_abbr}",
        "away_abbr": away_abbr,
        "away_score": away_score,
        "away_record": (away.get("records") or [{}])[0].get("summary", ""),
        "home_abbr": home_abbr,
        "home_score": home_score,
        "home_record": (home.get("records") or [{}])[0].get("summary", ""),
        "winner": winner_abbr,
        "away_q": away_q,
        "home_q": home_q,
        "wp_polyline": " ".join(wp_pts),
        "lead_changes": lead_changes,
        "min_winner_wp": min_winner_wp if wp_raw else 50,
        "mvp": mvp,
        "runner_up": runner_up,
        "other_finals": other_finals[:3],
    }
    _CACHE[cache_key] = (now, result)
    return result
