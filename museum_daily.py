"""Museum Masterpiece of the Day backed by The Metropolitan Museum of Art Open Access API."""

from datetime import date
import requests

MET_OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"

# Verified Met Open Access public-domain masterpieces with primaryImageSmall URLs
MET_MASTERPIECE_IDS = [
    436535, 436528, 436532, 437853, 437329, 436121, 436105, 437984, 436965, 436838,
    436524, 438817, 436102, 436106, 437430, 436819, 435809, 435882, 436575, 437490,
    436947, 437056, 437869, 436455, 436622, 436504, 437153, 436037, 11417, 10497,
    36131, 459106, 459080,
]

_CACHE: dict[int, dict] = {}


def _clean(text: str | None, limit: int = 80) -> str:
    s = " ".join((text or "").split())
    if len(s) > limit:
        s = s[: limit - 3].rstrip() + "..."
    return s


def fetch_daily_masterpiece(target_date: date | None = None) -> dict:
    d = target_date or date.today()
    object_id = MET_MASTERPIECE_IDS[d.toordinal() % len(MET_MASTERPIECE_IDS)]

    if object_id in _CACHE:
        art = _CACHE[object_id]
    else:
        resp = requests.get(MET_OBJECT_URL.format(object_id=object_id), timeout=8)
        resp.raise_for_status()
        art = resp.json()
        _CACHE[object_id] = art

    image_url = art.get("primaryImageSmall") or art.get("primaryImage") or ""
    if not image_url:
        raise ValueError(f"No image URL for Met object {object_id}")

    return {
        "title": "Museum Masterpiece",
        "artwork_title": _clean(art.get("title"), 70),
        "artist": _clean(art.get("artistDisplayName") or art.get("culture") or "Unknown Artist", 70),
        "year": _clean(art.get("objectDate") or "Public Domain", 35),
        "medium": _clean(art.get("medium"), 65),
        "image_url": image_url,
        "museum": "The Metropolitan Museum of Art",
        "date": d.strftime("%b %d, %Y").upper(),
    }
