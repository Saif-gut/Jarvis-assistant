"""Kleiner Client für das ausschließlich lokal erreichbare Ollama-Modell."""

from __future__ import annotations

import json
import logging
from collections import deque
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OLLAMA_API_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "gemma4:latest"
OLLAMA_TIMEOUT_SECONDS = 60.0
OLLAMA_KEEP_ALIVE = "10m"
MAX_HISTORY_ROUNDS = 4
LOCAL_AI_IDENTITY = (
    f"Ich bin JARVIS. Mein lokales KI-Sprachmodell ist {OLLAMA_MODEL} und läuft über Ollama "
    "direkt auf deinem Computer. Dafür verwende ich aktuell keine OpenAI- oder "
    "ChatGPT-Cloud-API."
)
SYSTEM_PROMPT = (
    "Du bist Jarvis, ein persönlicher deutschsprachiger Sprachassistent. Antworte natürlich, "
    "freundlich, intelligent und direkt. Sprich normalerweise in zwei bis vier kurzen Sätzen. "
    "Beantworte ausschließlich die gestellte Frage und halte keine unnötigen Vorträge. Wenn dir "
    "zuverlässige Informationen fehlen, sage das ehrlich. Verwende keine komplizierte "
    "Markdown-Formatierung, weil deine Antwort laut vorgelesen wird. Wenn du nach deinem Modell, "
    "deiner KI-Identität, Ollama, lokaler Ausführung, OpenAI oder ChatGPT gefragt wirst, müssen "
    f"diese technischen Fakten erhalten bleiben: {LOCAL_AI_IDENTITY}"
)
LOGGER = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    """Das lokale Ollama-Modell konnte keine nutzbare Antwort liefern."""


class OllamaClient:
    """Sendet Text lokal an Ollama und hält wenige Gesprächsrunden im RAM."""

    def __init__(
        self,
        request_json: Callable[[str, dict[str, Any], float], dict[str, Any]] | None = None,
        timeout_seconds: float = OLLAMA_TIMEOUT_SECONDS,
        max_history_rounds: int = MAX_HISTORY_ROUNDS,
    ) -> None:
        if max_history_rounds < 1:
            raise ValueError("max_history_rounds muss mindestens 1 sein")
        self._request_json = request_json or _post_json
        self._timeout_seconds = timeout_seconds
        self._history: deque[tuple[str, str]] = deque(maxlen=max_history_rounds)

    def answer(self, question: str) -> str:
        question = " ".join(question.split())
        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for previous_question, previous_answer in self._history:
            messages.extend(
                (
                    {"role": "user", "content": previous_question},
                    {"role": "assistant", "content": previous_answer},
                )
            )
        messages.append({"role": "user", "content": question})
        payload = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
        }
        try:
            response = self._request_json(OLLAMA_API_URL, payload, self._timeout_seconds)
        except (HTTPError, URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
            LOGGER.warning("Lokales Ollama ist nicht erreichbar (%s).", type(exc).__name__)
            raise OllamaError from exc

        message = response.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            LOGGER.warning("Lokales Ollama hat keine nutzbare Textantwort geliefert.")
            raise OllamaError

        answer = content.strip()
        self._history.append((question, answer))
        return answer


def _post_json(url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    if url != OLLAMA_API_URL:
        raise ValueError("Ollama darf nur über die feste lokale Adresse angesprochen werden")
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "JarvisAssistant/1.0"},
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - feste Loopback-Adresse
        result = json.load(response)
    if not isinstance(result, dict):
        raise json.JSONDecodeError("Ollama-Antwort ist kein JSON-Objekt", "", 0)
    return result
