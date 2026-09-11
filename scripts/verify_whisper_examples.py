"""Prüft Whisper mit fünf deutschen Testphrasen ohne Audio-Wiedergabe."""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.config import Settings
from jarvis.whisper_recognizer import LocalWhisperRecognizer
from jarvis.windows_speech import find_installed_voice, synthesize_to_wave


EXAMPLES = (
    "Erzähl mir, wer Albert Einstein ist",
    "Wie wird das Wetter morgen?",
    "Wie viel Speicher habe ich noch?",
    "Wie spät ist es?",
    "Beenden",
)


def _read_wave(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as source:
        if source.getsampwidth() != 2 or source.getnchannels() != 1:
            raise RuntimeError("Der lokale TTS-Test erzeugte kein erwartetes Mono-16-Bit-WAV.")
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype=np.int16)
    return samples.astype(np.float32) / 32768.0


def main() -> None:
    voice = find_installed_voice("Microsoft Stefan")
    if voice is None:
        raise RuntimeError("Microsoft Stefan wurde für den lokalen Test nicht gefunden.")
    recognizer = LocalWhisperRecognizer(Settings())
    with tempfile.TemporaryDirectory(prefix="jarvis-whisper-check-") as directory:
        wave_path = Path(directory) / "example.wav"
        for expected in EXAMPLES:
            synthesize_to_wave(voice, expected, wave_path)
            print(f"Erwartet: {expected}\nErkannt:  {recognizer.transcribe_samples(_read_wave(wave_path))}\n")


if __name__ == "__main__":
    main()
