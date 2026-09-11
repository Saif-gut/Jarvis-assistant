from urllib.error import URLError

import pytest

from jarvis.internet_answers import (
    DUCKDUCKGO_INSTANT_ANSWER_URL,
    WIKIPEDIA_API_URL,
    InternetAnswerService,
    InternetUnavailableError,
    NoInternetAnswerError,
)


def test_internet_answer_prefers_german_wikipedia() -> None:
    requests: list[tuple[str, dict[str, str]]] = []

    def fetch(url: str, parameters: dict[str, str], _timeout: float) -> dict:
        requests.append((url, parameters))
        if parameters.get("list") == "search":
            return {"query": {"search": [{"title": "Berlin"}]}}
        return {
            "query": {
                "pages": [
                    {
                        "title": "Berlin",
                        "extract": "Berlin ist die Hauptstadt Deutschlands.",
                    }
                ]
            }
        }

    answer = InternetAnswerService(fetch_json=fetch).answer("Was ist Berlin")

    assert answer.source_name == "Wikipedia: Berlin"
    assert answer.source_url.endswith("/Berlin")
    assert "Gemeinde" in answer.text
    assert [request[0] for request in requests] == [WIKIPEDIA_API_URL, WIKIPEDIA_API_URL]


def test_internet_answer_uses_instant_answer_when_wikipedia_has_no_hit() -> None:
    def fetch(url: str, _parameters: dict[str, str], _timeout: float) -> dict:
        if url == WIKIPEDIA_API_URL:
            return {"query": {"search": []}}
        assert url == DUCKDUCKGO_INSTANT_ANSWER_URL
        return {
            "Heading": "Beispielthema",
            "AbstractText": "Beispielthema ist eine kurze Antwort aus einer öffentlichen Quelle.",
            "AbstractSource": "Beispielquelle",
            "AbstractURL": "https://example.test/antwort",
        }

    answer = InternetAnswerService(fetch_json=fetch).answer("Was ist Beispielthema")

    assert answer.source_name == "Beispielquelle"
    assert answer.source_url == "https://example.test/antwort"


def test_internet_answer_reports_no_good_result() -> None:
    def fetch(_url: str, _parameters: dict[str, str], _timeout: float) -> dict:
        return {"query": {"search": []}}

    with pytest.raises(NoInternetAnswerError):
        InternetAnswerService(fetch_json=fetch).answer("Unklare Frage")


def test_internet_answer_reports_network_failure() -> None:
    def fetch(*_args: object) -> dict:
        raise URLError("offline")

    with pytest.raises(InternetUnavailableError):
        InternetAnswerService(fetch_json=fetch).answer("Unklare Frage")


def test_wikipedia_strips_question_filler_and_selects_albert_einstein() -> None:
    requests: list[dict[str, str]] = []

    def fetch(_url: str, parameters: dict[str, str], _timeout: float) -> dict:
        requests.append(parameters)
        if parameters.get("list") == "search":
            return {
                "query": {
                    "search": [
                        {"title": "Zebrarätsel"},
                        {"title": "Albert Einstein"},
                    ]
                }
            }
        return {
            "query": {
                "pages": [
                    {
                        "title": "Albert Einstein",
                        "extract": "Albert Einstein war ein deutscher theoretischer Physiker.",
                    }
                ]
            }
        }

    answer = InternetAnswerService(fetch_json=fetch).answer("Erzähl mir, wer Albert Einstein ist")

    assert requests[0]["srsearch"] == "albert einstein"
    assert answer.source_name == "Wikipedia: Albert Einstein"
    assert "theoretischer Physiker" in answer.text


def test_wikipedia_accepts_matching_marie_curie_title() -> None:
    def fetch(_url: str, parameters: dict[str, str], _timeout: float) -> dict:
        if parameters.get("list") == "search":
            return {"query": {"search": [{"title": "Marie Curie"}]}}
        return {
            "query": {
                "pages": [
                    {"title": "Marie Curie", "extract": "Marie Curie war eine Physikerin und Chemikerin."}
                ]
            }
        }

    answer = InternetAnswerService(fetch_json=fetch).answer("Kannst du mir sagen, wer Marie Curie ist")

    assert answer.source_name == "Wikipedia: Marie Curie"


def test_wikipedia_name_match_beats_generic_football_snippet_overlap() -> None:
    requests: list[dict[str, str]] = []

    def fetch(_url: str, parameters: dict[str, str], _timeout: float) -> dict:
        requests.append(parameters)
        if parameters.get("list") == "search":
            return {
                "query": {
                    "search": [
                        {
                            "title": "Kylian Mbappé",
                            "snippet": "Viele Tore erzielt, schon eine erfolgreiche Karriere.",
                        },
                        {
                            "title": "Neymar",
                            "snippet": "Brasilianischer Fußballspieler.",
                        },
                    ]
                }
            }
        return {
            "query": {
                "pages": [
                    {
                        "title": "Neymar",
                        "extract": "Neymar ist ein brasilianischer Fußballspieler.",
                    }
                ]
            }
        }

    answer = InternetAnswerService(fetch_json=fetch).answer(
        "wie viele tore erzielt der neymar schon in seiner karriere"
    )

    assert requests[0]["srsearch"] == "neymar"
    assert answer.source_name == "Wikipedia: Neymar"


def test_unmatched_wikipedia_title_uses_instant_answer() -> None:
    def fetch(url: str, parameters: dict[str, str], _timeout: float) -> dict:
        if url == WIKIPEDIA_API_URL:
            if parameters.get("list") == "search":
                return {"query": {"search": [{"title": "Zebrarätsel"}]}}
            raise AssertionError("Ein unpassender Wikipedia-Titel darf nicht geladen werden.")
        return {
            "AbstractText": "Albert Einstein war ein theoretischer Physiker.",
            "AbstractSource": "Beispielquelle",
            "AbstractURL": "https://example.test/einstein",
        }

    answer = InternetAnswerService(fetch_json=fetch).answer("Wer ist Albert Einstein")

    assert answer.source_name == "Beispielquelle"


