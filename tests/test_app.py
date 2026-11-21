from unittest.mock import patch, MagicMock
import json
import pytest

from app import rate_to_arrow

from app import app
from app import get_aircraft_logo
from app import get_aircraft_logo
from app import get_aircraft_logo
from app import get_aircraft_logo
import builtins
from unittest.mock import mock_open, patch
from app import get_aircraft_model
@pytest.fixture

def test_rate_to_arrow_positive():
    assert rate_to_arrow(100) == '&#9650;'
    assert rate_to_arrow('1') == '&#9650;'
    assert rate_to_arrow(99999) == '&#9650;'

def test_rate_to_arrow_negative():
    assert rate_to_arrow(-1) == '&#9660;'
    assert rate_to_arrow('-100') == '&#9660;'
    assert rate_to_arrow(-99999) == '&#9660;'

def test_rate_to_arrow_zero():
    assert rate_to_arrow(0) == ''
    assert rate_to_arrow('0') == ''

def test_rate_to_arrow_non_integer_string():
    assert rate_to_arrow('abc') == ''

def test_rate_to_arrow_float_string():
    assert rate_to_arrow('1.5') == ''

@patch('app.os.path')
@patch('app.os')
def test_get_aircraft_logo_found(mock_os, mock_path):
    # Setup mocks
    mock_os.path.dirname.return_value = '/fake/dir'
    mock_os.path.join.side_effect = lambda *args: '/'.join(args)
    mock_os.listdir.return_value = ['abc123_logo.png', 'def456_logo.png']
    mock_os.path.isfile.side_effect = lambda path: True

    result = get_aircraft_logo('abc123')
    assert result == 'abc123_logo.png'

@patch('app.os.path')
@patch('app.os')
def test_get_aircraft_logo_case_insensitive(mock_os, mock_path):
    mock_os.path.dirname.return_value = '/fake/dir'
    mock_os.path.join.side_effect = lambda *args: '/'.join(args)
    mock_os.listdir.return_value = ['ABC123_logo.png']
    mock_os.path.isfile.side_effect = lambda path: True

    result = get_aircraft_logo('abc123')
    assert result == 'ABC123_logo.png'

@patch('app.os.path')
@patch('app.os')
def test_get_aircraft_logo_not_found(mock_os, mock_path):
    mock_os.path.dirname.return_value = '/fake/dir'
    mock_os.path.join.side_effect = lambda *args: '/'.join(args)
    mock_os.listdir.return_value = ['xyz789_logo.png']
    mock_os.path.isfile.side_effect = lambda path: True

    result = get_aircraft_logo('abc123')
    assert result is None

@patch('app.os.path')
@patch('app.os')
def test_get_aircraft_logo_empty_dir(mock_os, mock_path):
    mock_os.path.dirname.return_value = '/fake/dir'
    mock_os.path.join.side_effect = lambda *args: '/'.join(args)
    mock_os.listdir.return_value = []
    mock_os.path.isfile.side_effect = lambda path: True

    result = get_aircraft_logo('abc123')
    assert result is None

def test_get_aircraft_model_found():
    mock_csv = "icao,model\nA320,Airbus A320\nB738,Boeing 737-800\n"
    with patch("builtins.open", mock_open(read_data=mock_csv)):
        result = get_aircraft_model("A320")
        assert result == "Airbus A320"

def test_get_aircraft_model_not_found():
    mock_csv = "icao,model\nA320,Airbus A320\nB738,Boeing 737-800\n"
    with patch("builtins.open", mock_open(read_data=mock_csv)):
        result = get_aircraft_model("B777")
        assert result is None

def test_get_aircraft_model_empty_type():
    mock_csv = "icao,model\nA320,Airbus A320\n"
    with patch("builtins.open", mock_open(read_data=mock_csv)):
        result = get_aircraft_model("")
        assert result is None

def test_get_aircraft_model_case_sensitive():
    mock_csv = "icao,model\nA320,Airbus A320\n"
    with patch("builtins.open", mock_open(read_data=mock_csv)):
        result = get_aircraft_model("a320")
        assert result is None  # function is case-sensitive

def test_get_aircraft_model_handles_spaces():
    mock_csv = "icao,model\n A320 , Airbus A320 \n"
    with patch("builtins.open", mock_open(read_data=mock_csv)):
        result = get_aircraft_model("A320")
        assert result == "Airbus A320"


