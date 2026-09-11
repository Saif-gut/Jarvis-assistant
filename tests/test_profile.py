import json

import pytest

from jarvis.commands import CommandExecutor
from jarvis.profile import PersonalProfile


@pytest.fixture
def profile(tmp_path) -> PersonalProfile:
    path = tmp_path / "jarvis.profile.json"
    path.write_text(
        json.dumps(
            {
                "first_name": "Test",
                "last_name": "Person",
                "full_name": "Test Person",
                "birth_date": "TESTDATUM",
                "birth_place": "TESTORT",
                "residence": "TESTLAND",
                "interests": "Programmieren und IT lernen",
            }
        ),
        encoding="utf-8",
    )
    return PersonalProfile.load(path)


class InternetMustNotBeCalled:
    def answer(self, _question: str):
        raise AssertionError("Persönliche Daten dürfen nie an einen Online-Dienst gehen.")


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Wie heiße ich?", "Test Person"),
        ("Wann habe ich Geburtstag?", "TESTDATUM"),
        ("Wo wurde ich geboren?", "TESTORT"),
        ("Wo wohne ich?", "TESTLAND"),
        ("Was sind meine Interessen?", "Programmieren"),
    ],
)
def test_profile_answers_individual_questions_locally(
    profile: PersonalProfile, question: str, expected: str
) -> None:
    result = CommandExecutor(
        personal_profile=profile, internet_answer_service=InternetMustNotBeCalled()
    ).execute(question)

    assert expected in result.response


def test_profile_answers_who_am_i_with_a_natural_summary(profile: PersonalProfile) -> None:
    response = CommandExecutor(
        personal_profile=profile, internet_answer_service=InternetMustNotBeCalled()
    ).execute("Wer bin ich?").response

    for value in ("Test Person", "TESTDATUM", "TESTORT", "TESTLAND", "IT"):
        assert value in response


def test_unknown_personal_question_stays_local_and_is_honest(profile: PersonalProfile) -> None:
    response = CommandExecutor(
        personal_profile=profile, internet_answer_service=InternetMustNotBeCalled()
    ).execute("Was ist meine Lieblingsfarbe?").response

    assert response == "Diese Information ist noch nicht in deinem lokalen Profil hinterlegt."


def test_unknown_personal_question_with_i_stays_local(profile: PersonalProfile) -> None:
    response = CommandExecutor(
        personal_profile=profile, internet_answer_service=InternetMustNotBeCalled()
    ).execute("Wie alt bin ich?").response

    assert response == "Diese Information ist noch nicht in deinem lokalen Profil hinterlegt."


def test_missing_profile_field_is_reported_honestly() -> None:
    response = PersonalProfile().answer("Wo wohne ich?")

    assert response == "Diese Information ist noch nicht in deinem lokalen Profil hinterlegt."
