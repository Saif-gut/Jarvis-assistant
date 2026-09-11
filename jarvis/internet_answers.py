"""Kurze, quellengestützte Internetantworten ohne Schlüssel oder Audioübertragung."""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


WIKIPEDIA_API_URL = "https://de.wikipedia.org/w/api.php"
DUCKDUCKGO_INSTANT_ANSWER_URL = "https://api.duckduckgo.com/"
LOGGER = logging.getLogger(__name__)

# Nur sprachliche Füll- und Funktionswörter. Diese Menge entscheidet niemals,
# ob eine Frage erlaubt ist; jede nicht lokale Aussage gelangt zur Suche.
_QUERY_STOP_WORDS = frozenset(
    {
        "aber", "als", "also", "am", "an", "auch", "auf", "aus", "bei", "bin",
        "bitte", "da", "das", "dass", "dem", "den", "der", "des", "die", "dir",
        "du", "ein", "eine", "einem", "einen", "einer", "erzahl", "es", "etwas",
        "fur", "gibt", "hat", "haben", "im", "in", "ist", "kann", "kannst",
        "mal", "man", "mein", "mit", "mir", "nach", "oder", "sagen", "sind",
        "uber", "und", "vom", "von", "warum", "was", "welche", "welcher", "welches",
        "wer", "wie", "wo", "wurde", "zu",
    }
)

# Wörter, die bei typischen Personenfragen das gesuchte Subjekt nur beschreiben.
# Sie bleiben für die spätere Auswahl des passenden Antwortsatzes erhalten, sollen
# aber weder als Personenname gelten noch einen Wikipedia-Titel dominieren.
_PERSON_FACT_WORDS = frozenset(
    {
        "alt", "alter", "anzahl", "bisher", "erzielte", "erzielt", "geboren",
        "geburt", "gewann", "gewonnen", "insgesamt", "jahr", "jahre", "karriere",
        "schon", "sein", "seine", "seinem", "seinen", "seiner", "spiel", "spiele",
        "spielt", "tor", "tore", "viel", "viele", "wieviel",
    }
)
_QUESTION_OPENERS = frozenset(
    {"beschreibe", "erzahl", "kann", "kannst", "warum", "was", "welche", "wer", "wie", "wo"}
)


class InternetAnswerError(RuntimeError):
    """Die Internetrecherche konnte keine nutzbare Antwort liefern."""


class InternetUnavailableError(InternetAnswerError):
    """Keine der verwendeten öffentlichen Quellen ist erreichbar."""


class NoInternetAnswerError(InternetAnswerError):
    """Es wurde keine kurze, vertrauenswürdige Antwort gefunden."""


@dataclass(frozen=True)
class InternetAnswer:
    text: str
    source_name: str
    source_url: str


