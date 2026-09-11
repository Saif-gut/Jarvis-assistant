import logging
import time
from datetime import datetime

from jarvis.assistant import JarvisAssistant, State
from jarvis.commands import CommandExecutor, CommandResult


class FakeQuestionRecognizer:
    def __init__(self, commands: list[str]) -> None:
        self._commands = iter(commands)

    def listen_for_command(self) -> str:
        return next(self._commands)


class FakeSpeaker:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def say(self, text: str) -> None:
        self.messages.append(text)


class FakeWakeRecognizer:
    pass


class PassiveAudio:
    def __init__(self, question: FakeQuestionRecognizer) -> None:
        self.question = question

    def listen_for_question(self) -> str:
        return self.question.listen_for_command()

class StoppableSpeaker(FakeSpeaker):
    def __init__(self) -> None:
        super().__init__()
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class SlowExecutor:
    def execute(self, _command: str) -> CommandResult:
        time.sleep(0.3)
        return CommandResult("Diese Antwort darf nicht gesprochen werden.")


def test_conversation_greets_once_and_handles_multiple_commands(caplog) -> None:
    recognizer = FakeQuestionRecognizer([" Wie spät ist es? ", "Datum", "Tschüss Jarvis"])
    speaker = FakeSpeaker()
    executor = CommandExecutor(now=lambda: datetime(2026, 8, 27, 9, 7))
    assistant = JarvisAssistant(FakeWakeRecognizer(), recognizer, speaker, executor, PassiveAudio(recognizer))  # type: ignore[arg-type]

    caplog.set_level(logging.INFO)
    assistant._run_conversation()

    assert len(speaker.messages) == 4
    assert speaker.messages[1] == "Es ist 09:07 Uhr."
    assert speaker.messages[2].startswith("Heute ist Donnerstag")
    assert speaker.messages[3] == "Auf Wiedersehen."
    assert assistant._state is State.WAITING
    assert caplog.messages.count("Erkannt: wie spat ist es") == 1
    assert caplog.messages.count("Erkannt: datum") == 1
    assert caplog.messages.count("Erkannt: tschuss jarvis") == 1
    assert "Frage: Wie spät ist es?" in caplog.messages
    assert "Antwort: Es ist 09:07 Uhr." in caplog.messages
    assert caplog.messages.count("Zustand: SPEAKING") == 3


class SourceExecutor:
    def __init__(self) -> None:
        self._calls = 0

    def execute(self, _command: str) -> CommandResult:
        self._calls += 1
        if self._calls == 1:
            return CommandResult(
                "Eine kurze Internetantwort.",
                source_name="Wikipedia: Beispiel",
                source_url="https://de.wikipedia.org/wiki/Beispiel",
            )
        return CommandResult("Auf Wiedersehen.", should_exit=True)


def test_conversation_logs_internet_source(caplog) -> None:
    recognizer = FakeQuestionRecognizer(["Was ist ein Beispiel", "Ende"])
    speaker = FakeSpeaker()
    assistant = JarvisAssistant(FakeWakeRecognizer(), recognizer, speaker, SourceExecutor(), PassiveAudio(recognizer))  # type: ignore[arg-type]

    caplog.set_level(logging.INFO)
    assistant._run_conversation()

    assert "Quelle: Wikipedia: Beispiel — https://de.wikipedia.org/wiki/Beispiel" in caplog.messages
