"""Abfragen des lokalen PCs ohne Seiteneffekte."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StorageInfo:
    free_bytes: int
    total_bytes: int


def system_drive() -> Path:
    return Path(os.environ.get("SystemDrive", "C:") + "\\")


def get_system_drive_storage() -> StorageInfo:
    usage = shutil.disk_usage(system_drive())
    return StorageInfo(free_bytes=usage.free, total_bytes=usage.total)


def bytes_to_gib(byte_count: int) -> float:
    if byte_count < 0:
        raise ValueError("byte_count darf nicht negativ sein")
    return byte_count / (1024**3)


def describe_storage(storage: StorageInfo) -> str:
    free_gib = bytes_to_gib(storage.free_bytes)
    total_gib = bytes_to_gib(storage.total_bytes)
    drive = system_drive().drive or "C:"
    return (
        f"Ich meine das Windows-Systemlaufwerk {drive}. Dort sind {free_gib:.1f} Gigabyte "
        f"von insgesamt {total_gib:.1f} Gigabyte frei."
    )
