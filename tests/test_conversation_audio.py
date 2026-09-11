from threading import Event

from jarvis.config import Settings
from jarvis.conversation_audio import ConversationAudio


class Wake:
    def __init__(self) -> None:
        self.calls = 0

    def wait_for_wake_word(self) -> None:
        self.calls += 1


class Whisper:
    def __init__(self) -> None:
        self.calls = 0

    def listen_for_command(self) -> str:
        self.calls += 1
        return "vollständige Whisper-Frage"

    def listen_for_interrupt(self, finished: Event) -> str:
        assert not finished.is_set()
        self.calls += 1
        return "stopp"


def test_conversation_audio_only_delegates_wake_and_full_whisper_question() -> None:
    wake = Wake()
    whisper = Whisper()
    audio = ConversationAudio(Settings(), wake, whisper)  # type: ignore[arg-type]

    audio.wait_for_wake_word()
    question = audio.listen_for_question()

    assert wake.calls == 1
    assert whisper.calls == 1
    assert question == "vollständige Whisper-Frage"
    assert not hasattr(audio, "monitor_speaking")


def test_conversation_audio_delegates_short_interrupt_listening() -> None:
    wake = Wake()
    whisper = Whisper()
    audio = ConversationAudio(Settings(), wake, whisper)  # type: ignore[arg-type]

    command = audio.listen_for_interrupt(Event())

    assert command == "stopp"
    assert whisper.calls == 1
