"""Zentrale, nicht geheime Laufzeitkonfiguration für Jarvis."""

from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "whisper"
DEFAULT_WAKE_MODEL_PATH = PROJECT_ROOT / "models" / "vosk-model-small-de-0.15"
LOCAL_AUDIO_CONFIG_PATH = PROJECT_ROOT / "jarvis.local.json"
DEFAULT_ONLINE_VOICE_NAME = "de-DE-ConradNeural"
DEFAULT_OFFLINE_FALLBACK_VOICE_NAME = "Microsoft Stefan"
# Dauerhafte Standardstadt für Wetterfragen. JARVIS_WEATHER_CITY kann sie bei
# Bedarf nur für die aktuelle Umgebung überschreiben.
DEFAULT_WEATHER_CITY = "Berlin, 10115"


def _audio_device_from_env() -> int | str | None:
    value = os.getenv("JARVIS_AUDIO_DEVICE")
    if value is None or not value.strip():
        return None
    value = value.strip()
    return int(value) if value.isdigit() else value


def _speech_end_silence_from_env() -> float:
    value = os.getenv("JARVIS_SPEECH_END_SILENCE_SECONDS")
    if value is None or not value.strip():
        return 1.2
    try:
        parsed = float(value)
    except ValueError:
        return 1.2
    return parsed if 0.3 <= parsed <= 2.0 else 1.2


def load_audio_selection(path: Path = LOCAL_AUDIO_CONFIG_PATH) -> tuple[int | None, int | None]:
    """Liest nur die lokal gespeicherte Mikrofonwahl; Audiodaten werden nie gespeichert."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        device = data.get("audio_device")
        sample_rate = data.get("sample_rate")
        if isinstance(device, int) and isinstance(sample_rate, int) and sample_rate > 0:
            return device, sample_rate
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return None, None


def save_audio_selection(device: int, sample_rate: int, path: Path = LOCAL_AUDIO_CONFIG_PATH) -> None:
    path.write_text(
        json.dumps({"audio_device": device, "sample_rate": sample_rate}, indent=2),
        encoding="utf-8",
    )


@dataclass(frozen=True)
class Settings:
    wake_word: str = "jarvis"
    sample_rate: int = 16_000
    block_size: int = 3_200
    command_timeout_seconds: float = 8.0
    wake_word_timeout_seconds: float = 12.0
    speech_end_silence_seconds: float = 1.2
    speech_energy_threshold: float = 150.0
    whisper_compute_type: str = "int8"
    whisper_cpu_threads: int = 4
    audio_device: int | str | None = None
    wake_model_path: Path = DEFAULT_WAKE_MODEL_PATH
    model_path: Path = DEFAULT_MODEL_PATH
    online_voice_name: str = DEFAULT_ONLINE_VOICE_NAME
    offline_fallback_voice_name: str = DEFAULT_OFFLINE_FALLBACK_VOICE_NAME
    weather_city: str | None = DEFAULT_WEATHER_CITY

    @classmethod
    def from_environment(cls) -> "Settings":
        model_path = Path(os.getenv("JARVIS_MODEL_PATH", str(DEFAULT_MODEL_PATH)))
        saved_device, saved_sample_rate = load_audio_selection()
        configured_device = saved_device if saved_device is not None else _audio_device_from_env()
        return cls(
            audio_device=configured_device,
            sample_rate=saved_sample_rate or 16_000,
            speech_end_silence_seconds=_speech_end_silence_from_env(),
            model_path=model_path,
            wake_model_path=Path(
                os.getenv("JARVIS_WAKE_MODEL_PATH", str(DEFAULT_WAKE_MODEL_PATH))
            ),
            online_voice_name=os.getenv("JARVIS_ONLINE_VOICE", DEFAULT_ONLINE_VOICE_NAME),
            offline_fallback_voice_name=os.getenv(
                "JARVIS_OFFLINE_FALLBACK_VOICE", DEFAULT_OFFLINE_FALLBACK_VOICE_NAME
            ),
            weather_city=os.getenv("JARVIS_WEATHER_CITY") or DEFAULT_WEATHER_CITY,
        )
