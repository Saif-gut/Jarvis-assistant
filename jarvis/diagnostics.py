"""Kurze, nicht aufzeichnende Systemprüfung."""

from __future__ import annotations

from pathlib import Path

import sounddevice as sd

from .whisper_recognizer import _looks_like_whisper_model
from .wake_recognizer import _looks_like_vosk_model


def run_diagnostics(model_path: Path, wake_model_path: Path | None = None) -> list[str]:
    results: list[str] = []
    results.append(
        f"Whisper-Modell: {'OK' if _looks_like_whisper_model(model_path) else 'FEHLT'} ({model_path})"
    )
    if wake_model_path is not None:
        results.append(
            f"Vosk-Aktivierungsmodell: {'OK' if _looks_like_vosk_model(wake_model_path) else 'FEHLT'} ({wake_model_path})"
        )
    try:
        devices = sd.query_devices()
        inputs = [device for device in devices if device.get("max_input_channels", 0) > 0]
        outputs = [device for device in devices if device.get("max_output_channels", 0) > 0]
        results.append(f"Mikrofon-Geräte: {len(inputs)} gefunden")
        results.append(f"Audio-Ausgänge: {len(outputs)} gefunden")
    except Exception as exc:
        results.append(f"Audio-Geräteprüfung: FEHLER ({type(exc).__name__})")
    return results
