"""Kostenlose Wetterabfrage über die öffentliche Open-Meteo-API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherError(RuntimeError):
    """Die Wetterdaten sind nicht nutzbar."""


class WeatherCityNotConfiguredError(WeatherError):
    """Es wurde keine Standardstadt angegeben."""


class WeatherLocationNotFoundError(WeatherError):
    """Die konfigurierte Stadt konnte nicht gefunden werden."""


class WeatherUnavailableError(WeatherError):
    """Die öffentliche Wetterquelle ist aktuell nicht erreichbar."""


@dataclass(frozen=True)
class DailyForecast:
    city: str
    country: str
    forecast_date: date
    weather_code: int
    minimum_celsius: float
    maximum_celsius: float


class WeatherService:
    """Löst eine Stadt auf und ruft die Tagesvorhersage ohne API-Schlüssel ab."""

    def __init__(
        self,
        fetch_json: Callable[[str, dict[str, str], float], dict[str, Any]] | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._fetch_json = fetch_json or _fetch_json
        self._timeout_seconds = timeout_seconds

    def get_daily_forecast(self, city: str | None, day_index: int) -> DailyForecast:
        if not city or not city.strip():
            raise WeatherCityNotConfiguredError
        if day_index not in (0, 1):
            raise ValueError("day_index muss 0 (heute) oder 1 (morgen) sein")

        locations = self._geocode(city.strip())
        if not locations and "," in city:
            locations = self._geocode(city.split(",", 1)[0].strip())
        if not isinstance(locations, list) or not locations:
            raise WeatherLocationNotFoundError
        location = locations[0]

        try:
            latitude = float(location["latitude"])
            longitude = float(location["longitude"])
            resolved_city = str(location["name"])
            country = str(location.get("country", ""))
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherUnavailableError from exc

        forecast_payload = self._request(
            FORECAST_URL,
            {
                "latitude": str(latitude),
                "longitude": str(longitude),
                "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                "timezone": "auto",
                "forecast_days": "2",
            },
        )
        try:
            daily = forecast_payload["daily"]
            forecast_date = date.fromisoformat(daily["time"][day_index])
            return DailyForecast(
                city=resolved_city,
                country=country,
                forecast_date=forecast_date,
                weather_code=int(daily["weather_code"][day_index]),
                minimum_celsius=float(daily["temperature_2m_min"][day_index]),
                maximum_celsius=float(daily["temperature_2m_max"][day_index]),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise WeatherUnavailableError from exc

    def _geocode(self, city: str) -> list[dict[str, Any]]:
        payload = self._request(
            GEOCODING_URL,
            {"name": city, "count": "1", "language": "de", "format": "json"},
        )
        results = payload.get("results")
        return results if isinstance(results, list) else []

    def _request(self, url: str, parameters: dict[str, str]) -> dict[str, Any]:
        try:
            return self._fetch_json(url, parameters, self._timeout_seconds)
        except (HTTPError, URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
            raise WeatherUnavailableError from exc


def _fetch_json(url: str, parameters: dict[str, str], timeout_seconds: float) -> dict[str, Any]:
    request_url = f"{url}?{urlencode(parameters)}"
    try:
        with urlopen(request_url, timeout=timeout_seconds) as response:  # noqa: S310 - feste HTTPS-URLs
            return json.load(response)
    except (HTTPError, URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
        raise WeatherUnavailableError from exc


def describe_forecast(forecast: DailyForecast, day_label: str) -> str:
    condition = _weather_description(forecast.weather_code)
    location = f"in {forecast.city}" + (f", {forecast.country}" if forecast.country else "")
    return (
        f"{day_label.capitalize()} wird es {location} {condition}, "
        f"bei {forecast.minimum_celsius:.0f} bis {forecast.maximum_celsius:.0f} Grad."
    )


def _weather_description(weather_code: int) -> str:
    descriptions = {
        0: "sonnig",
        1: "überwiegend sonnig",
        2: "teilweise bewölkt",
        3: "bedeckt",
        45: "neblig",
        48: "neblig mit Reif",
        51: "leicht nieselig",
        53: "nieselig",
        55: "stark nieselig",
        61: "leicht regnerisch",
        63: "regnerisch",
        65: "stark regnerisch",
        71: "leicht verschneit",
        73: "verschneit",
        75: "stark verschneit",
        80: "mit leichten Regenschauern",
        81: "mit Regenschauern",
        82: "mit starken Regenschauern",
        95: "gewittrig",
        96: "gewittrig mit leichtem Hagel",
        99: "gewittrig mit starkem Hagel",
    }
    return descriptions.get(weather_code, "wechselhaft")
