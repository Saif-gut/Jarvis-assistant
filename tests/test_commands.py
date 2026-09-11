from datetime import datetime

import pytest

from jarvis.commands import CommandExecutor, Intent, is_exit_command, normalize_text, select_intent
from jarvis.internet_answers import (
    InternetAnswer,
    InternetUnavailableError,
    NoInternetAnswerError,
)
from jarvis.pc_functions import StorageInfo
from jarvis.ollama_client import OLLAMA_MODEL, OllamaError
from jarvis.weather import (
    DailyForecast,
    WeatherCityNotConfiguredError,
    WeatherUnavailableError,
)


@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        ("Wie spät ist es?", Intent.TIME),
        ("Wie viel Uhr ist es?", Intent.TIME),
        ("Uhrzeit", Intent.TIME),
        ("Welches Datum haben wir?", Intent.DATE),
        ("Welcher Tag ist heute?", Intent.DATE),
        ("Datum", Intent.DATE),
        ("Wie viel Speicher habe ich noch?", Intent.STORAGE),
        ("Freier Speicher", Intent.STORAGE),
        ("Speicherplatz", Intent.STORAGE),
        ("Hilfe", Intent.HELP),
        ("Was kannst du?", Intent.HELP),
        ("Wie ist das Wetter heute?", Intent.WEATHER_TODAY),
        ("Wetter heute", Intent.WEATHER_TODAY),
        ("Wie wird das Wetter morgen?", Intent.WEATHER_TOMORROW),
        ("Wie warm wird es morgen?", Intent.WEATHER_TOMORROW),
        ("Temperatur morgen", Intent.WEATHER_TOMORROW),
        ("Wie geht es dir?", Intent.SMALLTALK),
        ("Hallo", Intent.SMALLTALK),
        ("Guten Morgen", Intent.SMALLTALK),
        ("Guten Tag", Intent.SMALLTALK),
        ("Guten Abend", Intent.SMALLTALK),
        ("Danke", Intent.SMALLTALK),
        ("Wer bist du?", Intent.AI_IDENTITY),
        ("Welches KI-Modell bist du?", Intent.AI_IDENTITY),
        ("Läufst du lokal?", Intent.AI_IDENTITY),
        ("Was machst du?", Intent.SMALLTALK),
        ("Morgen Wetter", Intent.WEATHER_TOMORROW),
        ("Beenden", Intent.EXIT),
        ("Tschüss Jarvis", Intent.EXIT),
        ("Auf Wiedersehen", Intent.EXIT),
        ("Das war’s", Intent.EXIT),
        ("Öffne den Browser", Intent.UNKNOWN),
    ],
)
def test_select_intent(spoken: str, expected: Intent) -> None:
    assert select_intent(spoken) is expected


def test_normalize_text_removes_case_spacing_and_punctuation() -> None:
    assert normalize_text("  WIE   SPÄT, ist es?!  ") == "wie spat ist es"


def test_executor_formats_time() -> None:
    executor = CommandExecutor(now=lambda: datetime(2026, 8, 27, 9, 7))
    assert executor.execute("Uhrzeit").response == "Es ist 09:07 Uhr."


def test_executor_requests_exit() -> None:
    result = CommandExecutor().execute("Beenden")
    assert result.should_exit is True


def test_only_complete_exit_phrases_end_a_conversation() -> None:
    assert is_exit_command("Auf Wiedersehen")
    assert is_exit_command("Tschüss Jarvis")
    assert not is_exit_command("Kannst du die Wiedergabe stoppen?")
    assert not is_exit_command("Erzähl mir etwas über Albert Einstein")


@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        ("Hallo", "Hallo."),
        ("Guten Morgen", "Guten Morgen."),
        ("Guten Tag", "Guten Tag."),
        ("Guten Abend", "Guten Abend."),
        ("Danke", "Gern geschehen."),
        ("Wer bist du?", "Ich bin JARVIS"),
        ("Was machst du?", "Alltagsfragen"),
        ("Erzähl mir etwas", "Frag mich einfach"),
        ("Was kannst du alles?", "plaudern"),
    ],
)
def test_executor_answers_smalltalk_locally(spoken: str, expected: str) -> None:
    response = CommandExecutor().execute(spoken).response

    assert expected in response


