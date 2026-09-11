"""Reservierter, bewusst deaktivierter Erweiterungspunkt für spätere KI-Dienste."""

from __future__ import annotations


class OptionalAIService:
    """V1 ruft keinen KI-Dienst auf und benötigt keine Zugangsdaten."""

    enabled = False

    def answer(self, _question: str) -> None:
        return None