def test_fallback_to_adsb_lol_on_rate_limit():
    from app import _FLIGHT_CACHE, fetch_flight_data_with_status

    _FLIGHT_CACHE.clear()
    fi_resp_429 = MagicMock(status_code=429, text="rate limit exceeded")
    lol_resp = MagicMock(status_code=200)
    lol_resp.json.return_value = {"ac": [{"flight": "UAL123 ", "dst": 4.2, "category": "A3", "r": "N123UA"}]}

    with patch("app.time.sleep") as mock_sleep, patch(
        "app._SESSION.get", side_effect=[fi_resp_429, fi_resp_429, lol_resp]
    ) as mock_get:
        data, err, status = fetch_flight_data_with_status("37.77", "-122.41", "25")

    assert status == 200
    assert err is None
    assert len(data["ac"]) == 1
    assert data["ac"][0]["flight"] == "UAL123 "
    assert mock_get.call_count == 3
    mock_sleep.assert_called_once_with(1.1)


def test_retry_succeeds_after_429():
    from app import _FLIGHT_CACHE, fetch_flight_data_with_status

    _FLIGHT_CACHE.clear()
    fi_resp_429 = MagicMock(status_code=429, text="rate limit exceeded")
    fi_resp_200 = MagicMock(status_code=200)
    fi_resp_200.json.return_value = {"aircraft": [{"flight": "SWA100 ", "dst": 2.5, "category": "A3"}]}

    with patch("app.time.sleep") as mock_sleep, patch(
        "app._SESSION.get", side_effect=[fi_resp_429, fi_resp_200]
    ) as mock_get:
        data, err, status = fetch_flight_data_with_status("37.77", "-122.41", "25")

    assert status == 200
    assert err is None
    assert len(data["ac"]) == 1
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once_with(1.1)


def test_upstream_all_fail_returns_upstream_status_not_404():
    from app import _FLIGHT_CACHE

    _FLIGHT_CACHE.clear()
    resp_429 = MagicMock(status_code=429, text="rate limit exceeded")

    with patch("app.time.sleep"), patch("app._SESSION.get", return_value=resp_429):
        client = app.test_client()
        resp = client.get("/closest_flight?lat=37.77&lon=-122.41&radius=25")

    assert resp.status_code == 429
    assert "No aircraft detected" not in resp.get_json()["error"]


def test_empty_aircraft_list_returns_404():
    from app import _FLIGHT_CACHE

    _FLIGHT_CACHE.clear()
    fi_resp = MagicMock(status_code=200)
    fi_resp.json.return_value = {"aircraft": []}

    with patch("app._SESSION.get", return_value=fi_resp):
        client = app.test_client()
        resp = client.get("/closest_flight?lat=37.77&lon=-122.41&radius=25")

    assert resp.status_code == 404
    assert resp.get_json()["error"] == "No aircraft detected"


def test_closest_flight_fractional_dst_and_registration():
    from app import _FLIGHT_CACHE

    _FLIGHT_CACHE.clear()
    fi_resp = MagicMock(status_code=200)
    fi_resp.json.return_value = {
        "aircraft": [
            {"flight": "FAR999  ", "dst": 9.9, "category": "A3", "r": "N999FF", "t": "B738"},
            {"flight": "NEAR111 ", "dst": 9.1, "category": "A3", "r": "N111NN", "t": "A320"},
        ]
    }

    with patch("app._SESSION.get", return_value=fi_resp), patch("app.get_route_info_json", return_value=None):
        client = app.test_client()
        resp = client.get("/closest_flight?lat=37.77&lon=-122.41&radius=25")
        resp_cached = client.get("/closest_flight?lat=37.77&lon=-122.41&radius=25")

    assert resp.status_code == 200
    assert resp_cached.status_code == 200
    body = resp.get_json()
    assert body["flight"] == "NEAR111"
    assert body["registration"] == "N111NN"


def test_get_closest_flight_prefers_airborne_over_ground():
    from app import get_closest_flight

    data = {
        "ac": [
            {"flight": "GND1", "dst": 1.5, "category": "A3", "alt_baro": "ground"},
            {"flight": "AIR2", "dst": 8.0, "category": "A3", "alt_baro": 4500},
        ]
    }
    chosen = get_closest_flight(data, prefer_airliners=1)
    assert chosen["flight"] == "AIR2"


