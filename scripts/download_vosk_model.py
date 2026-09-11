"""Lädt nur das kleine deutsche Vosk-Modell für Jarvis' schnellen Wartemodus."""

from __future__ import annotations

import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "vosk-model-small-de-0.15"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
TARGET = PROJECT_ROOT / "models" / MODEL_NAME


def main() -> None:
    if (TARGET / "am").is_dir() and (TARGET / "conf").is_dir():
        print(f"Vosk-Modell ist bereits vorhanden: {TARGET}")
        return
    with tempfile.TemporaryDirectory(prefix="jarvis-vosk-download-") as directory:
        archive = Path(directory) / f"{MODEL_NAME}.zip"
        print(f"Lade {MODEL_NAME} (etwa 45 MB) von der offiziellen Vosk-Quelle ...")
        urllib.request.urlretrieve(MODEL_URL, archive)  # noqa: S310 - feste HTTPS-Quelle
        with zipfile.ZipFile(archive) as package:
            package.extractall(directory)
        extracted = Path(directory) / MODEL_NAME
        if not (extracted / "am").is_dir() or not (extracted / "conf").is_dir():
            raise RuntimeError("Das geladene Archiv enthält kein gültiges Vosk-Modell.")
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(extracted), str(TARGET))
    print("Download abgeschlossen.")


if __name__ == "__main__":
    main()