@pytest.mark.parametrize(
    "spoken",
    [
        "Welches KI-Modell bist du?",
        "Welche AI bist du?",
        "Wer bist du?",
        "Was ist deine Identität?",
        "Welches Modell benutzt du?",
        "Läufst du über ChatGPT?",
        "Läufst du lokal?",
    ],
)
def test_executor_answers_ai_identity_questions_with_local_facts(spoken: str) -> None:
    internet = FakeInternetAnswerService(NoInternetAnswerError())
    ollama = FakeOllamaClient("Falsche Cloud-Antwort")
    executor = CommandExecutor(internet_answer_service=internet, ollama_client=ollama)  # type: ignore[arg-type]

    response = executor.execute(spoken).response

    assert "JARVIS" in response
    assert OLLAMA_MODEL in response
    assert "Ollama" in response
    assert "lokal" in response
    assert "keine OpenAI- oder ChatGPT-Cloud-API" in response
    assert internet.questions == []
    assert ollama.questions == []


@pytest.mark.parametrize(
    "spoken",
    [
        "Wie geht's?",
        "Alles gut bei dir?",
        "Wie fühlst du dich?",
        "Wie ist denn heute dein Befinden?",
        "Und, läuft bei dir alles rund?",
    ],
)
def test_wellbeing_variants_are_local_smalltalk(spoken: str) -> None:
    internet = FakeInternetAnswerService(NoInternetAnswerError())
    response = CommandExecutor(internet_answer_service=internet).execute(spoken).response

    assert response in {
        "Mir geht es gut, danke. Wie geht es dir?",
        "Sehr gut, danke der Nachfrage. Und selbst?",
        "Mir geht es bestens. Was kann ich für dich tun?",
        "Alles läuft gut. Wie geht es dir heute?",
        "Danke, mir geht es gut. Wobei kann ich dir helfen?",
        "Mir geht es prima. Was steht heute an?",
    }
    assert internet.questions == []


def test_wellbeing_response_never_repeats_directly() -> None:
    executor = CommandExecutor(internet_answer_service=FakeInternetAnswerService(NoInternetAnswerError()))

    responses = [executor.execute("Wie geht es dir?").response for _ in range(12)]

    assert all(previous != following for previous, following in zip(responses, responses[1:]))


def test_executor_uses_storage_provider() -> None:
    storage = StorageInfo(free_bytes=10 * 1024**3, total_bytes=20 * 1024**3)
    result = CommandExecutor(storage_provider=lambda: storage).execute("Speicher")
    assert "10.0 Gigabyte" in result.response
    assert "20.0 Gigabyte" in result.response


class FakeWeatherService:
    def __init__(self, result: DailyForecast | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str | None, int]] = []

    def get_daily_forecast(self, city: str | None, day_index: int) -> DailyForecast:
        self.calls.append((city, day_index))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_executor_answers_weather_for_tomorrow() -> None:
    weather = FakeWeatherService(
        DailyForecast(
            city="Berlin",
            country="Deutschland",
            forecast_date=datetime(2026, 8, 28).date(),
            weather_code=2,
            minimum_celsius=14.0,
            maximum_celsius=23.0,
        )
    )
    executor = CommandExecutor(weather_service=weather, weather_city="Berlin")

    response = executor.execute("Wie warm wird es morgen?").response

    assert weather.calls == [("Berlin", 1)]
    assert response == "Morgen wird es in Berlin, Deutschland teilweise bewölkt, bei 14 bis 23 Grad."


def test_executor_explains_missing_weather_city() -> None:
    executor = CommandExecutor(
        weather_service=FakeWeatherService(WeatherCityNotConfiguredError()),
        weather_city=None,
    )

    assert "JARVIS_WEATHER_CITY" in executor.execute("Wetter heute").response


def test_executor_explains_unavailable_weather_data() -> None:
    executor = CommandExecutor(
        weather_service=FakeWeatherService(WeatherUnavailableError()),
        weather_city="Berlin",
    )

    assert "Internetverbindung" in executor.execute("Wetter morgen").response


class FakeInternetAnswerService:
    def __init__(self, result: InternetAnswer | Exception) -> None:
        self.result = result
        self.questions: list[str] = []

    def answer(self, question: str) -> InternetAnswer:
        self.questions.append(question)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeOllamaClient:
    def __init__(self, result: str | Exception = "Ollama-Antwort") -> None:
        self.result = result
        self.questions: list[str] = []

    def answer(self, question: str) -> str:
        self.questions.append(question)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_executor_uses_internet_for_unknown_questions() -> None:
    internet = FakeInternetAnswerService(
        InternetAnswer(
            text="Die Erde ist der dritte Planet der Sonne.",
            source_name="Wikipedia: Erde",
            source_url="https://de.wikipedia.org/wiki/Erde",
        )
    )
    executor = CommandExecutor(internet_answer_service=internet)

    result = executor.execute("Was ist die Erde")

    assert internet.questions == ["Was ist die Erde"]
    assert result.source_name == "Wikipedia: Erde"
    assert result.source_url == "https://de.wikipedia.org/wiki/Erde"


