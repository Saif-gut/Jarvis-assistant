"""Sprachbefehle erkennen und in lokale Aktionen übersetzen."""

from __future__ import annotations

import re
import random
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Callable

from .config import DEFAULT_WEATHER_CITY
from .pc_functions import StorageInfo, describe_storage, get_system_drive_storage
from .profile import PersonalProfile
from .internet_answers import (
    InternetAnswerService,
    InternetUnavailableError,
    NoInternetAnswerError,
)
from .ollama_client import LOCAL_AI_IDENTITY, OllamaClient, OllamaError
from .weather import (
    WeatherCityNotConfiguredError,
    WeatherLocationNotFoundError,
    WeatherService,
    WeatherUnavailableError,
    describe_forecast,
)


class Intent(Enum):
    SMALLTALK = auto()
    AI_IDENTITY = auto()
    HELP = auto()
    TIME = auto()
    DATE = auto()
    STORAGE = auto()
    WEATHER_TODAY = auto()
    WEATHER_TOMORROW = auto()
    EXIT = auto()
    UNKNOWN = auto()


@dataclass(frozen=True)
class CommandResult:
    response: str
    should_exit: bool = False
    source_name: str | None = None
    source_url: str | None = None


def normalize_text(text: str) -> str:
    """Normalisiert erkannte Sprache für Protokollierung und Befehlsauswahl."""
    normalized = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", without_marks))


EXIT_COMMANDS = frozenset(
    {
        "beenden",
        "stopp",
        "auf wiedersehen",
        "das war s",
        "ende",
        "tschuss jarvis",
    }
)


def is_exit_command(text: str) -> bool:
    """Prüft nur vollständige, von Whisper erkannte Beenden-Aussagen."""
    return normalize_text(text) in EXIT_COMMANDS


def select_intent(text: str) -> Intent:
    normalized = normalize_text(text)
    words = set(normalized.split())

    if _asks_about_ai_identity(normalized):
        return Intent.AI_IDENTITY
    if normalized in _SMALLTALK_RESPONSES or _is_wellbeing_question(normalized):
        return Intent.SMALLTALK

    if is_exit_command(text):
        return Intent.EXIT
    if "hilfe" in words or ({"was", "kannst"} <= words) or ({"was", "kann"} <= words):
        return Intent.HELP
    if "wetter" in words or ({"warm", "morgen"} <= words) or ({"temperatur", "morgen"} <= words):
        return Intent.WEATHER_TOMORROW if "morgen" in words else Intent.WEATHER_TODAY
    if words & {"speicher", "speicherplatz", "festplatte", "laufwerk"}:
        return Intent.STORAGE
    if words & {"datum", "wochentag"} or ({"welcher", "tag"} <= words):
        return Intent.DATE
    if words & {"uhrzeit", "uhr", "zeit", "spat", "spet"}:
        return Intent.TIME
    return Intent.UNKNOWN


_SMALLTALK_RESPONSES = {
    "wie geht es dir": "Mir geht es gut, danke. Wie kann ich helfen?",
    "hallo": "Hallo. Wie kann ich helfen?",
    "guten morgen": "Guten Morgen. Wie kann ich helfen?",
    "guten tag": "Guten Tag. Wie kann ich helfen?",
    "guten abend": "Guten Abend. Wie kann ich helfen?",
    "danke": "Gern geschehen.",
    "wer bist du": LOCAL_AI_IDENTITY,
    "was machst du": "Ich helfe dir mit Alltagsfragen, Wetter und kurzen Wissensfragen.",
    "erzahl mir etwas": "Gern. Frag mich einfach nach einem Thema, das dich interessiert.",
    "was kannst du alles": "Ich kann mit dir plaudern und Fragen zu Wissen, Wetter, Uhrzeit, Datum und Speicher beantworten.",
    "wie lauft es": "Bei mir läuft alles gut. Wobei kann ich dir helfen?",
    "alles gut": "Danke, bei mir ist alles gut. Wie kann ich dir helfen?",
    "vielen dank": "Sehr gern.",
}

_WELLBEING_RESPONSES = (
    "Mir geht es gut, danke. Wie geht es dir?",
    "Sehr gut, danke der Nachfrage. Und selbst?",
    "Mir geht es bestens. Was kann ich für dich tun?",
    "Alles läuft gut. Wie geht es dir heute?",
    "Danke, mir geht es gut. Wobei kann ich dir helfen?",
    "Mir geht es prima. Was steht heute an?",
)


