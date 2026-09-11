"""Kommandozeilenstart für ``python -m jarvis``."""

from __future__ import annotations

import argparse
import logging
import sys

from .assistant import JarvisAssistant
from .audio_setup import run_audio_setup
from .commands import CommandExecutor
from .conversation_audio import ConversationAudio
from .config import Settings
from .diagnostics import run_diagnostics
from .ollama_client import OllamaClient
from .speech import SpeechRecognitionError, WindowsSpeaker
from .wake_recognizer import VoskGrammarRecognizer, WakeRecognitionError
from .whisper_recognizer import LocalWhisperRecognizer, WhisperRecognitionError


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lokaler Windows-Sprachassistent Jarvis")
    parser.add_argument(
        "--check", action="store_true", help="Modell und verfügbare Audiogeräte prüfen"
    )
    parser.add_argument(
        "--setup-audio", action="store_true", help="Mikrofon auswählen und Pegel prüfen"
    )
    return parser.parse_args()


def _configure_utf8_output() -> None:
    """Schreibt Terminal- und Pipe-Ausgaben auf allen Windows-Codepages als UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="strict")


def main() -> int:
    _configure_utf8_output()
    args = _arguments()
    settings = Settings.from_environment()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    if args.check:
        for result in run_diagnostics(settings.model_path, settings.wake_model_path):
            print(result)
        return 0
    if args.setup_audio:
        try:
            run_audio_setup()
        except Exception as exc:
            logging.error("Audioeinrichtung fehlgeschlagen: %s", exc)
            return 1
        return 0

    try:
        wake_recognizer = VoskGrammarRecognizer(settings)
        question_recognizer = LocalWhisperRecognizer(settings)
        assistant = JarvisAssistant(
            wake_recognizer=wake_recognizer,
            question_recognizer=question_recognizer,
            speaker=WindowsSpeaker(settings),
            executor=CommandExecutor(
                weather_city=settings.weather_city,
                ollama_client=OllamaClient(),
            ),
            audio=ConversationAudio(settings, wake_recognizer, question_recognizer),
        )
        assistant.run()
    except KeyboardInterrupt:
        logging.info("Jarvis wurde per Tastatur beendet")
        return 0
    except (SpeechRecognitionError, WakeRecognitionError, WhisperRecognitionError) as exc:
        logging.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
