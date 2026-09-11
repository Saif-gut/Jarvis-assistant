from jarvis import online_speech


def test_synthesize_to_mp3_uses_configured_voice(monkeypatch, tmp_path) -> None:
    calls: list[tuple[str, str, str]] = []

    class FakeCommunicate:
        def __init__(self, text: str, voice: str, rate: str) -> None:
            calls.append((text, voice, rate))

        def save_sync(self, target: str) -> None:
            with open(target, "wb") as audio:
                audio.write(b"mp3")

    monkeypatch.setattr(online_speech.edge_tts, "Communicate", FakeCommunicate)
    target = tmp_path / "speech.mp3"

    online_speech.synthesize_to_mp3("de-DE-ConradNeural", "Hallo", target)

    assert calls == [("Hallo", "de-DE-ConradNeural", "+5%")]
    assert target.read_bytes() == b"mp3"
