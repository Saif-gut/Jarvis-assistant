"""Lokales persönliches Profil ohne Netzwerkzugriff."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .config import PROJECT_ROOT


PROFILE_PATH = PROJECT_ROOT / "jarvis.profile.json"
_MISSING = "Diese Information ist noch nicht in deinem lokalen Profil hinterlegt."


@dataclass(frozen=True)
class PersonalProfile:
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    birth_date: str | None = None
    birth_place: str | None = None
    residence: str | None = None
    interests: str | None = None

    @classmethod
    def load(cls, path: Path = PROFILE_PATH) -> "PersonalProfile":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        return cls(**{field: _text_or_none(data.get(field)) for field in cls.__annotations__})

    def answer(self, question: str) -> str | None:
        """Antwortet nur auf lokale Profilfragen und gibt niemals Daten weiter."""
        normalized = _normalize_text(question)
        if normalized == "wer bin ich":
            values = (self.full_name, self.birth_date, self.birth_place, self.residence, self.interests)
            if not all(values):
                return _MISSING
            return (
                f"Du bist {self.full_name}. Du hast am {self.birth_date} Geburtstag, wurdest in "
                f"{self.birth_place} geboren, wohnst in {self.residence} und interessierst dich dafür, "
                f"{self.interests}."
            )
        if normalized in {"wie heisse ich", "wie ist mein name", "was ist mein name"}:
            return f"Du heißt {self.full_name}." if self.full_name else _MISSING
        if normalized in {"wann habe ich geburtstag", "wann ist mein geburtstag"}:
            return f"Dein Geburtstag ist am {self.birth_date}." if self.birth_date else _MISSING
        if normalized == "wo wurde ich geboren":
            return f"Du wurdest in {self.birth_place} geboren." if self.birth_place else _MISSING
        if normalized == "wo wohne ich":
            return f"Du wohnst in {self.residence}." if self.residence else _MISSING
        if normalized in {"was sind meine interessen", "welche interessen habe ich"}:
            return f"Deine Interessen sind {self.interests}." if self.interests else _MISSING
        if _looks_personal(normalized):
            return _MISSING
        return None


def _text_or_none(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", without_marks))


def _looks_personal(normalized: str) -> bool:
    words = set(normalized.split())
    return bool(words & {"mein", "meine", "meinen", "meiner"}) or (
        "ich" in words
        and bool(
            words
            & {
                "alt", "geboren", "wohne", "interessen", "hobby", "hobbys", "schule", "arbeit",
                "familie", "eltern", "geschwister", "lieblingsfarbe", "lieblingsessen", "augenfarbe",
            }
        )
    )
