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
    with pytest.raises(ValueError):
        rate_to_arrow('abc')

def test_rate_to_arrow_float_string():
    # Should raise ValueError because int('1.5') is invalid
    with pytest.raises(ValueError):
        rate_to_arrow('1.5')

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


def test_fallback_to_adsb_fi_on_rate_limit():
    import requests as req
    from app import _FLIGHT_CACHE, fetch_flight_data_with_status

    _FLIGHT_CACHE.clear()
    lol_resp = MagicMock(status_code=429, text="rate limit exceeded")
    fi_resp = MagicMock(status_code=200)
    fi_resp.json.return_value = {"aircraft": [{"flight": "UAL123 ", "dst": 4.2, "category": "A3", "r": "N123UA"}]}

    with patch("app._SESSION.get", side_effect=[lol_resp, fi_resp]) as mock_get:
        data, err, status = fetch_flight_data_with_status("37.77", "-122.41", "25")

    assert status == 200
    assert err is None
    assert len(data["ac"]) == 1
    assert data["ac"][0]["flight"] == "UAL123 "
    assert mock_get.call_count == 2


def test_upstream_all_fail_returns_upstream_status_not_404():
    from app import _FLIGHT_CACHE

    _FLIGHT_CACHE.clear()
    lol_resp = MagicMock(status_code=429, text="rate limit exceeded")
    fi_resp = MagicMock(status_code=429, text="rate limit exceeded")

    with patch("app._SESSION.get", side_effect=[lol_resp, fi_resp]):
        client = app.test_client()
        resp = client.get("/closest_flight?lat=37.77&lon=-122.41&radius=25")

    assert resp.status_code == 429
    assert "No aircraft detected" not in resp.get_json()["error"]


def test_empty_aircraft_list_returns_404():
    from app import _FLIGHT_CACHE

    _FLIGHT_CACHE.clear()
    lol_resp = MagicMock(status_code=200)
    lol_resp.json.return_value = {"ac": []}

    with patch("app._SESSION.get", return_value=lol_resp):
        client = app.test_client()
        resp = client.get("/closest_flight?lat=37.77&lon=-122.41&radius=25")

    assert resp.status_code == 404
    assert resp.get_json()["error"] == "No aircraft detected"


def test_closest_flight_fractional_dst_and_registration():
    from app import _FLIGHT_CACHE

    _FLIGHT_CACHE.clear()
    lol_resp = MagicMock(status_code=200)
    lol_resp.json.return_value = {
        "ac": [
            {"flight": "FAR999  ", "dst": 9.9, "category": "A3", "r": "N999FF", "t": "B738"},
            {"flight": "NEAR111 ", "dst": 9.1, "category": "A3", "r": "N111NN", "t": "A320"},
        ]
    }

    with patch("app._SESSION.get", return_value=lol_resp), patch("app.get_route_info_json", return_value=None):
        client = app.test_client()
        resp = client.get("/closest_flight?lat=37.77&lon=-122.41&radius=25")
        resp_cached = client.get("/closest_flight?lat=37.77&lon=-122.41&radius=25")

    assert resp.status_code == 200
    assert resp_cached.status_code == 200
    body = resp.get_json()
    assert body["flight"] == "NEAR111"
    assert body["registration"] == "N111NN"


