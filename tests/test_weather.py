from datetime import date
from urllib.error import URLError

import pytest

from jarvis.weather import (
    FORECAST_URL,
    GEOCODING_URL,
    WeatherCityNotConfiguredError,
    WeatherLocationNotFoundError,
    WeatherService,
    WeatherUnavailableError,
    describe_forecast,
)


def test_weather_service_resolves_city_and_reads_tomorrow() -> None:
    requests: list[tuple[str, dict[str, str]]] = []

    def fetch(url: str, parameters: dict[str, str], _timeout: float) -> dict:
        requests.append((url, parameters))
        if url == GEOCODING_URL:
            return {
                "results": [
                    {"name": "Berlin", "country": "Deutschland", "latitude": 52.52, "longitude": 13.41}
                ]
            }
        return {
            "daily": {
                "time": ["2026-08-27", "2026-08-28"],
                "weather_code": [0, 61],
                "temperature_2m_min": [12.0, 15.0],
                "temperature_2m_max": [24.0, 21.0],
            }
        }

    forecast = WeatherService(fetch_json=fetch).get_daily_forecast("Berlin", 1)

    assert forecast.forecast_date == date(2026, 8, 28)
    assert forecast.maximum_celsius == 21.0
    assert requests[0][0] == GEOCODING_URL
    assert requests[1][0] == FORECAST_URL
    assert requests[1][1]["timezone"] == "auto"
    assert describe_forecast(forecast, "morgen") == (
        "Morgen wird es in Berlin, Deutschland leicht regnerisch, bei 15 bis 21 Grad."
    )


def test_weather_retries_with_city_name_when_postal_code_has_no_match() -> None:
    searched_names: list[str] = []

    def fetch(url: str, parameters: dict[str, str], _timeout: float) -> dict:
        if url == GEOCODING_URL:
            searched_names.append(parameters["name"])
            if parameters["name"] == "Berlin, 10115":
                return {"results": []}
            return {
                "results": [
                    {"name": "Berlin", "country": "Deutschland", "latitude": 52.52, "longitude": 13.405}
                ]
            }
        return {
            "daily": {
                "time": ["2026-08-27", "2026-08-28"],
                "weather_code": [3, 2],
                "temperature_2m_min": [10.0, 12.0],
                "temperature_2m_max": [20.0, 22.0],
            }
        }

    forecast = WeatherService(fetch_json=fetch).get_daily_forecast("Berlin, 10115", 1)

    assert searched_names == ["Berlin, 10115", "Berlin"]
    assert forecast.city == "Berlin"


def test_weather_requires_configured_city() -> None:
    with pytest.raises(WeatherCityNotConfiguredError):
        WeatherService().get_daily_forecast(None, 0)


def test_weather_reports_unknown_city() -> None:
    service = WeatherService(fetch_json=lambda *_args: {"results": []})

    with pytest.raises(WeatherLocationNotFoundError):
        service.get_daily_forecast("Unbekannt", 0)


def test_weather_wraps_network_error() -> None:
    def failing_fetch(*_args: object) -> dict:
        raise URLError("offline")

    with pytest.raises(WeatherUnavailableError):
        WeatherService(fetch_json=failing_fetch).get_daily_forecast("Berlin", 0)
