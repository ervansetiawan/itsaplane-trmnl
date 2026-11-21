"""NFL Final Whistle: Random Post-Game Recap, Win-Probability Curve & Box Score."""

from datetime import date, timedelta
import random
import time
import requests

NFL_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
NFL_SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary"

_SCOREBOARD_CACHE: dict[str, tuple[float, date, list[dict]]] = {}
_STORY_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_CACHE_TTL_SECONDS = 900


def _team_stats_map(summary: dict, team_abbr: str) -> dict[str, str]:
    for tb in summary.get("boxscore", {}).get("teams", []):
        if tb.get("team", {}).get("abbreviation") == team_abbr:
            return {
                s.get("name"): str(s.get("displayValue", ""))
                for s in tb.get("statistics", [])
                if s.get("name")
            }
    return {}


def _build_team_compare(summary: dict, away_abbr: str, home_abbr: str) -> list[dict]:
    a_stats = _team_stats_map(summary, away_abbr)
    h_stats = _team_stats_map(summary, home_abbr)
    if not a_stats or not h_stats:
        return []
    specs = [
        ("YDS", "totalYards"),
        ("PASS", "netPassingYards"),
        ("RUSH", "rushingYards"),
        ("TO", "turnovers"),
    ]
    rows = []
    for label, key in specs:
        try:
            a_val = float(a_stats.get(key, 0) or 0)
            h_val = float(h_stats.get(key, 0) or 0)
        except (ValueError, TypeError):
            continue
        total = a_val + h_val
        a_pct = 50 if total <= 0 else max(12, min(88, round(a_val / total * 100)))
        rows.append(
            {
                "label": label,
                "away_val": str(int(round(a_val))),
                "home_val": str(int(round(h_val))),
                "away_pct": a_pct,
                "home_pct": 100 - a_pct,
            }
        )
    return rows


def _team_top_leader(summary: dict, team_abbr: str) -> dict | None:
    """Picks the standout offensive leader (from summary.leaders, with boxscore fallback)."""
    for grp in summary.get("leaders", []):
        if grp.get("team", {}).get("abbreviation") != team_abbr:
            continue
        best = None
        for cat in grp.get("leaders", []):
            cname = cat.get("name", "")
            if cname not in ("passingYards", "rushingYards", "receivingYards"):
                continue
            top_list = cat.get("leaders") or []
            if not top_list:
                continue
            top = top_list[0]
            try:
                val = float(top.get("value") or 0)
            except (ValueError, TypeError):
                val = 0.0
            score = val if cname == "passingYards" else val * 1.6
            if best is None or score > best["_score"]:
                best = {
                    "name": top.get("athlete", {}).get("shortName", ""),
                    "team": team_abbr,
                    "line": top.get("displayValue", ""),
                    "_score": score,
                }
        if best:
            best.pop("_score", None)
            return best

    best = None
    for tb in summary.get("boxscore", {}).get("players", []):
        if tb.get("team", {}).get("abbreviation") != team_abbr:
            continue
        for sg in tb.get("statistics", []):
            cat = (sg.get("name") or "").lower()
            if cat not in ("passing", "rushing", "receiving"):
                continue
            names = sg.get("names") or []
            if "YDS" not in names:
                continue
            yds_i = names.index("YDS")
            td_i = names.index("TD") if "TD" in names else None
            c_att_i = names.index("C/ATT") if "C/ATT" in names else None
            car_i = names.index("CAR") if "CAR" in names else None
            rec_i = names.index("REC") if "REC" in names else None
            for ath in sg.get("athletes", []):
                st = ath.get("stats", [])
                if len(st) <= yds_i:
                    continue
                try:
                    yds = int(float(st[yds_i]))
                except (ValueError, TypeError):
                    continue
                tds = st[td_i] if td_i is not None and len(st) > td_i else "0"
                if cat == "passing":
                    extra = f"{st[c_att_i]} · " if c_att_i is not None and len(st) > c_att_i else ""
                    line = f"{extra}{yds} PASS YDS · {tds} TD"
                    score = yds + int(tds or 0) * 25 if str(tds).isdigit() else yds
                elif cat == "rushing":
                    car = st[car_i] if car_i is not None and len(st) > car_i else ""
                    extra = f"{car} CAR · " if car else ""
                    line = f"{extra}{yds} RUSH YDS · {tds} TD"
                    score = yds * 1.4 + (int(tds or 0) * 30 if str(tds).isdigit() else 0)
                else:
                    rec = st[rec_i] if rec_i is not None and len(st) > rec_i else ""
                    extra = f"{rec} REC · " if rec else ""
                    line = f"{extra}{yds} REC YDS · {tds} TD"
                    score = yds * 1.4 + (int(tds or 0) * 30 if str(tds).isdigit() else 0)

                if best is None or score > best["_score"]:
                    best = {
                        "name": ath.get("athlete", {}).get("shortName", ""),
                        "team": team_abbr,
                        "line": line,
                        "_score": score,
                    }
    if best:
        best.pop("_score", None)
    return best


