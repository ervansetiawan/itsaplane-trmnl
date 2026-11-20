"""Museum Masterpiece of the Day backed by the Art Institute of Chicago public API."""

from datetime import date
import time
import requests

ARTIC_SEARCH_URL = "https://api.artic.edu/api/v1/artworks/search"
ARTIC_IIIF_URL = "https://www.artic.edu/iiif/2/{image_id}/full/843,/0/default.jpg"
HEADERS = {"User-Agent": "TRMNL-Museum-Masterpiece/1.0", "Accept": "application/json"}

_CACHE: dict = {"ts": 0.0, "items": None}
_CACHE_TTL_SECONDS = 21600  # 6 hours


def _load_catalog() -> list[dict]:
    now = time.time()
    if _CACHE["items"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL_SECONDS:
        return _CACHE["items"]

    resp = requests.get(
        ARTIC_SEARCH_URL,
        params={
            "query[term][is_public_domain]": "true",
            "fields": "id,title,artist_display,date_display,medium_display,image_id",
            "limit": 100,
        },
        headers=HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    raw = resp.json().get("data", [])
    items = [x for x in raw if x.get("image_id") and x.get("title")]
    _CACHE["ts"] = now
    _CACHE["items"] = items
    return items


def _clean(text: str | None, limit: int = 80) -> str:
    s = " ".join((text or "").split())
    if len(s) > limit:
        s = s[: limit - 3].rstrip() + "..."
    return s


def fetch_daily_masterpiece(target_date: date | None = None) -> dict:
    d = target_date or date.today()
    items = _load_catalog()
    if not items:
        raise ValueError("No public domain artworks found")

    art = items[d.toordinal() % len(items)]
    image_id = art["image_id"]

    return {
        "title": "Museum Masterpiece",
        "artwork_title": _clean(art.get("title"), 70),
        "artist": _clean(art.get("artist_display"), 70),
        "year": _clean(art.get("date_display"), 35),
        "medium": _clean(art.get("medium_display"), 65),
        "image_url": ARTIC_IIIF_URL.format(image_id=image_id),
        "museum": "Art Institute of Chicago",
        "date": d.strftime("%b %d, %Y").upper(),
    }
