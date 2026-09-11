"""Online-Sprachsynthese mit edge-tts ohne dauerhafte Audiodateien."""

from __future__ import annotations

from pathlib import Path

import edge_tts


class OnlineSpeechError(RuntimeError):
    """Die Online-Sprachsynthese war nicht erreichbar oder unvollständig."""


def synthesize_to_mp3(voice_name: str, text: str, target: Path) -> None:
    """Synthetisiert Text in eine kurzlebige MP3-Datei."""
    try:
        edge_tts.Communicate(text, voice=voice_name, rate="+5%").save_sync(str(target))
    except Exception as exc:
        raise OnlineSpeechError("Die Online-Sprachsynthese ist nicht verfügbar.") from exc

    if not target.is_file() or target.stat().st_size == 0:
        raise OnlineSpeechError("Die Online-Sprachsynthese lieferte keine Audiodaten.")
