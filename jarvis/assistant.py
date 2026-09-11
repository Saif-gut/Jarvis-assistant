"""Zustandsautomat für den stabilen, nicht unterbrechbaren Gesprächsmodus."""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum, auto
from threading import Event, Thread

from .commands import CommandExecutor, normalize_text
from .conversation_audio import ConversationAudio
from .speech import WindowsSpeaker
from .wake_recognizer import VoskGrammarRecognizer
from .whisper_recognizer import LocalWhisperRecognizer, WhisperRecognitionError


LOGGER = logging.getLogger(__name__)
STOP_COMMANDS = frozenset(
    {
        "stopp",
        "stop",
        "hor auf",
        "bitte stopp",
        "bitte stop",
        "hor bitte auf",
        "bitte hor auf",
        "jarvis stopp",
        "jarvis stop",
    }
)


class State(Enum):
    WAITING = auto()
    GREETING = auto()
    LISTENING = auto()
    EXECUTING = auto()
    STOPPED = auto()


def greeting_for_time(now: datetime | None = None) -> str:
    hour = (now or datetime.now()).hour
    if 5 <= hour < 11:
        return "Guten Morgen. Was kann ich für dich tun?"
    if 11 <= hour < 18:
        return "Guten Tag. Was kann ich für dich tun?"
    return "Guten Abend. Was kann ich für dich tun?"


class JarvisAssistant:
    def __init__(
        self,
        wake_recognizer: VoskGrammarRecognizer,
        question_recognizer: LocalWhisperRecognizer,
        speaker: WindowsSpeaker,
        executor: CommandExecutor,
        audio: ConversationAudio | None = None,
    ) -> None:
        self._audio = audio or ConversationAudio(
            getattr(question_recognizer, "_settings", None), wake_recognizer, question_recognizer
        )
        self._speaker = speaker
        self._executor = executor
        self._state = State.WAITING

    def _transition(self, state: State) -> None:
        self._state = state
        LOGGER.info("Zustand: %s", state.name)

    def run(self) -> None:
        LOGGER.info("Jarvis wurde gestartet")
        self._transition(State.WAITING)
        while self._state is not State.STOPPED:
            self._audio.wait_for_wake_word()
            self._run_conversation()
        LOGGER.info("Jarvis wurde beendet")

    def _run_conversation(self) -> None:
        """Führt ein offenes Gespräch ohne Zuhören während der Sprachausgabe."""
        self._transition(State.GREETING)
        greeting = greeting_for_time()
        LOGGER.info("Antwort: %s", greeting)
        self._speak(greeting)

        while True:
            self._transition(State.LISTENING)
            command = self._audio.listen_for_question()
            normalized = normalize_text(command)
            if normalized:
                LOGGER.info("Frage: %s", command.strip())
                LOGGER.info("Erkannt: %s", normalized)
            else:
                LOGGER.info("Kein Sprachbefehl erkannt")

            self._transition(State.EXECUTING)
            result = self._executor.execute(normalized)
            if result.source_name and result.source_url:
                LOGGER.info("Quelle: %s — %s", result.source_name, result.source_url)
            LOGGER.info("Antwort: %s", result.response.replace("\r", " ").replace("\n", " ").strip())
            LOGGER.info("Zustand: SPEAKING")
            self._speak(result.response)

            if result.should_exit:
                self._transition(State.WAITING)
                return

    def _speak(self, text: str) -> None:
        """Gibt jede Antwort vollständig aus, bevor wieder zugehört wird."""
        listen_for_interrupt = getattr(self._audio, "listen_for_interrupt", None)
        if not callable(listen_for_interrupt):
            self._speaker.say(text)
            return

        finished = Event()
        listener = Thread(
            target=self._listen_for_stop_during_speech,
            args=(finished,),
            name="jarvis-speech-interrupt",
            daemon=True,
        )
        listener.start()
        try:
            self._speaker.say(text)
        finally:
            finished.set()
            listener.join()

    def _listen_for_stop_during_speech(self, finished: Event) -> None:
        while not finished.is_set():
            try:
                command = self._audio.listen_for_interrupt(finished)
            except WhisperRecognitionError as exc:
                LOGGER.warning("Stopp-Erkennung während der Ausgabe fehlgeschlagen: %s", exc)
                return
            if finished.is_set():
                return
            normalized = normalize_text(command)
            if normalized in STOP_COMMANDS:
                LOGGER.info("Sprachausgabe durch '%s' gestoppt", normalized)
                self._speaker.stop()
                finished.set()
                return
