from __future__ import annotations

from typing import Any, Protocol


class TextProvider(Protocol):
    name: str

    def generate_json(self, system: str, prompt: str, temperature: float = 0.4) -> dict[str, Any]: ...
