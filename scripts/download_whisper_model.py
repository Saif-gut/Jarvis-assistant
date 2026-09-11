"""Lädt das lokale Whisper-Modell in den von Jarvis erwarteten Ordner."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "small"
MODEL_DIRECTORY = PROJECT_ROOT / "models" / "whisper"


def main() -> None:
    if (MODEL_DIRECTORY / f"{MODEL_NAME}.pt").is_file():
        print(f"Whisper-Modell ist bereits vorhanden: {MODEL_DIRECTORY}")
        return
    MODEL_DIRECTORY.mkdir(parents=True, exist_ok=True)
    import whisper

    print(f"Lade das Whisper-Modell '{MODEL_NAME}' nach {MODEL_DIRECTORY} ...")
    whisper.load_model(MODEL_NAME, device="cpu", download_root=str(MODEL_DIRECTORY))
    print("Download abgeschlossen.")


if __name__ == "__main__":
    main()
