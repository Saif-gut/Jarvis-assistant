from jarvis.config import Settings


def test_default_weather_city_is_public_example() -> None:
    assert Settings().weather_city == "Berlin, 10115"


def test_weather_city_can_be_configured_via_environment(monkeypatch) -> None:
    monkeypatch.setenv("JARVIS_WEATHER_CITY", "Hamburg")

    assert Settings.from_environment().weather_city == "Hamburg"


def test_speech_end_pause_has_a_fast_safe_default_and_can_be_changed(monkeypatch) -> None:
    assert Settings().speech_end_silence_seconds == 1.2
    assert Settings().speech_energy_threshold == 150.0
    monkeypatch.setenv("JARVIS_SPEECH_END_SILENCE_SECONDS", "0.65")

    assert Settings.from_environment().speech_end_silence_seconds == 0.65
