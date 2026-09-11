from datetime import datetime

from jarvis.assistant import JarvisAssistant, State
from jarvis.audio_setup import supported_sample_rate
from jarvis.commands import CommandExecutor
from jarvis.config import Settings, load_audio_selection, save_audio_selection
from jarvis.wake_recognizer import WAKE_VARIANTS


class WakeOnly:
    def __init__(self) -> None:
        self.exit_checks = 0

    def wait_for_wake_word(self) -> None:
        raise AssertionError("Der Gesprächsmodus darf nicht erneut auf Aktivierung warten.")

    def listen_for_exit(self, _timeout_seconds: float) -> str:
        self.exit_checks += 1
        return ""


class QuestionOnly:
    def __init__(self) -> None:
        self.calls = 0

    def listen_for_command(self) -> str:
        self.calls += 1
        return "Beenden"

    def wait_for_wake_word(self) -> None:
        raise AssertionError("Whisper darf im Wartemodus nicht verwendet werden.")

    def listen_for_exit(self, _timeout_seconds: float) -> str:
        raise AssertionError("Whisper darf nicht für Abbruchphrasen verwendet werden.")


class Speaker:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def say(self, text: str) -> None:
        self.messages.append(text)


class PassiveAudio:
    def __init__(self, question: QuestionOnly) -> None:
        self.question = question

    def listen_for_question(self) -> str:
        return self.question.listen_for_command()

    def monitor_speaking(self, _finished, _on_real_speech):
        return None


def test_conversation_uses_whisper_only_for_the_question() -> None:
    wake = WakeOnly()
    question = QuestionOnly()
    assistant = JarvisAssistant(
        wake,
        question,
        Speaker(),
        CommandExecutor(now=lambda: datetime(2026, 8, 27, 9, 7)),
        PassiveAudio(question),
    )  # type: ignore[arg-type]

    assistant._run_conversation()

    assert question.calls == 1
    assert wake.exit_checks == 0
    assert assistant._state is State.WAITING


def test_vosk_grammar_is_limited_to_wake_variants() -> None:
    assert WAKE_VARIANTS == ("jarvis", "jarwis", "jervis")


def test_saved_audio_selection_is_local_and_reusable(tmp_path) -> None:
    target = tmp_path / "jarvis.local.json"
    save_audio_selection(4, 48_000, target)

    assert load_audio_selection(target) == (4, 48_000)
    assert Settings().wake_word == "jarvis"


def test_audio_setup_uses_only_a_rate_reported_as_supported() -> None:
    checked: list[int] = []

    def checker(**kwargs: int) -> None:
        checked.append(kwargs["samplerate"])
        if kwargs["samplerate"] == 16_000:
            raise ValueError("not supported")

    assert supported_sample_rate(2, 48_000, checker) == 48_000
    assert checked == [16_000, 48_000]