def test_executor_explains_missing_internet_answer() -> None:
    executor = CommandExecutor(
        internet_answer_service=FakeInternetAnswerService(NoInternetAnswerError())
    )

    assert executor.execute("Unklare Frage").response == "Dazu habe ich gerade keine zuverlässige Antwort gefunden."


def test_executor_explains_unavailable_internet() -> None:
    executor = CommandExecutor(
        internet_answer_service=FakeInternetAnswerService(InternetUnavailableError())
    )

    assert executor.execute("Unklare Frage").response == "Dazu habe ich gerade keine zuverlässige Antwort gefunden."


def test_executor_never_uses_the_old_no_short_answer_message() -> None:
    executor = CommandExecutor(
        internet_answer_service=FakeInternetAnswerService(NoInternetAnswerError())
    )

    response = executor.execute("Unklare Frage").response

    assert response == "Dazu habe ich gerade keine zuverlässige Antwort gefunden."
    assert "keine kurze Antwort" not in response


def test_follow_up_question_keeps_the_previous_search_topic() -> None:
    internet = FakeInternetAnswerService(
        InternetAnswer("Lionel Messi ist Fußballspieler.", "Wikipedia: Lionel Messi", "https://example.test/messi")
    )
    executor = CommandExecutor(internet_answer_service=internet)

    executor.execute("Erzähl mir etwas über Messi")
    executor.execute("Wie viele Tore hat er?")

    assert internet.questions[0] == "Erzähl mir etwas über Messi"
    assert "messi" in internet.questions[1].casefold()


def test_device_action_request_is_explained_without_side_effects() -> None:
    internet = FakeInternetAnswerService(NoInternetAnswerError())
    response = CommandExecutor(internet_answer_service=internet).execute("Öffne ein Programm").response

    assert "keine Dateien, Programme oder Windows-Einstellungen verändern" in response
    assert internet.questions == []


def test_normal_conversation_uses_ollama_without_internet_search() -> None:
    internet = FakeInternetAnswerService(NoInternetAnswerError())
    ollama = FakeOllamaClient("Rekursion bedeutet, dass etwas sich selbst erneut verwendet.")
    executor = CommandExecutor(internet_answer_service=internet, ollama_client=ollama)  # type: ignore[arg-type]

    response = executor.execute("Erkläre mir Rekursion einfach").response

    assert response.startswith("Rekursion bedeutet")
    assert ollama.questions == ["Erkläre mir Rekursion einfach"]
    assert internet.questions == []


def test_existing_information_search_stays_ahead_of_ollama() -> None:
    internet = FakeInternetAnswerService(
        InternetAnswer("Die Erde ist ein Planet.", "Wikipedia: Erde", "https://example.test/erde")
    )
    ollama = FakeOllamaClient()
    executor = CommandExecutor(internet_answer_service=internet, ollama_client=ollama)  # type: ignore[arg-type]

    result = executor.execute("Was ist die Erde")

    assert result.response == "Die Erde ist ein Planet."
    assert result.source_url == "https://example.test/erde"
    assert ollama.questions == []


def test_ollama_answers_when_stable_information_search_has_no_result() -> None:
    internet = FakeInternetAnswerService(NoInternetAnswerError())
    ollama = FakeOllamaClient("Dazu kann ich eine allgemeine Erklärung geben.")
    executor = CommandExecutor(internet_answer_service=internet, ollama_client=ollama)  # type: ignore[arg-type]

    response = executor.execute("Was ist ein Gedankenexperiment").response

    assert response == "Dazu kann ich eine allgemeine Erklärung geben."
    assert internet.questions == ["Was ist ein Gedankenexperiment"]
    assert ollama.questions == ["Was ist ein Gedankenexperiment"]


def test_current_question_is_not_guessed_when_search_fails() -> None:
    internet = FakeInternetAnswerService(InternetUnavailableError())
    ollama = FakeOllamaClient()
    executor = CommandExecutor(internet_answer_service=internet, ollama_client=ollama)  # type: ignore[arg-type]

    response = executor.execute("Was ist der aktuelle Bitcoin Preis").response

    assert response == "Dazu habe ich gerade keine zuverlässige Antwort gefunden."
    assert ollama.questions == []


def test_unavailable_ollama_does_not_break_fixed_commands_or_jarvis() -> None:
    ollama = FakeOllamaClient(OllamaError())
    executor = CommandExecutor(ollama_client=ollama, now=lambda: datetime(2026, 8, 27, 9, 7))  # type: ignore[arg-type]

    assert executor.execute("Uhrzeit").response == "Es ist 09:07 Uhr."
    assert ollama.questions == []
    assert "nicht erreichbar" in executor.execute("Erkläre mir Rekursion").response
