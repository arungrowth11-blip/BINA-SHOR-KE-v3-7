from __future__ import annotations

from typing import Any

import requests

from bsk.errors import ProviderError
from bsk.providers.json_utils import extract_json


class OpenAICompatibleProvider:
    def __init__(self, name: str, api_key: str, model: str, base_url: str, timeout: int = 150):
        self.name = name
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate_json(self, system: str, prompt: str, temperature: float = 0.4) -> dict[str, Any]:
        if not self.api_key:
            raise ProviderError(f"{self.name} API key is not configured.")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system + "\nReturn one valid JSON object only. No Markdown fences."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "stream": False,
        }
        if self.name == "groq":
            payload["max_completion_tokens"] = 5000
        else:
            payload["max_tokens"] = 5000
        try:
            response = requests.post(
                self.base_url + "/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code >= 400:
                raise ProviderError(f"{self.name.title()} HTTP {response.status_code}: {response.text[:350]}")
            choices = response.json().get("choices") or []
            content = (choices[0].get("message") or {}).get("content", "") if choices else ""
            if not isinstance(content, str) or not content.strip():
                raise ProviderError(f"{self.name.title()} returned an empty completion.")
            return extract_json(content)
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError(f"{self.name.title()} request/response failed: {exc}") from exc
