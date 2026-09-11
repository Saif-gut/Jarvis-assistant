"""Lokale Whisper-Erkennung und Windows-Sprachausgabe."""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from threading import Lock

from .config import Settings
from .online_speech import OnlineSpeechError, synthesize_to_mp3
from .windows_speech import (
    WindowsSpeechError,
    WindowsVoice,
    default_fallback_voice,
    find_installed_voice,
    play_media,
    play_wave,
    stop_playback,
    synthesize_to_wave,
)


LOGGER = logging.getLogger(__name__)


class SpeechRecognitionError(RuntimeError):
    """Verständlicher Fehler beim Initialisieren oder Lesen von Audio."""


class WindowsSpeaker:
    def __init__(self, settings: Settings) -> None:
        self._online_voice_name = settings.online_voice_name
        self._fallback_voice = (
            find_installed_voice(settings.offline_fallback_voice_name) or default_fallback_voice()
        )
        if self._fallback_voice is None:
            raise SpeechRecognitionError("Keine verwendbare Windows-Stimme wurde gefunden.")
        self._generation_lock = Lock()
        self._playback_generation = 0
        LOGGER.info(
            "Sprachausgabe verwendet online %s; Offline-Ersatz: %s (%s)",
            self._online_voice_name,
            self._fallback_voice.name,
            self._fallback_voice.engine,
        )

    def say(self, text: str) -> None:
        started = time.monotonic()
        with self._generation_lock:
            generation = self._playback_generation
        try:
            self._speak_online(text, generation)
            LOGGER.info("Online-Stimme Conrad wird abgespielt")
        except (OnlineSpeechError, WindowsSpeechError) as exc:
            LOGGER.warning(
                "Offline-Ersatz %s wird benutzt: %s",
                self._fallback_voice.name.removeprefix("Microsoft "),
                self._online_failure_reason(exc),
            )
            try:
                self._speak_offline(self._fallback_voice, text, generation)
            except WindowsSpeechError as fallback_exc:
                raise SpeechRecognitionError(
                    "Die Online-Sprachausgabe und ihre Ersatzstimme sind fehlgeschlagen."
                ) from fallback_exc
        finally:
            LOGGER.info("Sprachausgabe: %.2f s", time.monotonic() - started)

    def stop(self) -> None:
        """Bricht eine laufende Ausgabe ab, ohne temporäre Dateien zu behalten."""
        with self._generation_lock:
            self._playback_generation += 1
        stop_playback()

    def _speak_offline(self, voice: WindowsVoice, text: str, generation: int) -> None:
        with tempfile.TemporaryDirectory(prefix="jarvis-tts-") as temporary:
            wave_path = Path(temporary) / "speech.wav"
            synthesize_to_wave(voice, text, wave_path)
            if not self._was_stopped(generation):
                play_wave(wave_path, generation, self._was_stopped)

    def _speak_online(self, text: str, generation: int) -> None:
        with tempfile.TemporaryDirectory(prefix="jarvis-online-tts-") as temporary:
            media_path = Path(temporary) / "speech.mp3"
            synthesize_to_mp3(self._online_voice_name, text, media_path)
            if not self._was_stopped(generation):
                play_media(media_path, generation, self._was_stopped)

    def _was_stopped(self, generation: int) -> bool:
        with self._generation_lock:
            return generation != self._playback_generation

    @staticmethod
    def _online_failure_reason(exc: OnlineSpeechError | WindowsSpeechError) -> str:
        if isinstance(exc, OnlineSpeechError):
            return "Online-Synthese nicht erreichbar"
        return "Online-Audiowiedergabe fehlgeschlagen"
