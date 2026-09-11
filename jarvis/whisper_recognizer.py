"""Lokale deutsche Whisper-Erkennung mit flüchtigen Audioframes."""

from __future__ import annotations

import logging
import importlib
import queue
import sys
import time
from types import ModuleType
from collections import deque
from pathlib import Path
from threading import Event
from typing import Any

import numpy as np
import sounddevice as sd

from .config import Settings


LOGGER = logging.getLogger(__name__)
MODEL_NAME = "small"
INTERRUPT_LISTEN_SECONDS = 1.25
INTERRUPT_END_SILENCE_SECONDS = 0.3


class WhisperRecognitionError(RuntimeError):
    """Das lokale Whisper-Modell oder das Mikrofon ist nicht verfügbar."""


class LocalWhisperRecognizer:
    """Hält das lokale Whisper-Modell im Speicher und speichert kein Audio."""

    def __init__(self, settings: Settings, model: Any | None = None) -> None:
        self._settings = settings
        if model is None and not _looks_like_whisper_model(settings.model_path):
            raise WhisperRecognitionError(
                f"Kein Whisper-Modell unter '{settings.model_path}'. "
                "Bitte zuerst 'python scripts/download_whisper_model.py' ausführen."
            )
        if model is not None:
            self._model = model
            return
        try:
            import torch

            _provide_numba_compatibility_if_blocked()
            import whisper

            torch.set_num_threads(settings.whisper_cpu_threads)
            self._model = whisper.load_model(
                MODEL_NAME, device="cpu", download_root=str(settings.model_path)
            )
        except Exception as exc:
            raise WhisperRecognitionError("Das lokale Whisper-Modell konnte nicht geladen werden.") from exc

    def listen_for_command(self) -> str:
        """Nimmt eine einzelne Frage auf und ruft Whisper genau einmal auf."""
        return self._listen_once(self._settings.command_timeout_seconds)

    def listen_for_interrupt(self, finished: Event) -> str:
        """Erkennt einen kurzen Einwurf und kann beim Ende der Ausgabe abbrechen."""
        return self._listen_once(
            INTERRUPT_LISTEN_SECONDS,
            finished=finished,
            end_silence_seconds=INTERRUPT_END_SILENCE_SECONDS,
        )

    def transcribe_samples(self, samples: np.ndarray) -> str:
        if samples.size == 0:
            return ""
        try:
            result = self._model.transcribe(
                samples,
                language="de",
                task="transcribe",
                fp16=False,
                temperature=0.0,
                beam_size=5,
                condition_on_previous_text=False,
                verbose=None,
            )
            text = result["text"] if isinstance(result, dict) else result.text
            return str(text).strip()
        except Exception as exc:
            raise WhisperRecognitionError("Die lokale Spracherkennung ist fehlgeschlagen.") from exc

    def _listen_once(
        self,
        timeout_seconds: float,
        finished: Event | None = None,
        end_silence_seconds: float | None = None,
    ) -> str:
        recording_started = time.monotonic()
        audio_queue: queue.Queue[bytes] = queue.Queue()
        pre_roll: deque[bytes] = deque(maxlen=3)
        frames: list[bytes] = []
        started = False
        last_voice_time = 0.0
        deadline = time.monotonic() + timeout_seconds

        def callback(audio_data: bytes, _frames: int, _time: object, status: object) -> None:
            if status:
                LOGGER.warning("Audio-Eingabestatus meldet eine Störung")
            audio_queue.put(bytes(audio_data))

        try:
            with sd.RawInputStream(
                samplerate=self._settings.sample_rate,
                blocksize=self._settings.block_size,
                device=self._settings.audio_device,
                dtype="int16",
                channels=1,
                callback=callback,
            ):
                while time.monotonic() < deadline and not (finished and finished.is_set()):
                    try:
                        data = audio_queue.get(timeout=min(0.15, max(0.01, deadline - time.monotonic())))
                    except queue.Empty:
                        continue
                    now = time.monotonic()
                    if _has_voice(data, self._settings.speech_energy_threshold):
                        if not started:
                            frames.extend(pre_roll)
                            started = True
                        frames.append(data)
                        last_voice_time = now
                    elif started:
                        frames.append(data)
                        required_silence = (
                            end_silence_seconds
                            if end_silence_seconds is not None
                            else self._settings.speech_end_silence_seconds
                        )
                        if now - last_voice_time >= required_silence:
                            break
                    else:
                        pre_roll.append(data)
        except Exception as exc:
            raise WhisperRecognitionError("Das Mikrofon konnte nicht geöffnet werden.") from exc

        if (finished and finished.is_set()) or not frames:
            LOGGER.info("Aufnahmezeit: %.2f s", time.monotonic() - recording_started)
            return ""
        samples = np.frombuffer(b"".join(frames), dtype=np.int16).astype(np.float32) / 32768.0
        LOGGER.info("Aufnahmezeit: %.2f s", time.monotonic() - recording_started)
        whisper_started = time.monotonic()
        text = self.transcribe_samples(samples)
        LOGGER.info("Whisper-Verarbeitung: %.2f s", time.monotonic() - whisper_started)
        return text


def _has_voice(audio_data: bytes, threshold: float) -> bool:
    samples = np.frombuffer(audio_data, dtype=np.int16)
    return bool(samples.size and np.mean(np.abs(samples.astype(np.int32))) >= threshold)


def _looks_like_whisper_model(path: Path) -> bool:
    return path.is_dir() and (path / f"{MODEL_NAME}.pt").is_file()


def _provide_numba_compatibility_if_blocked() -> None:
    """Installiert unter Windows nur bei blockierter Numba-DLL einen Whisper-Minimalersatz."""
    if not sys.platform.startswith("win"):
        return
    try:
        importlib.import_module("numba")
        return
    except (ImportError, OSError) as exc:
        if not _is_blocked_numba_import(exc):
            raise

    for module_name in tuple(sys.modules):
        if module_name == "numba" or module_name.startswith("numba."):
            sys.modules.pop(module_name, None)

    numba_compat = ModuleType("numba")

    def jit(*args: Any, **_kwargs: Any) -> Any:
        if len(args) == 1 and callable(args[0]):
            return args[0]

        def unchanged(function: Any) -> Any:
            return function

        return unchanged

    numba_compat.jit = jit  # type: ignore[attr-defined]
    sys.modules["numba"] = numba_compat
    LOGGER.warning("Numba-DLL wurde von Windows blockiert; Whisper verwendet den lokalen jit-Ersatz.")


def _is_blocked_numba_import(exc: BaseException) -> bool:
    markers = (
        "dll load failed",
        "anwendungssteuerungsrichtlinie",
        "application control policy",
        "blocked by group policy",
        "blocked by your system administrator",
    )
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if any(marker in str(current).lower() for marker in markers):
            return True
        current = current.__cause__ or current.__context__
    return False