def fetch_nfl_game_story(target_date: date | None = None, pick_random: bool = True) -> dict:
    requested_date = target_date or date.today()
    sb_key = requested_date.isoformat() if target_date else "latest"
    now = time.time()

    if sb_key in _SCOREBOARD_CACHE and (now - _SCOREBOARD_CACHE[sb_key][0]) < _CACHE_TTL_SECONDS:
        _, game_date, events = _SCOREBOARD_CACHE[sb_key]
    else:
        events = []
        game_date = requested_date
        if target_date is None:
            sb = requests.get(NFL_SCOREBOARD_URL, timeout=8).json()
            done = [e for e in sb.get("events", []) if e.get("status", {}).get("type", {}).get("state") == "post"]
            if done:
                events = done
        if not events:
            for back in range(7):
                d_try = requested_date - timedelta(days=back)
                sb = requests.get(NFL_SCOREBOARD_URL, params={"dates": d_try.strftime("%Y%m%d")}, timeout=8).json()
                done = [e for e in sb.get("events", []) if e.get("status", {}).get("type", {}).get("state") == "post"]
                if done:
                    events = done
                    game_date = d_try
                    break
        if events:
            _SCOREBOARD_CACHE[sb_key] = (now, game_date, events)

    if not events:
        raise ValueError("No completed NFL games found recently")

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
    home_logo = home["team"].get("logo") or f"https://a.espncdn.com/i/teamlogos/nfl/500/{home_abbr.lower()}.png"
    away_logo = away["team"].get("logo") or f"https://a.espncdn.com/i/teamlogos/nfl/500/{away_abbr.lower()}.png"
    home_score = int(home.get("score") or 0)
    away_score = int(away.get("score") or 0)
    winner_abbr = home_abbr if home_score >= away_score else away_abbr
    loser_abbr = away_abbr if winner_abbr == home_abbr else home_abbr

    summary = requests.get(NFL_SUMMARY_URL, params={"event": featured_ev["id"]}, timeout=8).json()

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

    away_q = [str(int(q.get("value", 0))) for q in away.get("linescores", [])]
    home_q = [str(int(q.get("value", 0))) for q in home.get("linescores", [])]
    ot_count = max(0, max(len(away_q), len(home_q)) - 4)
    ot_label = "" if ot_count == 0 else ("OT" if ot_count == 1 else f"{ot_count}OT")

    mvp = _team_top_leader(summary, winner_abbr)
    runner_up = _team_top_leader(summary, loser_abbr)
    team_compare = _build_team_compare(summary, away_abbr, home_abbr)

    all_q = [int(q) for q in away_q + home_q] or [14]
    max_q = max(all_q) or 14
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

    other_finals = []
    for ev in events:
        if ev["id"] == featured_ev["id"]:
            continue
        cs = ev["competitions"][0]["competitors"]
        a = next((c for c in cs if c.get("homeAway") == "away"), cs[-1])
        h = next((c for c in cs if c.get("homeAway") == "home"), cs[0])
        other_finals.append(f"{a['team']['abbreviation']} {a.get('score')} - {h.get('score')} {h['team']['abbreviation']}")

    diff = abs(home_score - away_score)
    reason = f"THRILLER · {diff}-PT MARGIN" if diff <= 7 else f"{diff}-PT MARGIN"
    wp_polygon = f"2.0,50 {' '.join(wp_pts)} 298.0,50" if wp_pts else ""

    result = {
        "title": "NFL Final Whistle",
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
