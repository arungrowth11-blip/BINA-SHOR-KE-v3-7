from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    groq_api_key: str = os.getenv("GROQ_API_KEY", "").strip()
    mistral_api_key: str = os.getenv("MISTRAL_API_KEY", "").strip()
    confirm_free_only: bool = os.getenv("BSK_CONFIRM_FREE_ONLY", "").strip().upper() == "YES"
    enable_mistral_free_only: bool = os.getenv("BSK_ENABLE_MISTRAL_FREE_ONLY", "NO").strip().upper() == "YES"
    gemini_text_model: str = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.8-flash").strip()
    gemini_tts_model: str = os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts").strip()
    groq_text_model: str = os.getenv("GROQ_TEXT_MODEL", "openai/gpt-oss-120b").strip()
    mistral_text_model: str = os.getenv("MISTRAL_TEXT_MODEL", "ministral-8b-latest").strip()
    writer_provider: str = os.getenv("BSK_WRITER_PROVIDER", "gemini").strip().lower()
    tts_voice: str = os.getenv("TTS_VOICE", "Kore").strip()
    tts_style: str = os.getenv(
        "TTS_STYLE",
        "Natural Hindi narration; warm, grounded, restrained, clear diction. Use natural pauses.",
    ).strip()
    asr_model: str = os.getenv("BSK_ASR_MODEL", "large-v3-turbo").strip()
    asr_device: str = os.getenv("BSK_ASR_DEVICE", "cpu").strip()
    asr_compute_type: str = os.getenv("BSK_ASR_COMPUTE_TYPE", "int8").strip()
    request_timeout_seconds: int = int(os.getenv("BSK_REQUEST_TIMEOUT_SECONDS", "150"))
    max_provider_attempts: int = int(os.getenv("BSK_PROVIDER_ATTEMPTS", "2"))

    @property
    def jobs_dir(self) -> Path:
        return PROJECT_ROOT / "data" / "jobs"

    @property
    def tts_cache_dir(self) -> Path:
        return PROJECT_ROOT / "data" / "cache" / "tts"

    @property
    def configured_text_providers(self) -> list[str]:
        providers: list[str] = []
        if self.gemini_api_key:
            providers.append("gemini")
        if self.groq_api_key:
            providers.append("groq")
        if self.mistral_api_key and self.enable_mistral_free_only:
            providers.append("mistral")
        return providers


settings = Settings()