class CommandExecutor:
    def __init__(
        self,
        now: Callable[[], datetime] = datetime.now,
        storage_provider: Callable[[], StorageInfo] = get_system_drive_storage,
        weather_service: WeatherService | None = None,
        weather_city: str | None = DEFAULT_WEATHER_CITY,
        internet_answer_service: InternetAnswerService | None = None,
        personal_profile: PersonalProfile | None = None,
        ollama_client: OllamaClient | None = None,
    ) -> None:
        self._now = now
        self._storage_provider = storage_provider
        self._weather_service = weather_service or WeatherService()
        self._weather_city = weather_city
        self._internet_answer_service = internet_answer_service or InternetAnswerService()
        self._personal_profile = personal_profile or PersonalProfile.load()
        self._ollama_client = ollama_client
        self._last_topic: str | None = None
        self._last_wellbeing_response: str | None = None

    def execute(self, text: str) -> CommandResult:
        intent = select_intent(text)

        if intent is Intent.HELP:
            return CommandResult(
                "Du kannst nach Uhrzeit, Datum, Speicherplatz oder dem Wetter heute und morgen fragen. "
                "Du kannst mich auch beenden."
            )
        if intent is Intent.TIME:
            current = self._now()
            return CommandResult(f"Es ist {current:%H:%M} Uhr.")
        if intent is Intent.DATE:
            return CommandResult(_format_german_date(self._now()))
        if intent is Intent.STORAGE:
            return CommandResult(describe_storage(self._storage_provider()))
        if intent in (Intent.WEATHER_TODAY, Intent.WEATHER_TOMORROW):
            return self._weather_response(intent)
        if intent is Intent.EXIT:
            return CommandResult("Auf Wiedersehen.", should_exit=True)
        if intent is Intent.AI_IDENTITY:
            return CommandResult(LOCAL_AI_IDENTITY)
        if _requests_device_action(text):
            return CommandResult(
                "Dabei kann ich dir nur erklären oder nachfragen, aber keine Dateien, Programme oder Windows-Einstellungen verändern."
            )
        profile_response = self._personal_profile.answer(text)
        if profile_response is not None:
            return CommandResult(profile_response)
        if intent is Intent.SMALLTALK:
            if _is_wellbeing_question(normalize_text(text)):
                return CommandResult(self._wellbeing_response())
            return CommandResult(_SMALLTALK_RESPONSES[normalize_text(text)])

        if self._ollama_client is not None and not _requires_internet_answer(text):
            return self._ollama_response(text)

        search_question = _with_conversation_context(text, self._last_topic)
        result = self._internet_response(search_question)
        if result is not None and result.source_url:
            self._last_topic = _topic_from_question(text)
            return result
        if self._ollama_client is not None and not _is_current_question(text):
            return self._ollama_response(text)
        return CommandResult("Dazu habe ich gerade keine zuverlässige Antwort gefunden.")

    def _wellbeing_response(self) -> str:
        choices = [
            response for response in _WELLBEING_RESPONSES
            if response != self._last_wellbeing_response
        ]
        response = random.choice(choices)
        self._last_wellbeing_response = response
        return response

    def _weather_response(self, intent: Intent) -> CommandResult:
        day_index = 0 if intent is Intent.WEATHER_TODAY else 1
        day_label = "heute" if day_index == 0 else "morgen"
        try:
            forecast = self._weather_service.get_daily_forecast(self._weather_city, day_index)
        except WeatherCityNotConfiguredError:
            return CommandResult(
                "Für das Wetter brauche ich eine Standardstadt. "
                "Die Voreinstellung ist Berlin, 10115; "
                "du kannst sie mit JARVIS_WEATHER_CITY überschreiben."
            )
        except WeatherLocationNotFoundError:
            return CommandResult(
                "Deine eingestellte Wetterstadt konnte ich nicht finden. "
                "Bitte prüfe JARVIS_WEATHER_CITY."
            )
        except WeatherUnavailableError:
            return CommandResult(
                "Ich kann Wetterdaten gerade nicht abrufen. Bitte prüfe die Internetverbindung."
            )
        return CommandResult(describe_forecast(forecast, day_label))

    def _internet_response(self, question: str) -> CommandResult | None:
        try:
            answer = self._internet_answer_service.answer(question)
        except (InternetUnavailableError, NoInternetAnswerError):
            return None
        return CommandResult(
            response=answer.text,
            source_name=answer.source_name,
            source_url=answer.source_url,
        )

    def _ollama_response(self, question: str) -> CommandResult:
        if self._ollama_client is None:
            return CommandResult("Dazu habe ich gerade keine zuverlässige Antwort gefunden.")
        try:
            return CommandResult(self._ollama_client.answer(question))
        except OllamaError:
            return CommandResult(
                "Mein lokales Sprachmodell ist gerade nicht erreichbar. "
                "Die festen Jarvis-Befehle funktionieren weiterhin."
            )


