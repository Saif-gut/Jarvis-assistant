from pathlib import Path
import sys

import numpy as np
import pytest

from jarvis.config import Settings
from jarvis import whisper_recognizer
from jarvis.whisper_recognizer import (
    LocalWhisperRecognizer,
    _has_voice,
    _looks_like_whisper_model,
    _provide_numba_compatibility_if_blocked,
)


class FakeModel:
    def __init__(self) -> None:
        self.arguments: dict[str, object] = {}

    def transcribe(self, _samples: np.ndarray, **kwargs: object) -> dict[str, str]:
        self.arguments = kwargs
        return {"text": " Erzähl mir, wer Albert Einstein ist. "}


def test_whisper_transcribes_german_with_local_model_interface() -> None:
    model = FakeModel()
    recognizer = LocalWhisperRecognizer(Settings(), model=model)

    text = recognizer.transcribe_samples(np.array([0.1, -0.1], dtype=np.float32))

    assert text == "Erzähl mir, wer Albert Einstein ist."
    assert model.arguments["language"] == "de"
    assert model.arguments["task"] == "transcribe"
    assert model.arguments["condition_on_previous_text"] is False


def test_voice_detection_uses_configured_energy_threshold() -> None:
    quiet = np.array([10, -10, 10], dtype=np.int16).tobytes()
    speech = np.array([500, -500, 500], dtype=np.int16).tobytes()

    assert not _has_voice(quiet, 180)
    assert _has_voice(speech, 180)


def test_whisper_model_check_requires_model_files(tmp_path: Path) -> None:
    assert not _looks_like_whisper_model(tmp_path)
    (tmp_path / "small.pt").touch()
    assert _looks_like_whisper_model(tmp_path)


def test_blocked_numba_import_gets_minimal_jit_replacement(monkeypatch: pytest.MonkeyPatch) -> None:
    original_numba_modules = {
        name: module for name, module in sys.modules.items() if name == "numba" or name.startswith("numba.")
    }
    for name in original_numba_modules:
        monkeypatch.delitem(sys.modules, name, raising=False)

    partial_module = object()

    def blocked_import(_name: str) -> None:
        sys.modules["numba.np"] = partial_module  # type: ignore[assignment]
        raise ImportError(
            "DLL load failed while importing _internal: "
            "Eine Anwendungssteuerungsrichtlinie hat diese Datei blockiert."
        )

    monkeypatch.setattr(whisper_recognizer.importlib, "import_module", blocked_import)
    monkeypatch.setattr(whisper_recognizer.sys, "platform", "win32")

    _provide_numba_compatibility_if_blocked()

    replacement = sys.modules["numba"]
    assert "numba.np" not in sys.modules
    assert replacement.jit(lambda: "ok")() == "ok"  # type: ignore[attr-defined]
    assert replacement.jit(nopython=True)(lambda: "ok")() == "ok"  # type: ignore[attr-defined]

    for name in tuple(sys.modules):
        if name == "numba" or name.startswith("numba."):
            sys.modules.pop(name, None)
    sys.modules.update(original_numba_modules)


def test_unknown_numba_import_error_is_not_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    def unknown_import(_name: str) -> None:
        raise ImportError("Numba source package is incomplete")

    monkeypatch.setattr(whisper_recognizer.importlib, "import_module", unknown_import)
    monkeypatch.setattr(whisper_recognizer.sys, "platform", "win32")

    with pytest.raises(ImportError, match="source package is incomplete"):
        _provide_numba_compatibility_if_blocked()
