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