def _requests_device_action(text: str) -> bool:
    words = set(normalize_text(text).split())
    action_words = {"offne", "starte", "losche", "andere", "andern", "installiere"}
    target_words = {"datei", "dateien", "programm", "programme", "windows", "einstellungen"}
    return bool(words & action_words and words & target_words)


def _requires_internet_answer(text: str) -> bool:
    normalized = normalize_text(text)
    factual_openers = (
        "wer ist ", "wer war ", "wer hat ", "was ist ", "was sind ", "wann ",
        "wo liegt ", "wie alt ", "wie viele ", "wie viel ", "erzahl mir etwas uber ",
    )
    return _is_current_question(text) or normalized.startswith(factual_openers)


def _is_current_question(text: str) -> bool:
    words = set(normalize_text(text).split())
    return bool(
        words
        & {
            "aktuell", "aktuelle", "aktuellen", "derzeit", "gerade", "heute", "jetzt",
            "kurs", "kurse", "nachrichten", "neueste", "neuesten", "preis", "preise",
            "stand", "wahlergebnis", "wahlergebnisse",
        }
    )


def _is_wellbeing_question(normalized: str) -> bool:
    """Erkennt frei formulierte Fragen nach Jarvis' Befinden lokal."""
    words = set(normalized.split())
    addressed_to_jarvis = bool(words & {"dir", "dich", "dein", "selbst"})
    wellbeing_word = any(
        word.startswith(("geh", "fuhl", "befind", "lauf")) for word in words
    ) or "gut" in words
    short_wellbeing = any(word.startswith(("geh", "fuhl", "lauf")) for word in words)
    return wellbeing_word and (addressed_to_jarvis or (short_wellbeing and len(words) <= 4))


def _asks_about_ai_identity(normalized: str) -> bool:
    """Hält technische Identitätsangaben lokal, eindeutig und konfigurationsnah."""
    if normalized == "wer bist du":
        return True
    words = set(normalized.split())
    addressed_to_jarvis = bool(words & {"du", "dir", "dein", "deine", "deiner"})
    identity_terms = {"ai", "ki", "identitat", "modell", "sprachmodell", "ollama", "openai", "chatgpt"}
    asks_if_local = "lokal" in words and any(word.startswith("lauf") for word in words)
    return addressed_to_jarvis and (bool(words & identity_terms) or asks_if_local)


def _with_conversation_context(question: str, last_topic: str | None) -> str:
    """Ergänzt nur eindeutig stellvertretende Folgefragen um das letzte Thema."""
    if not last_topic:
        return question
    words = set(normalize_text(question).split())
    if words & {"er", "sie", "es", "dieser", "diese", "dieses"}:
        return f"{question} {last_topic}"
    return question


def _topic_from_question(question: str) -> str:
    words = normalize_text(question).split()
    ignored = {
        "erzahl", "mir", "etwas", "uber", "wer", "was", "ist", "wie", "warum", "viele", "tore",
        "hat", "in", "der", "die", "das", "ein", "eine", "funktioniert", "bedeutet", "ganzen", "karriere",
    }
    topic = [word for word in words if word not in ignored]
    return " ".join(topic[-3:])


def _format_german_date(value: datetime) -> str:
    weekdays = (
        "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"
    )
    months = (
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember",
    )
    return f"Heute ist {weekdays[value.weekday()]}, der {value.day}. {months[value.month - 1]} {value.year}."
