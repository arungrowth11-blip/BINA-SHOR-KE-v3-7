from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import wave
from pathlib import Path
from typing import Any

import requests

from bsk.config import Settings, settings
from bsk.errors import ConfigurationError, GateError, ProviderError
from bsk.audio.wav import inspect_wav


class GeminiTTS:
    """Whole-narration Gemini TTS. The complete WAV is generated before any storyboard or visuals."""

    ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"

    def __init__(self, config: Settings = settings):
        self.config = config

    def _cache_key(self, text: str, style: str) -> str:
        material = "\n".join((self.config.gemini_tts_model, self.config.tts_voice, style, text))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _audio_data(body: dict[str, Any]) -> str | None:
        output = body.get("output_audio")
        if isinstance(output, dict) and output.get("data"):
            return output["data"]
        for step in body.get("steps", []):
            if isinstance(step, dict) and step.get("type") == "model_output":
                for content in step.get("content", []):
                    if isinstance(content, dict) and content.get("type") == "audio" and content.get("data"):
                        return content["data"]
        return None

    def generate(self, text: str, destination: Path, style: str | None = None) -> tuple[str, dict[str, Any]]:
        if not self.config.gemini_api_key:
            raise ConfigurationError("GEMINI_API_KEY is required for Hindi narration generation.")
        if not self.config.confirm_free_only:
            raise ConfigurationError(
                "Free-only usage has not been confirmed. Check Google AI Studio billing first, "
                "then set BSK_CONFIRM_FREE_ONLY=YES in your local .env."
            )
        if not text or not text.strip():
            raise GateError("Narration text is empty; refusing a TTS request.")
        style_text = (style or self.config.tts_style).strip()[:500]
        key = self._cache_key(text, style_text)
        cache_path = self.config.tts_cache_dir / f"{key}.wav"
        cache_meta = self.config.tts_cache_dir / f"{key}.json"
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        if cache_path.exists() and cache_meta.exists():
            try:
                meta = json.loads(cache_meta.read_text(encoding="utf-8"))
                file_digest = hashlib.sha256(cache_path.read_bytes()).hexdigest()
                if meta.get("cache_key") == key and meta.get("sha256") == file_digest:
                    details = inspect_wav(cache_path)
                    self._atomic_copy(cache_path, destination)
                    return "cached", details
            except Exception:
                pass  # Invalid cache is ignored and regenerated once.

        payload = {
            "model": self.config.gemini_tts_model,
            "input": [{
                "type": "user_input",
                "content": [{
                    "type": "text",
                    "text": text,
                    "annotations": [{"type": "speech_metadata", "style": style_text}],
                }],
            }],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": self.config.tts_voice}]},
        }
        body: dict[str, Any] | None = None
        last_error = "unknown TTS error"
        for attempt in range(3):
            try:
                response = requests.post(
                    self.ENDPOINT,
                    headers={"x-goog-api-key": self.config.gemini_api_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=max(self.config.request_timeout_seconds, 180),
                )
                if response.status_code in (429, 500, 502, 503, 504):
                    retry_after = response.headers.get("Retry-After", "")
                    try:
                        wait = min(max(float(retry_after), 1.0), 20.0) if retry_after else (5.0 * (attempt + 1))
                    except ValueError:
                        wait = 5.0 * (attempt + 1)
                    last_error = f"Gemini TTS HTTP {response.status_code}: {response.text[:250]}"
                    if attempt < 2:
                        time.sleep(wait)
                        continue
                    raise ProviderError(last_error)
                if response.status_code >= 400:
                    raise ProviderError(f"Gemini TTS HTTP {response.status_code}: {response.text[:350]}")
                body = response.json()
                break
            except requests.RequestException as exc:
                last_error = str(exc)
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
                else:
                    raise ProviderError(f"Gemini TTS request failed after bounded retries: {last_error}") from exc
        if body is None:
            raise ProviderError(f"Gemini TTS failed: {last_error}")
        audio_data = self._audio_data(body)
        if not audio_data:
            raise ProviderError("Gemini returned no audio block in its Interactions response.")
        try:
            wav_bytes = base64.b64decode(audio_data, validate=True)
        except ValueError as exc:
            raise ProviderError("Gemini returned invalid base64 audio data.") from exc
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(wav_bytes)
        try:
            details = inspect_wav(temporary)
            os.replace(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        self.config.tts_cache_dir.mkdir(parents=True, exist_ok=True)
        cache_temp = cache_path.with_suffix(".wav.tmp")
        cache_temp.write_bytes(wav_bytes)
        os.replace(cache_temp, cache_path)
        meta_temp = cache_meta.with_suffix(".json.tmp")
        meta_temp.write_text(json.dumps({"cache_key": key, "sha256": hashlib.sha256(wav_bytes).hexdigest(),
                                         "model": self.config.gemini_tts_model,
                                         "voice": self.config.tts_voice}, indent=2), encoding="utf-8")
        os.replace(meta_temp, cache_meta)
        return "generated", details

    @staticmethod
    def _atomic_copy(source: Path, destination: Path) -> None:
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(source.read_bytes())
        os.replace(temporary, destination)
