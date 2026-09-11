"""Interaktive, lokale Mikrofoneinrichtung ohne Aufzeichnung."""

from __future__ import annotations

import sys
from typing import Any

import numpy as np
import sounddevice as sd

from .config import save_audio_selection


def input_devices() -> list[tuple[int, dict[str, Any], bool]]:
    default_input = sd.default.device[0]
    devices = sd.query_devices()
    return [
        (index, dict(device), index == default_input)
        for index, device in enumerate(devices)
        if device.get("max_input_channels", 0) > 0
    ]


def run_audio_setup() -> None:
    devices = input_devices()
    if not devices:
        print("Keine Mikrofone gefunden.")
        return
    print("Verfügbare Mikrofone:")
    for index, device, is_default in devices:
        marker = " (Windows-Standardmikrofon)" if is_default else ""
        rate = int(device.get("default_samplerate", 0))
        print(f"  {index}: {device['name']} | {rate} Hz{marker}")

    while True:
        selected = input("Mikrofonnummer auswählen: ").strip()
        if selected.isdigit() and any(index == int(selected) for index, _device, _default in devices):
            break
        print("Bitte eine der angezeigten Nummern eingeben.")
    device_index = int(selected)
    device = next(item for index, item, _default in devices if index == device_index)
    sample_rate = supported_sample_rate(device_index, int(device["default_samplerate"]))
    _show_live_level(device_index, sample_rate)
    save_audio_selection(device_index, sample_rate)
    print(f"Gespeichert: Mikrofon {device_index} mit {sample_rate} Hz in jarvis.local.json")


def _show_live_level(device: int, sample_rate: int) -> None:
    print("Jetzt kurz sprechen. Der Pegel läuft live; mit Enter beenden.")

    def callback(indata: np.ndarray, _frames: int, _time: Any, _status: Any) -> None:
        level = int(min(40, np.sqrt(np.mean(np.square(indata.astype(np.float32)))) * 180))
        sys.stdout.write("\rPegel: [" + "#" * level + "." * (40 - level) + "]")
        sys.stdout.flush()

    try:
        with sd.InputStream(device=device, samplerate=sample_rate, channels=1, callback=callback):
            input()
    except Exception as exc:
        print(f"\nMikrofon konnte nicht geöffnet werden: {exc}")
        raise
    print()


def supported_sample_rate(device: int, default_rate: int, checker=sd.check_input_settings) -> int:
    """Wählt 16 kHz nur falls das ausgewählte Gerät diese Rate wirklich unterstützt."""
    for candidate in (16_000, default_rate):
        try:
            checker(device=device, samplerate=candidate, channels=1, dtype="int16")
            return candidate
        except Exception:
            continue
    raise RuntimeError("Das Mikrofon unterstützt keine verwendbare Mono-16-Bit-Sample-Rate.")
