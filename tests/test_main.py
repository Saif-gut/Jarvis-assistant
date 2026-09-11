from __future__ import annotations

import jarvis.__main__ as jarvis_main


class ReconfigurableStream:
    def __init__(self) -> None:
        self.options: dict[str, str] | None = None

    def reconfigure(self, **options: str) -> None:
        self.options = options


def test_command_line_output_is_explicitly_configured_as_utf8(monkeypatch) -> None:
    stdout = ReconfigurableStream()
    stderr = ReconfigurableStream()
    monkeypatch.setattr(jarvis_main.sys, "stdout", stdout)
    monkeypatch.setattr(jarvis_main.sys, "stderr", stderr)

    jarvis_main._configure_utf8_output()

    expected = {"encoding": "utf-8", "errors": "strict"}
    assert stdout.options == expected
    assert stderr.options == expected
