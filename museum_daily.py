"""Museum Masterpiece of the Day backed by The Cleveland Museum of Art Open Access API."""

from datetime import date
import re
import time
import requests

CMA_API_URL = "https://openaccess-api.clevelandart.org/api/artworks/"
_CACHE: dict = {"ts": 0.0, "items": []}
_CACHE_TTL_SECONDS = 86400


def _clean(text: str | None, limit: int = 80) -> str:
    s = " ".join((text or "").split())
    if len(s) > limit:
        s = s[: limit - 3].rstrip() + "..."
    return s


def _parse_creator(creators: list[dict] | None) -> tuple[str, str]:
    if not creators:
        return "Unknown Artist", ""
    desc = " ".join((creators[0].get("description") or "").split())
    if "(" in desc and desc.endswith(")"):
        name_part, bio_part = desc.split("(", 1)
        return _clean(name_part, 70), _clean(bio_part[:-1], 75)
    return _clean(desc or "Unknown Artist", 70), ""


def _load_catalog() -> list[dict]:
    now = time.time()
    if _CACHE["items"] and (now - _CACHE["ts"]) < _CACHE_TTL_SECONDS:
        return _CACHE["items"]

    try:
        resp = requests.get(
            CMA_API_URL,
            params={"has_image": 1, "cc0": 1, "type": "Painting", "limit": 50},
            timeout=10,
        )
        resp.raise_for_status()
        items = [
            a for a in resp.json().get("data", [])
            if (a.get("images") or {}).get("web", {}).get("url")
        ]
    except requests.RequestException:
        if _CACHE["items"]:
            return _CACHE["items"]
        raise
    if not items:
        raise ValueError("No artworks with images returned from Cleveland Museum of Art")
    _CACHE["ts"] = now
    _CACHE["items"] = items
    return items


def fetch_daily_masterpiece(target_date: date | None = None) -> dict:
    d = target_date or date.today()
    items = _load_catalog()
    art = items[d.toordinal() % len(items)]

    image_url = art["images"]["web"]["url"]
    artist, artist_bio = _parse_creator(art.get("creators"))

    raw_year = art.get("creation_date_latest") or art.get("creation_date_earliest")
    if not isinstance(raw_year, (int, float)):
        m = re.search(r"(\d{4})", str(art.get("creation_date") or ""))
        raw_year = int(m.group(1)) if m else None

    timeline_x = None
    if isinstance(raw_year, (int, float)) and raw_year > 0:
        clamped = max(1400, min(2000, int(raw_year)))
        timeline_x = round(10 + ((clamped - 1400) / 600) * 180)

    dims = _clean((art.get("measurements") or "").split(";", 1)[0], 55)
    medium = _clean((art.get("technique") or "").capitalize(), 65)

    return {
        "title": "Museum Masterpiece",
        "artwork_title": _clean(art.get("title"), 70),
        "artist": artist,
        "artist_bio": artist_bio,
        "year": _clean(art.get("creation_date") or "Public Domain", 35),
        "timeline_x": timeline_x,
        "medium": medium,
        "dimensions": dims,
        "department": _clean(art.get("department"), 45),
        "gallery": _clean(art.get("current_location"), 20),
        "credit_line": _clean(art.get("creditline"), 90),
        "object_id": art.get("id"),
        "image_url": image_url,
        "museum": "The Cleveland Museum of Art",
        "date": d.strftime("%b %d, %Y").upper(),
    }
