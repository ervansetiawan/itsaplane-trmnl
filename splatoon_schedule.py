"""Live Splatoon 3 Stage & Salmon Run Schedule backed by splatoon3.ink."""

from datetime import datetime, timezone
import time
import requests

SPLAT_SCHEDULES_URL = "https://splatoon3.ink/data/schedules.json"
_HEADERS = {"User-Agent": "itsaplane-trmnl/1.0 (https://github.com/ervansetiawan/itsaplane-trmnl)"}
_CACHE: dict = {"ts": 0.0, "data": None}
_CACHE_TTL_SECONDS = 1800


def _fmt_window(start_iso: str | None, end_iso: str | None) -> str:
    if not start_iso or not end_iso:
        return ""
    try:
        s = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        return f"{s.strftime('%H:%M')}–{e.strftime('%H:%M')} UTC"
    except ValueError:
        return ""


def _parse_match(node: dict | None, key: str) -> dict | None:
    if not node:
        return None
    setting = node.get(key) or {}
    stages = [
        {
            "name": s.get("name", ""),
            "image_url": (s.get("image") or {}).get("url", ""),
        }
        for s in (setting.get("vsStages") or [])[:2]
    ]
    if not stages:
        return None
    return {
        "rule": (setting.get("vsRule") or {}).get("name", "Turf War"),
        "window": _fmt_window(node.get("startTime"), node.get("endTime")),
        "stages": stages,
    }


def fetch_splatoon_schedule() -> dict:
    """Fetches current Splatoon 3 Turf War, Anarchy, and Salmon Run rotations."""
    now = time.time()
    if _CACHE["data"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL_SECONDS:
        raw = _CACHE["data"]
    else:
        try:
            resp = requests.get(SPLAT_SCHEDULES_URL, headers=_HEADERS, timeout=8)
            resp.raise_for_status()
            raw = resp.json().get("data", {})
            _CACHE["ts"] = now
            _CACHE["data"] = raw
        except requests.RequestException:
            if _CACHE["data"] is not None:
                raw = _CACHE["data"]
            else:
                raise

    reg_nodes = (raw.get("regularSchedules") or {}).get("nodes") or []
    bankara_nodes = (raw.get("bankaraSchedules") or {}).get("nodes") or []
    coop_nodes = ((raw.get("coopGroupingSchedule") or {}).get("regularSchedules") or {}).get("nodes") or []

    turf = _parse_match(reg_nodes[0] if reg_nodes else None, "regularMatchSetting")

    series = None
    open_match = None
    if bankara_nodes:
        for ms in bankara_nodes[0].get("bankaraMatchSettings") or []:
            mode = (ms.get("bankaraMode") or "").upper()
            parsed = {
                "rule": (ms.get("vsRule") or {}).get("name", ""),
                "window": _fmt_window(bankara_nodes[0].get("startTime"), bankara_nodes[0].get("endTime")),
                "stages": [
                    {"name": s.get("name", ""), "image_url": (s.get("image") or {}).get("url", "")}
                    for s in (ms.get("vsStages") or [])[:2]
                ],
            }
            if mode == "CHALLENGE" and series is None:
                series = parsed
            elif mode == "OPEN" and open_match is None:
                open_match = parsed

    salmon = None
    if coop_nodes:
        cs = coop_nodes[0].get("setting") or {}
        stage = cs.get("coopStage") or {}
        boss = (cs.get("boss") or {}).get("name", "")
        weapons = [w.get("name", "") for w in (cs.get("weapons") or []) if w.get("name")]
        salmon = {
            "stage": stage.get("name", ""),
            "image_url": (stage.get("thumbnailImage") or stage.get("image") or {}).get("url", ""),
            "boss": boss,
            "weapons": weapons[:4],
            "window": _fmt_window(coop_nodes[0].get("startTime"), coop_nodes[0].get("endTime")),
        }

    return {
        "title": "Splatoon 3 Schedule",
        "date": datetime.now(timezone.utc).strftime("%b %d · %H:%M UTC").upper(),
        "turf": turf,
        "series": series,
        "open": open_match,
        "salmon": salmon,
    }