def test_get_closest_flight_falls_back_to_ground_when_none_airborne():
    from app import get_closest_flight

    data = {
        "ac": [
            {"flight": "GND2", "dst": 5.0, "category": "A3", "alt_baro": "ground"},
            {"flight": "GND1", "dst": 1.5, "category": "A3", "alt_baro": "ground"},
        ]
    }
    chosen = get_closest_flight(data, prefer_airliners=1)
    assert chosen["flight"] == "GND1"


def test_is_route_plausible_accepts_on_corridor_and_rejects_far_off_route():
    from app import is_route_plausible

    # MSP (44.88, -93.22) -> ORD (41.98, -87.90), plane over Wisconsin (43.5, -90.5)
    assert is_route_plausible(44.88, -93.22, 41.98, -87.90, 43.5, -90.5) is True
    # Plane over Los Angeles (33.94, -118.41) cannot plausibly be on MSP -> ORD
    assert is_route_plausible(44.88, -93.22, 41.98, -87.90, 33.94, -118.41) is False


def test_mitre_daily_endpoint():
    client = app.test_client()
    resp = client.get("/mitre/daily?date=2026-11-20")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["title"] == "MITRE ATT&CK Daily"
    assert len(body["tactics"]) == 14
    assert sum(1 for t in body["tactics"] if t["active"]) == 1
    assert body["technique_id"].startswith("T")
    assert body["detection"]
    assert body["mitigation"]


def test_isc_daily_endpoint():
    import sans_isc

    sans_isc._CACHE["data"] = None
    sans_isc._CACHE["ts"] = 0.0

    def fake_get(url, headers=None, timeout=6):
        resp = MagicMock(status_code=200)
        resp.raise_for_status.return_value = None
        if "infocon" in url:
            resp.json.return_value = {"status": "green"}
        else:
            resp.json.return_value = [
                {"targetport": "445", "records": "1200000", "targets": "85000", "sources": "14000"},
                {"targetport": "22", "records": "600000", "targets": "45000", "sources": "9000"},
            ]
        return resp

    with patch("sans_isc.requests.get", side_effect=fake_get):
        client = app.test_client()
        resp = client.get("/isc/daily")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["infocon"] == "GREEN"
    assert body["top_port"]["port"] == 445
    assert body["top_port"]["service"] == "SMB"
    assert body["top_ports"][0]["bar_pct"] == 100
    assert body["top_ports"][1]["service"] == "SSH"
    assert body["top_ports"][1]["bar_pct"] == 50


def test_nba_story_picks_randomly_from_completed_games():
    import nba_game_story

    nba_game_story._SCOREBOARD_CACHE.clear()
    nba_game_story._STORY_CACHE.clear()

    sb_payload = {
        "events": [
            {
                "id": "101",
                "status": {"type": {"state": "post"}},
                "competitions": [
                    {
                        "competitors": [
                            {"homeAway": "home", "score": "110", "team": {"abbreviation": "BOS"}, "records": [{"summary": "10-2"}], "linescores": []},
                            {"homeAway": "away", "score": "108", "team": {"abbreviation": "NYK"}, "records": [{"summary": "8-4"}], "linescores": []},
                        ]
                    }
                ],
            },
            {
                "id": "102",
                "status": {"type": {"state": "post"}},
                "competitions": [
                    {
                        "competitors": [
                            {"homeAway": "home", "score": "120", "team": {"abbreviation": "LAL"}, "records": [{"summary": "9-3"}], "linescores": []},
                            {"homeAway": "away", "score": "100", "team": {"abbreviation": "PHX"}, "records": [{"summary": "7-5"}], "linescores": []},
                        ]
                    }
                ],
            },
        ]
    }

    def fake_get(url, params=None, timeout=8):
        resp = MagicMock(status_code=200)
        if "scoreboard" in url:
            resp.json.return_value = sb_payload
        else:
            resp.json.return_value = {"winprobability": [], "boxscore": {"players": []}}
        return resp

    with patch("nba_game_story.requests.get", side_effect=fake_get), patch(
        "nba_game_story.random.choice", side_effect=lambda seq: seq[1]
    ):
        client = app.test_client()
        resp = client.get("/nba/story?date=2026-11-20")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["matchup"] == "PHX @ LAL"
    assert body["winner"] == "LAL"


