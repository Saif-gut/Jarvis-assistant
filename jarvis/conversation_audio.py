"""Zentraler Gesprächsablauf ohne Mikrofonzugriff während der Ausgabe."""

from __future__ import annotations

from threading import Event

from .config import Settings
from .wake_recognizer import VoskGrammarRecognizer
from .whisper_recognizer import LocalWhisperRecognizer


class ConversationAudio:
    """Öffnet den Mikrofonzugriff nur für Aktivierung oder vollständige Fragen."""

    def __init__(
        self,
        settings: Settings,
        wake_recognizer: VoskGrammarRecognizer,
        question_recognizer: LocalWhisperRecognizer,
    ) -> None:
        self._settings = settings
        self._wake_recognizer = wake_recognizer
        self._question_recognizer = question_recognizer

    def wait_for_wake_word(self) -> None:
        self._wake_recognizer.wait_for_wake_word()

    def listen_for_question(self) -> str:
        """Erkennt genau eine vollständige Frage mit Whisper nach der Ausgabe."""
        return self._question_recognizer.listen_for_command()

    def listen_for_interrupt(self, finished: Event) -> str:
        """Erkennt während einer Ausgabe einen kurzen gesprochenen Einwurf."""
        return self._question_recognizer.listen_for_interrupt(finished)
