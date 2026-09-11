import logging

from jarvis import speech
from jarvis.config import Settings
from jarvis.online_speech import OnlineSpeechError
from jarvis import windows_speech
from jarvis.windows_speech import WindowsVoice


STEFAN = WindowsVoice(name="Microsoft Stefan", language="de-DE", engine="onecore")


def test_speaker_uses_configured_online_voice(monkeypatch, caplog) -> None:
    spoken: list[tuple[str, str]] = []
    temporary_files = []

    monkeypatch.setattr(
        speech,
        "find_installed_voice",
        lambda name: STEFAN if name == "Microsoft Stefan" else None,
    )
    monkeypatch.setattr(
        speech,
        "synthesize_to_mp3",
        lambda voice, text, target: (
            spoken.append((voice, text)), target.write_bytes(b"audio"), temporary_files.append(target)
        ),
    )
    monkeypatch.setattr(speech, "play_media", lambda _path, _generation, _was_stopped: None)

    caplog.set_level(logging.INFO)
    speaker = speech.WindowsSpeaker(Settings())
    speaker.say("Guten Abend.")

    assert spoken == [("de-DE-ConradNeural", "Guten Abend.")]
    assert not temporary_files[0].exists()
    assert "Online-Stimme Conrad wird abgespielt" in caplog.messages


def test_speaker_uses_stefan_when_online_speech_fails(monkeypatch, caplog) -> None:
    spoken: list[WindowsVoice] = []

    monkeypatch.setattr(
        speech,
        "find_installed_voice",
        lambda name: STEFAN if name == "Microsoft Stefan" else None,
    )
    monkeypatch.setattr(speech, "default_fallback_voice", lambda: STEFAN)
    monkeypatch.setattr(
        speech,
        "synthesize_to_mp3",
        lambda *_args: (_ for _ in ()).throw(OnlineSpeechError("offline")),
    )
    monkeypatch.setattr(
        speech,
        "synthesize_to_wave",
        lambda voice, _text, target: (spoken.append(voice), target.write_bytes(b"audio")),
    )
    monkeypatch.setattr(speech, "play_wave", lambda _path, _generation, _was_stopped: None)

    speaker = speech.WindowsSpeaker(Settings())
    speaker.say("Test")

    assert spoken == [STEFAN]
    assert "Offline-Ersatz Stefan wird benutzt: Online-Synthese nicht erreichbar" in caplog.messages


def test_media_player_uses_nonblocking_windows_mci_playback(monkeypatch, tmp_path) -> None:
    commands: list[str] = []
    def mci_command(command: str, response_length: int = 0) -> str:
        commands.append(command)
        return "stopped" if command.startswith("status ") else ""

    monkeypatch.setattr(windows_speech, "_mci_command", mci_command)

    windows_speech.play_media(tmp_path / "speech.mp3", 0, lambda _generation: False)

    assert commands == [
        f'open "{tmp_path / "speech.mp3"}" type mpegvideo alias jarvis_online_tts',
        "play jarvis_online_tts",
        "status jarvis_online_tts mode",
        "close jarvis_online_tts",
    ]


def test_stopped_synthesis_cannot_start_playback_later(monkeypatch) -> None:
    played: list[object] = []
    monkeypatch.setattr(speech, "find_installed_voice", lambda _name: STEFAN)
    monkeypatch.setattr(
        speech,
        "synthesize_to_mp3",
        lambda _voice, _text, target: (target.write_bytes(b"audio"), speaker.stop()),
    )
    monkeypatch.setattr(speech, "play_media", played.append)

    speaker = speech.WindowsSpeaker(Settings())
    speaker.say("Alte Antwort")

    assert played == []
