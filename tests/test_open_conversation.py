from datetime import datetime

from jarvis.assistant import JarvisAssistant, State
from jarvis.commands import CommandExecutor


class Questions:
    def __init__(self, values: list[str]) -> None:
        self._values = iter(values)
        self.calls = 0

    def listen_for_command(self) -> str:
        self.calls += 1
        return next(self._values)


class Speaker:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.stops = 0

    def say(self, text: str) -> None:
        self.messages.append(text)

    def stop(self) -> None:
        self.stops += 1


class Audio:
    """Absichtlich ohne Ausgabemonitor: während say darf nicht zugehört werden."""

    def __init__(self, questions: Questions) -> None:
        self.questions = questions

    def listen_for_question(self) -> str:
        return self.questions.listen_for_command()


def test_answers_are_spoken_fully_before_the_next_whisper_question() -> None:
    questions = Questions(["Uhrzeit", "Datum", "Beenden"])
    speaker = Speaker()
    assistant = JarvisAssistant(
        object(), questions, speaker,
        CommandExecutor(now=lambda: datetime(2026, 8, 27, 9, 7)), Audio(questions),
    )  # type: ignore[arg-type]

    assistant._run_conversation()

    assert speaker.messages[1] == "Es ist 09:07 Uhr."
    assert speaker.messages[2].startswith("Heute ist Donnerstag")
    assert speaker.messages[-1] == "Auf Wiedersehen."
    assert speaker.stops == 0
    assert questions.calls == 3
    assert assistant._state is State.WAITING


def test_stop_ends_only_after_a_normal_whisper_listen() -> None:
    questions = Questions(["Stopp"])
    speaker = Speaker()
    assistant = JarvisAssistant(
        object(), questions, speaker, CommandExecutor(), Audio(questions)
    )  # type: ignore[arg-type]

    assistant._run_conversation()

    assert questions.calls == 1
    assert speaker.messages[-1] == "Auf Wiedersehen."
    assert speaker.stops == 0
