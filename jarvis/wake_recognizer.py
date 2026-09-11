"""Schnelle lokale Vosk-Grammatik ausschließlich für die Aktivierung."""

from __future__ import annotations

import json
import logging
import queue
import time
from pathlib import Path
from typing import Iterable

import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel

from .config import Settings


LOGGER = logging.getLogger(__name__)
WAKE_VARIANTS = ("jarvis", "jarwis", "jervis")


class WakeRecognitionError(RuntimeError):
    """Das kleine Vosk-Modell oder das Mikrofon ist nicht verfügbar."""


class VoskGrammarRecognizer:
    """Erkennt ausschließlich wenige kurze Phrasen und verwirft alte Audioblöcke."""

    def __init__(self, settings: Settings, model: Model | None = None) -> None:
        self._settings = settings
        if model is None and not _looks_like_vosk_model(settings.wake_model_path):
            raise WakeRecognitionError(
                f"Kein kleines Vosk-Modell unter '{settings.wake_model_path}'. "
                "Bitte scripts/download_vosk_model.py ausführen."
            )
        try:
            SetLogLevel(-1)
            self._model = model or Model(str(settings.wake_model_path))
        except Exception as exc:
            raise WakeRecognitionError("Das kleine Vosk-Modell konnte nicht geladen werden.") from exc

    def wait_for_wake_word(self) -> None:
        LOGGER.info("Warte auf Jarvis")
        started = time.monotonic()
        self._listen_for(WAKE_VARIANTS, timeout_seconds=None)
        LOGGER.info("Jarvis erkannt")
        LOGGER.info("Aktivierung: %.2f s", time.monotonic() - started)

    def _listen_for(self, phrases: Iterable[str], timeout_seconds: float | None) -> str:
        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=4)
        grammar = tuple(phrases)
        recognizer = KaldiRecognizer(
            self._model, self._settings.sample_rate, json.dumps([*grammar, "[unk]"])
        )
        deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds

        def callback(data: bytes, _frames: int, _time: object, status: object) -> None:
            if status:
                LOGGER.warning("Audio-Eingabestatus meldet eine Störung")
            try:
                audio_queue.put_nowait(bytes(data))
            except queue.Full:
                try:
                    audio_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    audio_queue.put_nowait(bytes(data))
                except queue.Full:
                    pass

        try:
            with sd.RawInputStream(
                samplerate=self._settings.sample_rate,
                blocksize=1_600,
                device=self._settings.audio_device,
                dtype="int16",
                channels=1,
                callback=callback,
            ):
                while deadline is None or time.monotonic() < deadline:
                    remaining = 0.1 if deadline is None else max(0.01, deadline - time.monotonic())
                    try:
                        data = audio_queue.get(timeout=min(0.1, remaining))
                    except queue.Empty:
                        continue
                    for text in _recognized_texts(recognizer, data):
                        if text in grammar:
                            return text
        except Exception as exc:
            raise WakeRecognitionError("Das ausgewählte Mikrofon konnte nicht geöffnet werden.") from exc
        return ""


def _recognized_texts(recognizer: KaldiRecognizer, data: bytes) -> tuple[str, ...]:
    payload = recognizer.Result() if recognizer.AcceptWaveform(data) else recognizer.PartialResult()
    try:
        result = json.loads(payload)
    except json.JSONDecodeError:
        return ()
    return tuple(str(result.get(key, "")).strip().casefold() for key in ("text", "partial"))


def _looks_like_vosk_model(path: Path) -> bool:
    return path.is_dir() and (path / "am").is_dir() and (path / "conf").is_dir()
