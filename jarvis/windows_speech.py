"""Windows-Sprachsynthese über klassische SAPI- und OneCore-Stimmen."""

from __future__ import annotations

import ctypes
import locale
import os
import subprocess
import time
import wave
import winreg
import winsound
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal


VoiceEngine = Literal["classic", "onecore"]


@dataclass(frozen=True)
class WindowsVoice:
    name: str
    language: str
    engine: VoiceEngine


class WindowsSpeechError(RuntimeError):
    """Fehler der lokalen Windows-Sprachsynthese."""


_VOICE_REGISTRY_PATHS: tuple[tuple[VoiceEngine, str], ...] = (
    ("onecore", r"SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens"),
    ("classic", r"SOFTWARE\Microsoft\Speech\Voices\Tokens"),
)


POWERSHELL_SYNTHESIZER = r"""
$ErrorActionPreference = 'Stop'
$voiceName = $env:JARVIS_TTS_VOICE
$text = $env:JARVIS_TTS_TEXT
$outputPath = $env:JARVIS_TTS_WAVE
$engine = $env:JARVIS_TTS_ENGINE

if ($engine -eq 'classic') {
    Add-Type -AssemblyName System.Speech
    $synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
    try {
        $synth.SelectVoice($voiceName)
        $synth.SetOutputToWaveFile($outputPath)
        $synth.Speak($text)
    }
    finally {
        $synth.Dispose()
    }
    exit 0
}

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]

function Await-Operation($operation, [Type]$resultType) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq 'AsTask' -and
            $_.IsGenericMethod -and
            $_.GetParameters().Count -eq 1 -and
            $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
        } |
        Select-Object -First 1
    $task = $method.MakeGenericMethod($resultType).Invoke($null, @($operation))
    $task.Wait()
    return $task.Result
}

$synth = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::new()
$voice = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices |
    Where-Object DisplayName -eq $voiceName |
    Select-Object -First 1
if (-not $voice) {
    throw "OneCore-Stimme nicht gefunden: $voiceName"
}

$synth.Voice = $voice
$speechStream = Await-Operation ($synth.SynthesizeTextToStreamAsync($text)) `
    ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
$input = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($speechStream)
$output = [System.IO.File]::Create($outputPath)
try {
    $input.CopyTo($output)
}
finally {
    $output.Dispose()
    $input.Dispose()
    $speechStream.Dispose()
    $synth.Dispose()
}
"""


MCI_MEDIA_TYPE = "mpegvideo"
MCI_ALIAS = "jarvis_online_tts"


def installed_windows_voices() -> tuple[WindowsVoice, ...]:
    voices: list[WindowsVoice] = []
    for engine, registry_path in _VOICE_REGISTRY_PATHS:
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                registry_path,
                access=winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as tokens:
                for index in range(winreg.QueryInfoKey(tokens)[0]):
                    token_name = winreg.EnumKey(tokens, index)
                    with winreg.OpenKey(tokens, token_name + r"\Attributes") as attributes:
                        name = str(winreg.QueryValueEx(attributes, "Name")[0])
                        language_code = str(winreg.QueryValueEx(attributes, "Language")[0])
                    voices.append(
                        WindowsVoice(
                            name=name,
                            language=_language_from_lcid(language_code),
                            engine=engine,
                        )
                    )
        except OSError:
            continue
    return tuple(voices)


def find_installed_voice(name: str) -> WindowsVoice | None:
    requested = name.casefold().strip()
    return next(
        (voice for voice in installed_windows_voices() if voice.name.casefold() == requested),
        None,
    )


def default_fallback_voice() -> WindowsVoice | None:
    voices = installed_windows_voices()
    return next((voice for voice in voices if voice.language.casefold().startswith("de")), None) or (
        voices[0] if voices else None
    )


def synthesize_to_wave(voice: WindowsVoice, text: str, target: Path) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "JARVIS_TTS_ENGINE": voice.engine,
            "JARVIS_TTS_VOICE": voice.name,
            "JARVIS_TTS_TEXT": text,
            "JARVIS_TTS_WAVE": str(target),
        }
    )
    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                POWERSHELL_SYNTHESIZER,
            ],
            check=True,
            env=environment,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise WindowsSpeechError(f"Stimme '{voice.name}' konnte nicht synthetisieren.") from exc


def play_wave(
    path: Path, generation: int, was_stopped: Callable[[int], bool]
) -> None:
    try:
        with wave.open(str(path), "rb") as audio:
            if audio.getsampwidth() != 2:
                raise WindowsSpeechError(
                    f"Nicht unterstützte Samplebreite: {audio.getsampwidth() * 8} Bit"
                )
            duration = audio.getnframes() / audio.getframerate()
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            if was_stopped(generation):
                winsound.PlaySound(None, winsound.SND_PURGE)
                return
            time.sleep(0.05)
    except (OSError, wave.Error, RuntimeError) as exc:
        if isinstance(exc, WindowsSpeechError):
            raise
        raise WindowsSpeechError("Die Windows-Audioausgabe ist fehlgeschlagen.") from exc


def play_media(
    path: Path, generation: int, was_stopped: Callable[[int], bool]
) -> None:
    """Spielt eine MP3 über die aktuelle Windows-Standardausgabe ab."""
    try:
        _mci_command(f'open "{path}" type {MCI_MEDIA_TYPE} alias {MCI_ALIAS}')
        try:
            _mci_command(f"play {MCI_ALIAS}")
            while True:
                if was_stopped(generation):
                    _mci_command(f"stop {MCI_ALIAS}")
                    return
                try:
                    is_playing = (
                        _mci_command(f"status {MCI_ALIAS} mode", response_length=32)
                        .strip()
                        .casefold()
                        == "playing"
                    )
                except RuntimeError:
                    if was_stopped(generation):
                        return
                    raise
                if not is_playing:
                    break
                time.sleep(0.05)
        finally:
            try:
                _mci_command(f"close {MCI_ALIAS}")
            except RuntimeError:
                if not was_stopped(generation):
                    raise
    except (OSError, RuntimeError) as exc:
        raise WindowsSpeechError("Die Windows-Audioausgabe ist fehlgeschlagen.") from exc


def stop_playback() -> None:
    """Stoppt eine aktive Jarvis-Ausgabe, falls eine läuft."""
    try:
        _mci_command(f"stop {MCI_ALIAS}")
        _mci_command(f"close {MCI_ALIAS}")
    except (OSError, RuntimeError):
        pass
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except RuntimeError:
        pass


def _mci_command(command: str, response_length: int = 0) -> str:
    winmm = ctypes.WinDLL("winmm")
    response = ctypes.create_unicode_buffer(response_length) if response_length else None
    result = winmm.mciSendStringW(command, response, response_length, None)
    if result:
        error_text = ctypes.create_unicode_buffer(256)
        winmm.mciGetErrorStringW(result, error_text, len(error_text))
        raise RuntimeError(error_text.value or f"MCI-Fehler {result}")
    return response.value if response is not None else ""


def _language_from_lcid(value: str) -> str:
    try:
        return locale.windows_locale.get(int(value, 16), value).replace("_", "-")
    except ValueError:
        return value