def test_instant_answer_rejects_an_unrelated_result() -> None:
    def fetch(url: str, _parameters: dict[str, str], _timeout: float) -> dict:
        if url == WIKIPEDIA_API_URL:
            return {"query": {"search": []}}
        return {
            "Heading": "Zebrarätsel",
            "AbstractText": "Das Zebrarätsel ist ein Logikrätsel.",
            "AbstractSource": "Beispielquelle",
            "AbstractURL": "https://example.test/zebra",
        }

    with pytest.raises(NoInternetAnswerError):
        InternetAnswerService(fetch_json=fetch).answer("Wer ist Albert Einstein")


@pytest.mark.parametrize(
    ("question", "title", "extract"),
    [
        ("Erzähl mir etwas über Albert Einstein", "Albert Einstein", "Albert Einstein war ein Physiker."),
        ("Warum ist der Himmel blau?", "Himmel", "Der Himmel erscheint durch Streuung von Licht blau."),
        ("Wie funktioniert ein Computer?", "Computer", "Ein Computer verarbeitet Daten nach Programmen."),
        ("Was bedeutet Demokratie?", "Demokratie", "Demokratie ist eine Form politischer Herrschaft."),
    ],
)
def test_free_questions_select_a_relevant_wikipedia_result(
    question: str, title: str, extract: str
) -> None:
    def fetch(_url: str, parameters: dict[str, str], _timeout: float) -> dict:
        if parameters.get("list") == "search":
            return {"query": {"search": [{"title": "Unpassendes Thema"}, {"title": title}]}}
        return {"query": {"pages": [{"title": title, "extract": extract}]}}

    answer = InternetAnswerService(fetch_json=fetch).answer(question)

    assert answer.source_name == f"Wikipedia: {title}"
    assert answer.text == extract


@pytest.mark.parametrize(
    ("question", "extract", "expected"),
    [
        (
            "Wie viele Tore hat Messi?",
            "Lionel Messi ist Fußballspieler. Stand: 1. Januar 2026. Er erzielte insgesamt 850 Tore.",
            "insgesamt 850 Tore",
        ),
        (
            "Wie alt ist Messi?",
            "Lionel Messi wurde am 24. Juni 1987 geboren.",
            "24. Juni 1987",
        ),
        (
            "Wo wurde Messi geboren?",
            "Lionel Messi wurde in Rosario, Argentinien geboren.",
            "Rosario, Argentinien",
        ),
    ],
)
def test_specific_messi_questions_extract_only_the_requested_fact(
    question: str, extract: str, expected: str
) -> None:
    def fetch(_url: str, parameters: dict[str, str], _timeout: float) -> dict:
        if parameters.get("list") == "search":
            return {"query": {"search": [{"title": "Lionel Messi"}]}}
        return {"query": {"pages": [{"title": "Lionel Messi", "extract": extract}]}}

    answer = InternetAnswerService(fetch_json=fetch).answer(question)

    assert expected in answer.text
    assert "Fußballspieler" not in answer.text


def test_messi_summary_uses_a_short_summary() -> None:
    extract = "Lionel Messi ist ein argentinischer Fußballspieler. Er gewann zahlreiche Titel."

    def fetch(_url: str, parameters: dict[str, str], _timeout: float) -> dict:
        if parameters.get("list") == "search":
            return {"query": {"search": [{"title": "Lionel Messi"}]}}
        return {"query": {"pages": [{"title": "Lionel Messi", "extract": extract}]}}

    answer = InternetAnswerService(fetch_json=fetch).answer("Erzähl mir etwas über Messi")

    assert answer.text == extract


def test_specific_question_without_a_direct_fact_uses_a_helpful_summary() -> None:
    def fetch(url: str, parameters: dict[str, str], _timeout: float) -> dict:
        if url == WIKIPEDIA_API_URL:
            if parameters.get("list") == "search":
                return {"query": {"search": [{"title": "Lionel Messi"}]}}
            return {"query": {"pages": [{"title": "Lionel Messi", "extract": "Lionel Messi ist Fußballspieler."}]}}
        return {"Heading": "Lionel Messi", "AbstractText": "Lionel Messi ist Fußballspieler.", "AbstractURL": "https://example.test/messi"}

    answer = InternetAnswerService(fetch_json=fetch).answer("Wie viele Tore hat Messi?")

    assert answer.text == "Lionel Messi ist Fußballspieler."
    assert answer.source_name == "Wikipedia: Lionel Messi"


def test_unseen_colloquial_topic_uses_relevant_article_section() -> None:
    extract = (
        "Quantencomputer verwenden quantenmechanische Zustände.\n"
        "Anwendungsgebiete\n"
        "Vorteile können sich bei speziellen Optimierungsproblemen ergeben. "
        "Nachteile sind die hohe Fehleranfälligkeit und aufwendige Kühlung."
    )

    def fetch(_url: str, parameters: dict[str, str], _timeout: float) -> dict:
        if parameters.get("list") == "search":
            return {"query": {"search": [{"title": "Quantencomputer", "snippet": "Vorteile und Nachteile"}]}}
        return {"query": {"pages": [{"title": "Quantencomputer", "extract": extract}]}}

    answer = InternetAnswerService(fetch_json=fetch).answer("Quantencomputer, Vorteile Nachteile?")

    assert "Vorteile" in answer.text
    assert "Nachteile" in answer.text
    assert "quantenmechanische Zustände" not in answer.text
