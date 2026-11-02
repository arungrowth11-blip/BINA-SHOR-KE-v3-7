from __future__ import annotations

from typing import Any

import requests

from bsk.errors import ProviderError
from bsk.providers.json_utils import extract_json


class GeminiTextProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: int = 150):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def generate_json(self, system: str, prompt: str, temperature: float = 0.4) -> dict[str, Any]:
        if not self.api_key:
            raise ProviderError("GEMINI_API_KEY is not configured.")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": temperature},
        }
        try:
            response = requests.post(url, params={"key": self.api_key}, json=payload, timeout=self.timeout)
            if response.status_code >= 400:
                raise ProviderError(f"Gemini HTTP {response.status_code}: {response.text[:350]}")
            body = response.json()
            candidates = body.get("candidates") or []
            parts = (candidates[0].get("content") or {}).get("parts") or [] if candidates else []
            text = next((part.get("text", "") for part in parts if isinstance(part, dict)), "")
            if not text.strip():
                raise ProviderError("Gemini returned no text candidate.")
            return extract_json(text)
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError(f"Gemini request/response failed: {exc}") from exc