class InternetAnswerService:
    """Sucht zuerst bei Wikipedia und danach in freien Instant Answers."""

    def __init__(
        self,
        fetch_json: Callable[[str, dict[str, str], float], dict[str, Any]] | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._fetch_json = fetch_json or _fetch_json
        self._timeout_seconds = timeout_seconds

    def answer(self, question: str) -> InternetAnswer:
        original_question = " ".join(question.split())
        if not original_question:
            raise NoInternetAnswerError
        search_term = _search_term(original_question)
        started = time.monotonic()

        source_errors: list[InternetUnavailableError] = []
        try:
            answer = self._wikipedia_answer(search_term, original_question)
            if answer:
                LOGGER.info("Internetsuche: %.2f s", time.monotonic() - started)
                return answer
        except InternetUnavailableError as exc:
            source_errors.append(exc)

        try:
            answer = self._instant_answer(search_term, original_question)
            if answer:
                LOGGER.info("Internetsuche: %.2f s", time.monotonic() - started)
                return answer
        except InternetUnavailableError as exc:
            source_errors.append(exc)

        if len(source_errors) == 2:
            raise InternetUnavailableError
        raise NoInternetAnswerError

    def _wikipedia_answer(self, search_term: str, original_question: str) -> InternetAnswer | None:
        search_payload = self._request(
            WIKIPEDIA_API_URL,
            {
                "action": "query",
                "list": "search",
                "srsearch": search_term,
                "srlimit": "5",
                "format": "json",
                "formatversion": "2",
            },
        )
        results = search_payload.get("query", {}).get("search", [])
        if not isinstance(results, list) or not results:
            return None
        title = _matching_title(results, original_question)
        if not title:
            return None

        extract_payload = self._request(
            WIKIPEDIA_API_URL,
            {
                "action": "query",
                "prop": "extracts",
                "titles": title,
                "explaintext": "1",
                "exsectionformat": "plain",
                "format": "json",
                "formatversion": "2",
            },
        )
        pages = extract_payload.get("query", {}).get("pages", [])
        if not isinstance(pages, list) or not pages:
            return None
        extract = str(pages[0].get("extract", "")).strip()
        if not extract:
            return None
        return InternetAnswer(
            text=_select_answer(original_question, extract, title),
            source_name=f"Wikipedia: {title}",
            source_url=f"https://de.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
        )

    def _instant_answer(self, search_term: str, original_question: str) -> InternetAnswer | None:
        payload = self._request(
            DUCKDUCKGO_INSTANT_ANSWER_URL,
            {
                "q": search_term,
                "format": "json",
                "no_html": "1",
                "no_redirect": "1",
                "skip_disambig": "1",
            },
        )
        answer = str(payload.get("AbstractText", "")).strip()
        heading = str(payload.get("Heading", "")).strip()
        source_url = str(payload.get("AbstractURL", "")).strip()
        source_name = str(payload.get("AbstractSource", "")).strip() or "DuckDuckGo Instant Answer"
        if not answer or not source_url or not _answer_matches_question(search_term, heading, answer):
            return None
        return InternetAnswer(
            text=_select_answer(original_question, answer, heading),
            source_name=source_name,
            source_url=source_url,
        )

    def _request(self, url: str, parameters: dict[str, str]) -> dict[str, Any]:
        try:
            return self._fetch_json(url, parameters, self._timeout_seconds)
        except (HTTPError, URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
            raise InternetUnavailableError from exc


def _fetch_json(url: str, parameters: dict[str, str], timeout_seconds: float) -> dict[str, Any]:
    request = Request(
        f"{url}?{urlencode(parameters)}",
        headers={"User-Agent": "JarvisAssistant/1.0 (local personal assistant)"},
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - feste HTTPS-URLs
            return json.load(response)
    except (HTTPError, URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
        raise InternetUnavailableError from exc


def _search_term(question: str) -> str:
    """Bereitet jede Aussage über Inhaltswörter vor, ohne Themen zu begrenzen."""
    name_candidates = _name_candidates(question)
    if name_candidates:
        return " ".join(name_candidates)
    important = _important_words(question)
    return " ".join(important) or _normalized_words(question)


def _matching_title(results: list[dict[str, Any]], question: str) -> str:
    """Bewertet alle gelieferten Treffer nach Titel und Suchausschnitt."""
    query_words = set(_important_words(question))
    if not query_words:
        return ""
    name_candidates = set(_name_candidates(question))
    best_title = ""
    best_score = (False, 0, 0)
    for result in results:
        title = str(result.get("title", "")).strip()
        snippet = str(result.get("snippet", ""))
        title_words = set(_important_words(title))
        snippet_words = set(_important_words(snippet))
        name_matches = name_candidates & title_words
        lexical_score = 3 * len(query_words & title_words) + len(query_words & snippet_words)
        # Die ersten beiden Komponenten haben Vorrang vor dem normalen Overlap:
        # Ein exakter Name im Titel kann daher nie durch zufällige Snippet-Wörter
        # wie "Tore", "erzielt" oder "Karriere" überstimmt werden.
        score = (bool(name_matches), len(name_matches), lexical_score)
        if score > best_score:
            best_title = title
            best_score = score
    return best_title if best_score[2] else ""


def _name_candidates(question: str) -> tuple[str, ...]:
    """Erkennt Eigennamen aus Originalschreibung oder typischen Personenfragen."""
    candidates: list[str] = []
    original_words = re.findall(r"[^\W_]+", question, flags=re.UNICODE)
    for index, original_word in enumerate(original_words):
        normalized = _normalized_words(original_word)
        if (
            normalized
            and normalized not in _QUERY_STOP_WORDS
            and normalized not in _PERSON_FACT_WORDS
            and original_word[0].isupper()
            and (index > 0 or normalized not in _QUESTION_OPENERS)
        ):
            candidates.append(normalized)

    if not candidates:
        important = _important_words(question)
        if set(important) & _PERSON_FACT_WORDS:
            candidates.extend(word for word in important if word not in _PERSON_FACT_WORDS)

    return tuple(dict.fromkeys(candidates))


def _select_answer(question: str, source_text: str, subject: str = "") -> str:
    """Wählt allgemein die ein bis drei Sätze mit dem stärksten Fragebezug."""
    sentences = _sentences(source_text)
    if not sentences:
        return _short_answer(source_text)

    if _is_summary_request(question):
        return _join_short(sentences[:2])

    question_words = set(_important_words(question))
    focus_words = question_words - set(_important_words(subject))
    if focus_words:
        question_words = focus_words
    asks_for_quantity = bool(set(_normalized_words(question).split()) & {"anzahl", "viel", "viele", "wieviel"})
    asks_for_age = "alt" in _normalized_words(question).split()
    scored: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        sentence_words = set(_important_words(sentence))
        score = 2 * len(question_words & sentence_words)
        if asks_for_quantity and re.search(r"\d", sentence):
            score += 2
        if asks_for_age and (
            set(sentence_words) & {"alter", "geboren", "geburt", "jahre"} or re.search(r"\b\d{4}\b", sentence)
        ):
            score += 2
        scored.append((score, index, sentence))

    best_score = max((item[0] for item in scored), default=0)
    if best_score <= 0:
        return _join_short(sentences[:2])
    selected = sorted((item for item in scored if item[0] == best_score), key=lambda item: item[1])[:3]
    selected_indexes = {item[1] for item in selected}
    for _, index, sentence in selected:
        if re.search(r"\d", sentence) and index > 0 and re.search(
            r"\b(?:stand|aktualisiert)\b", sentences[index - 1], flags=re.IGNORECASE
        ):
            selected_indexes.add(index - 1)
    return _join_short([sentences[index] for index in sorted(selected_indexes)[:3]])


def _is_summary_request(question: str) -> bool:
    words = set(_normalized_words(question).split())
    return bool(words & {"erzahl", "beschreibe", "zusammenfassung", "uberblick"})


def _sentences(text: str) -> list[str]:
    compact = re.sub(r"\[[^\]]+\]", "", text)
    protected = re.sub(
        r"(\d)\.(?=\s+(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\b)",
        r"\1<ORD>",
        compact,
        flags=re.IGNORECASE,
    )
    parts = re.split(r"(?<=[.!?])\s+|\n+", protected)
    return [
        " ".join(part.replace("<ORD>", ".").split())
        for part in parts
        if part.strip() and not re.fullmatch(r"=+.*=+", part.strip())
    ]


def _join_short(sentences: list[str], limit: int = 420) -> str:
    answer = " ".join(sentences[:3]).strip()
    return _short_answer(answer, limit=limit)


def _short_answer(text: str, limit: int = 420) -> str:
    compact = " ".join(re.sub(r"\[[^\]]+\]", "", text).split())
    if len(compact) <= limit:
        return compact
    shortened = compact[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{shortened}."


def _answer_matches_question(question: str, heading: str, answer: str) -> bool:
    query_words = set(_important_words(question))
    candidate_words = set(_important_words(f"{heading} {answer}"))
    return bool(query_words and query_words & candidate_words)


def _important_words(text: str) -> tuple[str, ...]:
    return tuple(word for word in _normalized_words(text).split() if word not in _QUERY_STOP_WORDS)


def _normalized_words(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", without_marks))
