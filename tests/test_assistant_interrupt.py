from threading import Event

from jarvis.assistant import JarvisAssistant
from jarvis.commands import CommandResult


class Questions:
    def listen_for_command(self) -> str:
        return "Beenden"


class Audio:
    def __init__(self, questions: Questions) -> None:
        self._questions = questions

    def listen_for_question(self) -> str:
        return self._questions.listen_for_command()


class Speaker:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.stop_calls = 0

    def say(self, text: str) -> None:
        self.messages.append(text)

    def stop(self) -> None:
        self.stop_calls += 1


class Executor:
    def execute(self, command: str) -> CommandResult:
        assert command == "beenden"
        return CommandResult("Auf Wiedersehen.", should_exit=True)


def test_stable_mode_has_no_speech_interrupt_or_vosk_exit_path() -> None:
    questions = Questions()
    speaker = Speaker()
    assistant = JarvisAssistant(
        object(), questions, speaker, Executor(), Audio(questions)
    )  # type: ignore[arg-type]

    assistant._run_conversation()

    assert speaker.messages[-1] == "Auf Wiedersehen."
    assert speaker.stop_calls == 0
    assert not hasattr(assistant, "_speak_openly")
    assert not hasattr(assistant, "_execute_with_exit_monitoring")


class InterruptAudio(Audio):
    def __init__(self, questions: Questions, command: str) -> None:
        super().__init__(questions)
        self.command = command
        self.listener_finished = Event()

    def listen_for_interrupt(self, finished: Event) -> str:
        if finished.is_set():
            self.listener_finished.set()
            return ""
        self.listener_finished.set()
        return self.command


class BlockingSpeaker(Speaker):
    def __init__(self) -> None:
        super().__init__()
        self.stopped = Event()

    def say(self, text: str) -> None:
        self.messages.append(text)
        self.stopped.wait(timeout=1.0)

    def stop(self) -> None:
        super().stop()
        self.stopped.set()


def test_stop_command_interrupts_speech_immediately() -> None:
    questions = Questions()
    audio = InterruptAudio(questions, "Hör bitte auf!")
    speaker = BlockingSpeaker()
    assistant = JarvisAssistant(
        object(), questions, speaker, Executor(), audio
    )  # type: ignore[arg-type]

    assistant._speak("Eine lange Antwort")

    assert speaker.stop_calls == 1
    assert audio.listener_finished.is_set()


class FinishingAudio(Audio):
    def __init__(self, questions: Questions) -> None:
        super().__init__(questions)
        self.listener_started = Event()
        self.listener_finished = Event()

    def listen_for_interrupt(self, finished: Event) -> str:
        self.listener_started.set()
        finished.wait(timeout=1.0)
        self.listener_finished.set()
        return ""


class WaitForListenerSpeaker(Speaker):
    def __init__(self, listener_started: Event) -> None:
        super().__init__()
        self._listener_started = listener_started

    def say(self, text: str) -> None:
        assert self._listener_started.wait(timeout=1.0)
        self.messages.append(text)


def test_interrupt_listener_ends_when_normal_speech_finishes() -> None:
    questions = Questions()
    audio = FinishingAudio(questions)
    speaker = WaitForListenerSpeaker(audio.listener_started)
    assistant = JarvisAssistant(
        object(), questions, speaker, Executor(), audio
    )  # type: ignore[arg-type]

    assistant._speak("Kurze Antwort")

    assert speaker.stop_calls == 0
    assert audio.listener_finished.is_set()
