import copy
from typing import Any
from urllib.error import URLError

import pytest

from jarvis.ollama_client import (
    LOCAL_AI_IDENTITY,
    OLLAMA_API_URL,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MODEL,
    SYSTEM_PROMPT,
    OllamaClient,
    OllamaError,
)


def test_ollama_client_sends_local_non_streaming_chat_request() -> None:
    requests: list[tuple[str, dict[str, Any], float]] = []

    def request(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        requests.append((url, copy.deepcopy(payload), timeout))
        return {"message": {"content": " Eine kurze Antwort. "}}

    client = OllamaClient(request_json=request, timeout_seconds=12.0)

    assert client.answer("Hallo Jarvis") == "Eine kurze Antwort."
    url, payload, timeout = requests[0]
    assert url == OLLAMA_API_URL == "http://127.0.0.1:11434/api/chat"
    assert payload["model"] == OLLAMA_MODEL == "gemma4:latest"
    assert payload["stream"] is False
    assert payload["keep_alive"] == OLLAMA_KEEP_ALIVE
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][-1] == {"role": "user", "content": "Hallo Jarvis"}
    assert timeout == 12.0


def test_system_prompt_knows_the_configured_local_ai_identity() -> None:
    assert OLLAMA_MODEL in LOCAL_AI_IDENTITY
    assert LOCAL_AI_IDENTITY in SYSTEM_PROMPT
    assert "JARVIS" in LOCAL_AI_IDENTITY
    assert "Ollama" in LOCAL_AI_IDENTITY
    assert "lokales KI-Sprachmodell" in LOCAL_AI_IDENTITY
    assert "keine OpenAI- oder ChatGPT-Cloud-API" in LOCAL_AI_IDENTITY


def test_ollama_history_is_limited_to_the_last_few_rounds() -> None:
    requests: list[dict[str, Any]] = []

    def request(_url: str, payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        requests.append(copy.deepcopy(payload))
        question = payload["messages"][-1]["content"]
        return {"message": {"content": f"Antwort auf {question}"}}

    client = OllamaClient(request_json=request, max_history_rounds=2)
    for number in range(1, 6):
        client.answer(f"Frage {number}")

    contents = [message["content"] for message in requests[-1]["messages"]]
    assert contents[1:] == [
        "Frage 3",
        "Antwort auf Frage 3",
        "Frage 4",
        "Antwort auf Frage 4",
        "Frage 5",
    ]
    assert "Frage 1" not in contents
    assert "Frage 2" not in contents


def test_ollama_connection_failure_becomes_controlled_error() -> None:
    def unavailable(_url: str, _payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        raise URLError("connection refused")

    with pytest.raises(OllamaError):
        OllamaClient(request_json=unavailable).answer("Hallo")