def test_nfl_story_picks_randomly_from_completed_games():
    import nfl_game_story

    nfl_game_story._SCOREBOARD_CACHE.clear()
    nfl_game_story._STORY_CACHE.clear()

    sb_payload = {
        "events": [
            {
                "id": "201",
                "status": {"type": {"state": "post"}},
                "competitions": [
                    {
                        "competitors": [
                            {"homeAway": "home", "score": "27", "team": {"abbreviation": "KC"}, "records": [{"summary": "9-1"}], "linescores": [{"value": 7}, {"value": 10}, {"value": 3}, {"value": 7}]},
                            {"homeAway": "away", "score": "24", "team": {"abbreviation": "BUF"}, "records": [{"summary": "8-2"}], "linescores": [{"value": 7}, {"value": 7}, {"value": 7}, {"value": 3}]},
                        ]
                    }
                ],
            },
        ]
    }

    def fake_get(url, params=None, timeout=8):
        resp = MagicMock(status_code=200)
        if "scoreboard" in url:
            resp.json.return_value = sb_payload
        else:
            resp.json.return_value = {"winprobability": [], "boxscore": {"teams": [], "players": []}}
        return resp

    with patch("nfl_game_story.requests.get", side_effect=fake_get):
        client = app.test_client()
        resp = client.get("/nfl/story?date=2026-11-20")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["title"] == "NFL Final Whistle"
    assert body["matchup"] == "BUF @ KC"
    assert body["winner"] == "KC"
    assert len(body["quarter_bars"]) == 4


def test_museum_daily_uses_cleveland_open_access():
    import museum_daily

    museum_daily._CACHE["items"] = []
    museum_daily._CACHE["ts"] = 0.0

    cma_resp = MagicMock(status_code=200)
    cma_resp.raise_for_status.return_value = None
    cma_resp.json.return_value = {
        "data": [
            {
                "id": 94979,
                "title": "Nathaniel Hurd",
                "creation_date": "c. 1765",
                "creation_date_latest": 1770,
                "technique": "oil on canvas",
                "measurements": "Unframed: 76.2 x 64.8 cm (30 x 25 1/2 in.)",
                "department": "American Painting and Sculpture",
                "current_location": "204",
                "creditline": "Gift of the John Huntington Art and Polytechnic Trust",
                "creators": [{"description": "John Singleton Copley (American, 1738–1815)"}],
                "images": {"web": {"url": "https://openaccess-cdn.clevelandart.org/1915.534/1915.534_web.jpg"}},
            }
        ]
    }

    with patch("museum_daily.requests.get", return_value=cma_resp):
        client = app.test_client()
        resp = client.get("/museum/daily?date=2026-11-20")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["artwork_title"] == "Nathaniel Hurd"
    assert body["artist"] == "John Singleton Copley"
    assert body["artist_bio"] == "American, 1738–1815"
    assert body["image_url"].startswith("https://openaccess-cdn.clevelandart.org/")


def test_stoic_daily_endpoint():
    client = app.test_client()
    resp = client.get("/stoic/daily?date=2026-11-21&lat=44.97&lon=-93.26")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["title"] == "Stoic Sundial"
    assert len(body["weeks"]) == 52
    assert sum(1 for w in body["weeks"] if w["state"] == "current") == 1
    assert body["quote"]
    assert body["challenge"]


def test_build_route_map_projects_coastlines_and_arc():
    from route_map import build_route_map

    rm = build_route_map(44.88, -93.22, 33.68, -117.87, 41.2, -101.5, track_deg=245.0, progress_pct=35.0)
    assert rm is not None
    assert len(rm["land_paths"]) >= 1
    assert rm["flown_path"].startswith("M ")
    assert rm["rem_path"].startswith("M ")
    assert rm["plane_angle"] == 155.0


def test_retro_random_endpoint():
    client = app.test_client()
    resp = client.get("/retro/random?seed=42")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["title"] == "Retro Game Showcase"
    assert body["image_url"].startswith("https://raw.githubusercontent.com/libretro-thumbnails/")
    assert body["platform"]
    assert body["trivia"]


