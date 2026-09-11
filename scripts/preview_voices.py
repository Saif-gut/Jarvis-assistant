"""Spielt die installierten SAPI-/OneCore-Stimmen über das Headset vor.

Dieses Hilfsskript ändert Jarvis' Konfiguration nicht. Synthetisierte WAV-Daten
liegen nur in einem temporären Ordner und werden beim Beenden gelöscht.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import sounddevice as sd

from jarvis.windows_speech import WindowsVoice, play_wave, synthesize_to_wave


SENTENCE = "Guten Abend. Ich bin Jarvis. Wie kann ich Ihnen helfen?"
VOICES = (
    (1, "Hedda", "classic", "Microsoft Hedda Desktop"),
    (2, "Katja", "onecore", "Microsoft Katja"),
    (3, "Stefan", "onecore", "Microsoft Stefan"),
    (4, "Zira", "classic", "Microsoft Zira Desktop"),
)
def default_output_device() -> int:
    default_device = sd.default.device
    return int(default_device[1])


def main() -> int:
    device_index = default_output_device()
    device_name = sd.query_devices(device_index)["name"]
    print(f"Windows-Standardausgabe: {device_name}")

    with tempfile.TemporaryDirectory(prefix="jarvis-voice-preview-") as temporary:
        temporary_path = Path(temporary)
        for number, short_name, engine, system_name in VOICES:
            print(f"{number}. {short_name}", flush=True)
            wave_path = temporary_path / f"{number}-{short_name.casefold()}.wav"
            voice = WindowsVoice(name=system_name, language="", engine=engine)
            synthesize_to_wave(voice, f"{short_name}. {SENTENCE}", wave_path)
            play_wave(wave_path, 0, lambda _generation: False)
            time.sleep(0.4)

    print("Vorschau abgeschlossen; temporäre Sprachdaten wurden gelöscht.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
