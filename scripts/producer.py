#!/usr/bin/env python3
"""BINA SHOR KE weekly faceless Reel factory.

The default GitHub/Kaggle production path generates original Hindi stories, FLUX.1 Schnell
illustrated stills, Depth Anything V2 depth maps, deterministic 2.5D parallax, Hindi narration,
branded post-production, technical/visual QA and a publish kit for one pinned private Telegram
chat. Legacy Wan2.2 manifests remain supported separately; it never publishes to Facebook or
falls back to a paid service.
"""
from __future__ import annotations

import argparse
import base64
import csv
import difflib
import hashlib
import json
import math
import os
import random
import re
import shutil
import statistics
import subprocess
import unicodedata
import sys
import time
import wave
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont
import voice_first
import story_engine
import motion_comic

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
HISTORY_PATH = ROOT / "data" / "history.json"
PERFORMANCE_PATH = ROOT / "data" / "performance_log.csv"
TELEGRAM_STATE_PATH = ROOT / "data" / "telegram_state.json"
# Restored/saved by GitHub Actions cache between finalization retries; never committed to Git.
TTS_CACHE_DIR = Path(os.getenv("BSK_TTS_CACHE_DIR", str(ROOT / "data" / "tts_cache")))
TZ = ZoneInfo("Asia/Kolkata")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL", "openai/gpt-oss-120b").strip()
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "").strip()
MISTRAL_TEXT_MODEL = os.getenv("MISTRAL_TEXT_MODEL", "ministral-8b-latest").strip()
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "").strip()
CF_API_TOKEN = os.getenv("CF_API_TOKEN", "").strip()
CF_WORKERS_AI_ENABLED = os.getenv("CF_WORKERS_AI_FREE_ONLY", "").strip().upper() == "YES"
CF_TEXT_MODEL = os.getenv("CF_TEXT_MODEL", "@cf/meta/llama-3.1-8b-instruct").strip()
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.8-flash")
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-lite-tts")
# Vision QA uses independent provider routing; text-only models are never selected here.
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b").strip()
MISTRAL_VISION_MODEL = os.getenv("MISTRAL_VISION_MODEL", "ministral-8b-2512").strip()
CF_VISION_MODEL = os.getenv("CF_VISION_MODEL", "@cf/qwen/qwen3.8-27b").strip()
VISION_REQUIRED_SCORE_KEYS = (
    "text_legibility", "devanagari_rendering", "anatomy_integrity",
    "story_visual_match", "safe_composition", "visual_quality",
    "character_continuity", "metadata_text_cleanliness",
)
TTS_VOICE = os.getenv("TTS_VOICE", "Kore")
FONT_DIR = "/usr/share/fonts/truetype/noto"
# A conservative request pacing guard for free-tier TTS quotas (roughly <= 3 requests/min).
TTS_MIN_INTERVAL_SECONDS = max(0.0, float(os.getenv("TTS_MIN_INTERVAL_SECONDS", "21")))
# The WAV/cache transport gate accepts up to 12s; the voice-first scene planner
# separately enforces its stricter 8.1s shot limit and reports when a beat must split.
TTS_MIN_DURATION_SECONDS = 1.0
TTS_MAX_DURATION_SECONDS = 12.0
_LAST_TTS_REQUEST_AT = 0.0
_ASR_MODEL = None
_LAST_TEXT_PROVIDER_USED: str | None = None
# Per-run circuit breaker: do not repeatedly spend requests on a provider that has
# already exhausted quota or is returning transient server/network failures.
_PROVIDER_COOLDOWN_UNTIL: dict[str, float] = {}
_PROVIDER_DISABLED_THIS_RUN: set[str] = set()

# Broad Hindi-speaking audience, but one recognizable brand promise.
# Long-run mix: 60% human stories, 25% cinematic reveals/moments, 15% broadly useful everyday insight.
PILLAR_CYCLE = [
    "micro_story", "cinematic_moment", "micro_story", "everyday_insight",
    "micro_story", "cinematic_moment", "micro_story", "micro_story",
    "everyday_insight", "micro_story", "cinematic_moment", "micro_story",
    "cinematic_moment", "micro_story", "everyday_insight", "micro_story",
    "cinematic_moment", "micro_story", "micro_story", "micro_story",
]
PILLAR_LABELS = {
    "micro_story": "Original Hindi micro-story about everyday human choices",
    "cinematic_moment": "Cinematic faceless mini-story with a reveal or emotional turn",
    "everyday_insight": "Broad practical insight about everyday decisions, communication or habits",
}
SERIES_BY_PILLAR = {
    "micro_story": "एक पल, एक फैसला",
    "cinematic_moment": "जो दिखा, पूरा सच नहीं",
    "everyday_insight": "छोटी बात, बड़ा असर",
}

# Narrative engines rotate independently of the content pillar so the catalogue does not
# collapse into the same hook-conflict-twist-moral formula.
NARRATIVE_ENGINES = [
    "A small choice has a quiet but visible cost",
    "Two people read the same silence differently",
    "An ordinary object reveals an unseen act of care",
    "A boundary is tested by a believable everyday pressure",
    "A person repairs a mistake without asking for praise",
    "Parallel routines reveal an unexpected shared need",
    "A promise is tested by inconvenience rather than drama",
    "A delayed reply changes the meaning of an earlier moment",
    "Someone overlooked gets the final meaningful choice",
    "A practical detail disproves a confident assumption",
    "Kindness happens without an audience or reward",
    "A familiar habit is seen from the other person's side",
]


def log(message: str) -> None:
    print(f"[{datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}] {message}", flush=True)


def require_env() -> None:
    # Pexels is optional. The all-original local graphic scene renderer remains available without it.
    missing = [name for name, value in {
        "GEMINI_API_KEY": GEMINI_API_KEY,
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    }.items() if not value]
    if missing:
        raise RuntimeError("Missing GitHub Actions secrets: " + ", ".join(missing))


def load_history() -> dict[str, Any]:
    defaults = {"generated_count": 0, "topics": [], "asset_ids": [], "performance": [], "one_reel_qualification": None, "created_at": None}
    if not HISTORY_PATH.exists():
        return defaults.copy()
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        for key, value in defaults.items():
            data.setdefault(key, value)
        if not isinstance(data["performance"], list):
            data["performance"] = []
        return data
    except (json.JSONDecodeError, OSError):
        log("WARNING: history.json invalid; starting a new lightweight history.")
        return defaults.copy()


def save_history(history: dict[str, Any]) -> None:
    """Atomically persist the factory's long-lived creative and performance memory."""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    history["created_at"] = datetime.now(TZ).isoformat(timespec="seconds")
    temporary = HISTORY_PATH.with_suffix(HISTORY_PATH.suffix + ".tmp")
    temporary.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(HISTORY_PATH)


def _gemini_json_request(system: str, user_prompt: str, temperature: float = 0.8, timeout: int = 120) -> dict[str, Any]:
    """One Gemini text request. Kept separate so provider routing never hides errors."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TEXT_MODEL}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": temperature},
    }
    response = requests.post(url, headers={"x-goog-api-key": GEMINI_API_KEY}, json=payload, timeout=timeout)
    if response.status_code >= 400:
        # Preserve the response object so retry logic can honour Retry-After.
        raise requests.HTTPError(
            f"Gemini HTTP {response.status_code}: {response.text[:300]}",
            response=response,
        )
    body = response.json()
    candidates = body.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {str(body)[:300]}")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    response_text = next((part.get("text") for part in parts if isinstance(part, dict) and part.get("text")), "")
    if not response_text:
        raise RuntimeError("Gemini returned no text part.")
    return extract_json(response_text)


def gemini_json(system: str, user_prompt: str, temperature: float = 0.8, timeout: int = 120) -> dict[str, Any]:
    """Gemini primary with bounded retry/backoff. Does not invoke other paid services."""
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return _gemini_json_request(system, user_prompt, temperature, timeout)
        except Exception as exc:
            last_error = exc
            message = str(exc).lower()
            # Auth/configuration and malformed-request errors will not improve by retrying.
            if any(marker in message for marker in ("http 400", "http 401", "http 403", "http 404")):
                break
            if attempt < 2:
                retry_after = 0
                if isinstance(exc, requests.HTTPError) and getattr(exc, "response", None) is not None:
                    try:
                        retry_after = int(float(exc.response.headers.get("Retry-After", "0")))
                    except (TypeError, ValueError):
                        retry_after = 0
                # Bounded backoff: respect provider Retry-After, otherwise wait 8s then 16s.
                # A hard 90s cap prevents an upstream header from holding a GitHub runner forever.
                time.sleep(max(min(retry_after, 90), 8 * (2 ** attempt)))
    raise RuntimeError(f"Gemini text request failed after bounded retries: {last_error}")


def _openai_json_completion(body: dict[str, Any], provider: str, max_output_tokens: int) -> dict[str, Any]:
    """Validate a completed OpenAI-compatible JSON response without repairing broken model output."""
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError(f"{provider} returned no choices: {str(body)[:300]}")
    choice = choices[0]
    finish_reason = str(choice.get("finish_reason") or "").lower()
    if finish_reason in {"length", "max_tokens"}:
        raise RuntimeError(
            f"{provider} output reached its {max_output_tokens}-token limit "
            f"(finish_reason={finish_reason}); refusing to parse truncated JSON."
        )
    message = choice.get("message") or {}
    content = message.get("content", "")
    if isinstance(content, list):
        content = "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict) and part.get("type", "text") == "text"
        )
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(f"{provider} returned an empty or unsupported message content.")
    return extract_json(content)


def groq_json(system: str, user_prompt: str, temperature: float = 0.8, timeout: int = 120) -> dict[str, Any]:
    """Groq OpenAI-compatible JSON route; only used when GROQ_API_KEY is configured."""
    if not GROQ_API_KEY:
        raise RuntimeError("Groq is not configured (GROQ_API_KEY is absent).")
    payload = {
        "model": GROQ_TEXT_MODEL,
        "messages": [
            {"role": "system", "content": system + "\nReturn valid JSON only; do not wrap it in Markdown."},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_completion_tokens": 12000,
        # GPT-OSS supports hidden reasoning in JSON mode; low effort reserves more of the
        # completion budget for the structured screenplay instead of internal reasoning.
        "reasoning_effort": "low",
        # GPT-OSS 120B does not support reasoning_format; suppress its separate reasoning field.
        "include_reasoning": False,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Groq HTTP {response.status_code}: {response.text[:300]}")
    return _openai_json_completion(response.json(), "Groq", 12000)



def _mistral_free_only_enabled() -> bool:
    return os.getenv("BSK_MISTRAL_FREE_ONLY", "").strip().upper() in {"YES", "TRUE"}


def mistral_json(system: str, user_prompt: str, temperature: float = 0.8, timeout: int = 120) -> dict[str, Any]:
    """Mistral route is unavailable unless the owner explicitly confirms free-only billing."""
    if not MISTRAL_API_KEY:
        raise RuntimeError("Mistral is not configured (MISTRAL_API_KEY is absent).")
    if not _mistral_free_only_enabled():
        raise RuntimeError(
            "Mistral is disabled: set BSK_MISTRAL_FREE_ONLY=YES only after confirming "
            "the connected Mistral workspace has no paid billing."
        )
    payload = {
        "model": MISTRAL_TEXT_MODEL,
        "messages": [
            {"role": "system", "content": system + "\nReturn valid JSON only; do not wrap it in Markdown."},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": 8000,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    response = requests.post(
        "https://api.mistral.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Mistral HTTP {response.status_code}: {response.text[:300]}")
    return _openai_json_completion(response.json(), "Mistral", 8000)

def cloudflare_json(system: str, user_prompt: str, temperature: float = 0.8, timeout: int = 120) -> dict[str, Any]:
    """Optional Cloudflare Workers AI tertiary route; requires explicit free-plan opt-in."""
    if not (CF_WORKERS_AI_ENABLED and CF_ACCOUNT_ID and CF_API_TOKEN):
        raise RuntimeError("Cloudflare Workers AI is disabled or incompletely configured.")
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/v1/chat/completions"
    payload = {
        "model": CF_TEXT_MODEL,
        "messages": [
            {"role": "system", "content": system + "\nReturn valid JSON only; do not wrap it in Markdown."},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": 1800,
        "stream": False,
        "options": {"rejectIfBusy": True},
    }
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Cloudflare Workers AI HTTP {response.status_code}: {response.text[:300]}")
    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError(f"Cloudflare Workers AI returned no choices: {str(body)[:300]}")
    content = (choices[0].get("message") or {}).get("content", "")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Cloudflare Workers AI returned an empty message.")
    return extract_json(content)


def _provider_failure_cooldown(name: str, exc: Exception) -> None:
    message = str(exc).lower()
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code in {400, 401, 403, 404} or any(
        token in message for token in ("http 400", "http 401", "http 403", "http 404", "invalid api key", "unauthorized", "model_not_found", "unknown model")
    ):
        _PROVIDER_DISABLED_THIS_RUN.add(name)
        log(f"Provider circuit opened for {name} for the remainder of this run (configuration/model error).")
    elif status_code == 429 or any(token in message for token in ("http 429", "quota", "rate limit", "resource_exhausted")):
        _PROVIDER_COOLDOWN_UNTIL[name] = time.monotonic() + 900
        log(f"Provider circuit opened for {name} for 15 minutes (quota/rate-limit response).")
    elif any(token in message for token in (
        "jsondecodeerror", "unterminated string", "expecting ',' delimiter",
        "output reached its", "invalid json", "empty or unsupported message content",
    )):
        # Invalid JSON is a response-quality failure, not proof the provider is unavailable.
        log(f"Provider {name} returned invalid/truncated structured output; retaining it for a bounded candidate retry.")
    elif status_code in {408, 500, 502, 503, 504} or any(token in message for token in (
        "http 408", "http 500", "http 502", "http 503", "http 504", "timeout", "connection", "temporarily unavailable"
    )):
        _PROVIDER_COOLDOWN_UNTIL[name] = time.monotonic() + 120
        log(f"Provider circuit opened for {name} for 2 minutes (transient failure).")

def _provider_available(name: str) -> bool:
    if name in _PROVIDER_DISABLED_THIS_RUN:
        return False
    return time.monotonic() >= _PROVIDER_COOLDOWN_UNTIL.get(name, 0.0)


def _text_provider_order(prefer_independent: bool = False) -> list[tuple[str, Any]]:
    providers: dict[str, Any] = {"gemini": gemini_json, "groq": groq_json, "mistral": mistral_json, "cloudflare": cloudflare_json}
    if prefer_independent:
        names = ["groq", "mistral", "cloudflare", "gemini"]
    else:
        primary = os.getenv("BSK_TEXT_PROVIDER", "gemini").strip().lower()
        if primary not in providers:
            primary = "gemini"
        names = [primary] + [name for name in ("gemini", "groq", "mistral", "cloudflare") if name != primary]
    enabled = {
        "gemini": bool(GEMINI_API_KEY),
        "groq": bool(GROQ_API_KEY),
        "mistral": bool(MISTRAL_API_KEY and _mistral_free_only_enabled()),
        "cloudflare": bool(CF_WORKERS_AI_ENABLED and CF_ACCOUNT_ID and CF_API_TOKEN),
    }
    return [(name, providers[name]) for name in names if enabled[name] and _provider_available(name)]


def text_json(system: str, user_prompt: str, temperature: float = 0.8, timeout: int = 120) -> dict[str, Any]:
    """Use a bounded provider cascade. It never has a paid provider or paid fallback."""
    global _LAST_TEXT_PROVIDER_USED
    order = _text_provider_order(prefer_independent=False)
    if not order:
        raise RuntimeError("No configured free text providers are currently available (missing credentials, disabled provider, or active cooldown).")
    failures = []
    for index, (name, provider) in enumerate(order):
        try:
            result = provider(system, user_prompt, temperature=temperature, timeout=timeout)
            if index:
                log(f"Text generation recovered through {name} after an earlier provider failed.")
            _LAST_TEXT_PROVIDER_USED = name
            return result
        except Exception as exc:
            failures.append(f"{name}: {str(exc)[:350]}")
            _provider_failure_cooldown(name, exc)
            log(f"Text provider {name} failed: {str(exc)[:240]}")
    raise RuntimeError("All configured free text providers failed; no paid fallback was attempted. " + " | ".join(failures))


def independent_review_json(system: str, user_prompt: str, temperature: float = 0.2, timeout: int = 120) -> dict[str, Any]:
    """Prefer a different model family for the critic, then fail over within configured free providers."""
    order = _text_provider_order(prefer_independent=True)
    # A real second opinion should come from a different provider than the author where possible.
    # If only one free provider is configured, it remains the last-resort reviewer.
    if _LAST_TEXT_PROVIDER_USED and len(order) > 1:
        author = [item for item in order if item[0] == _LAST_TEXT_PROVIDER_USED]
        order = [item for item in order if item[0] != _LAST_TEXT_PROVIDER_USED] + author
    if not order:
        raise RuntimeError("No text AI provider is configured for editorial review.")
    failures = []
    for index, (name, provider) in enumerate(order):
        try:
            result = provider(system, user_prompt, temperature=temperature, timeout=timeout)
            if index:
                log(f"Editorial critic used {name} after preferred independent provider failed.")
            return result
        except Exception as exc:
            failures.append(f"{name}: {str(exc)[:300]}")
            _provider_failure_cooldown(name, exc)
            log(f"Editorial critic provider {name} failed: {str(exc)[:220]}")
    raise RuntimeError("No configured free provider could complete the editorial review. " + " | ".join(failures))


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        result = json.loads(text[start:end + 1])
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object from Gemini.")
    return result


def next_post_slots(count: int, rotation: int = 0, history: dict[str, Any] | None = None) -> list[datetime]:
    """Plan Sun/Tue/Thu experiments; adapt lunch/evening only after enough measured results."""
    now = datetime.now(TZ)
    weekdays = (6, 1, 3)  # Sunday, Tuesday, Thursday
    schedule_a = {6: (20, 37), 1: (13, 7), 3: (20, 37)}
    schedule_b = {6: (13, 7), 1: (20, 37), 3: (13, 7)}
    baseline = schedule_a if rotation % 2 == 0 else schedule_b
    performance = performance_context(history or {})
    by_window = performance.get("by_post_window", {})
    enough_data = all(by_window.get(window, {}).get("posts_with_metrics", 0) >= 5 for window in ("midday", "evening"))
    adaptive_best = None
    adaptive_other = None
    # Keep one explore-first baseline week every four weeks; otherwise use best window for 2/3 posts.
    if enough_data and rotation % 4 != 0:
        ranked = sorted(((by_window[window]["median_internal_score"], window) for window in ("midday", "evening")), reverse=True)
        if ranked and ranked[0][0] != ranked[1][0]:
            adaptive_best, adaptive_other = ranked[0][1], ranked[1][1]
            log(f"Posting-time adaptation: current measured winner is {adaptive_best}; retain one weekly exploration slot. Sample-based signal, not a guarantee.")

    candidates: list[datetime] = []
    slot_index = 0
    for day_offset in range(0, 16):
        day_dt = now + timedelta(days=day_offset)
        if day_dt.weekday() not in weekdays:
            continue
        if adaptive_best:
            window = adaptive_other if slot_index % 3 == 1 else adaptive_best
            hour, minute = (13, 7) if window == "midday" else (20, 37)
        else:
            hour, minute = baseline[day_dt.weekday()]
        candidate = datetime(day_dt.year, day_dt.month, day_dt.day, hour, minute, tzinfo=TZ)
        if candidate > now + timedelta(minutes=20):
            candidates.append(candidate)
            slot_index += 1
        if len(candidates) >= count:
            break
    return sorted(candidates)[:count]


def next_carousel_slot() -> datetime:
    """Choose the next Saturday late-morning slot as an experiment, not a proven best time."""
    now = datetime.now(TZ)
    days = (5 - now.weekday()) % 7  # Saturday
    candidate_day = (now + timedelta(days=days)).date()
    candidate = datetime(candidate_day.year, candidate_day.month, candidate_day.day, 11, 0, tzinfo=TZ)
    if candidate <= now + timedelta(minutes=20):
        candidate += timedelta(days=7)
    return candidate


def choose_pillar(history: dict[str, Any], offset: int) -> str:
    idx = (int(history.get("generated_count", 0)) + offset) % len(PILLAR_CYCLE)
    baseline = PILLAR_CYCLE[idx]
    perf = performance_context(history)
    by_pillar = perf["by_pillar"]
    adequate = all(by_pillar.get(key, {}).get("posts_with_metrics", 0) >= 5 for key in PILLAR_LABELS)
    # One of every five pieces can be adaptive. The remaining four preserve the baseline mix.
    if adequate and ((int(history.get("generated_count", 0)) + offset + 1) % 5 == 0):
        ranked = sorted(
            ((float(value["mean_internal_score"]), key) for key, value in by_pillar.items() if key in PILLAR_LABELS),
            reverse=True,
        )
        if ranked:
            best = ranked[0][1]
            log(f"Adaptive slot: testing pillar '{best}' from observed Page data. This is a weak signal, not a forecast.")
            return best
    return baseline


def _metric_score(row: dict[str, Any]) -> float | None:
    """A within-Page editorial signal; missing metrics are excluded, never treated as zero."""
    try:
        views = max(0, int(row.get("views_24h", row.get("views", 0)) or 0))
        if views <= 0:
            return None
        definitions = (
            ("new_follows", 0.30, lambda value: min(1.0, (value / views * 1000) / 8.0)),
            ("shares", 0.20, lambda value: min(1.0, (value / views * 1000) / 20.0)),
            ("saves", 0.10, lambda value: min(1.0, (value / views * 1000) / 15.0)),
            ("completion_rate_percent", 0.25, lambda value: min(1.0, max(0.0, value) / 60.0)),
            ("average_watch_time_seconds", 0.15, lambda value: min(1.0, max(0.0, value) / 15.0)),
        )
        observed: list[tuple[float, float]] = []
        has_retention = False
        for key, weight, transform in definitions:
            raw = row.get(key)
            if raw is None or raw == "":
                continue
            value = float(raw)
            if value < 0:
                continue
            observed.append((weight, transform(value)))
            if key in {"completion_rate_percent", "average_watch_time_seconds"}:
                has_retention = True
        # Do not let sparse or engagement-only records train the factory.
        if len(observed) < 3 or not has_retention:
            return None
        weight_total = sum(weight for weight, _ in observed)
        return round(100 * sum(weight * value for weight, value in observed) / weight_total, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def performance_context(history: dict[str, Any]) -> dict[str, Any]:
    """Use medians and minimum samples to reduce overreaction to one unusually strong Reel."""
    rows = [row for row in history.get("performance", []) if isinstance(row, dict) and _metric_score(row) is not None]
    by_pillar: dict[str, list[float]] = {}
    by_window: dict[str, list[float]] = {}
    for row in rows:
        score = float(_metric_score(row))
        pillar = str(row.get("pillar", "unknown"))
        by_pillar.setdefault(pillar, []).append(score)
        window = str(row.get("post_window", "unknown"))
        if window in {"midday", "evening"}:
            by_window.setdefault(window, []).append(score)
    def summarise(groups: dict[str, list[float]]) -> dict[str, dict[str, Any]]:
        return {
            key: {
                "posts_with_metrics": len(scores),
                "median_internal_score": round(statistics.median(scores), 1),
                # Kept as a compatibility alias for older report readers.
                "mean_internal_score": round(statistics.median(scores), 1),
            }
            for key, scores in groups.items() if scores
        }
    return {
        "posts_with_metrics": len(rows),
        "by_pillar": summarise(by_pillar),
        "by_post_window": summarise(by_window),
        "minimum_sample_for_pillar_adaptation": 5,
        "minimum_sample_for_time_adaptation": 5,
        "aggregation": "median; records with fewer than 3 observed metrics including at least one retention metric are excluded",
    }


def normalize_for_similarity(value: str) -> str:
    value = re.sub(r"[^\w\s]", " ", (value or "").lower())
    return " ".join(value.split())


def topic_is_too_similar(title: str, theme: str, past_topics: list[dict[str, Any]]) -> bool:
    """Reject obvious recent repeats by title similarity or high theme-word overlap."""
    candidate_title = normalize_for_similarity(title)
    stop = {"aur", "hai", "tha", "thi", "the", "mein", "ki", "ka", "ke", "se", "par", "ek", "to", "ko", "jo", "woh", "ye"}
    candidate_words = set(normalize_for_similarity(theme).split()) - stop
    for old in past_topics[-35:]:
        old_title = normalize_for_similarity(str(old.get("title", "")))
        if candidate_title and old_title and difflib.SequenceMatcher(None, candidate_title, old_title).ratio() >= 0.84:
            return True
        old_words = set(normalize_for_similarity(str(old.get("theme", ""))).split()) - stop
        if len(candidate_words) >= 5 and len(old_words) >= 5:
            overlap = len(candidate_words & old_words) / max(1, len(candidate_words | old_words))
            if overlap >= 0.72:
                return True
    return False


def human_detail_is_too_similar(detail: str, past_topics: list[dict[str, Any]], lookback: int = 12) -> bool:
    """Catch obvious repeats of a distinctive lived-in story anchor without overclaiming semantic similarity."""
    candidate = normalize_for_similarity(detail)
    if len(candidate.split()) < 4:
        return False
    for old in past_topics[-lookback:]:
        previous = normalize_for_similarity(str(old.get("human_detail", "")))
        if len(previous.split()) < 4:
            continue
        if candidate == previous or difflib.SequenceMatcher(None, candidate, previous).ratio() >= 0.93:
            return True
    return False


def generate_concept(
    history: dict[str, Any], pillar: str, slot: datetime, index: int, correction_feedback: str = ""
) -> dict[str, Any]:
    recent_topics = history.get("topics", [])[-35:]
    recent_titles = [x.get("title", "") for x in recent_topics]
    recent_themes = [x.get("theme", "") for x in recent_topics]
    observed_performance = performance_context(history)
    narrative_engine = NARRATIVE_ENGINES[(int(history.get("generated_count", 0)) + index) % len(NARRATIVE_ENGINES)]
    recent_engines = [str(x.get("narrative_engine", "")) for x in recent_topics[-6:] if x.get("narrative_engine")]
    recent_story_anchors = [str(x.get("human_detail", "")) for x in recent_topics[-12:] if x.get("human_detail")]
    system = """You are the lead screenwriter of BINA SHOR KE. Write a tiny human film, not a motivational post disguised as cinema. The viewer should recognise a real feeling before they recognise the message. Prioritise emotional truth, subtext, human contradiction, consequence and restraint. Begin from a specific person in a specific ordinary moment with a concrete want, pressure or misunderstanding. Let an action, object, omission or choice carry meaning. Do not explain emotions that the image can show. Never make every character a saint or villain; give people mixed motives and believable limits. The ending must be earned by earlier details and leave a small aftertaste—not a lecture, slogan, twist for its own sake, or forced tearjerker. Avoid ready-made moral lines such as 'ज़िंदगी यही सिखाती है', 'अपनों की कदर', 'वक्त सब सिखा देता है', 'कभी-कभी खामोशी', and other interchangeable motivational clichés. Do not rely on poverty porn, illness/death reveals, abandoned-child twists, rich-vs-poor humiliation, miracle coincidences or manipulative guilt. Do not repeatedly use a phone notification, rain, a letter, an old person or a missed call as the reveal; only use such devices when causally essential and fresh. Vary sentence length, syntax, silence and point of view. Spoken Hindi must sound like a thoughtful person speaking—not translated English, formal essay Hindi or artificial shayari. Use simple vivid words, idiomatic Devanagari and natural pauses; Hinglish only when an actual speaker would use it. Give every spoken turn a distinct, restrained vocal delivery and assign each line to its actual speaker. If two or more characters speak, never merge their words into one voice: each turn needs its own speaker_id. Do not invent a speaker just to fill a cast. A narrator is optional and must be a separate character when used. Output valid JSON only. Do not imitate any creator, film, book, song or viral script. Avoid fake factual claims, medical/legal/financial advice, real allegations, identifiable real people, copyrighted lyrics, rage bait, deceptive hooks and forced engagement bait. Fictional stories must never be presented as verified true events. Every beat must advance a causal story, reveal information, change the audience's interpretation, or earn the ending. Visual prompts are for a semi-painterly 2.5D Indian graphic-novel motion-comic video model: separated foreground/midground/background cues, one physically plausible action, controlled camera movement, warm practical light, tactile illustrated materials and restrained cinematic colour. Never ask the model to render words, subtitles, logos or watermarks. Avoid complex hand interactions, fast choreographed movement, multiple speaking faces, visible brand marks and impossible actions. Keep recurring subject/clothes/setting consistent; prefer partial profiles, backs, silhouettes and object-led scenes when faces are not essential. Each Reel must be understandable without sound. Editorial scores are quality controls, not a Meta monetization/recommendation guarantee."""
    pillar_rules = {
        "micro_story": "Create a compact fictional everyday story about human choices: trust, work, family, friendship, responsibility, misunderstanding, dignity, kindness or boundaries. Include a conflict, a consequential turn and an earned payoff. Avoid gender stereotypes and moralising.",
        "cinematic_moment": "Create a compact cinematic mini-story using everyday environments and objects with a genuine reveal or re-interpretation. The aesthetic must serve the story; no random pretty footage plus vague quote.",
        "everyday_insight": "Create one broadly useful, low-risk observation or practical framework about communication, attention, decisions, routines, digital life or social behaviour. Give concrete examples and an actionable payoff. Avoid medical/legal/financial claims, product promotion, body-shaming and luxury pressure.",
    }
    user = f"""Build Reel #{int(history.get('generated_count', 0)) + index + 1} for {PILLAR_LABELS[pillar]}.

PILLAR BRIEF: {pillar_rules[pillar]}
PLANNED PUBLISH SLOT (test, not a guarantee): {slot.strftime('%A %d %B %Y, %I:%M %p IST')}
Brand promise: 'कम शब्द। साफ़ कहानी। ऐसा अर्थ जो याद रहे।'
NARRATIVE ENGINE TO EXPLORE (do not use it as a formula): {narrative_engine}. If this feels forced for the pillar, use a fresh variation but avoid the recent engines {json.dumps(recent_engines, ensure_ascii=False)}.
Human-depth test: name a small human_detail (an observable gesture, object, unfinished task, habit or sensory detail) that feels lived-in; state the character_contradiction (what they want versus what they do or cannot say); identify the cost_of_choice (a small, believable consequence); let the audience infer emotion from behaviour; let the final line change the meaning of an earlier detail. Do not end with a generic moral. Avoid repeating recent story anchors {json.dumps(recent_story_anchors, ensure_ascii=False)}. One brief line of natural direct speech is allowed only when a real person would say it; do not turn every beat into a quote.
Target audience hypothesis: Hindi-understanding adults across genders, regions and life stages who enjoy grounded stories about everyday decisions, relationships, work, trust, digital life and useful habits. Do not write only for men or only for romance audiences.
Choose one story_type from emotional, suspense, twist, comedy, poetry or insight. Duration is adaptive: emotional/suspense target 35s (30–45s, 75–110 Hindi words); twist/comedy target 25s (20–30s, 52–78 words); poetry target 22s (18–26s, 32–60 words); insight target 28s (20–35s, 50–82 words). Use exactly 6 narrative beats in this order: hook, context, conflict, escalation, turn, payoff; these are story beats, not final editorial shots. Every beat must include narrative_role, state_change (4–32 words describing what new information, choice, action or interpretation changes), and causal_link (4–32 words describing the opening pressure for beat 1 or how beats 2–6 follow from the previous beat). Do not use generic transitions; describe actual cause and effect. Every state_change must be distinct. The payoff beat must resolve or deliberately reframe an earlier detail. Write the complete screenplay first. Each beat contains an ordered speech_segments array; each segment has one speaker_id and one complete spoken turn. Multiple speakers may speak in the same beat, but never merge their lines or assign the same voice to different characters. Some beats may be silent when visual action carries the story. Keep individual turns naturally speakable (usually 8–20 words) and stay inside the chosen story_type word range. Never shorten a line merely to fit a fixed-duration clip. Every speaking character must appear in characters, and every speaker_id must match exactly one cast member. For cast entries, OMIT voice_profile_id entirely (or set it to an empty string): the production pipeline derives the canonical age/gender-matched profile. Do not guess or copy a Gemini voice name into this field. If you choose a young-adult woman, the pipeline assigns Leda; if you choose an adult woman (30–54), it assigns Aoede. Make the appearance age explicit and consistent with age_band.

PREVIOUS STRUCTURAL FEEDBACK (must be corrected in this candidate): {correction_feedback or 'No previous candidate feedback.'}

OBSERVED PAGE PERFORMANCE (may be empty; use only as weak evidence, not causal truth): {json.dumps(observed_performance, ensure_ascii=False)}
If there are fewer than 5 valid metric-bearing posts per pillar, continue the baseline mix. Missing metrics are unknown, not zero. Even with five or more observations, treat the signal as weak and test a distinct variation rather than blindly repeating a past winner.

RECENT TITLES (do not reuse): {json.dumps(recent_titles, ensure_ascii=False)}
RECENT THEMES (do not repeat the same situation/twist): {json.dumps(recent_themes, ensure_ascii=False)}

Return one JSON object with exactly these fields:
{{
  "title": "short distinct internal title",
  "characters": [
    {{"character_id":"protagonist","display_name":"natural Hindi name","role":"protagonist|supporting|narrator","gender_presentation":"male|female|unspecified","age_band":"child|teen|young_adult|adult|older_adult|elder","visual_age_description":"visible age anchor consistent with age_band; normalized by the pipeline","appearance":"specific visual identity and exact age-consistent face/body/clothing anchors","personality":"brief behaviour traits","voice_direction":"natural Hindi performance direction for this character"}}
  ],
  "pillar": "{pillar}",
  "story_type": "emotional|suspense|twist|comedy|poetry|insight",
  "series_name": "one of the brand's three editorial series; it will be normalized from the pillar",
  "theme": "one-sentence theme, specific and not generic",
  "audience_reason": "one sentence why this audience may care; state as a hypothesis, not certainty",
  "share_reason": "the genuine human insight or practical utility that could make someone naturally send this to a friend; no forced CTA",
  "share_recipient": "one specific relationship/person this story naturally fits, e.g. younger sister, father, office friend, old school friend",
  "narrative_engine": "brief name of the story device actually used",
  "emotional_aftertaste": "the quiet feeling or thought the ending should leave; not a moral",
  "human_detail": "one small, observable, non-generic lived-in detail used in the story",
  "character_contradiction": "what the main character wants versus what they do, avoid or cannot say",
  "cost_of_choice": "the believable small price or consequence of the character's choice",
  "hook": "a compelling first-screen line, 4–10 Hindi words, no deceptive promise",
  "visual_bible": "consistent visual language, scene setting, lighting and any recurring non-identifiable character details",
  "beats": [
    {{"narrative_role":"hook|context|conflict|escalation|turn|payoff in exact sequence", "state_change":"4–32 words describing the new information/action/interpretation in this beat", "causal_link":"4–32 words linking this beat to the opening pressure or immediately previous beat", "speech_segments":[{{"segment_id":"beat_01_line_01","speaker_id":"protagonist","text":"one complete natural Hindi spoken turn","emotion":"subtle emotion or acting cue"}}], "voiceover":"exact spoken words in this beat, joined in dialogue order for subtitle/ASR compatibility", "voice_direction":"optional overall beat direction", "screen_text":"short readable line, max 2 lines", "visual_query":"3–7 English keywords describing the shot", "visual_direction":"what new information or emotion this shot contributes", "video_prompt":"55–80 concrete English words describing the beat's visible action, shot size, motivated light, tactile materials, continuity and restrained grade; this is a temporary prompt and will be replaced after measured voice generation; no text, subtitles, logo or watermark", "overlay_type":"message|note|step|contrast|keyword", "overlay_text":"a short original clue/label that adds context rather than repeating the subtitle"}}
  ],
  "caption": "2–3 short natural lines, do not simply repeat the whole script",
  "hashtags": ["#BinaShorKe", "#relevant2", "#relevant3"],
  "cover_text": "short cover phrase, ideally 3–7 words",
  "posting_note": "one sentence explaining the test hypothesis for this reel"
}}

SHARE-RECIPIENT GATE: identify one concrete real-world recipient for the story, not generic "everyone" or "people". The premise, detail and emotional turn should make sense for why this exact person would receive it. Do not force a call-to-action.\n\nRules: first frame delivers a specific curiosity gap within 1 second, with no logo intro. Return a beats array containing EXACTLY SIX objects—no prologue object, no epilogue object, no seventh beat, and no merged beats—with narrative_role values in this exact order: hook, context, conflict, escalation, turn, payoff. Count the objects before returning JSON. Every beat must include explicit state_change and causal_link fields; reject any beat that only restates the previous one. The payoff must be earned by earlier details, not introduced from nowhere. The selected story_type controls the total spoken-word range described above. speech_segments is the source of truth; voiceover must be the exact joined text of those segments and may be empty only when speech_segments is empty. Never force every beat to the same word count. Audio is generated before video; the measured voice duration selects the final Reel duration and editorial shot timing. Do not compress or shorten dialogue to fit a generated clip. Each beat must materially change the story or audience understanding. The last line should pay off the opening, not tack on a generic moral. The video_prompt must specify what is actually visible; never ask the model to show Hindi text. Make every shot different but coherent, with a clear beginning/middle/end progression. overlay_text must add context rather than duplicate narration. Use 3–5 relevant hashtags. Never force shares/comments or claim virality. Do not use copyrighted songs, movie clips or another creator's post. For fictional stories, communicate fiction appropriately.

CAST AGE/VOICE HARD GATE: visible age is selected first and is immutable. The age_band controls the canonical visual_age_description and the voice profile; the appearance description must visibly agree with it. Adult women use Aoede, not Gacrux. Gacrux is only for older-adult/elder women; apply the equivalent age mapping to male profiles. Child/teen characters may appear silently, but no speech segment may be assigned to them until a dedicated age-appropriate Hindi voice has been auditioned. Never make a child/teen sound adult, and never age a character up/down just to fit a voice. The pipeline rejects an explicit voice-profile mismatch before TTS/GPU work. Return JSON only."""

    concept = text_json(system, user, temperature=0.85)
    # Upgrade legacy narrator concepts or validate an explicit multi-speaker screenplay.
    concept = voice_first.normalise_screenplay(concept)
    # Normalize stable required fields, then locally validate shape.
    concept["pillar"] = pillar
    concept["series_name"] = SERIES_BY_PILLAR[pillar]
    concept["planned_publish_at"] = slot.isoformat()
    concept["planned_publish_label"] = slot.strftime("%a %d %b, %I:%M %p IST")
    if isinstance(concept.get("beats"), list) and concept["beats"] and concept.get("hook"):
        # The opening frame must display the promised hook; do not rely on a vague intro scene.
        concept["beats"][0]["screen_text"] = str(concept["hook"]).strip()
    concept = repair_concept_structure(concept)
    validate_concept_shape(concept)
    return concept


def _infer_share_recipient(concept: dict[str, Any]) -> str:
    """Choose one concrete, singular recipient from story context without an AI call."""
    parts = [
        concept.get("title", ""),
        concept.get("theme", ""),
        concept.get("share_reason", ""),
        concept.get("human_detail", ""),
        concept.get("character_contradiction", ""),
        concept.get("cost_of_choice", ""),
    ]
    for beat in concept.get("beats", []):
        if isinstance(beat, dict):
            parts.extend((beat.get("voiceover", ""), beat.get("visual_direction", "")))
    for character in concept.get("characters", []):
        if isinstance(character, dict):
            parts.extend((character.get("role", ""), character.get("personality", "")))

    raw_text = " ".join(str(value or "") for value in parts).casefold()
    tokens = set(normalize_for_similarity(raw_text).split())
    relationship_rules = (
        ({"mother", "mom", "mum", "mummy", "ma"}, ("माँ", "मां", "माता", "अम्मा"), "अपनी माँ को"),
        ({"father", "dad", "papa", "papi"}, ("पिता", "पापा", "बाबा", "बाप"), "अपने पिता को"),
        ({"sister"}, ("बहन", "दीदी", "अप्पा"), "अपनी बहन को"),
        ({"brother"}, ("भाई", "भैया"), "अपने भाई को"),
        ({"wife", "husband", "spouse", "partner"}, ("पति", "पत्नी", "जीवनसाथी"), "अपने जीवनसाथी को"),
        ({"daughter", "son", "child", "children"}, ("बेटी", "बेटा", "बच्चा", "बच्चे", "संतान"), "अपने बच्चे को"),
        ({"teacher", "mentor"}, ("शिक्षक", "शिक्षिका", "गुरु", "अध्यापक"), "अपने शिक्षक को"),
        ({"colleague", "coworker", "office"}, ("सहकर्मी", "दफ्तर", "ऑफिस"), "अपने सहकर्मी को"),
        ({"friend"}, ("दोस्त", "मित्र", "यार"), "उस दोस्त को"),
    )
    for english_markers, hindi_markers, recipient in relationship_rules:
        if tokens & english_markers or any(marker in raw_text for marker in hindi_markers):
            return recipient
    return "उस दोस्त को"


def _share_recipient_is_generic(value: str) -> bool:
    """Reject audience labels; a recipient must be one identifiable person or relationship."""
    normalized = normalize_for_similarity(str(value or ""))
    generic_phrases = {
        "everyone", "anyone", "all people", "people", "sabko", "har kisi ko",
        "kisi ko", "logon ko", "log", "sabhi log", "hindi audience",
        "general audience", "social media audience", "audience", "viewers",
        "general public", "public", "followers", "friends", "family",
        "darshak", "darshakon", "janata", "users", "all viewers",
    }
    if normalized in generic_phrases:
        return True
    generic_tokens = {
        "audience", "viewers", "followers", "public", "people", "users",
        "friends", "family", "darshak", "darshakon", "janata",
    }
    return bool(set(normalized.split()) & generic_tokens)


def repair_concept_structure(concept: dict[str, Any]) -> dict[str, Any]:
    """Repair mechanical draft defects locally and use AI only for incomplete visual shots.

    Share-recipient selection is a deterministic editorial label, not a creative field
    worth another provider call. Spoken narration is never shortened locally.
    """
    if not isinstance(concept, dict):
        raise ValueError("Generated Reel must be a JSON object.")
    beats = concept.get("beats")
    if not isinstance(beats, list):
        return concept  # The main validator emits the canonical schema error.

    allowed_overlay_types = {"message", "note", "step", "contrast", "keyword"}
    overlay_aliases = {
        "label": "keyword", "tag": "keyword", "text": "keyword",
        "quote": "message", "dialogue": "message",
        "fact": "note", "tip": "note", "context": "note",
        "number": "step", "comparison": "contrast", "compare": "contrast",
    }
    for i, beat in enumerate(beats):
        if not isinstance(beat, dict):
            continue
        raw_type = beat.get("overlay_type", "")
        overlay_type = raw_type.strip().lower() if isinstance(raw_type, str) else ""
        if overlay_type not in allowed_overlay_types:
            fallback = overlay_aliases.get(overlay_type, "keyword")
            beat["overlay_type"] = fallback
            log(f"Structural repair: Beat {i+1} overlay_type normalized to {fallback}.")
        else:
            beat["overlay_type"] = overlay_type

    # Resolve the recipient locally: provider outages must not invalidate an otherwise
    # sound story merely because the model returned "everyone" or "Hindi audience".
    recipient = str(concept.get("share_recipient") or "").strip()
    recipient_needs_repair = (
        not 1 <= len(recipient.split()) <= 12
        or len(recipient) > 100
        or _share_recipient_is_generic(recipient)
    )
    if recipient_needs_repair:
        concept["share_recipient"] = _infer_share_recipient(concept)
        recipient = concept["share_recipient"]
        log(f"Structural repair: selected specific share recipient locally ({recipient}).")
    prompt_repairs = []
    for i, beat in enumerate(beats):
        if not isinstance(beat, dict):
            continue
        prompt = str(beat.get("video_prompt") or "").strip()
        words = len(prompt.split())
        if words < 45 or words > 180 or len(prompt) > 1600:
            prompt_repairs.append({
                "beat": i + 1,
                "visual_direction": str(beat.get("visual_direction") or ""),
                "visual_query": str(beat.get("visual_query") or ""),
                "current_prompt": prompt,
            })

    if prompt_repairs:
        context = {
            "title": str(concept.get("title") or ""),
            "theme": str(concept.get("theme") or ""),
            "share_reason": str(concept.get("share_reason") or ""),
            "human_detail": str(concept.get("human_detail") or ""),
            "character_contradiction": str(concept.get("character_contradiction") or ""),
            "characters": [
                {
                    "display_name": item.get("display_name", ""),
                    "role": item.get("role", ""),
                }
                for item in concept.get("characters", [])
                if isinstance(item, dict)
            ],
            "visual_bible": str(concept.get("visual_bible") or ""),
            "shots_requiring_repair": prompt_repairs,
        }
        requested_fields = []
        if prompt_repairs:
            requested_fields.append("video_prompts")
        repair_system = (
            "You are a production continuity editor. Repair only the explicitly requested "
            "structural fields. Preserve the story, characters, actions, emotional meaning "
            "and visual continuity. Return one valid JSON object only."
        )
        repair_prompt = f"""Repair this BINA SHOR KE draft's structural defects.

CONTEXT:
{json.dumps(context, ensure_ascii=False)}

REQUIRED OUTPUT FIELDS: {json.dumps(requested_fields)}
Rules:
- video_prompts must contain exactly one object for every supplied beat, preserving its beat number. Each replacement must be 65–100 concrete English words, describe only the supplied shot and its actual visible action, and retain the visual bible. Include framing, motivated light, tactile detail and coherent depth. Do not invent dialogue, characters, props or plot. No text, subtitles, logos or watermark.
- Do not return or alter the Hindi script, voiceover, speaker identity, beat order, caption or any unrequested field.
Return JSON only:
{{"video_prompts":[{{"beat":3,"video_prompt":"65–100 concrete English words"}}]}}"""
        repaired = text_json(repair_system, repair_prompt, temperature=0.2, timeout=90)
        if prompt_repairs:
            returned = repaired.get("video_prompts") if isinstance(repaired, dict) else None
            if not isinstance(returned, list):
                raise ValueError("Targeted structural repair returned no video_prompts list.")
            expected = {int(item["beat"]) for item in prompt_repairs}
            replacements: dict[int, str] = {}
            for item in returned:
                if not isinstance(item, dict):
                    raise ValueError("Targeted structural repair returned a malformed video prompt.")
                number = item.get("beat")
                prompt = item.get("video_prompt")
                if isinstance(number, bool) or not isinstance(number, int) or number not in expected or number in replacements:
                    raise ValueError("Targeted structural repair returned an unexpected or duplicate beat.")
                if not isinstance(prompt, str) or not 55 <= len(prompt.split()) <= 180 or len(prompt) > 1600:
                    raise ValueError(f"Targeted structural repair left Beat {number} outside the 55–180 word prompt gate.")
                lowered = prompt.lower()
                if any(term in lowered for term in ("subtitle overlay", "watermark text", "show the words", "write a caption")):
                    raise ValueError(f"Targeted structural repair introduced a forbidden text instruction in Beat {number}.")
                replacements[number] = prompt.strip()
            if set(replacements) != expected:
                raise ValueError("Targeted structural repair omitted one or more requested video prompts.")
            for number, prompt in replacements.items():
                beats[number - 1]["video_prompt"] = prompt
                log(f"Structural repair: Beat {number} visual prompt rewritten and revalidated.")

    # A near-threshold prompt can be completed safely without another model request.
    continuity_suffix = (
        "Preserve the established character design, wardrobe, spatial continuity, and layered "
        "foreground, middle ground, and background throughout."
    )
    for i, beat in enumerate(beats):
        if not isinstance(beat, dict):
            continue
        prompt = str(beat.get("video_prompt") or "").strip()
        words = len(prompt.split())
        if 45 <= words < 55 and len(prompt) + len(continuity_suffix) + 1 <= 1600:
            beat["video_prompt"] = prompt + " " + continuity_suffix
            log(f"Structural repair: Beat {i+1} visual prompt completed with continuity detail ({words} -> {len(beat['video_prompt'].split())} words).")

    invalid_lines = []
    for i, beat in enumerate(beats):
        if not isinstance(beat, dict):
            continue
        # Structured dialogue is validated as one complete screenplay below.
        # Never rewrite or shorten individual turns merely to fit a fixed-duration clip.
        if isinstance(beat.get("speech_segments"), list):
            continue
        voiceover = beat.get("voiceover")
        if not isinstance(voiceover, str):
            continue  # Main validator reports missing/invalid required fields.
        word_count = len(voiceover.split())
        if not 7 <= word_count <= 18:
            invalid_lines.append({
                "beat": i + 1,
                "voiceover": voiceover,
                "previous_line": beats[i - 1].get("voiceover", "") if i > 0 and isinstance(beats[i - 1], dict) else "",
                "next_line": beats[i + 1].get("voiceover", "") if i + 1 < len(beats) and isinstance(beats[i + 1], dict) else "",
                "word_count": word_count,
            })

    if invalid_lines:
        repair_system = (
            "You are a Hindi dialogue editor for short cinematic stories. "
            "Rewrite only the specified narration lines. Preserve meaning, causal continuity "
            "and natural spoken Hindi. Return valid JSON only."
        )
        repair_prompt = f"""Some narration lines failed a strict production timing check.

Story title: {concept.get('title', '')}
Story theme: {concept.get('theme', '')}
Human detail: {concept.get('human_detail', '')}
Character contradiction: {concept.get('character_contradiction', '')}

Lines requiring repair (beat numbers are one-based):
{json.dumps(invalid_lines, ensure_ascii=False)}

For EVERY listed beat, return exactly one replacement line with 7–18 whitespace-separated Hindi words. Preserve the same event and emotional meaning. Do not add facts, change the plot, use a moral slogan, or combine two sentences. Do not rewrite any other beat.
Return exactly this JSON shape:
{{"replacements":[{{"beat":1,"voiceover":"short natural Hindi line"}}]}}
The replacements array must contain every requested beat exactly once and no other beat numbers."""
        repaired = text_json(repair_system, repair_prompt, temperature=0.2)
        replacements = repaired.get("replacements") if isinstance(repaired, dict) else None
        expected = {int(item["beat"]) for item in invalid_lines}
        if not isinstance(replacements, list):
            raise ValueError("Targeted narration repair returned no replacements array.")
        received: dict[int, str] = {}
        for item in replacements:
            if not isinstance(item, dict):
                raise ValueError("Targeted narration repair returned a malformed replacement.")
            beat_number = item.get("beat")
            line = item.get("voiceover")
            if isinstance(beat_number, bool) or not isinstance(beat_number, int) or not isinstance(line, str):
                raise ValueError("Targeted narration repair returned an invalid beat number or line.")
            if beat_number not in expected or beat_number in received:
                raise ValueError("Targeted narration repair returned an unexpected or duplicate beat.")
            line = line.strip()
            repaired_word_count = len(line.split())
            if not 7 <= repaired_word_count <= 18:
                raise ValueError(
                    f"Targeted narration repair left Beat {beat_number} at {repaired_word_count} words; "
                    "the allowed range is 7–18."
                )
            received[beat_number] = line
        if set(received) != expected:
            missing = sorted(expected - set(received))
            raise ValueError("Targeted narration repair omitted beat(s): " + ", ".join(map(str, missing)))
        for beat_number, line in received.items():
            beats[beat_number - 1]["voiceover"] = line
            log(f"Structural repair: Beat {beat_number} narration shortened and revalidated.")

    return concept


def validate_concept_shape(concept: dict[str, Any]) -> None:
    required = ["title", "theme", "hook", "beats", "story_type", "caption", "hashtags", "cover_text", "visual_bible", "share_reason", "share_recipient", "narrative_engine", "emotional_aftertaste", "human_detail", "character_contradiction", "cost_of_choice"]
    missing = [k for k in required if not concept.get(k)]
    if missing:
        raise ValueError("Generated concept misses required fields: " + ", ".join(missing))
    recipient = str(concept.get("share_recipient") or "").strip()
    if not 1 <= len(recipient.split()) <= 12 or len(recipient) > 100:
        raise ValueError("Share recipient must identify one specific person or relationship (1–12 words), not a broad audience.")
    recipient_normalized = normalize_for_similarity(recipient)
    if _share_recipient_is_generic(recipient):
        raise ValueError("Share recipient is too generic; name a concrete relationship or person.")
    if not isinstance(concept["beats"], list) or len(concept["beats"]) != 6:
        raise ValueError("Screenplay must contain exactly 6 narrative beats; editorial coverage is derived after measured voice timing.")
    story_engine.validate_narrative_arc(concept["beats"])
    allowed_overlay_types = {"message", "note", "step", "contrast", "keyword"}
    structured_script = all(isinstance(beat.get("speech_segments"), list) for beat in concept["beats"] if isinstance(beat, dict))
    character_ids = {
        str(item.get("character_id", "")) for item in concept.get("characters", [])
        if isinstance(item, dict)
    }
    if structured_script and not character_ids:
        raise ValueError("Structured screenplay requires at least one cast character.")
    for i, beat in enumerate(concept["beats"]):
        beat.setdefault("voice_direction", "Natural Hindi; restrained and conversational.")
        for key in ("narrative_role", "state_change", "causal_link", "screen_text", "visual_query", "visual_direction", "video_prompt", "overlay_text", "overlay_type"):
            if not isinstance(beat.get(key), str) or not beat[key].strip():
                raise ValueError(f"Beat {i+1} misses {key}.")
        if not structured_script and (not isinstance(beat.get("voiceover"), str) or not beat["voiceover"].strip()):
            raise ValueError(f"Beat {i+1} misses voiceover.")
        if beat["overlay_type"] not in allowed_overlay_types:
            raise ValueError(f"Beat {i+1} has an unsupported overlay_type.")
        if structured_script:
            if not isinstance(beat.get("speech_segments"), list):
                raise ValueError(f"Beat {i+1} speech_segments must be a list.")
            for line_index, segment in enumerate(beat["speech_segments"], start=1):
                if not isinstance(segment, dict) or str(segment.get("speaker_id", "")) not in character_ids:
                    raise ValueError(f"Beat {i+1} line {line_index} references an unknown speaker.")
                if not isinstance(segment.get("text"), str) or not segment["text"].strip():
                    raise ValueError(f"Beat {i+1} line {line_index} has no dialogue text.")
            beat["voiceover"] = " ".join(segment["text"] for segment in beat["speech_segments"])
        else:
            spoken_words = len(beat["voiceover"].split())
            if not 7 <= spoken_words <= 18:
                raise ValueError(f"Beat {i+1} narration has {spoken_words} words; use 7–18 words; measured audio, not a fixed beat template, controls shot timing.")
        if len(beat["screen_text"]) > 70 or len(beat["overlay_text"]) > 42:
            raise ValueError(f"Beat {i+1} text exceeds mobile-safe limits.")
        prompt_words = len(beat["video_prompt"].split())
        if not 55 <= prompt_words <= 180 or len(beat["video_prompt"]) > 1600:
            raise ValueError(f"Beat {i+1} video_prompt has {prompt_words} words; use 55–180 concrete words for a cinematic shot.")
        lowered_prompt = beat["video_prompt"].lower()
        for forbidden in ("subtitle overlay", "watermark text", "show the words", "write a caption"):
            if forbidden in lowered_prompt:
                raise ValueError(f"Beat {i+1} video prompt risks text artifacts: {forbidden}.")
        # The custom editorial layer must add information/context, not simply duplicate the subtitle.
        overlay_norm = normalize_for_similarity(beat["overlay_text"])
        screen_norm = normalize_for_similarity(beat["screen_text"])
        voice_norm = normalize_for_similarity(beat["voiceover"])
        if overlay_norm and (overlay_norm == screen_norm or overlay_norm in voice_norm and len(overlay_norm.split()) >= 4):
            raise ValueError(f"Beat {i+1} overlay repeats the narration instead of adding creative context.")
    overlay_texts = [normalize_for_similarity(b["overlay_text"]) for b in concept["beats"]]
    if len(set(overlay_texts)) < max(3, len(overlay_texts) - 1):
        raise ValueError("Too many repeated editorial overlays; every beat must add distinct context.")
    visual_queries = [normalize_for_similarity(b["visual_query"]) for b in concept["beats"]]
    if len(set(visual_queries)) < max(3, len(visual_queries) - 1):
        raise ValueError("Too many repeated visual queries; each shot must serve a distinct story beat.")
    if not isinstance(concept["hashtags"], list):
        concept["hashtags"] = []
    if len(concept["hashtags"]) > 5:
        concept["hashtags"] = concept["hashtags"][:5]
    if len(concept["hashtags"]) < 3:
        concept["hashtags"] = list(concept["hashtags"]) + ["#HindiStories", "#HumanBehaviour"]
    if not any(str(tag).lower() == "#binashorke" for tag in concept["hashtags"]):
        concept["hashtags"].insert(0, "#BinaShorKe")
        concept["hashtags"] = concept["hashtags"][:5]
    concept["hashtags"] = [str(t).strip().replace(" ", "") for t in concept["hashtags"]]
    story_engine.validate_screenplay_length(concept)
    hook_word_count = len(str(concept["hook"]).split())
    if len(concept["hook"]) > 70 or not 3 <= hook_word_count <= 10:
        raise ValueError("Hook must be a clear 3–10-word first-screen line and under 70 characters.")



def generate_voice_aware_storyboard(concept: dict[str, Any]) -> dict[str, Any]:
    """Author final shot prompts only after speaker WAVs and exact durations are locked."""
    if concept.get("voice_first_plan", {}).get("status") != "voice_measured_before_video":
        raise RuntimeError("Voice-aware storyboard requires measured TTS audio before any video prompt is finalized.")
    characters = concept.get("characters", [])
    cast = {
        str(item["character_id"]): {
            "display_name": item.get("display_name", item["character_id"]),
            "role": item.get("role", "supporting"),
            "appearance": item.get("appearance", ""),
            "personality": item.get("personality", ""),
            "gender_presentation": item.get("gender_presentation", "unspecified"),
            "age_band": item.get("age_band", "adult"),
            "visual_age_description": item.get("visual_age_description") or voice_first.visual_age_description(item.get("age_band", "adult")),
            "voice_profile_id": item.get("voice_profile_id", ""),
            "voice_style": item.get("voice_direction", ""),
        }
        for item in characters
    }
    brief = []
    for index, beat in enumerate(concept.get("beats", []), start=1):
        timing = beat.get("voice_timing")
        if not isinstance(timing, dict) or timing.get("timing_source") != "measured_tts_wav_before_gpu":
            raise RuntimeError(f"Beat {index} is missing its measured voice timeline; refusing to guess scene duration.")
        turns = []
        placed_by_id = {str(item["segment_id"]): item for item in timing.get("segments", [])}
        for segment in beat.get("speech_segments", []):
            speaker = cast.get(str(segment.get("speaker_id")), {})
            placed = placed_by_id.get(str(segment.get("segment_id")), {})
            turns.append({
                "speaker_id": segment.get("speaker_id"),
                "speaker_name": speaker.get("display_name"),
                "appearance": speaker.get("appearance"),
                "visual_age_description": speaker.get("visual_age_description"),
                "personality": speaker.get("personality"),
                "voice_profile_id": speaker.get("voice_profile_id"),
                "spoken_dialogue": segment.get("text"),
                "emotion": segment.get("emotion"),
                "audio_start_seconds": placed.get("start_seconds"),
                "audio_end_seconds": placed.get("end_seconds"),
                "actual_audio_duration_seconds": segment.get("duration_seconds"),
            })
        brief.append({
            "beat_index": index,
            "narrative_role": beat.get("narrative_role"),
            "state_change": beat.get("state_change"),
            "causal_link": beat.get("causal_link"),
            "target_duration_seconds": timing["target_duration_seconds"],
            "target_frames": timing["target_frames"],
            "fps": timing["fps"],
            "visual_direction": beat.get("visual_direction", ""),
            "visual_query": beat.get("visual_query", ""),
            "visual_bible": concept.get("visual_bible", ""),
            "spoken_turns_in_exact_audio_order": turns,
            "initial_visual_prompt_for_reference_only": beat.get("video_prompt", ""),
        })

    system = (
        "You are the animation director and shot designer for a premium Hindi 2.5D motion-comic studio. "
        "The screenplay and all character voices are already final and measured. You are writing the "
        "FINAL video-generation shot prompts AFTER audio lock. Never rewrite dialogue, change the cast, "
        "add a character, add a prop, invent an event, or change the established story outcome. "
        "Match each shot's exact duration and its speaker turn timestamps. For dialogue, make the correct "
        "speaker visibly speak during their own audio interval; show natural mouth/jaw motion, eye focus, "
        "micro-expressions and restrained gestures. For the listener, use a believable reaction without "
        "moving the mouth as if speaking. If there are multiple turns, plan a clear camera cut or deliberate "
        "shot composition that follows the turn order; the final editor will preserve the full audio timeline. "
        "Use each beat's narrative_role to control its visual purpose and depict its state_change rather than repeating the previous image. Respect causal_link: do not show a later consequence before its cause. Use the visual bible, canonical visual_age_description and character appearance verbatim for continuity. Keep the same illustrated character design, outfit, palette and environment across every source beat. "
        "The visible age/gender presentation of every speaker must match that speaker's locked voice profile; "
        "never age a character up or down to fit a voice. One clear physical action per "
        "shot, plausible anatomy and physics, purposeful camera coverage, illustrated surface treatment, layered foreground/midground/background separation and readable "
        "silhouette. Never put any readable text, subtitles, logo or watermark inside the generated video. "
        "Do not shorten any line or force every beat to the same length. Return valid JSON only."
    )
    user_prompt = f"""Create exactly six source-scene prompts from this voice-locked Hindi screenplay. These are narrative-beat source clips; final editorial cuts are assembled from measured timing.

TITLE: {concept.get("title", "")}
STYLE / VISUAL BIBLE: {concept.get("visual_bible", "")}
CAST (immutable): {json.dumps(cast, ensure_ascii=False)}
MEASURED AUDIO AND BEAT STORYBOARDS:
{json.dumps(brief, ensure_ascii=False)}

Return exactly:
{{"shots":[
  {{"beat_index":1,"video_prompt":"100–160 concrete English words. Describe the exact characters, shot size, camera placement/movement, physical action, speaker/listener facial acting and mouth motion, lighting, environment, material detail and continuity. The shot is exactly the supplied target duration."}}
]}}
Rules:
- Exactly one entry for every beat_index 1 through 6, no missing or duplicate indices.
- The video_prompt is final and must be 55–180 whitespace-separated words, <=1600 characters. Use a mature semi-painterly Indian graphic-novel motion-comic style, not photoreal live-action or generic glossy 3D.
- The measured target_duration_seconds and target_frames are authoritative; do not change them.
- If a beat is silent, do not invent dialogue or fake speech mouth motion.
- Keep every character's visible age exactly aligned with the canonical visual_age_description and age_band in CAST; never de-age or age-up a speaker.
- Adult feminine speakers must look adult and use the adult profile; reserve older/elder appearance and Gacrux for older_adult/elder characters only.
- Do not convert this story to a different genre or add characters merely to improve a shot.
- Do not return or modify any Hindi script, dialogue, captions or voice metadata.
Return JSON only."""
    response = text_json(system, user_prompt, temperature=0.45, timeout=150)
    shots = response.get("shots")
    if not isinstance(shots, list) or len(shots) != 6:
        raise ValueError("Voice-aware storyboard must return exactly six shot prompts.")
    by_index: dict[int, str] = {}
    for shot in shots:
        if not isinstance(shot, dict):
            raise ValueError("Each voice-aware storyboard shot must be an object.")
        try:
            index = int(shot.get("beat_index"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Every storyboard shot needs an integer beat_index.") from exc
        if index in by_index or index not in range(1, 7):
            raise ValueError(f"Duplicate or out-of-range storyboard beat_index: {index}")
        prompt = str(shot.get("video_prompt") or "").strip()
        word_count = len(prompt.split())
        if not 55 <= word_count <= 180 or len(prompt) > 1600:
            raise ValueError(f"Final shot {index} has {word_count} words / {len(prompt)} characters; expected 55–180 words and <=1600 characters.")
        lowered = prompt.lower()
        for forbidden in ("subtitle overlay", "watermark text", "show the words", "write a caption"):
            if forbidden in lowered:
                raise ValueError(f"Final shot {index} risks generated text artifacts: {forbidden}.")
        by_index[index] = prompt
    if set(by_index) != set(range(1, 7)):
        raise ValueError("Final storyboard is missing one or more beat indices.")
    for index, beat in enumerate(concept["beats"], start=1):
        beat["video_prompt"] = by_index[index]
    concept["voice_aware_storyboard"] = {
        "status": "generated_after_voice_lock",
        "timing_basis": "measured_tts_wav_before_gpu",
        "source_scene_count": 6,
        "dialogue_rewritten": False,
        "target_frames_changed": False,
    }
    beat_durations = [float(beat["voice_timing"]["target_duration_seconds"]) for beat in concept["beats"]]
    duration_lock = story_engine.validate_measured_duration(sum(beat_durations), concept.get("story_type", "emotional"))
    shot_plan = story_engine.build_editorial_shot_plan(beat_durations, concept.get("story_type", "emotional"))
    concept["duration_lock"] = duration_lock
    concept["editorial_shot_plan"] = shot_plan
    concept["visual_pipeline"] = shot_plan["visual_pipeline"]
    concept["visual_style_profile"] = shot_plan["visual_style_profile"]
    for beat_index, beat in enumerate(concept["beats"], start=1):
        beat["editorial_shots"] = story_engine.shots_for_beat(shot_plan, beat_index)
    log(f"Locked {duration_lock['measured_seconds']:.2f}s {duration_lock['story_type']} story; {shot_plan['editorial_shot_count']} editorial shots from {shot_plan['source_beat_count']} source-video generations.")
    return concept


def judge_concept(concept: dict[str, Any]) -> dict[str, Any]:
    system = (
        "You are an independent Hindi short-film story editor, dialogue doctor, "
        "audience psychologist and illustrated motion-comic shot supervisor. Evaluate the story "
        "as a human experience before evaluating production craft. Return JSON only. "
        "Reject generic motivation, forced sentiment, emotional manipulation, "
        "recycled twists, implausible behaviour and AI-artifact-prone prompts."
    )
    prompt = f"""Evaluate this BINA SHOR KE Reel concept as a strict second-opinion editor:
{json.dumps(concept, ensure_ascii=False)}

Score every dimension from 1 to 5. Test whether a real person recognises the situation, whether emotion is earned through specific behaviour, and whether the ending leaves a memorable human aftertaste without preaching. Inspect share_recipient: it must name a concrete person/relationship and match the story's real emotional or practical reason for sending.
Required scores: hook_clarity, specificity, human_specificity, emotional_resonance, story_progression, payoff, readability, originality, creative_contribution_beyond_stock, visual_match, illustrated_visual_quality, motion_feasibility, continuity_coherence, voiceover_rhythm, caption_quality, share_value, platform_safety.

Human-specificity: at least one small, observable, non-generic detail should make the scene feel lived-in. Emotional resonance must come from a choice, pause, object or consequence; do not reward tragedy or melodrama alone. Dialogue must sound natural when read aloud, not like an essay, translation or generic moral. The ending should change the meaning of an earlier detail or reveal a cost/choice.

Visual test: every prompt must describe a mature illustrated graphic-novel shot, clear action, physically plausible motion, foreground/midground/background depth cues, coherent camera framing, motivated light, tactile painterly detail and continuity. Penalize impossible physics, inconsistent clothing/characters, generated text, vague "cinematic 8K" filler and repeated shots.

Return JSON exactly in this shape:
{{"scores":{{"hook_clarity":1,"specificity":1,"human_specificity":1,"emotional_resonance":1,"story_progression":1,"payoff":1,"readability":1,"originality":1,"creative_contribution_beyond_stock":1,"visual_match":1,"illustrated_visual_quality":1,"motion_feasibility":1,"continuity_coherence":1,"voiceover_rhythm":1,"caption_quality":1,"share_value":1,"platform_safety":1}},"approved":true,"revision_notes":["..."],"main_risk":"...","human_truth":"one sentence describing the recognisable human truth, or what is missing"}}

Approve only if average >=4.2 and every critical dimension is >=4: hook_clarity, story_progression, payoff, human_specificity, emotional_resonance, originality, creative_contribution_beyond_stock, illustrated_visual_quality, motion_feasibility, continuity_coherence, voiceover_rhythm, share_value and platform_safety. A high emotional score must be earned by writing, not dramatic subject matter. This is an editorial gate, not a Meta eligibility or reach verdict."""
    return independent_review_json(system, prompt, temperature=0.2)


def revise_concept(concept: dict[str, Any], review: dict[str, Any], history: dict[str, Any], slot: datetime) -> dict[str, Any]:
    notes = review.get("revision_notes", []) if isinstance(review, dict) else []
    prompt = f"""Revise this Reel using the specific editorial critique. Do not merely paraphrase it. Preserve the useful core only if original enough; replace the angle completely if needed. Return the full production JSON schema including story_type, share_reason, share_recipient, visual_bible, narrative_engine, emotional_aftertaste, human_detail, character_contradiction, cost_of_choice and every beat's narrative_role, state_change, causal_link, voice_direction, video_prompt, overlay_type and overlay_text. Choose exactly one overlay_type from message, note, step, contrast, keyword. Every overlay adds context and must not repeat narration. Use exactly 6 beats in hook, context, conflict, escalation, turn, payoff order; keep every voiceover line to story_type-specific spoken-word ranges. Each video_prompt must be one physically plausible semi-painterly 2.5D illustrated vertical shot with a single action, practical light, camera/lens language, natural imperfect texture, no generated text/logo/watermark, and continuity with visual_bible.
CURRENT DRAFT: {json.dumps(concept, ensure_ascii=False)}
REVIEW NOTES: {json.dumps(notes, ensure_ascii=False)}
PRIMARY RISK: {str(review.get('main_risk',''))[:500]}
RECENT TITLES/THEMES TO AVOID: {json.dumps([{ "title": x.get("title", ""), "theme": x.get("theme", "") } for x in history.get("topics", [])[-35:]], ensure_ascii=False)}
Return one valid JSON object only."""
    revised = text_json("You are a senior editor rewriting original Hindi short-form content. Apply the critique directly. Output JSON only.", prompt, temperature=0.55)
    revised["pillar"] = concept["pillar"]
    revised["story_type"] = concept["story_type"]
    revised["series_name"] = SERIES_BY_PILLAR[concept["pillar"]]
    revised["planned_publish_at"] = slot.isoformat()
    revised["planned_publish_label"] = slot.strftime("%a %d %b, %I:%M %p IST")
    revised = repair_concept_structure(revised)
    validate_concept_shape(revised)
    if topic_is_too_similar(str(revised.get("title", "")), str(revised.get("theme", "")), history.get("topics", [])):
        raise ValueError("Revised concept is too similar to recent title/theme history.")
    if human_detail_is_too_similar(str(revised.get("human_detail", "")), history.get("topics", [])):
        raise ValueError("Revised concept repeats a recent distinctive human detail; choose a genuinely different lived-in anchor.")
    return revised


def acquire_approved_concept(history: dict[str, Any], pillar: str, slot: datetime, index: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """Draft, independently critique, apply targeted revisions once, then fail closed."""
    concept = None
    draft_failures: list[str] = []
    # Three bounded candidate attempts absorb occasional malformed beat-count/cast metadata
    # without unbounded provider calls. All providers remain on the configured free-tier allowlist.
    previous_feedback = ""
    for candidate_attempt in range(3):
        try:
            candidate = generate_concept(
                history, pillar, slot, index + candidate_attempt * 7,
                correction_feedback=previous_feedback,
            )
            if topic_is_too_similar(str(candidate.get("title", "")), str(candidate.get("theme", "")), history.get("topics", [])):
                raise ValueError("Recent title/theme similarity detected; choose a genuinely different story angle.")
            if human_detail_is_too_similar(str(candidate.get("human_detail", "")), history.get("topics", [])):
                raise ValueError("Recent lived-in story detail repeated; create a distinct human observation.")
            concept = candidate
            break
        except Exception as exc:
            message = str(exc)
            draft_failures.append(message[:400])
            log(f"Draft candidate {candidate_attempt + 1}/3 rejected: {message[:400]}")
            previous_feedback = message[:700]
            lowered = message.lower()
            # Once all configured free providers have failed with quota/transient errors,
            # a second candidate cannot help. Stop here instead of making a redundant call.
            provider_unavailable = any(marker in lowered for marker in (
                "no configured free text providers are currently available",
                "http 429", "http 500", "http 502", "http 503", "http 504",
                "quota exceeded", "rate limit", "temporarily unavailable",
                "timed out", "timeout", "connection error",
            ))
            if provider_unavailable:
                raise RuntimeError(
                    "Configured free AI providers are temporarily unavailable or rate-limited; "
                    "no paid fallback was attempted. Retry later. " + message[:700]
                )
    if concept is None:
        raise RuntimeError("No valid non-duplicate Reel draft passed the structural gate. Nothing was delivered. " + " | ".join(draft_failures))

    review = judge_concept(concept)
    def verdict(result: dict[str, Any]) -> tuple[bool, dict[str, Any], float, float, float, float, float]:
        expected_scores = (
            "hook_clarity", "specificity", "human_specificity", "emotional_resonance", "story_progression", "payoff", "readability",
            "originality", "creative_contribution_beyond_stock", "visual_match", "illustrated_visual_quality",
            "motion_feasibility", "continuity_coherence", "voiceover_rhythm", "caption_quality", "share_value", "platform_safety",
        )
        scores = result.get("scores", {})
        if not isinstance(scores, dict) or any(key not in scores for key in expected_scores):
            return False, scores if isinstance(scores, dict) else {}, 0.0, 0.0, 0.0, 0.0, 0.0
        if any(not isinstance(scores[key], (int, float)) or not 1 <= float(scores[key]) <= 5 for key in expected_scores):
            return False, scores, 0.0, 0.0, 0.0, 0.0, 0.0
        values = [float(scores[key]) for key in expected_scores]
        avg = sum(values) / len(values)
        orig = float(scores["originality"])
        creative = float(scores["creative_contribution_beyond_stock"])
        safety = float(scores["platform_safety"])
        visual_quality = float(scores["illustrated_visual_quality"])
        motion = float(scores["motion_feasibility"])
        share = float(scores["share_value"])
        human = float(scores["human_specificity"])
        emotion = float(scores["emotional_resonance"])
        continuity = float(scores["continuity_coherence"])
        rhythm = float(scores["voiceover_rhythm"])
        progression = float(scores["story_progression"])
        payoff = float(scores["payoff"])
        approved = bool(result.get("approved")) and avg >= 4.2 and progression >= 4 and payoff >= 4 and orig >= 4 and creative >= 4 and visual_quality >= 4 and motion >= 4 and continuity >= 4 and rhythm >= 4 and share >= 4 and human >= 4 and emotion >= 4 and safety >= 4
        return approved, scores, avg, orig, creative, safety, share

    approved, scores, avg, orig, creative, safety, share = verdict(review)
    passes = 1
    if not approved:
        log(f"Editorial gate requested revision (avg={avg:.2f}, progression={scores.get('story_progression', 0)}, payoff={scores.get('payoff', 0)}, human={scores.get('human_specificity', 0)}, emotion={scores.get('emotional_resonance', 0)}, originality={orig:.1f}, share_value={share:.1f}, safety={safety:.1f}).")
        concept = revise_concept(concept, review, history, slot)
        review = judge_concept(concept)
        approved, scores, avg, orig, creative, safety, share = verdict(review)
        passes = 2

    concept["editorial_review"] = {
        "scores": scores,
        "average_score": round(avg, 2),
        "approved": approved,
        "revision_notes": review.get("revision_notes", []),
        "main_risk": review.get("main_risk", ""),
        "department_notes": review.get("department_notes", {}),
        "passes": passes,
    }
    concept["originality_safeguards"] = {
        "original_script_and_story_arc": True,
        "custom_story_specific_overlays_required": True,
        "recent_title_theme_similarity_check": "passed",
        "source_clip_reuse_check": "active",
        "not_a_Meta_eligibility_guarantee": True,
    }
    if not approved:
        raise RuntimeError(
            f"Editorial gate rejected draft after targeted revision (average={avg:.2f}, originality={orig:.1f}, "
            f"creative={creative:.1f}, share_value={share:.1f}, safety={safety:.1f}). No Reel delivered. Notes={review.get('revision_notes', [])}"
        )
    return concept, review


def pexels_search(query: str, history_asset_ids: set[str], current_ids: set[str]) -> dict[str, Any]:
    headers = {"Authorization": PEXELS_API_KEY}
    queries = [query]
    # A fallback query drops modifiers to improve recall without repeating the first exact search.
    words = re.findall(r"[A-Za-z]+", query)
    if len(words) >= 4:
        queries.append(" ".join(words[:3]))
    for q in queries:
        params = {"query": q, "orientation": "portrait", "per_page": 12}
        response = requests.get("https://api.pexels.com/v1/videos/search", headers=headers, params=params, timeout=45)
        if response.status_code == 429:
            time.sleep(8)
            response = requests.get("https://api.pexels.com/v1/videos/search", headers=headers, params=params, timeout=45)
        response.raise_for_status()
        videos = response.json().get("videos", [])
        # If no vertical clips are returned, allow all aspect ratios and crop carefully.
        if not videos:
            params.pop("orientation", None)
            response = requests.get("https://api.pexels.com/v1/videos/search", headers=headers, params=params, timeout=45)
            response.raise_for_status()
            videos = response.json().get("videos", [])
        candidates = []
        for video in videos:
            vid = str(video.get("id", ""))
            if not vid or vid in history_asset_ids or vid in current_ids:
                continue
            files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("link")]
            if not files:
                continue
            def file_score(f: dict[str, Any]) -> tuple[float, float]:
                w, h = float(f.get("width", 0) or 0), float(f.get("height", 0) or 0)
                if not w or not h:
                    return (999.0, 0)
                aspect_penalty = abs((w / h) - (9 / 16))
                size_penalty = 0 if h <= 2000 and w <= 1200 else 0.25
                res_reward = min(h, 1920) / 1920
                return (aspect_penalty + size_penalty, -res_reward)
            files.sort(key=file_score)
            best = files[0]
            if int(best.get("height", 0) or 0) < 480:
                continue
            candidates.append((file_score(best)[0], -min(int(best.get("height", 0) or 0), 1920), video, best))
        if candidates:
            candidates.sort(key=lambda x: (x[0], x[1]))
            # Use a small random choice from the best few to avoid deterministic-looking repeats.
            top = candidates[: min(4, len(candidates))]
            _, _, video, best_file = random.choice(top)
            return {
                "id": str(video["id"]),
                "url": video.get("url", "https://www.pexels.com"),
                "creator": (video.get("user") or {}).get("name", "Pexels contributor"),
                "creator_url": (video.get("user") or {}).get("url", "https://www.pexels.com"),
                "download_url": best_file["link"],
                "width": best_file.get("width"),
                "height": best_file.get("height"),
                "query_used": q,
            }
    raise RuntimeError(f"No unused Pexels clip found for visual query: {query!r}. Nothing will be fabricated; rerun later or revise query.")


def download_file(url: str, destination: Path, max_bytes: int = 150 * 1024 * 1024) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=(20, 90)) as response:
        response.raise_for_status()
        length = int(response.headers.get("content-length", "0") or 0)
        if length and length > max_bytes:
            raise RuntimeError(f"Downloaded asset is too large ({length} bytes); refusing it.")
        written = 0
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 512):
                if not chunk:
                    continue
                written += len(chunk)
                if written > max_bytes:
                    raise RuntimeError("Asset exceeded size limit while downloading.")
                handle.write(chunk)
    if destination.stat().st_size < 20_000:
        destination.unlink(missing_ok=True)
        raise RuntimeError("Downloaded video is unexpectedly small or invalid.")


def tts_wav(
    text: str,
    destination: Path,
    voice_direction: str | None = None,
    voice_name: str | None = None,
) -> None:
    """Generate one speaker's Hindi turn using free-tier TTS and save 24 kHz mono WAV."""
    url = "https://generativelanguage.googleapis.com/v1beta/interactions"
    direction = (voice_direction or "").strip()
    selected_voice = str(voice_name or TTS_VOICE).strip()
    if not selected_voice:
        raise ValueError("A non-empty Gemini TTS voice name is required.")
    speech_style = (
        "Natural Hindi; warm, grounded, restrained, clear diction. "
        "Line direction: " + direction[:120]
    )
    # Current Interactions API schema; narration text is only the requested line, style is metadata.
    # Request raw PCM explicitly so the WAV container below is correct (no nested WAV headers).
    payload = {
        "model": GEMINI_TTS_MODEL,
        "input": [{
            "type": "user_input",
            "content": [{
                "type": "text",
                "text": text,
                "annotations": [{"type": "speech_metadata", "style": speech_style}],
            }],
        }],
        "response_format": {"type": "audio", "mime_type": "audio/l16", "sample_rate": 24000},
        "generation_config": {"speech_config": [{"voice": selected_voice}]},
    }
    global _LAST_TTS_REQUEST_AT
    last_error = None
    retryable_http_statuses = {408, 429, 500, 502, 503, 504}
    for attempt in range(3):
        elapsed = time.monotonic() - _LAST_TTS_REQUEST_AT
        if _LAST_TTS_REQUEST_AT and elapsed < TTS_MIN_INTERVAL_SECONDS:
            time.sleep(TTS_MIN_INTERVAL_SECONDS - elapsed)
        _LAST_TTS_REQUEST_AT = time.monotonic()

        try:
            response = requests.post(
                url,
                headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                json=payload,
                timeout=180,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < 2:
                time.sleep((attempt + 1) * 5)
                continue
            break

        if response.status_code in retryable_http_statuses:
            last_error = f"Gemini TTS HTTP {response.status_code}: {response.text[:300]}"
            if attempt < 2:
                # Back off only for explicit transient provider statuses. Never retry an
                # authentication, request, safety-policy, response-format or local file error.
                time.sleep((attempt + 1) * (20 if response.status_code == 429 else 8))
                continue
            break
        if response.status_code >= 400:
            raise RuntimeError(
                f"Gemini TTS non-retryable HTTP {response.status_code}: {response.text[:300]}. "
                "The request was not retried."
            )

        body = response.json()
        audio_data = (body.get("output_audio") or {}).get("data")
        if not audio_data:
            for step in body.get("steps", []):
                if step.get("type") == "model_output":
                    for content in step.get("content", []):
                        if content.get("type") == "audio" and content.get("data"):
                            audio_data = content["data"]
        if not audio_data:
            raise ValueError("No audio block found in Gemini TTS response; request was not retried.")
        pcm = base64.b64decode(audio_data, validate=True)
        if len(pcm) < 4000 or len(pcm) % 2:
            raise ValueError("Gemini TTS returned an unexpectedly small or misaligned PCM payload; request was not retried.")

        destination.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(destination), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            wav_file.writeframes(pcm)
        with wave.open(str(destination), "rb") as check:
            if check.getnchannels() != 1 or check.getsampwidth() != 2 or check.getframerate() != 24000:
                raise ValueError("Rendered voice WAV failed sample-format verification; request was not retried.")
        return

    raise RuntimeError(
        f"Gemini TTS failed after bounded transient retries: {last_error}. "
        "No paid model fallback was attempted."
    )


def _tts_wav_validation_error(path: Path) -> str | None:
    """Return a precise cache-format/duration defect without hiding WAV measurements."""
    try:
        with wave.open(str(path), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            frames = wav_file.getnframes()
            if channels != 1:
                return f"expected mono audio, received {channels} channel(s)"
            if sample_width != 2:
                return f"expected 16-bit PCM, received {sample_width * 8}-bit samples"
            if sample_rate != 24000:
                return f"expected 24000 Hz, received {sample_rate} Hz"
            if frames <= 0:
                return "WAV contains zero PCM frames"
            duration = frames / float(sample_rate)
            if duration < TTS_MIN_DURATION_SECONDS or duration > TTS_MAX_DURATION_SECONDS:
                return (
                    f"measured duration {duration:.3f}s is outside the "
                    f"{TTS_MIN_DURATION_SECONDS:.2f}–{TTS_MAX_DURATION_SECONDS:.2f}s "
                    "TTS transport/cache range"
                )
            return None
    except (OSError, EOFError, wave.Error) as exc:
        return f"unreadable WAV container ({type(exc).__name__}): {exc}"


def _valid_tts_wav(path: Path) -> bool:
    return _tts_wav_validation_error(path) is None


def ensure_tts_wav(
    text: str,
    destination: Path,
    voice_direction: str | None = None,
    voice_name: str | None = None,
) -> str:
    """Reuse only a validated WAV whose SHA-256 sidecar matches this exact narration text.

    The repository-wide cache is restored by GitHub Actions so transient finalization
    retries do not regenerate identical voice lines and burn additional free-tier quota.
    """
    selected_voice = str(voice_name or TTS_VOICE).strip()
    cache_material = text + "\n[voice_direction=" + (voice_direction or "") + "]\n[gemini_voice=" + selected_voice + "]"
    digest = hashlib.sha256(cache_material.encode("utf-8")).hexdigest()
    sidecar_suffix = ".wav.sha256"
    cached_audio = TTS_CACHE_DIR / f"{digest}.wav"
    cached_sidecar = TTS_CACHE_DIR / f"{digest}{sidecar_suffix}"
    local_sidecar = destination.with_suffix(destination.suffix + ".sha256")

    if cached_audio.exists() and cached_sidecar.exists():
        try:
            cache_matches = cached_sidecar.read_text(encoding="ascii").strip() == digest
        except (OSError, UnicodeError):
            cache_matches = False
        if cache_matches and _valid_tts_wav(cached_audio):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cached_audio, destination)
            local_sidecar.write_text(digest, encoding="ascii")
            log(f"Reusing validated global TTS cache: {cached_audio.name}")
            return "cached"

    # Also support a same-run local cache, useful if an exception restarts one Reel.
    if destination.exists() and local_sidecar.exists():
        try:
            same_text = local_sidecar.read_text(encoding="ascii").strip() == digest
        except (OSError, UnicodeError):
            same_text = False
        if same_text and _valid_tts_wav(destination):
            log(f"Reusing validated local TTS cache: {destination.name}")
            return "cached"

    destination.unlink(missing_ok=True)
    local_sidecar.unlink(missing_ok=True)
    tts_wav(text, destination, voice_direction=voice_direction, voice_name=selected_voice)
    validation_error = _tts_wav_validation_error(destination)
    if validation_error:
        raise RuntimeError(
            "TTS result failed cache-format/duration validation: " + validation_error
        )

    TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Write a temporary file then atomically replace to avoid partially cached audio.
    tmp_cache = cached_audio.with_suffix(".wav.tmp")
    shutil.copy2(destination, tmp_cache)
    tmp_cache.replace(cached_audio)
    tmp_sidecar = cached_sidecar.with_suffix(cached_sidecar.suffix + ".tmp")
    tmp_sidecar.write_text(digest, encoding="ascii")
    tmp_sidecar.replace(cached_sidecar)
    # Marker is consumed by the workflow before cache/save, so periodic no-op polls
    # do not create a new cache snapshot every two hours.
    (TTS_CACHE_DIR / ".dirty").touch()
    local_sidecar.write_text(digest, encoding="ascii")
    return "generated"


def _scene_audio_filter(audio_tempo: float, audio_pad_duration: float, *, has_speech: bool) -> str:
    """Build a finite-safe scene audio chain; loudnorm is undefined for all-silence audio."""
    if not math.isfinite(audio_tempo) or audio_tempo <= 0:
        raise ValueError("Scene audio tempo must be finite and positive.")
    if not math.isfinite(audio_pad_duration) or audio_pad_duration < 0:
        raise ValueError("Scene audio padding must be finite and non-negative.")
    filters: list[str] = []
    if audio_tempo > 1.000001:
        filters.append(f"atempo={audio_tempo:.6f}")
    filters.append(f"apad=pad_dur={audio_pad_duration:.3f}")
    # FFmpeg loudnorm on digital silence can produce NaN/Inf and break AAC encoding.
    filters.append("loudnorm=I=-16:TP=-1.5:LRA=11" if has_speech else "anull")
    return ",".join(filters)


def run_cmd(args: list[str], timeout: int = 240) -> None:
    proc = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if proc.returncode != 0:
        tail = proc.stderr[-3000:] if proc.stderr else proc.stdout[-1000:]
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(args[:8])}\n{tail}")



def _valid_visual_scorecard(result: Any) -> bool:
    """A provider is eligible only when it returns every required score and a real boolean gate."""
    if not isinstance(result, dict) or not isinstance(result.get("scores"), dict):
        return False
    if not isinstance(result.get("critical_issue"), bool):
        return False
    for key in VISION_REQUIRED_SCORE_KEYS:
        value = result["scores"].get(key)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or not 1.0 <= float(value) <= 5.0
        ):
            return False
    return True


def _visual_contact_sheet(image_paths: list[Path]) -> Path | None:
    """Build a small whole-Reel overview so per-provider image batches retain continuity context."""
    if len(image_paths) < 3:
        return None
    try:
        from PIL import Image, ImageOps

        cell_width, cell_height, columns = 180, 320, 3
        rows = math.ceil(len(image_paths) / columns)
        sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), (24, 24, 24))
        for index, image_path in enumerate(image_paths):
            with Image.open(image_path) as source:
                thumb = ImageOps.contain(source.convert("RGB"), (cell_width, cell_height))
            x = (index % columns) * cell_width + (cell_width - thumb.width) // 2
            y = (index // columns) * cell_height + (cell_height - thumb.height) // 2
            sheet.paste(thumb, (x, y))
        destination = image_paths[0].parent / "qa_contact_sheet.jpg"
        sheet.save(destination, format="JPEG", quality=82, optimize=True)
        return destination
    except Exception as exc:
        # The full-resolution frames remain authoritative; overview is an aid, never a gate.
        log(f"Could not build optional visual QA contact sheet: {str(exc)[:180]}")
        return None


def _gemini_visual_qa_request(
    system: str,
    user_prompt: str,
    image_paths: list[Path],
    temperature: float = 0.2,
    model: str | None = None,
) -> dict[str, Any]:
    """Gemini multimodal request with a bounded transient retry; caller handles provider fallback."""
    if not GEMINI_API_KEY:
        raise RuntimeError("Gemini visual QA is not configured (GEMINI_API_KEY is absent).")
    selected_model = model or GEMINI_TEXT_MODEL
    parts: list[dict[str, Any]] = [{"text": user_prompt}]
    for image_path in image_paths:
        raw = image_path.read_bytes()
        parts.append({"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(raw).decode("ascii")}})
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": temperature},
    }
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.post(url, headers={"x-goog-api-key": GEMINI_API_KEY}, json=payload, timeout=150)
            response.raise_for_status()
            body = response.json()
            candidates = body.get("candidates") or []
            if not candidates:
                raise RuntimeError(f"Gemini visual QA returned no candidates: {str(body)[:300]}")
            response_parts = (candidates[0].get("content") or {}).get("parts") or []
            output_text = next(
                (part.get("text") for part in response_parts if isinstance(part, dict) and part.get("text")),
                "",
            )
            if not output_text:
                raise RuntimeError("Gemini visual QA returned no text part.")
            return extract_json(output_text)
        except Exception as exc:
            last_error = exc
            error_response = getattr(exc, "response", None)
            status_code = getattr(error_response, "status_code", None)
            transient_http = status_code in {408, 429, 500, 502, 503, 504}
            transient_network = isinstance(exc, (requests.Timeout, requests.ConnectionError))
            malformed_response = isinstance(exc, (json.JSONDecodeError, KeyError, IndexError, ValueError, RuntimeError))
            if attempt >= 2 or not (transient_http or transient_network or malformed_response):
                break
            retry_after = 0
            if error_response is not None:
                try:
                    retry_after = int(float(error_response.headers.get("Retry-After", "0")))
                except (AttributeError, TypeError, ValueError):
                    retry_after = 0
            delay = min(retry_after, 10) if retry_after > 0 else min(3 * (2 ** attempt), 8)
            log(f"Gemini visual QA transient/response failure (attempt {attempt + 1}/3): {str(exc)[:220]}; retrying in {delay}s.")
            time.sleep(delay)
    raise RuntimeError(f"Gemini visual QA failed after bounded retries: {last_error}") from last_error


def _openai_compatible_visual_qa_request(
    provider: str,
    endpoint: str,
    api_key: str,
    model: str,
    system: str,
    user_prompt: str,
    image_paths: list[Path],
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Vision request for Groq, Mistral, or explicitly enabled Cloudflare Workers AI."""
    if not api_key:
        raise RuntimeError(f"{provider} vision QA is not configured.")
    content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
    for image_path in image_paths:
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
        })
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system + "\nReturn valid JSON only. Follow the requested scorecard exactly."},
            {"role": "user", "content": content},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    if provider == "Groq":
        payload["max_completion_tokens"] = 6000
        payload["reasoning_effort"] = "low"
    else:
        payload["max_tokens"] = 6000
    response = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=150,
    )
    response.raise_for_status()
    return _openai_json_completion(response.json(), provider, 6000)


def _vision_provider_order() -> list[tuple[str, str, str, str, str, int]]:
    """Configured free-tier providers only; each route uses a documented vision model."""
    providers = {
        "gemini": ("Gemini", GEMINI_TEXT_MODEL, "", GEMINI_API_KEY, 18),
        "groq": ("Groq", GROQ_VISION_MODEL, "https://api.groq.com/openai/v1/chat/completions", GROQ_API_KEY, 3),
        "mistral": ("Mistral", MISTRAL_VISION_MODEL, "https://api.mistral.ai/v1/chat/completions", MISTRAL_API_KEY, 8),
        "cloudflare": (
            "Cloudflare Workers AI", CF_VISION_MODEL,
            f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/v1/chat/completions",
            CF_API_TOKEN, 8,
        ),
    }
    primary = os.getenv("BSK_VISION_PROVIDER", "groq").strip().lower()
    names = [primary] + [name for name in ("gemini", "groq", "mistral", "cloudflare") if name != primary]
    enabled = {
        "gemini": bool(GEMINI_API_KEY),
        "groq": bool(GROQ_API_KEY),
        # Mistral may be connected to a billable workspace. A key alone never enables it.
        "mistral": bool(
            MISTRAL_API_KEY
            and _mistral_free_only_enabled()
        ),
        # Cloudflare is used only when the operator explicitly enables its free-only route.
        "cloudflare": bool(CF_WORKERS_AI_ENABLED and CF_ACCOUNT_ID and CF_API_TOKEN),
    }
    return [
        (name, *providers[name])
        for name in names
        if name in providers and enabled[name] and _provider_available(f"{name}_vision")
    ]


def gemini_json_with_images(
    system: str,
    user_prompt: str,
    image_paths: list[Path],
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Use every configured free-tier vision provider until one completes the full validated review.

    A real visual rejection is returned immediately and cannot be overwritten by a second model.
    Provider outages or malformed/incomplete scorecards move to the next configured vision model.
    """
    if not image_paths:
        raise RuntimeError("Visual QA received no rendered frames.")
    order = _vision_provider_order()
    if not order:
        raise RuntimeError(
            "No configured free-tier vision providers are available "
            "(Gemini, Groq, Mistral, or explicitly enabled Cloudflare Workers AI)."
        )
    contact_sheet = _visual_contact_sheet(image_paths)
    failures: list[str] = []
    for provider_key, provider_label, model, endpoint, api_key, max_images in order:
        try:
            if provider_key == "gemini":
                result = _gemini_visual_qa_request(
                    system, user_prompt, image_paths, temperature=temperature, model=model
                )
                if not _valid_visual_scorecard(result):
                    raise ValueError("Gemini returned an incomplete or invalid visual QA scorecard.")
                result["visual_qa_provider"] = provider_label
                result["visual_qa_model"] = model
                result["visual_qa_batches"] = 1
                log(f"Visual QA completed with {provider_label} model {model}.")
                return result

            # Groq documents a maximum of 3 images/request; Mistral and Workers AI
            # are kept to 8/request. A whole-Reel overview accompanies detailed batches.
            overview = contact_sheet if contact_sheet is not None else None
            detail_limit = max(1, max_images - (1 if overview else 0))
            batches = [
                image_paths[index:index + detail_limit]
                for index in range(0, len(image_paths), detail_limit)
            ]
            batch_results: list[dict[str, Any]] = []
            hard_rejection = False
            for batch_index, batch in enumerate(batches, start=1):
                request_images = ([overview] if overview else []) + batch
                batch_prompt = user_prompt
                if overview:
                    batch_prompt += (
                        "\nThe first image is a small contact sheet of ALL ordered Reel samples. "
                        "Use it to judge whole-Reel continuity. The remaining images are full-resolution "
                        f"detail samples for batch {batch_index}/{len(batches)}; inspect each closely."
                    )
                if len(batches) > 1:
                    batch_prompt += (
                        f"\nThis is detail batch {batch_index} of {len(batches)}. "
                        "Score every required dimension for the supplied detailed frames, "
                        "and report any critical defect visible either in the overview or detail frames."
                    )
                result = _openai_compatible_visual_qa_request(
                    provider_label, endpoint, api_key, model, system, batch_prompt,
                    request_images, temperature=temperature,
                )
                if not _valid_visual_scorecard(result):
                    raise ValueError(
                        f"{provider_label} batch {batch_index}/{len(batches)} returned an incomplete or invalid visual QA scorecard."
                    )
                batch_results.append(result)
                # A genuine critical finding is a hard rejection; do not shop for a more
                # favourable model response or spend tokens reviewing additional batches.
                if result.get("critical_issue") is True or min(
                    float(result["scores"][key]) for key in VISION_REQUIRED_SCORE_KEYS
                ) <= 2:
                    hard_rejection = True
                    break

            combined_scores = {
                key: min(float(item["scores"][key]) for item in batch_results)
                for key in VISION_REQUIRED_SCORE_KEYS
            }
            confidence_order = {"low": 0, "medium": 1, "high": 2}
            confidences = [
                str(item.get("confidence", "low")).lower()
                for item in batch_results
            ]
            confidence = min(
                (value for value in confidences if value in confidence_order),
                key=lambda value: confidence_order[value],
                default="low",
            )
            notes = []
            for item in batch_results:
                item_notes = item.get("notes", [])
                if isinstance(item_notes, list):
                    notes.extend(str(note)[:400] for note in item_notes[:8])
            combined = {
                "scores": combined_scores,
                "critical_issue": any(item["critical_issue"] for item in batch_results),
                "notes": notes[:24],
                "confidence": confidence,
                "visual_qa_provider": provider_label,
                "visual_qa_model": model,
                "visual_qa_batches": len(batch_results),
                "visual_qa_expected_batches": len(batches),
            }
            # A critical result can stop early (and reject); a pass is accepted only after
            # every expected detail batch was reviewed successfully.
            if not hard_rejection and len(batch_results) != len(batches):
                raise RuntimeError(f"{provider_label} visual QA stopped before all batches were reviewed.")
            log(
                f"Visual QA completed with {provider_label} model {model} "
                f"({len(batch_results)}/{len(batches)} batches)."
            )
            return combined
        except Exception as exc:
            failures.append(f"{provider_label}/{model}: {str(exc)[:300]}")
            _provider_failure_cooldown(f"{provider_key}_vision", exc)
            log(f"Visual QA provider {provider_label} model {model} failed: {str(exc)[:240]}")
    raise RuntimeError(
        "All configured free-tier vision providers failed to complete a valid whole-Reel scorecard; "
        "no paid fallback was attempted. " + " | ".join(failures)
    )

def deterministic_local_visual_qa(frame_paths: list[Path]) -> dict[str, Any]:
    """Run dependency-light, deterministic checks on every sampled frame.

    This verifies frame integrity and gross technical defects only. It deliberately does
    not claim to understand story meaning, anatomy, character identity or artistic quality.
    """
    from PIL import ImageFilter, ImageStat

    if len(frame_paths) < 2:
        return {
            "status": "not_completed",
            "engine": "bsk_local_frame_qa_v1",
            "frames_scanned": len(frame_paths),
            "hard_failures": ["At least two rendered frames are required."],
            "human_review_required": True,
        }

    hard_failures: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    review_notes: list[dict[str, Any]] = []

    for frame_path in frame_paths:
        try:
            with Image.open(frame_path) as opened:
                image = opened.convert("RGB")
                image.load()
        except Exception as exc:
            hard_failures.append({
                "frame": frame_path.name,
                "check": "image_integrity",
                "detail": str(exc)[:180],
            })
            continue

        width, height = image.size
        if width < 320 or height < 568:
            hard_failures.append({
                "frame": frame_path.name,
                "check": "minimum_resolution",
                "detail": f"Frame is only {width}x{height}; minimum is 320x568.",
            })
        ratio = width / max(height, 1)
        if not 0.52 <= ratio <= 0.61:
            hard_failures.append({
                "frame": frame_path.name,
                "check": "portrait_aspect_ratio",
                "detail": f"Expected a 9:16 portrait frame; received {width}x{height}.",
            })

        gray = image.convert("L")
        histogram = gray.histogram()
        pixel_count = max(width * height, 1)
        near_black_fraction = sum(histogram[:9]) / pixel_count
        luminance = ImageStat.Stat(gray)
        mean_luma = float(luminance.mean[0])
        luma_stddev = float(luminance.stddev[0])
        edge_stddev = float(ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).stddev[0])

        if near_black_fraction >= 0.995:
            hard_failures.append({
                "frame": frame_path.name,
                "check": "near_black_frame",
                "detail": f"{near_black_fraction:.3%} of pixels are near black.",
            })
        elif luma_stddev < 1.5 or edge_stddev < 0.8:
            review_notes.append({
                "frame": frame_path.name,
                "check": "low_visual_information",
                "detail": "Frame has very little tonal or edge variation; inspect manually.",
            })

        observations.append({
            "frame": frame_path.name,
            "width": width,
            "height": height,
            "mean_luminance": round(mean_luma, 2),
            "luminance_stddev": round(luma_stddev, 2),
            "edge_stddev": round(edge_stddev, 2),
            "near_black_fraction": round(near_black_fraction, 5),
        })

    return {
        "status": "warning" if hard_failures else "passed",
        "engine": "bsk_local_frame_qa_v1",
        "frames_scanned": len(observations),
        "hard_failures": hard_failures,
        "review_notes": review_notes,
        "observations": observations,
        "checks": ["image_integrity", "minimum_resolution", "portrait_aspect_ratio", "near_black_frame"],
        "not_assessed": [
            "story_visual_match",
            "anatomy_integrity",
            "character_continuity",
            "Hindi subtitle correctness and safe-area placement",
            "subjective visual quality and emotional impact",
        ],
        "human_review_required": True,
    }


def local_visual_review_fallback(reason: str, local_report: dict[str, Any]) -> dict[str, Any]:
    """Create an honest human-review state; never fabricate an AI score or an AI pass."""
    return {
        "status": "local_pass_human_review",
        "critical_issue": False,
        "review_mode": "deterministic_local_fallback",
        "visual_ai_review": {
            "status": "not_completed",
            "reason": str(reason)[:500],
        },
        "local_visual_diagnostics": local_report,
        "scores": {},
        "notes": [
            "Local frame-integrity checks passed; AI semantic review was unavailable.",
            "A human must inspect story match, anatomy, character continuity, subtitle placement and overall visual quality before approval.",
        ],
        "human_review_required": True,
    }


def normalize_transcript_for_comparison(text_value: str) -> str:
    """Normalize transcription text without translating or changing lexical content."""
    value = unicodedata.normalize("NFC", str(text_value or ""))
    # Python's stdlib re has no Unicode property classes; retain letters/numbers only.
    return "".join(ch for ch in value if ch.isalnum())


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Small-memory Levenshtein CER over normalized Unicode characters."""
    ref = list(normalize_transcript_for_comparison(reference))
    hyp = list(normalize_transcript_for_comparison(hypothesis))
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, left in enumerate(ref, start=1):
        current = [i]
        for j, right in enumerate(hyp, start=1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
    return round(previous[-1] / len(ref), 4)


def audio_transcript_qa(audio_paths: list[Path], expected_lines: list[str], reel_dir: Path) -> dict[str, Any]:
    """Run local Whisper ASR on dry voice audio; this is advisory, not an auto-publish gate."""
    global _ASR_MODEL
    report_path = reel_dir / "audio_qa_report.json"
    if not audio_paths or len(audio_paths) != len(expected_lines):
        return {"status": "not_completed", "reason": "Narration audio/text inputs were incomplete.", "human_review_required": True}
    voice_only = reel_dir / "voice_only.wav"
    # Every beat WAV is 24 kHz mono PCM, so concat without re-encoding each segment.
    inputs = []
    for path in audio_paths:
        inputs.extend(["-i", str(path)])
    labels = "".join(f"[{i}:a]" for i in range(len(audio_paths)))
    graph = f"{labels}concat=n={len(audio_paths)}:v=0:a=1[out]"
    try:
        run_cmd(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
                 "-filter_complex", graph, "-map", "[out]", "-c:a", "pcm_s16le", str(voice_only)], timeout=180)
        expected = " ".join(str(x).strip() for x in expected_lines)
        (reel_dir / "narration_expected.txt").write_text(expected + "\n", encoding="utf-8")
        if not voice_only.exists() or voice_only.stat().st_size < 4000:
            raise RuntimeError("Could not build the dry voice-only narration track.")
        if os.getenv("BSK_ASR_QA", "1").strip().lower() not in {"1", "true", "yes"}:
            return {"status": "disabled", "human_review_required": True}
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            return {"status": "not_available", "reason": f"faster-whisper is not installed: {exc}", "human_review_required": True}
        if _ASR_MODEL is None:
            model_name = os.getenv("BSK_ASR_MODEL", "large-v3-turbo").strip() or "large-v3-turbo"
            cache_dir = Path(os.getenv("BSK_ASR_CACHE_DIR", str(Path.home() / ".cache" / "huggingface" / "hub")))
            cache_dir.mkdir(parents=True, exist_ok=True)
            _ASR_MODEL = WhisperModel(model_name, device="cpu", compute_type="int8", download_root=str(cache_dir))
        segments, info = _ASR_MODEL.transcribe(
            str(voice_only), language="hi", beam_size=3, vad_filter=True,
            condition_on_previous_text=False,
        )
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
        cer = character_error_rate(expected, transcript)
        language_probability = float(getattr(info, "language_probability", 0.0) or 0.0)
        status = "likely_match" if cer <= 0.18 and language_probability >= 0.70 else "review_required"
        report = {
            "status": status, "model": os.getenv("BSK_ASR_MODEL", "large-v3-turbo"),
            "engine": "faster-whisper CPU int8", "language": getattr(info, "language", "unknown"),
            "language_probability": round(language_probability, 3),
            "character_error_rate": cer, "expected_characters": len(normalize_transcript_for_comparison(expected)),
            "transcribed_characters": len(normalize_transcript_for_comparison(transcript)),
            "transcript": transcript, "human_review_required": True,
            "threshold_note": "CER <= 0.18 is only a likely transcript match, not proof of correct pronunciation or voice quality. Threshold is conservative and must be calibrated on real Hindi clips.",
        }
        (reel_dir / "asr_transcript.txt").write_text(transcript + "\n", encoding="utf-8")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
    except Exception as exc:
        report = {"status": "not_completed", "reason": str(exc)[:700], "human_review_required": True}
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"Local narration ASR QA did not complete; it will not block the Reel: {exc}")
        return report


def motion_diagnostics(video_path: Path) -> dict[str, Any]:
    """Full-duration FFmpeg scan for black intervals and unusually long frozen sections."""
    command = [
        "ffmpeg", "-hide_banner", "-i", str(video_path),
        "-vf", "freezedetect=n=-50dB:d=1.0,blackdetect=d=0.20:pix_th=0.10",
        "-an", "-f", "null", "-",
    ]
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=600)
        log_text = (result.stderr or "") + "\n" + (result.stdout or "")
        freeze_events = [float(x) for x in re.findall(r"freeze_duration:([0-9.]+)", log_text)]
        black_events = [float(x) for x in re.findall(r"black_duration:([0-9.]+)", log_text)]
        if result.returncode:
            return {"status": "not_completed", "reason": log_text[-500:], "human_review_required": True}
        severe_black = [x for x in black_events if x >= 0.20]
        long_freezes = [x for x in freeze_events if x >= 1.0]
        if severe_black:
            status = "warning"
        elif long_freezes:
            status = "review_required"
        else:
            status = "passed"
        return {
            "status": status, "black_intervals_seconds": [round(x, 3) for x in black_events],
            "long_freeze_intervals_seconds": [round(x, 3) for x in long_freezes],
            "full_video_scanned": True, "human_review_required": True,
            "note": "Black/freeze detection is a technical signal; deliberate fades or locked-off shots can be valid. It does not assess cinematic taste or all motion artefacts.",
        }
    except Exception as exc:
        return {"status": "not_completed", "reason": str(exc)[:500], "human_review_required": True}


def metadata_ocr_qa(video_path: Path, reel_dir: Path, duration: float) -> dict[str, Any]:
    """OCR a full-timeline sample and hard-reject leaked production labels."""
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return {
            "status": "not_completed",
            "reason": "Tesseract OCR is not installed; internal-label QA cannot be skipped.",
            "frames_scanned": 0,
            "human_review_required": True,
        }
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(float(duration)) or duration <= 0:
        return {"status": "not_completed", "reason": "OCR duration is invalid.", "frames_scanned": 0, "human_review_required": True}

    frames_dir = reel_dir / "metadata_ocr_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    pattern = frames_dir / "ocr_%04d.jpg"
    try:
        run_cmd([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(video_path), "-vf", "fps=1,scale=720:-2",
            "-q:v", "4", str(pattern),
        ], timeout=240)
        frames = sorted(frames_dir.glob("ocr_*.jpg"))
        if not frames:
            raise RuntimeError("FFmpeg did not produce OCR sample frames.")
        forbidden = re.compile(r"\b(?:KEYWORD|STEP|CONTRAST|SCENE|HOOK|PROMPT|CLOSING)\b")
        detections: list[dict[str, str]] = []
        for frame in frames:
            result = subprocess.run(
                [tesseract, str(frame), "stdout", "-l", "eng+hin", "--psm", "11"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
            )
            if result.returncode:
                raise RuntimeError(f"Tesseract failed for {frame.name}: {(result.stderr or '')[-400:]}")
            text_value = result.stdout or ""
            for match in forbidden.finditer(text_value):
                detections.append({
                    "frame": frame.name,
                    "term": match.group(0),
                    "context": text_value[max(0, match.start()-70):min(len(text_value), match.end()+70)].strip(),
                })
            if re.search(r"[\[{]\s*['\"]?(?:role|prompt|scene|keyword|step)\b", text_value, flags=re.IGNORECASE):
                detections.append({"frame": frame.name, "term": "raw_json_fragment", "context": text_value[:140].strip()})
        report = {
            "status": "warning" if detections else "passed",
            "frames_scanned": len(frames),
            "sample_rate_fps": 1,
            "forbidden_terms_detected": detections,
            "full_timeline_sampled": True,
            "human_review_required": True,
            "note": "OCR supplements VLM review; it cannot prove the absence of every visual text artifact.",
        }
    except Exception as exc:
        report = {
            "status": "not_completed",
            "reason": str(exc)[:700],
            "frames_scanned": 0,
            "human_review_required": True,
        }
    (reel_dir / "metadata_ocr_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def reconcile_actual_voice_timing(beat: dict[str, Any], measured_durations: dict[str, float]) -> dict[str, Any]:
    """Make the validated WAV files authoritative and rebuild the beat timing without truncating speech.

    The planning and finalization runners may restore different snapshots of a shared cache.
    Matching transcript/voice identity does not guarantee an identical synthesized duration.
    A duration drift is therefore reconciled against the exact WAV being rendered, then the
    normal scene-duration and bounded video-retiming guards decide whether it is safe.
    """
    segments = beat.get("speech_segments")
    if not isinstance(segments, list) or not segments:
        return {"adjusted": False, "differences": []}

    old_timing = beat.get("voice_timing")
    old_segments = old_timing.get("segments", []) if isinstance(old_timing, dict) else []
    planned_by_id = {
        str(item.get("segment_id")): float(item["duration_seconds"])
        for item in old_segments
        if isinstance(item, dict)
        and item.get("segment_id") is not None
        and isinstance(item.get("duration_seconds"), (int, float))
        and not isinstance(item.get("duration_seconds"), bool)
    }

    differences: list[dict[str, Any]] = []
    for segment in segments:
        segment_id = str(segment.get("segment_id") or "")
        if segment_id not in measured_durations:
            raise RuntimeError(f"Measured WAV duration is missing for voice segment {segment_id!r}.")
        measured = float(measured_durations[segment_id])
        if not math.isfinite(measured) or measured <= 0:
            raise RuntimeError(f"Measured WAV duration is invalid for voice segment {segment_id!r}.")
        planned = planned_by_id.get(segment_id)
        if planned is not None and abs(measured - planned) > 0.15:
            differences.append({
                "segment_id": segment_id,
                "planned_seconds": round(planned, 4),
                "actual_wav_seconds": round(measured, 4),
                "delta_seconds": round(measured - planned, 4),
            })
        segment["duration_seconds"] = round(measured, 4)

    if differences:
        gap_count = max(0, len(segments) - 1)
        recorded_gap = (
            float(old_timing.get("dialogue_gap_seconds", 0.0) or 0.0)
            if isinstance(old_timing, dict) else 0.0
        )
        gap_per_turn = (
            recorded_gap / gap_count if gap_count else voice_first.DEFAULT_DIALOGUE_GAP_SECONDS
        )
        rebuilt = voice_first.build_scene_timing_plan(
            segments,
            {str(item["segment_id"]): float(item["duration_seconds"]) for item in segments},
            dialogue_gap_seconds=gap_per_turn,
            head_handle_seconds=float(
                old_timing.get("head_handle_seconds", voice_first.HEAD_HANDLE_SECONDS)
                if isinstance(old_timing, dict) else voice_first.HEAD_HANDLE_SECONDS
            ),
            tail_handle_seconds=float(
                old_timing.get("tail_handle_seconds", voice_first.TAIL_HANDLE_SECONDS)
                if isinstance(old_timing, dict) else voice_first.TAIL_HANDLE_SECONDS
            ),
            fps=int(
                old_timing.get("fps", voice_first.FPS)
                if isinstance(old_timing, dict) else voice_first.FPS
            ),
        )
        beat["voice_timing"] = rebuilt
        beat["target_frames"] = rebuilt["target_frames"]
        log(
            "Rebuilt voice-first timing from the exact validated WAV duration(s): "
            + ", ".join(
                f"{item['segment_id']} {item['planned_seconds']:.3f}s→{item['actual_wav_seconds']:.3f}s"
                for item in differences
            )
            + f"; new scene target {rebuilt['target_duration_seconds']:.3f}s."
        )

    return {
        "adjusted": bool(differences),
        "differences": differences,
        "new_target_duration_seconds": (
            beat.get("voice_timing", {}).get("target_duration_seconds")
            if isinstance(beat.get("voice_timing"), dict) else None
        ),
    }


def persist_visual_qa_report(reel_dir: Path, review: dict[str, Any]) -> Path:
    """Persist QA results and frame evidence even when a later hard gate rejects the Reel."""
    frames_dir = reel_dir / "qa_frames"
    frames = sorted(
        path.relative_to(reel_dir).as_posix()
        for path in frames_dir.glob("frame_*.jpg")
        if path.is_file() and path.stat().st_size > 1000
    )
    contact_sheet = frames_dir / "qa_contact_sheet.jpg"
    report = dict(review)
    report["qa_evidence"] = {
        "frames": frames,
        "contact_sheet": (
            contact_sheet.relative_to(reel_dir).as_posix()
            if contact_sheet.is_file() else None
        ),
    }
    destination = reel_dir / "visual_qa_report.json"
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return destination


def visual_qa(video_path: Path, reel_dir: Path, duration: float, segment_durations: list[float] | None = None) -> dict[str, Any]:
    """Sample the whole Reel, run local diagnostics, then use the configured vision-provider cascade."""
    frames_dir = reel_dir / "qa_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    timestamps = []
    if segment_durations:
        cursor = 0.0
        for beat_duration in segment_durations:
            beat_duration = max(0.0, float(beat_duration))
            timestamps.extend([cursor + beat_duration * 0.32, cursor + beat_duration * 0.72])
            cursor += beat_duration
    if not timestamps:
        timestamps = [duration * fraction for fraction in (0.04, 0.14, 0.24, 0.36, 0.48, 0.60, 0.72, 0.84, 0.96)]
    timestamps = sorted(set(round(max(0.05, min(duration - 0.05, stamp)), 2) for stamp in timestamps))[:18]
    frame_paths = []
    for idx, stamp in enumerate(timestamps, start=1):
        frame = frames_dir / f"frame_{idx}.jpg"
        run_cmd(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{stamp:.2f}", "-i", str(video_path), "-frames:v", "1", "-vf", "scale=540:-2", "-q:v", "5", str(frame)], timeout=60)
        if frame.exists() and frame.stat().st_size > 1000:
            frame_paths.append(frame)
    if len(frame_paths) < 2:
        return {"status": "not_completed", "reason": "Could not extract enough frames for automated visual QA.", "human_review_required": True}

    local_report = deterministic_local_visual_qa(frame_paths)
    if local_report.get("status") != "passed":
        result: dict[str, Any] = {
            "status": "warning" if local_report.get("status") == "warning" else "not_completed",
            "critical_issue": bool(local_report.get("hard_failures")),
            "review_mode": "local_precheck_blocked",
            "local_visual_diagnostics": local_report,
            "human_review_required": True,
            "notes": ["Local frame-integrity checks did not pass; AI review cannot override a technical defect."],
        }
    else:
        try:
            result = gemini_json_with_images(
                "You are a visual quality-control editor for a premium Hindi vertical Reel. Evaluate only the supplied rendered frames; do not infer unseen frames. Return JSON only.",
                "These ordered samples cover the full 9:16 Hindi Reel (two frames per narrative beat). Inspect EVERY supplied frame for malformed faces/hands, duplicated limbs, broken object geometry, visual mismatch to the beat's narrative_role and state_change, subtitle glyph errors, clipping, contrast and UI-safe margins. Compare recurring characters across all frames: same face shape, apparent age, hair, clothing, clothing colour and distinguishing props; report visible identity or wardrobe drift under character_continuity. Treat the first clear appearance of each recurring character as its visual anchor. Check visible text for internal production labels or prompt metadata, especially KEYWORD, STEP, CONTRAST, PROMPT, SCENE, HOOK or raw JSON fragments; score this under metadata_text_cleanliness. Do not infer movement or anything between sampled frames. Return JSON: {\"scores\":{\"text_legibility\":1,\"devanagari_rendering\":1,\"anatomy_integrity\":1,\"story_visual_match\":1,\"safe_composition\":1,\"visual_quality\":1,\"character_continuity\":1,\"metadata_text_cleanliness\":1},\"critical_issue\":false,\"notes\":[\"short note\"],\"confidence\":\"low|medium|high\"}. Scores 1-5. Set character_continuity or metadata_text_cleanliness to 1–2 for a clear defect; set critical_issue=true for obvious malformed anatomy, severe continuity mismatch, leaked internal labels, broken text or clipping. Do not auto-reject subjective style preference.",
                frame_paths,
            )
            scores = result.get("scores", {}) if isinstance(result, dict) else {}
            required_scores = (
                "text_legibility", "devanagari_rendering", "anatomy_integrity",
                "story_visual_match", "safe_composition", "visual_quality",
                "character_continuity", "metadata_text_cleanliness",
            )

            def valid_visual_score(value: Any) -> bool:
                # bool is a subclass of int in Python; explicitly reject it. A model
                # response outside the documented 1–5 scale must never count as QA.
                return (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(float(value))
                    and 1.0 <= float(value) <= 5.0
                )

            missing_scores = [key for key in required_scores if not valid_visual_score(scores.get(key))]
            numeric = [float(scores[key]) for key in required_scores if valid_visual_score(scores.get(key))]
            critical_issue_valid = isinstance(result.get("critical_issue"), bool)
            result["average_score"] = round(sum(numeric) / len(numeric), 2) if numeric else None
            result["missing_required_scores"] = missing_scores
            result["missing_required_fields"] = [] if critical_issue_valid else ["critical_issue"]
            if missing_scores or not critical_issue_valid:
                result["status"] = "not_completed"
            elif result["critical_issue"] is True or min(numeric) <= 2:
                result["status"] = "warning"
            else:
                result["status"] = "reviewed"

            result["review_mode"] = "ai_assisted"
            result["local_visual_diagnostics"] = local_report
            result["human_review_required"] = True
            if result["status"] == "not_completed":
                result = local_visual_review_fallback(
                    "Gemini returned an incomplete visual scorecard; semantic review is still required.",
                    local_report,
                )
        except Exception as exc:
            log(f"Visual AI review unavailable; retaining local QA result for human review: {exc}")
            result = local_visual_review_fallback(str(exc), local_report)

    ocr_report = metadata_ocr_qa(video_path, reel_dir, duration)
    result["metadata_ocr_qa"] = ocr_report
    result["qa_evidence"] = {
        "frames": [
            path.relative_to(reel_dir).as_posix()
            for path in frame_paths
            if path.is_file()
        ],
        "contact_sheet": (
            (frames_dir / "qa_contact_sheet.jpg").relative_to(reel_dir).as_posix()
            if (frames_dir / "qa_contact_sheet.jpg").is_file() else None
        ),
    }
    if ocr_report.get("status") == "warning":
        result["critical_issue"] = True
        result["status"] = "warning"
    elif ocr_report.get("status") != "passed" and result.get("status") != "warning":
        result["status"] = "not_completed"
    return result


def enforce_visual_qa(review: dict[str, Any]) -> None:
    """Require objective local checks, OCR and full-video motion checks before human review."""
    status = review.get("status")
    if status == "warning" or review.get("critical_issue") is True:
        raise RuntimeError(
            "Rendered-frame QA detected a potentially critical visual defect; "
            "the Reel was not added to the publish kit. Check QA frames and rerun."
        )

    if status == "local_pass_human_review":
        local = review.get("local_visual_diagnostics")
        if (
            review.get("review_mode") != "deterministic_local_fallback"
            or review.get("human_review_required") is not True
            or not isinstance(local, dict)
            or local.get("engine") != "bsk_local_frame_qa_v1"
            or local.get("status") != "passed"
            or int(local.get("frames_scanned", 0) or 0) < 2
            or local.get("hard_failures")
        ):
            raise RuntimeError("Local visual QA did not pass its required checks; refusing human-review handoff.")
    elif status != "reviewed":
        raise RuntimeError(
            "Rendered-frame QA did not complete successfully; the Reel was not added to the publish kit. "
            "Review the QA outage/scorecard and rerun."
        )

    ocr = review.get("metadata_ocr_qa")
    if not isinstance(ocr, dict) or ocr.get("status") != "passed" or ocr.get("forbidden_terms_detected"):
        raise RuntimeError("Metadata OCR did not pass; refusing to deliver a Reel with unknown or leaked production labels.")
    motion = review.get("full_video_motion_diagnostics")
    if not isinstance(motion, dict) or motion.get("status") != "passed" or motion.get("full_video_scanned") is not True:
        raise RuntimeError("Full-video black/freeze diagnostics did not pass; refusing to deliver a Reel with incomplete motion QA.")


def create_original_sound_bed(destination: Path, duration: float, pillar: str) -> None:
    """Create a subtle, original, royalty-free tonal ambience locally; no song/library is downloaded."""
    sample_rate = 24000
    frame_count = max(1, int(sample_rate * duration))
    palettes = {
        "micro_story": (55.0, 82.41, 110.0),
        "cinematic_moment": (49.0, 73.42, 146.83),
        "everyday_insight": (65.41, 98.0, 130.81),
    }
    f1, f2, f3 = palettes.get(pillar, palettes["micro_story"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Gentle, non-melodic tone texture with a small story-turn swell; restrained under narration.
    with wave.open(str(destination), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        block = bytearray()
        for n in range(frame_count):
            t = n / sample_rate
            fade_in = min(1.0, t / 0.75)
            fade_out = min(1.0, max(0.0, duration - t) / 1.25)
            envelope = fade_in * fade_out
            slow_breathe = 0.78 + 0.22 * math.sin(2.0 * math.pi * t / 9.5)
            base = (0.105 * math.sin(2*math.pi*f1*t)
                    + 0.045 * math.sin(2*math.pi*f2*t + 0.35)
                    + 0.026 * math.sin(2*math.pi*f3*t + 1.1))
            turn = math.exp(-((t - duration * 0.68) / 0.65) ** 2) * 0.024 * math.sin(2*math.pi*196.0*t)
            sample = (base * slow_breathe + turn) * envelope * 0.18
            left = max(-1.0, min(1.0, sample * 0.98))
            right = max(-1.0, min(1.0, sample * 1.02))
            block.extend(int(left * 32767).to_bytes(2, "little", signed=True))
            block.extend(int(right * 32767).to_bytes(2, "little", signed=True))
            if len(block) >= 65536:
                wav_file.writeframesraw(block)
                block.clear()
        if block:
            wav_file.writeframesraw(block)


def final_audio_mix_filter() -> str:
    """Mix the restrained original ambience, then master the complete Reel audio."""
    return (
        "[1:a]volume=0.22[bed];"
        "[0:a][bed]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        "loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.84[a]"
    )


def probe_duration(path: Path) -> float:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], text=True, capture_output=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe could not read {path.name}: {result.stderr[-800:]}")
    return float(result.stdout.strip())


def probe_media(path: Path, expected_fps: int | None = None) -> dict[str, Any]:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], text=True, capture_output=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe could not inspect {path.name}: {result.stderr[-800:]}")
    body = json.loads(result.stdout)
    streams = body.get("streams", [])
    video = next((x for x in streams if x.get("codec_type") == "video"), None)
    audio = next((x for x in streams if x.get("codec_type") == "audio"), None)
    if video is None or audio is None:
        raise RuntimeError("Technical QA failed: final file must contain both video and audio streams.")
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    if (width, height) != (1080, 1920):
        raise RuntimeError(f"Technical QA failed: expected 1080x1920, got {width}x{height}.")
    fps = video.get("avg_frame_rate", video.get("r_frame_rate", "unknown"))
    try:
        num, den = fps.split("/", 1)
        fps_value = float(num) / max(float(den), 1e-9)
    except (ValueError, AttributeError):
        fps_value = 0.0
    accepted_fps = [expected_fps] if expected_fps else [24, 30]
    if all(abs(fps_value - target) > 0.6 for target in accepted_fps):
        labels = ", ".join(str(value) for value in accepted_fps)
        raise RuntimeError(f"Technical QA failed: expected about {labels} fps, got {fps}.")
    return {"width": width, "height": height, "video_codec": video.get("codec_name"), "audio_codec": audio.get("codec_name"), "frame_rate": fps, "reported_r_frame_rate": video.get("r_frame_rate", "unknown"), "format": body.get("format", {}).get("format_name", "unknown")}


def ass_time(seconds: float) -> str:
    centis = max(0, int(seconds * 100))
    hours = centis // 360000
    minutes = (centis // 6000) % 60
    secs = (centis // 100) % 60
    cs = centis % 100
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def clean_ass_text(text: str) -> str:
    text = text.replace("{", "(").replace("}", ")")
    text = text.replace("\n", "\\N")
    return text


def wrap_screen_text(text: str, max_chars: int = 17) -> str:
    text = " ".join(text.split())
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + len(word) + 1 > max_chars:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    # ASS boxes get busy on three lines; compress by keeping a maximum of two lines.
    if len(lines) > 2:
        split = (len(text) + 1) // 2
        # Split near a space at the midpoint.
        pos = text.rfind(" ", 0, split + 5)
        if pos < 3:
            pos = text.find(" ", split)
        if pos > 0:
            lines = [text[:pos].strip(), text[pos + 1:].strip()]
        else:
            lines = [text[:max_chars], text[max_chars:]]
    return "\\N".join(lines)


def write_ass(path: Path, beat_text: str, duration: float, is_cover: bool = False, overlay_text: str = "", overlay_type: str = "keyword", scene_index: int = 1, scene_count: int = 1) -> None:
    playres_x, playres_y = 1080, 1920
    if is_cover:
        content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {playres_x}
PlayResY: {playres_y}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Brand,Noto Sans,30,&H00D6BA8A,&H000000FF,&H00101010,&H00000000,-1,0,0,0,100,100,2,0,1,2,0,8,50,50,0,1
Style: Cover,Noto Sans Devanagari,86,&H00F7F1E7,&H000000FF,&H00101010,&HAA101010,-1,0,0,0,100,100,2,0,3,2,0,5,72,72,0,1
Style: Sub,Noto Sans Devanagari,43,&H00E0D9CE,&H000000FF,&H00101010,&H00000000,0,0,0,0,100,100,1,0,1,1,0,5,72,72,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 2,0:00:00.00,0:00:01.00,Brand,,0,0,0,,{{\\an8\\pos(540,280)}}BINA SHOR KE
Dialogue: 1,0:00:00.00,0:00:01.00,Cover,,0,0,0,,{{\\an5\\pos(540,920)\\fad(0,0)}}{clean_ass_text(wrap_screen_text(beat_text, 14))}
Dialogue: 0,0:00:00.00,0:00:01.00,Sub,,0,0,0,,{{\\an5\\pos(540,1260)}}कम शब्द। साफ़ कहानी।
"""
    else:
        safe_text = clean_ass_text(wrap_screen_text(beat_text))
        content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {playres_x}
PlayResY: {playres_y}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Brand,Noto Sans,28,&H00D6BA8A,&H000000FF,&H00101010,&HAA101010,-1,0,0,0,100,100,2,0,3,1,0,8,60,60,0,1
Style: Main,Noto Sans Devanagari,58,&H00F8F4EC,&H000000FF,&H00101010,&HAA101010,-1,0,0,0,100,100,0,0,3,2,0,5,68,68,0,1
Style: Tag,Noto Sans Devanagari,28,&H00E9D3A5,&H000000FF,&H00201D19,&HBB201D19,-1,0,0,0,100,100,1,0,3,1,0,7,32,32,0,1
Style: Counter,Noto Sans,24,&H00E6DFD3,&H000000FF,&H00101010,&HAA101010,-1,0,0,0,100,100,1,0,3,1,0,9,48,48,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 3,0:00:00.00,{ass_time(duration)},Brand,,0,0,0,,{{\\an8\\pos(540,165)}}BINA SHOR KE
Dialogue: 2,0:00:00.00,{ass_time(duration)},Counter,,0,0,0,,{{\\an9\\pos(1010,170)}}{scene_index:02d} / {scene_count:02d}
Dialogue: 2,0:00:00.14,{ass_time(max(0.25, duration - 0.12))},Tag,,0,0,0,,{{\\an7\\pos(72,430)\\fad(160,100)}}{clean_ass_text(overlay_text[:65])}
Dialogue: 1,0:00:00.10,{ass_time(max(0.2, duration - 0.1))},Main,,0,0,0,,{{\\an5\\pos(540,1180)\\fad(180,180)}}{safe_text}
"""
    path.write_text(content, encoding="utf-8")


def create_original_scene_image(beat: dict[str, Any], scene_index: int, scene_count: int, destination: Path, cover_mode: bool = False, clean_scene: bool = False) -> None:
    """Create a bespoke original story scene locally with Pillow—no stock asset or image-gen API."""
    width, height = 1080, 1920
    palettes = [
        ((20, 24, 31), (37, 39, 43), (218, 183, 127)),
        ((18, 27, 37), (35, 43, 48), (230, 196, 137)),
        ((27, 25, 26), (45, 39, 36), (218, 183, 127)),
        ((20, 28, 29), (36, 43, 40), (206, 183, 141)),
        ((23, 24, 34), (40, 39, 48), (215, 184, 136)),
    ]
    pick = (scene_index + len(str(beat.get("visual_query", "")))) % len(palettes)
    top, bottom, amber = palettes[pick]
    cream, muted = (248, 244, 236), (190, 188, 182)
    image = Image.new("RGB", (width, height), top)
    draw = ImageDraw.Draw(image)
    # Smooth enough gradient from 48 bands; this is generated locally and consumes no API credits.
    for band in range(96):
        y0 = int(height * band / 96)
        y1 = int(height * (band + 1) / 96)
        t = band / 95
        col = tuple(round(top[c] * (1 - t) + bottom[c] * t) for c in range(3))
        draw.rectangle((0, y0, width, y1), fill=col)
    regular_path = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"
    bold_path = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"
    latin_path = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
    latin_bold_path = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
    fallback = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    for attr, path in (("regular", regular_path), ("bold", bold_path), ("latin", latin_path), ("latin_bold", latin_bold_path)):
        if not Path(path).exists():
            if attr in {"regular", "bold"}:
                if attr == "regular": regular_path = fallback
                else: bold_path = fallback
            else:
                if attr == "latin": latin_path = fallback
                else: latin_bold_path = fallback

    font_brand = ImageFont.truetype(latin_bold_path, 30)
    font_small = ImageFont.truetype(regular_path, 26)
    font_large = ImageFont.truetype(bold_path, 43)
    font_icon = ImageFont.truetype(latin_bold_path, 28)
    # Four subtle scene-index variations keep consecutive frames from feeling like one duplicated template.
    variation = scene_index % 4
    low_ink = (56, 60, 61)
    if variation == 0:
        draw.arc((-100, 340, 310, 750), start=265, end=80, fill=low_ink, width=4)
        draw.line((84, 1600, 260, 1600), fill=(67, 64, 58), width=3)
    elif variation == 1:
        for j in range(7):
            yy = 550 + j * 46
            draw.line((940, yy, 986 - (j % 3) * 12, yy), fill=(62, 64, 61), width=3)
        draw.arc((800, 1370, 1160, 1730), start=40, end=250, fill=low_ink, width=4)
    elif variation == 2:
        draw.arc((760, 280, 1130, 650), start=90, end=300, fill=low_ink, width=4)
        for j in range(5):
            draw.ellipse((94 + j * 22, 1630 + (j % 2) * 14, 100 + j * 22, 1636 + (j % 2) * 14), fill=(92, 82, 68))
    else:
        draw.line((810, 1550, 990, 1710), fill=(61, 62, 59), width=3)
        draw.line((850, 1500, 1015, 1650), fill=(52, 59, 59), width=3)
    # Deliberate brand architecture: branded scenes use a header/footer; clean_scene omits overlays which are burned once by ASS.
    # so the cover's own large title will not duplicate the brand header or editorial overlay.
    if not cover_mode and not clean_scene:
        draw.rounded_rectangle((50, 48, 1030, 1870), radius=36, outline=(79, 75, 68), width=2)
        draw.rounded_rectangle((82, 91, 99, 151), radius=8, fill=amber)
        draw.text((123, 91), "BINA SHOR KE", font=font_brand, fill=cream)
        draw.text((123, 133), "कम शब्द। साफ़ कहानी।", font=font_small, fill=amber)
        draw.text((985, 104), f"{scene_index:02d}/{scene_count:02d}", font=font_icon, fill=muted, anchor="ra")
        draw.line((82, 202, 998, 202), fill=(86, 78, 66), width=2)
        for j in range(8):
            x = 845 + j * 19
            draw.line((x, 255, x + 80, 255), fill=(63 + j * 2, 61 + j, 57 + j), width=2)
    type_value = str(beat.get("overlay_type", "keyword")).lower()
    query = str(beat.get("visual_query", "")).lower()
    direction = str(beat.get("visual_direction", "")).lower()
    combined = query + " " + direction
    panel = (115, 500, 965, 1105)
    draw.rounded_rectangle(panel, radius=34, fill=(19, 23, 28), outline=(91, 83, 69), width=2)
    # Object-specific original vector illustrations are selected from the story beat, not randomized filler.
    if any(term in combined for term in ("phone", "message", "notification", "chat", "text", "call")) or type_value == "message":
        x0, y0, x1, y1 = 360, 550, 720, 1045
        draw.rounded_rectangle((x0, y0, x1, y1), radius=48, fill=(12, 16, 21), outline=amber, width=5)
        draw.rounded_rectangle((x0+18, y0+32, x1-18, y1-24), radius=28, fill=(29, 35, 41))
        draw.rounded_rectangle((x0+125, y0+12, x0+235, y0+25), radius=7, fill=(65, 68, 68))
        for j, (label, right) in enumerate((("अनुरोध", False), ("एक और काम", True), ("आज संभव नहीं", False))):
            yy = y0 + 110 + j * 100
            xx = x0 + (110 if right else 26)
            draw.rounded_rectangle((xx, yy, xx + 190, yy + 62), radius=18,
                                   fill=(78, 76, 66) if right else (49, 58, 65))
            fit, lines = _fit_text(draw, label, regular_path, 165, 2, 24, 18)
            for li, line in enumerate(lines):
                draw.text((xx+14, yy+13+li*25), line, font=fit, fill=cream)
    elif any(term in combined for term in ("tea", "cup", "coffee", "chai")):
        # A warm original illustration of a cup and steam.
        for xx in (390, 480, 570):
            draw.arc((xx, 590, xx+62, 750), start=180, end=310, fill=muted, width=5)
        draw.rounded_rectangle((320, 720, 675, 900), radius=36, fill=(191, 174, 144), outline=amber, width=4)
        draw.ellipse((320, 690, 675, 770), fill=(227, 215, 192), outline=amber, width=4)
        draw.ellipse((352, 706, 643, 752), fill=(73, 52, 39))
        draw.arc((630, 755, 780, 880), start=265, end=95, fill=amber, width=16)
        draw.line((270, 917, 760, 917), fill=(103, 91, 77), width=3)
    elif any(term in combined for term in ("rain", "window", "street", "city", "night", "road")):
        draw.rounded_rectangle((245, 575, 835, 1000), radius=14, outline=amber, width=8)
        draw.line((540, 580, 540, 995), fill=amber, width=6)
        draw.line((252, 780, 828, 780), fill=amber, width=6)
        for j in range(12):
            x = 275 + (j * 41) % 515
            y = 600 + (j * 67) % 355
            draw.line((x, y, x-9, y+34), fill=(122, 157, 167), width=4)
        draw.rounded_rectangle((400, 825, 690, 950), radius=18, fill=(47, 58, 65))
        draw.rounded_rectangle((445, 850, 645, 890), radius=10, fill=amber)
    elif any(term in combined for term in ("shirt", "outfit", "clothing", "wardrobe", "watch", "grooming", "fashion")):
        draw.line((540, 570, 540, 650), fill=amber, width=12)
        draw.arc((460, 540, 620, 680), start=180, end=360, fill=amber, width=8)
        pts = [(450, 700), (390, 760), (450, 825), (480, 795), (480, 970), (600, 970), (600, 795), (630, 825), (690, 760), (630, 700), (590, 735), (490, 735)]
        draw.polygon(pts, fill=(63, 77, 81), outline=amber)
        draw.line((540, 740, 540, 950), fill=(154, 165, 160), width=3)
        draw.ellipse((514, 830, 566, 882), outline=amber, width=4)
    elif any(term in combined for term in ("laptop", "desk", "work", "notebook", "office", "writing", "paper")):
        draw.rounded_rectangle((315, 625, 765, 855), radius=22, fill=(27, 37, 44), outline=amber, width=5)
        draw.rounded_rectangle((341, 650, 739, 825), radius=10, fill=(44, 55, 60))
        draw.line((275, 890, 805, 890), fill=amber, width=9)
        draw.polygon([(360, 900), (720, 900), (785, 955), (295, 955)], fill=(83, 86, 83), outline=amber)
        draw.rounded_rectangle((650, 700, 850, 990), radius=12, fill=(221, 214, 196), outline=amber, width=3)
        for yy in (755, 800, 845, 890):
            draw.line((680, yy, 820, yy), fill=(115, 111, 101), width=3)
    else:
        # Original editorial framework / decision cards for themes without a literal object.
        labels = ["स्थिति", "प्रतिक्रिया", "नतीजा"]
        for j, label in enumerate(labels):
            yy = 590 + j * 135
            xx = 220 + j * 32
            draw.rounded_rectangle((xx, yy, 860-j*32, yy+95), radius=22,
                                   fill=(36+j*6, 43+j*4, 47+j*3), outline=amber if j == scene_index % 3 else (91, 86, 76), width=3)
            draw.ellipse((xx+24, yy+27, xx+64, yy+67), fill=amber if j == scene_index % 3 else muted)
            draw.text((xx+88, yy+25), label, font=font_large, fill=cream)
            draw.line((xx+88, yy+69, 790-j*28, yy+69), fill=(108, 105, 96), width=3)
    # Add the specific creative layer as a separate design element; the burned-in scene caption is separate below.
    if not cover_mode and not clean_scene:
        overlay = str(beat.get("overlay_text", "")).strip()
        label_font, label_lines = _fit_text(draw, overlay, bold_path, 780, 2, 41, 26)
        label_y = 335
        draw.rounded_rectangle((82, 305, 998, 450), radius=24, fill=(26, 29, 31), outline=(86, 78, 65), width=2)
        line_h = int(label_font.size * 1.20)
        for line in label_lines:
            draw.text((112, label_y), line, font=label_font, fill=amber)
            label_y += line_h
        # Original footer/navigation marks; subtitles burned later over a clean lower third.
        draw.line((82, 1450, 998, 1450), fill=(73, 70, 64), width=2)
        draw.rounded_rectangle((82, 1450, 82 + int(916 * scene_index / max(scene_count, 1)), 1458), radius=4, fill=amber)
        footer_font = ImageFont.truetype(latin_path, 22)
        draw.text((82, 1510), "ORIGINAL STORY VISUAL", font=footer_font, fill=muted)
        draw.text((998, 1510), f"{scene_index:02d} / {scene_count:02d}", font=footer_font, fill=amber, anchor="ra")
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)


def create_cover_background(destination: Path, seed_text: str = "BINA SHOR KE") -> None:
    """Create a clean, reusable-looking-but-seed-varied premium editorial cover background locally."""
    width, height = 1080, 1920
    seed = sum(ord(ch) for ch in seed_text) % 5
    palettes = [
        ((17, 21, 28), (35, 34, 32), (218, 183, 127)),
        ((17, 26, 34), (34, 39, 42), (224, 190, 133)),
        ((25, 22, 25), (39, 34, 33), (210, 177, 126)),
        ((19, 28, 29), (32, 39, 37), (205, 184, 145)),
        ((20, 23, 34), (38, 37, 45), (217, 184, 139)),
    ]
    top, bottom, accent = palettes[seed]
    image = Image.new("RGB", (width, height), top)
    draw = ImageDraw.Draw(image)
    for band in range(96):
        y0 = int(height * band / 96)
        y1 = int(height * (band + 1) / 96)
        t = band / 95
        color = tuple(round(top[c] * (1 - t) + bottom[c] * t) for c in range(3))
        draw.rectangle((0, y0, width, y1), fill=color)
    # Fine editorial frame, asymmetrical arcs and subtle amber guide marks; typography stays clear.
    draw.rounded_rectangle((62, 78, 1018, 1842), radius=40, outline=(65, 62, 57), width=2)
    draw.line((92, 300, 290, 300), fill=accent, width=5)
    draw.line((790, 1620, 990, 1620), fill=(82, 76, 67), width=3)
    draw.arc((190, 540, 890, 1240), start=205 + seed * 5, end=500 + seed * 5, fill=(67, 64, 59), width=5)
    draw.arc((280, 630, 800, 1150), start=30 + seed * 7, end=315 + seed * 7, fill=(52, 58, 60), width=3)
    for j in range(8):
        x = 830 + (j * 23)
        y = 420 + (j % 3) * 18
        draw.ellipse((x, y, x + 5, y + 5), fill=(92 + j * 3, 83 + j * 2, 68 + j))
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)


def fit_ai_scene_timing(audio_duration: float, clip_duration: float, *, allow_tiny_audio_tempo_fit: bool = False) -> dict[str, float]:
    """Synchronize narration without forcing harsh video speed-ups or rejecting short VO.

    The source AI clip is kept within a conservative 0.72x–1.38x playback range.
    If narration is shorter than that range, retain the clip's natural duration and
    pad the audio bed. If narration is slightly longer, slow the clip only to 1.38x
    and clone the final frame for a tightly bounded editorial hold. The hold remains
    below motion_diagnostics' 1.35s freeze threshold. A dedicated repair may also
    apply at most 3% pitch-preserving audio acceleration for borderline cases.
    """
    if audio_duration <= 0 or clip_duration <= 0:
        raise ValueError("Audio and AI clip durations must be positive.")

    audio_pad = 0.08
    max_video_ratio = 1.38
    min_video_ratio = 0.72
    max_tail_hold = 1.20
    rendered_audio_duration = audio_duration
    tempo = 1.0
    target_duration = audio_duration + audio_pad
    raw_ratio = target_duration / clip_duration

    # Preserve the previously qualified <=3% pitch-preserving fit for borderline
    # cases only. Larger timing mismatches are handled by a short visual end-hold,
    # never by speeding up Hindi narration or pushing the video beyond 1.38x.
    if raw_ratio > max_video_ratio and allow_tiny_audio_tempo_fit and raw_ratio <= 1.42:
        max_audio_duration = clip_duration * max_video_ratio - audio_pad
        if max_audio_duration <= 0:
            raise RuntimeError("AI scene is too short for the bounded voice-timing repair.")
        tempo = audio_duration / max_audio_duration
        if not 1.0 < tempo <= 1.03:
            raise RuntimeError(
                f"Voice timing repair would require {tempo:.3f}x audio tempo; "
                "maximum allowed is 1.03x. Regenerate the voiceover or scene."
            )
        rendered_audio_duration = audio_duration / tempo
        target_duration = rendered_audio_duration + audio_pad
        raw_ratio = target_duration / clip_duration

    # Never accelerate a short visual just to match a short spoken line. Let the
    # scene play at its native duration while the mixed ambience carries the tail.
    if raw_ratio < min_video_ratio:
        target_duration = clip_duration
        video_speed_ratio = 1.0
    else:
        video_speed_ratio = min(raw_ratio, max_video_ratio)

    video_hold_duration = max(0.0, target_duration - clip_duration * video_speed_ratio)
    if video_hold_duration > max_tail_hold + 1e-6:
        raise RuntimeError(
            f"AI scene needs a {video_hold_duration:.2f}s end hold, above the "
            f"{max_tail_hold:.2f}s quality limit; regenerate a longer scene or shorten the narration."
        )

    audio_pad_duration = max(0.0, target_duration - rendered_audio_duration)
    return {
        "audio_tempo": round(tempo, 6),
        "original_audio_duration": round(audio_duration, 4),
        "rendered_audio_duration": round(rendered_audio_duration, 4),
        "target_duration": round(target_duration, 4),
        "video_speed_ratio": round(video_speed_ratio, 6),
        "video_hold_duration": round(video_hold_duration, 4),
        "audio_pad_duration": round(audio_pad_duration, 4),
    }
def render_reel(concept: dict[str, Any], reel_dir: Path, asset_ids: set[str], history_asset_ids: set[str]) -> dict[str, Any]:
    """Render a Reel from original custom graphics; optionally use 2 Pexels shots in cinematic pillar."""
    clips_dir = reel_dir / "clips"
    art_dir = reel_dir / "original_art"
    voice_dir = reel_dir / "voice"
    segments_dir = reel_dir / "segments"
    for folder in (clips_dir, art_dir, voice_dir, segments_dir):
        folder.mkdir(parents=True, exist_ok=True)
    editorial_plan = concept.get("editorial_shot_plan")
    if isinstance(editorial_plan, dict):
        (reel_dir / "editorial_shot_plan.json").write_text(
            json.dumps(editorial_plan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    pexels_credits: list[dict[str, Any]] = []
    current_ids = set(asset_ids)
    used_assets: list[str] = []
    segment_paths: list[Path] = []
    voice_audio_paths: list[Path] = []
    first_visual: Path | None = None
    first_beat: dict[str, Any] | None = None
    total_voice_seconds = 0.0
    rhythm_adjustments: list[dict[str, Any]] = []
    original_graphic_scenes = 0
    stock_scenes = 0

    require_ai_video = os.getenv("REQUIRE_AI_VIDEO", "0").strip() == "1"
    primary_image_first = (
        require_ai_video
        and concept.get("visual_pipeline") == story_engine.PRIMARY_25D_PIPELINE
    )
    # Wan legacy source clips stay at 24 FPS. Primary 2.5D masters are rendered at 30 FPS.
    target_fps = (
        30 if story_engine.is_25d_pipeline(concept.get("visual_pipeline"))
        else (24 if require_ai_video else 30)
    )
    if require_ai_video and not primary_image_first:
        # Preserve the clear legacy error contract: detect missing Wan source assets
        # before reporting an absent editorial plan, and always before TTS generation.
        missing_legacy_clips = [
            f"scene_{i+1:02d}.mp4"
            for i in range(len(concept["beats"]))
            if not (reel_dir / "ai_clips" / f"scene_{i+1:02d}.mp4").is_file()
        ]
        if missing_legacy_clips:
            raise RuntimeError(
                "AI-video mode is missing required clips before TTS starts: "
                + ", ".join(missing_legacy_clips)
            )
    if require_ai_video:
        if not isinstance(editorial_plan, dict):
            raise RuntimeError("AI production requires a voice-locked editorial_shot_plan; refusing a legacy fallback.")
        if int(editorial_plan.get("source_beat_count", 0)) != len(concept["beats"]):
            raise RuntimeError("Editorial shot plan source beat count does not match the screenplay.")
        expected_shots = int(editorial_plan.get("editorial_shot_count", 0))
        policy = story_engine.policy_for(concept.get("story_type", "emotional"))
        if not policy["min_shots"] <= expected_shots <= policy["max_shots"]:
            raise RuntimeError(f"Editorial shot plan has {expected_shots} shots; expected {policy['min_shots']}–{policy['max_shots']} for {policy['story_type']}.")
        if primary_image_first:
            sources = [shot.get("source") for shot in editorial_plan.get("shots", [])]
            if not sources or any(source != "depth_parallax" for source in sources):
                raise RuntimeError("Primary 2.5D must use only depth-parallax editorial shots; a Wan hero-video route is not permitted in the default image-first mode.")
            for i, beat in enumerate(concept["beats"], start=1):
                still = reel_dir / "ai_clips" / f"scene_{i:02d}.png"
                depth_clip = reel_dir / "ai_clips" / f"scene_{i:02d}_25d.mp4"
                if not still.is_file() or still.stat().st_size < 100_000:
                    raise RuntimeError(f"Image-first 2.5D is missing or has an invalid still asset: {still.name}")
                try:
                    with Image.open(still) as image:
                        image.verify()
                    with Image.open(still) as image:
                        if image.size != (704, 1280):
                            raise RuntimeError(f"Image-first still {still.name} must be 704x1280; got {image.size}.")
                except Exception as exc:
                    raise RuntimeError(f"Image-first still {still.name} failed image validation: {exc}") from exc
                if not depth_clip.is_file() or depth_clip.stat().st_size < 100_000:
                    raise RuntimeError(f"Image-first 2.5D is missing required depth-parallax clip {depth_clip.name}.")
                measured = probe_duration(depth_clip)
                planned = float((beat.get("voice_timing") or {}).get("target_duration_seconds", 0) or 0)
                if planned <= 0 or abs(measured - planned) > 0.20:
                    raise RuntimeError(
                        f"Image-first parallax duration mismatch for beat {i}: planned {planned:.3f}s, "
                        f"measured {measured:.3f}s."
                    )
        elif story_engine.is_25d_pipeline(concept.get("visual_pipeline")):
            missing_ai = [
                f"scene_{i:02d}.mp4" for i in range(1, len(concept["beats"]) + 1)
                if not (reel_dir / "ai_clips" / f"scene_{i:02d}.mp4").is_file()
            ]
            if missing_ai:
                raise RuntimeError("Legacy hybrid video mode is missing required Wan source clips: " + ", ".join(missing_ai))
            for i in range(len(concept["beats"])):
                source_clip = reel_dir / "ai_clips" / f"scene_{i+1:02d}.mp4"
                depth_clip = reel_dir / "ai_clips" / f"scene_{i+1:02d}_25d.mp4"
                if not depth_clip.is_file() or depth_clip.stat().st_size < 100_000:
                    raise RuntimeError(f"Legacy hybrid mode is missing a valid depth-parallax scene {depth_clip.name}.")
                if abs(probe_duration(source_clip) - probe_duration(depth_clip)) > 0.20:
                    raise RuntimeError(f"Legacy hybrid depth-parallax duration mismatch for beat {i+1}.")
        else:
            missing_ai = [
                f"scene_{i+1:02d}.mp4" for i in range(len(concept["beats"]))
                if not (reel_dir / "ai_clips" / f"scene_{i+1:02d}.mp4").is_file()
            ]
            if missing_ai:
                raise RuntimeError("AI-video mode is missing required clips before TTS starts: " + ", ".join(missing_ai))
            for i in range(len(concept["beats"])):
                clip = reel_dir / "ai_clips" / f"scene_{i+1:02d}.mp4"
                if clip.stat().st_size < 100_000 or probe_duration(clip) < 2.5:
                    raise RuntimeError(f"AI scene {clip.name} is missing, too small or too short; refusing to spend TTS quota on an invalid batch.")

    for i, beat in enumerate(concept["beats"]):
        log(f"[{concept['title']}] Voice-first render {i+1}/{len(concept['beats'])}: {beat['visual_query']}")
        audio_path = voice_dir / f"beat_{i+1:02d}.wav"
        speech_segments = beat.get("speech_segments")
        if isinstance(speech_segments, list):
            line_paths: list[Path] = []
            spoken_seconds = 0.0
            measured_line_durations: dict[str, float] = {}
            for line_index, line in enumerate(speech_segments, start=1):
                speaker_id = str(line["speaker_id"])
                segment_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(line.get("segment_id") or f"beat_{i+1:02d}_line_{line_index:02d}"))
                line_path = voice_dir / f"{segment_id}_{speaker_id}.wav"
                voice_direction = (
                    str(line.get("voice_direction") or "Natural Hindi dialogue.")
                    + " Performance emotion: " + str(line.get("emotion") or "natural, restrained")
                )
                ensure_tts_wav(
                    str(line["text"]), line_path,
                    voice_direction=voice_direction,
                    voice_name=str(line.get("gemini_voice") or TTS_VOICE),
                )
                measured = voice_first.wav_duration(line_path)
                measured_line_durations[segment_id] = measured
                spoken_seconds += measured
                line_paths.append(line_path)
            if line_paths:
                timing_reconciliation = reconcile_actual_voice_timing(
                    beat, measured_line_durations
                )
                if timing_reconciliation["adjusted"]:
                    log(
                        f"[{concept['title']}] Beat {i+1}: exact WAV timing differed from the "
                        "planning snapshot; the beat was safely replanned from measured audio."
                    )
            if not line_paths:
                planned_scene = float((beat.get("voice_timing") or {}).get("target_duration_seconds", 2.5))
                voice_first.write_silence_wav(audio_path, max(2.5, planned_scene))
                audio_duration = voice_first.wav_duration(audio_path)
            else:
                audio_duration = voice_first.assemble_dialogue_wav(
                    line_paths, audio_path,
                    leading_silence_seconds=voice_first.HEAD_HANDLE_SECONDS,
                )
            total_voice_seconds += spoken_seconds
        else:
            # Backward compatibility for an older pending manifest or a hand-authored test concept.
            ensure_tts_wav(beat["voiceover"], audio_path, voice_direction=beat.get("voice_direction"))
            audio_duration = probe_duration(audio_path)
            total_voice_seconds += audio_duration
        voice_audio_paths.append(audio_path)
        if not 1.0 <= audio_duration <= 12.0:
            raise RuntimeError(f"Rendered dialogue beat {i+1} length {audio_duration:.2f}s is outside the 1–12s safety range; storyboard must split the scene, never shorten its words.")
        rendered_audio_duration = audio_duration
        target_duration = audio_duration + 0.08
        audio_tempo = 1.0

        # Image-first primary 2.5D uses one generated still plus its real depth-parallax
        # motion master per beat. Legacy Wan routes remain available only for old manifests.
        if primary_image_first:
            still_image = reel_dir / "ai_clips" / f"scene_{i+1:02d}.png"
            ai_clip = reel_dir / "ai_clips" / f"scene_{i+1:02d}_25d.mp4"
            if not still_image.is_file() or not ai_clip.is_file():
                raise RuntimeError(f"Image-first primary 2.5D is missing still/parallax assets for beat {i+1}; refusing static or legacy downgrade.")
            if first_visual is None:
                first_visual = still_image
                first_beat = beat
        else:
            still_image = None
            ai_clip = reel_dir / "ai_clips" / f"scene_{i+1:02d}.mp4"
            if require_ai_video and not ai_clip.exists():
                raise RuntimeError(f"AI-video mode requires scene clip {ai_clip.name}; refusing to silently downgrade to static graphics.")
        if ai_clip.exists():
            if first_visual is None:
                first_visual = still_image if primary_image_first else ai_clip
                first_beat = beat
            clip_duration = probe_duration(ai_clip)
            if clip_duration < 2.5:
                raise RuntimeError(f"AI scene {i+1} too short ({clip_duration:.2f}s); refusing low-quality loop.")
            timing = fit_ai_scene_timing(
                audio_duration, clip_duration,
                allow_tiny_audio_tempo_fit=os.getenv("BSK_ALLOW_TINY_VO_TEMPO_FIT", "0").strip().lower() in {"1", "true", "yes"},
            )
            target_duration = timing["target_duration"]
            rendered_audio_duration = timing["rendered_audio_duration"]
            audio_tempo = timing["audio_tempo"]
            ratio = timing["video_speed_ratio"]
            video_hold_duration = timing["video_hold_duration"]
            audio_pad_duration = timing["audio_pad_duration"]
            if audio_tempo > 1.000001 or video_hold_duration > 0.001 or audio_pad_duration > 0.081:
                adjustment = {
                    "scene_index": i + 1,
                    "method": "bounded video retime / intentional end-hold / audio padding",
                    "audio_tempo": audio_tempo,
                    "original_audio_duration_seconds": timing["original_audio_duration"],
                    "rendered_audio_duration_seconds": timing["rendered_audio_duration"],
                    "video_speed_ratio_before": round((audio_duration + 0.08) / clip_duration, 4),
                    "video_speed_ratio_after": ratio,
                    "video_hold_duration_seconds": video_hold_duration,
                    "audio_pad_duration_seconds": audio_pad_duration,
                    "human_listening_review_required": True,
                }
                rhythm_adjustments.append(adjustment)
                log(
                    f"Timed AI scene {i+1}: video ratio={ratio:.4f}x, "
                    f"end hold={video_hold_duration:.3f}s, audio pad={audio_pad_duration:.3f}s."
                )
            if story_engine.is_25d_pipeline(concept.get("visual_pipeline")):
                parallax_clip = reel_dir / "ai_clips" / f"scene_{i+1:02d}_25d.mp4"
                editorial_clip = clips_dir / f"scene_{i+1:02d}_editorial.mp4"
                beat_shots = story_engine.retime_beat_shots(beat.get("editorial_shots", []), target_duration)
                motion_comic.render_editorial_montage(
                    None if primary_image_first else ai_clip,
                    parallax_clip, editorial_clip, beat_shots,
                    target_duration=target_duration,
                    video_speed_ratio=ratio,
                    video_hold_duration=video_hold_duration,
                    fps=target_fps,
                )
                input_args = ["-i", str(editorial_clip), "-i", str(audio_path)]
                video_filter = (
                    f"fps={target_fps},eq=contrast=1.035:saturation=0.96:brightness=-0.006,vignette=PI/6,"
                    f"subtitles='{(segments_dir / f'beat_{i+1:02d}.ass').as_posix()}':fontsdir={FONT_DIR}"
                )
            else:
                input_args = ["-i", str(ai_clip), "-i", str(audio_path)]
                hold_filter = (
                    f",tpad=stop_mode=clone:stop_duration={video_hold_duration:.3f}"
                    if video_hold_duration > 0.001 else ""
                )
                video_filter = (
                    f"setpts=PTS*{ratio:.5f}{hold_filter},scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                    f"fps={target_fps},eq=contrast=1.035:saturation=0.94:brightness=-0.008,vignette=PI/6,"
                    f"subtitles='{(segments_dir / f'beat_{i+1:02d}.ass').as_posix()}':fontsdir={FONT_DIR}"
                )
            original_graphic_scenes += 0
            stock_clip = None
        else:
            stock_clip = None
        # Pexels is an optional support asset only when strict AI mode is off.
        if not ai_clip.exists() and not require_ai_video and PEXELS_API_KEY and concept.get("pillar") == "cinematic_moment" and i in (1, 4):
            try:
                asset = pexels_search(beat["visual_query"], history_asset_ids, current_ids)
                current_ids.add(asset["id"])
                used_assets.append(asset["id"])
                stock_clip = clips_dir / f"clip_{i+1:02d}.mp4"
                download_file(asset["download_url"], stock_clip)
                pexels_credits.append({"video_id": asset["id"], "video_url": asset["url"], "creator": asset["creator"], "creator_url": asset["creator_url"], "query": asset["query_used"]})
                stock_scenes += 1
            except Exception as exc:
                log(f"Optional Pexels shot unavailable; switching to original graphic for scene {i+1}: {exc}")
                stock_clip = None

        if ai_clip.exists():
            # AI clip path already prepared above; each scene is independently generated, then post-produced.
            pass
        elif stock_clip is None:
            visual_path = art_dir / f"scene_{i+1:02d}.png"
            create_original_scene_image(beat, i+1, len(concept["beats"]), visual_path, clean_scene=True)
            original_graphic_scenes += 1
            if first_visual is None:
                first_visual = visual_path
                first_beat = beat
            input_args = ["-loop", "1", "-framerate", "30", "-i", str(visual_path), "-i", str(audio_path)]
            video_filter = (
                "zoompan=z='min(zoom+0.00020,1.035)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,"
                "eq=contrast=1.04:saturation=0.91:brightness=-0.012,vignette=PI/5,"
                f"subtitles='{(segments_dir / f'beat_{i+1:02d}.ass').as_posix()}':fontsdir={FONT_DIR}"
            )
        else:
            if first_visual is None:
                first_visual = stock_clip
                first_beat = beat
            input_args = ["-stream_loop", "-1", "-i", str(stock_clip), "-i", str(audio_path)]
            video_filter = (
                "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                "eq=contrast=1.045:saturation=0.90:brightness=-0.018,vignette=PI/5,"
                f"subtitles='{(segments_dir / f'beat_{i+1:02d}.ass').as_posix()}':fontsdir={FONT_DIR}"
            )

        ass_path = segments_dir / f"beat_{i+1:02d}.ass"
        write_ass(ass_path, beat["screen_text"], target_duration,
                  overlay_text=beat["overlay_text"], overlay_type=beat["overlay_type"],
                  scene_index=i + 1, scene_count=len(concept["beats"]))
        segment_path = segments_dir / f"segment_{i+1:02d}.mp4"
        duration = target_duration
        audio_pad_duration = timing["audio_pad_duration"] if ai_clip.exists() else 0.08
        has_speech = bool(speech_segments) or bool(str(beat.get("voiceover") or "").strip())
        audio_filter = _scene_audio_filter(audio_tempo, audio_pad_duration, has_speech=has_speech)
        run_cmd([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *input_args,
            "-vf", video_filter, "-map", "0:v:0", "-map", "1:a:0",
            "-t", f"{duration:.3f}", "-r", str(target_fps), "-vsync", "cfr",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
            "-af", audio_filter,
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(segment_path),
        ], timeout=300)
        segment_paths.append(segment_path)

    narration_qa = audio_transcript_qa(voice_audio_paths, [beat["voiceover"] for beat in concept["beats"]], reel_dir)

    list_path = reel_dir / "concat.txt"
    list_path.write_text("\n".join("file '" + p.as_posix().replace("'", "'\\''") + "'" for p in segment_paths) + "\n", encoding="utf-8")
    video_path = reel_dir / "reel.mp4"
    run_cmd(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", "-movflags", "+faststart", str(video_path)], timeout=300)

    # Compress only when needed to remain safely under Telegram's documented 50 MB sendVideo limit.
    if video_path.stat().st_size > 38 * 1024 * 1024:
        compact = reel_dir / "reel_compact.mp4"
        run_cmd(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video_path), "-c:v", "libx264", "-preset", "fast", "-crf", "24", "-maxrate", "2600k", "-bufsize", "5200k", "-c:a", "aac", "-b:a", "112k", "-movflags", "+faststart", str(compact)], timeout=300)
        compact.replace(video_path)

    base_duration = probe_duration(video_path)
    bed_path = reel_dir / "original_sound_bed.wav"
    create_original_sound_bed(bed_path, base_duration, concept.get("pillar", "micro_story"))
    mixed_path = reel_dir / "reel_with_sound_bed.mp4"
    run_cmd([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video_path), "-i", str(bed_path),
        "-filter_complex", final_audio_mix_filter(),
        "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(mixed_path),
    ], timeout=300)
    if not mixed_path.exists() or mixed_path.stat().st_size < 100_000:
        raise RuntimeError("Original sound design mix failed technical validation.")
    mixed_path.replace(video_path)
    final_duration = probe_duration(video_path)
    media_info = probe_media(video_path, expected_fps=target_fps)
    duration_policy = story_engine.policy_for(concept.get("story_type", "emotional"))
    if not duration_policy["min_seconds"] - 0.5 <= final_duration <= duration_policy["max_seconds"] + 0.5:
        raise RuntimeError(
            f"Technical QA rejected {final_duration:.1f}s {duration_policy['story_type']} Reel; "
            f"expected {duration_policy['min_seconds']}–{duration_policy['max_seconds']} seconds."
        )
    if video_path.stat().st_size > 45 * 1024 * 1024:
        raise RuntimeError("Technical QA rejected video over 45 MB (Telegram delivery safety limit).")

    if first_visual is None:
        raise RuntimeError("No first visual available for cover generation.")
    cover_bg = reel_dir / "cover_bg.jpg"
    cover_art = reel_dir / "cover_background.png"
    first_ai_clip = reel_dir / "ai_clips" / "scene_01.mp4"
    if first_ai_clip.exists():
        run_cmd(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "0.8", "-i", str(first_ai_clip), "-frames:v", "1", "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", "-q:v", "2", str(cover_bg)], timeout=90)
    else:
        create_cover_background(cover_art, concept.get("title", "BINA SHOR KE"))
        with Image.open(cover_art) as image:
            image.convert("RGB").save(cover_bg, quality=93)
    cover_ass = reel_dir / "cover.ass"
    write_ass(cover_ass, concept["cover_text"], 1.0, is_cover=True)
    cover_path = reel_dir / "cover.png"
    run_cmd(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(cover_bg), "-vf", f"subtitles='{cover_ass.as_posix()}':fontsdir={FONT_DIR}", "-frames:v", "1", str(cover_path)], timeout=90)

    segment_durations = [probe_duration(path) for path in segment_paths]
    frame_review = visual_qa(video_path, reel_dir, final_duration, segment_durations=segment_durations)
    frame_review["full_video_motion_diagnostics"] = motion_diagnostics(video_path)
    # Save the scorecard and sampled frames before the fail-closed gate so rejected
    # Reels always carry the evidence referenced by Telegram alerts and Actions artifacts.
    persist_visual_qa_report(reel_dir, frame_review)
    # Fail closed for unmistakably broken text/composition. If visual model review is
    # unavailable, deliver only with an explicit human-review requirement instead.
    enforce_visual_qa(frame_review)
    technical = {
        "duration_seconds": round(final_duration, 2),
        "resolution": "1080x1920", "aspect_ratio": "9:16",
        "frame_rate_target": f"{target_fps} fps" + (" (primary 2.5D editorial master; Wan source 24 fps)" if story_engine.is_25d_pipeline(concept.get("visual_pipeline")) else (" (native Wan cadence)" if require_ai_video else "")),
        "visual_style_profile": concept.get("visual_style_profile", {}),
        "primary_visual_pipeline": story_engine.PRIMARY_25D_PIPELINE,
        "ffprobe_media_info": media_info, "file_size_mb": round(video_path.stat().st_size / 1024 / 1024, 2),
        "voice_segments": len(concept["beats"]), "editorial_shots": int((concept.get("editorial_shot_plan") or {}).get("editorial_shot_count", len(concept["beats"]))), "stock_video_segments": stock_scenes,
        "original_custom_graphic_scenes": original_graphic_scenes,
        "ai_source_video_scenes": sum(1 for i in range(len(concept["beats"])) if (reel_dir / "ai_clips" / f"scene_{i+1:02d}.mp4").exists()),
        "depth_parallax_scenes": sum(1 for i in range(len(concept["beats"])) if (reel_dir / "ai_clips" / f"scene_{i+1:02d}_25d.mp4").exists()),
        "visual_pipeline": concept.get("visual_pipeline", "legacy_wan_video"),
        "custom_story_specific_overlays": sum(1 for beat in concept["beats"] if beat.get("overlay_text")),
        "unique_pexels_video_ids_in_reel": len(set(used_assets)),
        "originality_safeguards": concept.get("originality_safeguards", {}),
        "meta_originality_or_monetization_guaranteed": False,
        "technical_checks_passed": True, "original_sound_bed_mixed": True, "rendered_frame_visual_qa": frame_review,
        "audio_timing_adjustments": rhythm_adjustments,
        "manual_review_required": [
            "Listen once for Hindi pronunciation and pacing.",
            "Check every subtitle on a phone screen before publishing.",
            "Confirm the cover and caption match the intended Page brand.",
            "Check illustrated style consistency, character continuity, parallax depth, natural motion and obvious AI defects. If anything feels visibly broken, do not publish; regenerate that beat.",
            "Evaluate whether the story and editing add meaningful creative value beyond AI-generated footage.",
            "Use Meta's current AI disclosure/label option when required for realistic synthetic media; do not imply a fictional story is a verified real event.",
        ],
    }
    return {"video_path": video_path, "cover_path": cover_path, "credits": pexels_credits, "asset_ids": used_assets, "technical": technical, "voice_seconds": round(total_voice_seconds, 2), "audio_timing_adjustments": rhythm_adjustments}


def generate_carousel(history: dict[str, Any], slot: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate and editorially validate a useful, original 5-slide carousel."""
    recent_topics = history.get("topics", [])[-35:]
    recent_titles = [x.get("title", "") for x in recent_topics]
    recent_themes = [x.get("theme", "") for x in recent_topics]
    system = (
        "You are the senior editorial strategist for BINA SHOR KE. Create original, useful Hindi carousels, "
        "not quote dumps. Do not imitate creators, movies, books, songs, or viral scripts. Avoid fake facts, "
        "medical/legal/financial advice, identifiable people, rage bait, false claims, and forced engagement. "
        "Return JSON only. Write natural Hindi in Devanagari; use Hinglish only when natural."
    )
    prompt = f"""Create one original 5-slide Facebook photo-carousel post for BINA SHOR KE.
Brand promise: 'कम शब्द। साफ़ कहानी।' Audience is Hindi-understanding adults interested in human behaviour, self-respect, practical lifestyle and everyday decisions.
Choose a specific, useful topic that complements rather than repeats recent content. Prefer a small practical framework, a relatable behavioural observation, or a specific men's presentation habit. Do not create generic motivational quotes.
Planned slot: {slot.strftime('%A %d %B %Y, %I:%M %p IST')} (test only; not a proven best time).
Recent titles: {json.dumps(recent_titles, ensure_ascii=False)}
Recent themes: {json.dumps(recent_themes, ensure_ascii=False)}
Return JSON with exactly these fields:
{{
  "title": "short unique post title",
  "theme": "specific one-sentence theme",
  "audience_reason": "one-sentence hypothesis, not a certainty",
  "caption": "a useful 2-3 line caption, not a restatement of all slides",
  "hashtags": ["#BinaShorKe", "#relevant2", "#relevant3"],
  "slides": [
    {{"headline":"slide heading", "body":"specific useful copy, 1-3 short sentences", "purpose":"why this slide matters"}},
    {{"headline":"...", "body":"...", "purpose":"..."}},
    {{"headline":"...", "body":"...", "purpose":"..."}},
    {{"headline":"...", "body":"...", "purpose":"..."}},
    {{"headline":"...", "body":"clear takeaway or practical next step", "purpose":"..."}}
  ]
}}
Rules: slide 1 must be a genuine hook; slides 2-4 must add progressive information or a short story, not repeat a claim; slide 5 must deliver a useful takeaway. Keep each headline under 58 characters and each body under 220 characters. No invented statistics, product promotion, or "comment/share/follow" bait. 3-5 relevant hashtags. Return JSON only."""

    last_error = None
    last_revision_notes: list[str] = []
    for attempt in range(2):
        try:
            revised_prompt = prompt
            if attempt == 1:
                revised_prompt += "\nEDITORIAL REVISIONS REQUIRED FROM FIRST ATTEMPT: " + json.dumps(last_revision_notes, ensure_ascii=False) + "\nReplace weak sections directly; do not simply paraphrase them. Avoid every recent theme."
            carousel = text_json(system, revised_prompt, temperature=0.7)
            validate_carousel_shape(carousel)
            review_prompt = f"""Review this 5-slide Facebook carousel for BINA SHOR KE:
{json.dumps(carousel, ensure_ascii=False)}
Score 1-5: hook_clarity, usefulness, specificity, progression, readability, originality, platform_safety. Return JSON only: {{"scores":{{"hook_clarity":1,"usefulness":1,"specificity":1,"progression":1,"readability":1,"originality":1,"platform_safety":1}},"approved":true,"revision_notes":[],"main_risk":""}}. Approve only if average score >=4.0 and no major originality or safety issue. Reject generic quote collections and repeated points."""
            review = independent_review_json("You are a strict editorial reviewer. Be candid, not flattering. Output JSON only.", review_prompt, temperature=0.15)
            score_keys = ("hook_clarity", "usefulness", "specificity", "progression", "readability", "originality", "platform_safety")
            scores = review.get("scores", {})
            scores_valid = isinstance(scores, dict) and all(
                key in scores and isinstance(scores[key], (int, float)) and 1 <= float(scores[key]) <= 5
                for key in score_keys
            )
            avg = sum(float(scores[key]) for key in score_keys) / len(score_keys) if scores_valid else 0.0
            safety = float(scores["platform_safety"]) if scores_valid else 0.0
            carousel["editorial_review"] = {
                "scores": scores,
                "average_score": round(avg, 2),
                "approved": bool(review.get("approved")),
                "revision_notes": review.get("revision_notes", []),
                "main_risk": review.get("main_risk", ""),
            }
            carousel["planned_publish_at"] = slot.isoformat()
            carousel["planned_publish_label"] = slot.strftime("%a %d %b, %I:%M %p IST")
            if topic_is_too_similar(str(carousel["title"]), str(carousel["theme"]), recent_topics):
                raise ValueError("Carousel title/theme is too similar to recent published/generated content.")
            if scores_valid and review.get("approved") and avg >= 4.0 and safety >= 4:
                return carousel, review
            last_revision_notes = [str(note) for note in review.get("revision_notes", [])][:8]
            last_error = f"Carousel editorial gate rejected content: average={avg:.2f}, safety={safety:.1f}, notes={last_revision_notes}"
            log(last_error)
        except Exception as exc:
            last_error = str(exc)
            last_revision_notes = (last_revision_notes + [f"Previous attempt failed validation: {last_error[:400]}"])[-8:]
            log(f"Carousel draft attempt {attempt+1} failed validation: {last_error}")
            if "HTTP 429" in last_error:
                break  # Stop hammering a free quota that is already rate-limited.
    raise RuntimeError("Carousel editorial gate rejected both drafts. No carousel was delivered. " + str(last_error))


def validate_carousel_shape(carousel: dict[str, Any]) -> None:
    required = ("title", "theme", "caption", "hashtags", "slides")
    missing = [key for key in required if not carousel.get(key)]
    if missing:
        raise ValueError("Carousel misses required fields: " + ", ".join(missing))
    if not isinstance(carousel["slides"], list) or len(carousel["slides"]) != 5:
        raise ValueError("Carousel must contain exactly 5 slides.")
    for i, slide in enumerate(carousel["slides"], start=1):
        for key in ("headline", "body", "purpose"):
            if not isinstance(slide.get(key), str) or not slide[key].strip():
                raise ValueError(f"Carousel slide {i} misses {key}.")
        if len(slide["headline"]) > 58 or len(slide["body"]) > 220:
            raise ValueError(f"Carousel slide {i} copy exceeds the mobile layout limit.")
    if not isinstance(carousel["hashtags"], list):
        carousel["hashtags"] = []
    carousel["hashtags"] = [str(tag).strip().replace(" ", "") for tag in carousel["hashtags"][:5]]
    if not any(tag.lower() == "#binashorke" for tag in carousel["hashtags"]):
        carousel["hashtags"].insert(0, "#BinaShorKe")
    carousel["hashtags"] = carousel["hashtags"][:5]
    if len(carousel["hashtags"]) < 3:
        carousel["hashtags"] += ["#HindiStories", "#HumanBehaviour"][:3-len(carousel["hashtags"])]


def _wrap_pixels(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap text by measured width instead of character count, keeping Hindi glyphs together."""
    lines: list[str] = []
    for paragraph in str(text).split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = current + " " + word
            if draw.textlength(trial, font=font) <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font_path: str, max_width: int, max_lines: int,
              start_size: int, min_size: int = 30) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    for size in range(start_size, min_size - 1, -2):
        font = ImageFont.truetype(font_path, size=size)
        lines = _wrap_pixels(draw, text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines
    font = ImageFont.truetype(font_path, size=min_size)
    return font, _wrap_pixels(draw, text, font, max_width)[:max_lines]


def render_carousel(carousel: dict[str, Any], slot: datetime) -> dict[str, Any]:
    """Render a branded 5-slide 4:5 image carousel without requiring an image-generation subscription."""
    safe_title = re.sub(r"[^a-z0-9]+", "-", carousel["title"].lower()).strip("-")[:32] or "weekly-carousel"
    stamp = datetime.now(TZ).strftime("%Y%m%d_%H%M")
    out_dir = OUT / f"{stamp}_carousel_{safe_title}"
    out_dir.mkdir(parents=True, exist_ok=True)
    regular_path = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"
    bold_path = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"
    latin_regular_path = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
    latin_bold_path = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
    if not all(Path(path).exists() for path in (regular_path, bold_path, latin_regular_path, latin_bold_path)):
        raise RuntimeError("Required Noto Sans + Devanagari fonts are not installed; cannot safely render carousel text.")

    slide_paths: list[Path] = []
    width, height = 1080, 1350
    bg_top = (23, 25, 29)
    bg_bottom = (39, 37, 34)
    cream = (248, 244, 236)
    muted = (193, 188, 179)
    amber = (216, 180, 122)
    for idx, slide in enumerate(carousel["slides"], start=1):
        image = Image.new("RGB", (width, height), bg_top)
        pixels = image.load()
        for y in range(height):
            t = y / max(height - 1, 1)
            color = tuple(int(bg_top[c] * (1 - t) + bg_bottom[c] * t) for c in range(3))
            for x in range(width):
                pixels[x, y] = color
        draw = ImageDraw.Draw(image)
        # Restrained editorial grid and accent; consistent brand signature across the carousel.
        draw.rounded_rectangle((60, 56, 1020, 1290), radius=32, outline=(69, 65, 58), width=2)
        draw.rounded_rectangle((82, 88, 98, 150), radius=8, fill=amber)
        brand_font = ImageFont.truetype(latin_bold_path, size=30)
        label_font = ImageFont.truetype(regular_path, size=24)
        small_font = ImageFont.truetype(latin_regular_path, size=23)
        draw.text((120, 88), "BINA SHOR KE", font=brand_font, fill=cream)
        draw.text((120, 132), "कम शब्द। साफ़ कहानी।", font=label_font, fill=amber)
        draw.text((930, 95), f"{idx:02d}/05", font=brand_font, fill=muted, anchor="ra")
        draw.line((82, 190, 998, 190), fill=(91, 82, 67), width=2)
        # Tiny visual marker creates a rhythm without competing with reading.
        draw.rounded_rectangle((82, 240, 220, 250), radius=5, fill=amber)
        head_font, head_lines = _fit_text(draw, slide["headline"], bold_path, 850, 3, 68 if idx == 1 else 60, 42)
        head_height = int(head_font.size * 1.27)
        head_y = 290
        for line in head_lines:
            draw.text((82, head_y), line, font=head_font, fill=cream, stroke_width=0)
            head_y += head_height
        body_text = str(slide["body"]).strip()
        body_font, body_lines = _fit_text(draw, body_text, regular_path, 850, 7, 44, 34)
        body_y = max(head_y + 42, 455)
        body_line_h = int(body_font.size * 1.48)
        if body_y + (len(body_lines) * body_line_h) > 1090:
            body_font, body_lines = _fit_text(draw, body_text, regular_path, 850, 6, 40, 30)
            body_line_h = int(body_font.size * 1.43)
        if body_y + (len(body_lines) * body_line_h) > 1115:
            body_y = 1100 - (len(body_lines) * body_line_h)
        for line in body_lines:
            draw.text((82, body_y), line, font=body_font, fill=muted)
            body_y += body_line_h
        # Bottom navigation bar + branded signature.
        draw.rounded_rectangle((82, 1190, 998, 1198), radius=4, fill=(74, 69, 60))
        draw.rounded_rectangle((82, 1190, 82 + int(916 * idx / 5), 1198), radius=4, fill=amber)
        footer_font = ImageFont.truetype(latin_regular_path, size=22)
        draw.text((82, 1225), "ONE IDEA TO KEEP" if idx < 5 else "A SMALL STEP. A CLEARER CHOICE.", font=footer_font, fill=amber)
        draw.text((82, 1262), "BINA SHOR KE  ·  ORIGINAL HINDI CONTENT", font=small_font, fill=(136, 132, 124))
        dest = out_dir / f"slide_{idx:02d}.png"
        image.save(dest, format="PNG", optimize=True)
        slide_paths.append(dest)

    hashtags = " ".join(carousel["hashtags"][:5])
    caption = f"{carousel['caption'].strip()}\n\n{hashtags}".strip()
    kit_lines = [
        "BINA SHOR KE — CAROUSEL PUBLISH KIT",
        "=" * 38,
        f"TITLE: {carousel['title']}",
        f"PLANNED TEST SLOT: {slot.strftime('%A %d %B %Y, %I:%M %p IST')}",
        "FORMAT: 5-image Facebook photo post. Upload images in slide_01 to slide_05 order.",
        "",
        "CAPTION (copy/paste):",
        caption,
        "",
        f"AUDIENCE HYPOTHESIS: {carousel.get('audience_reason', 'Evaluate saves, shares and profile visits using Page Insights.')}",
        f"EDITORIAL REVIEW: {json.dumps(carousel.get('editorial_review', {}), ensure_ascii=False, indent=2)}",
        "",
        "SLIDE COPY:",
    ]
    for i, slide in enumerate(carousel["slides"], start=1):
        kit_lines.append(f"\nSLIDE {i}\n{slide['headline']}\n{slide['body']}\nPurpose: {slide['purpose']}")
    kit_path = out_dir / "carousel_publish.txt"
    kit_path.write_text("\n".join(kit_lines) + "\n", encoding="utf-8")
    return {"out_dir": out_dir, "slide_paths": slide_paths, "kit_path": kit_path, "caption": caption}


def load_telegram_state() -> dict[str, Any]:
    defaults: dict[str, Any] = {"owner_chat_id": None, "last_update_id": 0}
    if not TELEGRAM_STATE_PATH.exists():
        return defaults.copy()
    try:
        state = json.loads(TELEGRAM_STATE_PATH.read_text(encoding="utf-8"))
        return {**defaults, **state}
    except (json.JSONDecodeError, OSError):
        log("WARNING: telegram_state.json invalid; refusing to guess the private chat. Re-enrol by repairing this state file.")
        return defaults.copy()


def save_telegram_state(state: dict[str, Any]) -> None:
    """Atomically persist the Telegram update cursor to avoid reprocessing/losing updates."""
    TELEGRAM_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = TELEGRAM_STATE_PATH.with_suffix(TELEGRAM_STATE_PATH.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(TELEGRAM_STATE_PATH)


def telegram_get_updates(offset: int | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": 100, "timeout": 0, "allowed_updates": json.dumps(["message"])}
    if offset is not None:
        params["offset"] = offset
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    response = requests.get(url, params=params, timeout=25)
    response.raise_for_status()
    body = response.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram getUpdates failed: {body}")
    return body.get("result", [])


def telegram_chat_id() -> str:
    """Bind delivery to one private /start chat; never retarget to an arbitrary sender."""
    state = load_telegram_state()
    pinned_env = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if pinned_env:
        if state.get("owner_chat_id") and str(state["owner_chat_id"]) != pinned_env:
            raise RuntimeError("TELEGRAM_CHAT_ID does not match the already pinned Telegram owner. Remove the optional secret or reset telegram_state.json deliberately.")
        state["owner_chat_id"] = pinned_env
        save_telegram_state(state)
        return pinned_env
    if state.get("owner_chat_id"):
        return str(state["owner_chat_id"])
    updates = telegram_get_updates()
    starts = []
    for update in updates:
        message = update.get("message", {})
        chat = message.get("chat", {})
        text_value = str(message.get("text", "")).strip()
        if chat.get("type") == "private" and text_value.split(maxsplit=1)[0:1] == ["/start"]:
            starts.append((int(update.get("update_id", 0)), str(chat.get("id"))))
    if not starts:
        raise RuntimeError("Telegram bot has no private /start event. Open your bot in Telegram and send /start, then rerun this workflow.")
    # Only an explicit /start can enrol the owner; save the exact update cursor so later /insights messages are retained.
    update_id, owner_chat_id = starts[-1]
    state["owner_chat_id"] = owner_chat_id
    state["last_update_id"] = update_id
    save_telegram_state(state)
    log("Telegram owner chat pinned from private /start. Other chats will be ignored.")
    return owner_chat_id


def _parse_insights_message(message_text: str, history: dict[str, Any], update_id: int | None = None) -> dict[str, Any] | None:
    """Parse a compact `/insights key=value; ...` manual Meta Insights record."""
    text_value = message_text.strip()
    if not text_value.lower().startswith("/insights"):
        return None
    payload = text_value[len("/insights"):].strip()
    pairs = re.findall(r"([a-zA-Z_]+)\s*=\s*([^;|\n]+)", payload)
    values = {key.lower().strip(): value.strip() for key, value in pairs}
    if not values:
        raise ValueError("No key=value fields found.")

    title = values.get("title", "").strip()
    pillar_raw = values.get("pillar", "").lower().replace("-", "_").replace(" ", "_")
    pillar_aliases = {
        "story": "micro_story", "microstory": "micro_story", "micro_story": "micro_story",
        "cinematic": "cinematic_moment", "moment": "cinematic_moment", "cinematic_moment": "cinematic_moment",
        "lifestyle": "everyday_insight", "useful_lifestyle": "everyday_insight", "everyday_insight": "everyday_insight",
    }
    pillar = pillar_aliases.get(pillar_raw, pillar_raw)
    if not pillar and title:
        normalized_title = normalize_for_similarity(title)
        for old in reversed(history.get("topics", [])):
            if normalize_for_similarity(str(old.get("title", ""))) == normalized_title:
                pillar = str(old.get("pillar", ""))
                break
    if not title or pillar not in PILLAR_LABELS:
        raise ValueError("title and pillar=micro_story|cinematic_moment|everyday_insight are required.")

    def numeric(keys: tuple[str, ...], integer: bool = False) -> int | float | None:
        raw = next((values[k] for k in keys if k in values), None)
        if raw is None or not raw.strip():
            return None
        raw = raw.strip().replace(",", "").replace("%", "")
        number = float(raw)
        if number < 0:
            raise ValueError(f"{keys[0]} cannot be negative.")
        return int(number) if integer else number

    views = numeric(("views", "views24h", "views_24h"), integer=True)
    if views is None or views <= 0:
        raise ValueError("views must be a positive number. Enter the 24-hour Reel views for consistent comparison.")
    matching_topics = [topic for topic in history.get("topics", []) if normalize_for_similarity(str(topic.get("title", ""))) == normalize_for_similarity(title)]
    matched_topic = matching_topics[-1] if matching_topics else {}
    planned_publish_at = matched_topic.get("planned_publish_at")
    actual_publish_at = matched_topic.get("published_at_ist")
    comparison_time = actual_publish_at or planned_publish_at
    post_window = "unknown"
    planned_hour = None
    if comparison_time:
        try:
            planned_dt = datetime.fromisoformat(str(comparison_time))
            planned_hour = planned_dt.hour
            post_window = "midday" if planned_hour < 16 else "evening"
        except (ValueError, TypeError):
            comparison_time = None
    record = {
        "title": title[:160], "pillar": pillar, "views_24h": views,
        "planned_publish_at": planned_publish_at, "actual_publish_at": actual_publish_at,
        "planned_post_hour": planned_hour, "post_window": post_window,
        "reach": numeric(("reach",), integer=True),
        "average_watch_time_seconds": numeric(("watch", "avg_watch", "average_watch_time", "average_watch_time_seconds")),
        "completion_rate_percent": numeric(("completion", "complete", "completion_rate", "completion_rate_percent")),
        "shares": numeric(("shares",), integer=True), "saves": numeric(("saves",), integer=True),
        "comments": numeric(("comments",), integer=True),
        "profile_visits": numeric(("visits", "profile_visits"), integer=True),
        "new_follows": numeric(("follows", "new_follows"), integer=True),
        "observed_at_ist": datetime.now(TZ).isoformat(timespec="seconds"),
        "source": "manual_meta_insights",
        "telegram_update_id": update_id,
    }
    record["new_follows_per_1000_views"] = round(record["new_follows"] / views * 1000, 3) if record["new_follows"] is not None else None
    if record["completion_rate_percent"] is not None and record["completion_rate_percent"] > 100:
        raise ValueError("completion must be a percent between 0 and 100.")
    return record


def _parse_published_message(message_text: str, history: dict[str, Any]) -> dict[str, Any] | None:
    """Mark one generated topic as manually published after an owner-confirmed Facebook upload."""
    text_value = message_text.strip()
    if not text_value.lower().startswith("/published"):
        return None
    payload = text_value[len("/published"):].strip()
    pairs = re.findall(r"([a-zA-Z_]+)\s*=\s*([^;|\n]+)", payload)
    values = {key.lower().strip(): value.strip() for key, value in pairs}
    title = values.get("title", "").strip()
    if not title:
        raise ValueError("Add the Reel title: /published title=Exact Reel Title; url=https://facebook.com/...")
    target = normalize_for_similarity(title)
    matches = [item for item in history.get("topics", []) if normalize_for_similarity(str(item.get("title", ""))) == target]
    if not matches:
        raise ValueError("This title was not found in the factory history. Use the exact title from the Telegram publish kit.")
    topic = matches[-1]
    if topic.get("status") == "published_manual_confirmed":
        return {"title": topic.get("title", title), "already_published": True, "published_at_ist": topic.get("published_at_ist")}
    topic["status"] = "published_manual_confirmed"
    topic["published_at_ist"] = datetime.now(TZ).isoformat(timespec="seconds")
    if values.get("url", "").startswith(("https://", "http://")):
        topic["facebook_post_url"] = values["url"][:500]
    topic["publication_confirmation_source"] = "owner_telegram_command"
    return {"title": topic.get("title", title), "already_published": False, "published_at_ist": topic["published_at_ist"]}


def _parse_review_message(message_text: str, history: dict[str, Any], approved: bool) -> dict[str, Any] | None:
    """Record the owner's final review decision; it never publishes to Facebook."""
    command = "/approve" if approved else "/reject"
    if not message_text.strip().lower().startswith(command):
        return None
    payload = message_text.strip()[len(command):].strip()
    pairs = re.findall(r"([a-zA-Z_]+)\s*=\s*([^;|\n]+)", payload)
    values = {key.lower().strip(): value.strip() for key, value in pairs}
    title = values.get("title", "").strip()
    if not title:
        raise ValueError(f"Add the exact title from the publish kit: {command} title=Exact Reel Title")
    target = normalize_for_similarity(title)
    matches = [item for item in history.get("topics", []) if normalize_for_similarity(str(item.get("title", ""))) == target]
    if not matches:
        raise ValueError("This title was not found in factory history. Copy the exact title from the Telegram publish kit.")
    topic = matches[-1]
    if topic.get("status") == "published_manual_confirmed":
        raise ValueError("This Reel is already marked published; its publication record cannot be overwritten by review status.")
    decision = "owner_approved_for_manual_publish" if approved else "owner_rejected_not_published"
    was_already_recorded = topic.get("status") == decision
    if not was_already_recorded:
        topic["status"] = decision
        topic["reviewed_at_ist"] = datetime.now(TZ).isoformat(timespec="seconds")
        topic["review_source"] = "owner_private_telegram_command"
        if not approved and values.get("reason"):
            topic["owner_rejection_reason"] = values["reason"][:500]

    qualification_created = False
    if (
        approved
        and topic.get("qa_passed") is True
        and topic.get("visual_qa_status") == "reviewed"
        and topic.get("motion_diagnostics_status") == "passed"
        and topic.get("metadata_ocr_status") == "passed"
        and topic.get("telegram_delivered") is True
        and topic.get("reel_id")
    ):
        current = history.get("one_reel_qualification")
        candidate = {
            "status": "qualified",
            "reel_id": str(topic["reel_id"]),
            "job_id": str(topic.get("job_id") or ""),
            "title": str(topic.get("title", title)),
            "qa_passed": True,
            "visual_qa_status": "reviewed",
            "motion_diagnostics_status": "passed",
            "metadata_ocr_status": "passed",
            "telegram_delivered": True,
            "owner_approved": True,
            "approved_at_ist": topic.get("reviewed_at_ist") or datetime.now(TZ).isoformat(timespec="seconds"),
            "review_source": "owner_private_telegram_command",
        }
        # Do not downgrade or replace a qualification with a weaker record.
        if current != candidate:
            history["one_reel_qualification"] = candidate
            qualification_created = True

    if was_already_recorded and not qualification_created:
        return {"title": topic.get("title", title), "already_recorded": True, "approved": approved}
    return {
        "title": topic.get("title", title),
        "already_recorded": False,
        "approved": approved,
        "weekly_qualification_created": qualification_created,
    }


def append_performance_csv(record: dict[str, Any]) -> None:
    PERFORMANCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fields = ["observed_at_ist", "title", "pillar", "views_24h", "reach", "average_watch_time_seconds", "completion_rate_percent", "shares", "saves", "comments", "profile_visits", "new_follows", "new_follows_per_1000_views", "source"]
    file_exists = PERFORMANCE_PATH.exists() and PERFORMANCE_PATH.stat().st_size > 0
    with PERFORMANCE_PATH.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(record)


def process_telegram_feedback(history: dict[str, Any]) -> int:
    """Read only the pinned owner's private /insights and /published messages."""
    chat_id = telegram_chat_id()
    state = load_telegram_state()
    offset = int(state.get("last_update_id", 0)) + 1
    updates = telegram_get_updates(offset=offset)
    highest = int(state.get("last_update_id", 0))
    accepted_insights = 0
    history_changed = False
    for update in updates:
        update_id = int(update.get("update_id", 0))
        highest = max(highest, update_id)
        message = update.get("message", {})
        chat = message.get("chat", {})
        if str(chat.get("id", "")) != str(chat_id) or chat.get("type") != "private":
            continue
        text_value = str(message.get("text", "")).strip()
        if text_value == "/start" or text_value.startswith("/start "):
            telegram_post("sendMessage", data={"chat_id": chat_id, "text": "BINA SHOR KE Studio linked. After the final Reel review use /approve title=Exact Title or /reject title=Exact Title; after a Facebook upload use /published title=Exact Title; after about 24h use /insights. Approval only marks your review decision; it never publishes automatically."}, timeout=25)
            continue
        if text_value.lower().startswith("/approve") or text_value.lower().startswith("/reject"):
            approved = text_value.lower().startswith("/approve")
            try:
                record = _parse_review_message(text_value, history, approved=approved)
                if record:
                    history_changed = not record.get("already_recorded", False) or history_changed
                    if record.get("already_recorded"):
                        reply = "ℹ️ Review decision already recorded for: " + record["title"]
                    elif approved:
                        reply = "✅ Approved for your manual Facebook upload: " + record["title"] + "\nThe factory only records your approval; it does not publish."
                    else:
                        reply = "⛔ Marked not to publish: " + record["title"] + "\nThis Reel stays rejected; create a fresh concept instead of posting it."
                    telegram_post("sendMessage", data={"chat_id": chat_id, "text": reply}, timeout=25)
            except Exception as exc:
                telegram_post("sendMessage", data={"chat_id": chat_id, "text": "⚠️ Review decision not saved: " + str(exc)[:700]}, timeout=25)
            continue
        if text_value.lower().startswith("/published"):
            try:
                record = _parse_published_message(text_value, history)
                if record:
                    history_changed = not record.get("already_published", False) or history_changed
                    status_line = "was already marked published" if record.get("already_published") else "marked as manually published"
                    telegram_post("sendMessage", data={"chat_id": chat_id, "text": f"✅ {record['title']} {status_line}.\nThis only updates the private project log; the factory never publishes to Facebook."}, timeout=25)
            except Exception as exc:
                telegram_post("sendMessage", data={"chat_id": chat_id, "text": "⚠️ Publication record not saved: " + str(exc)[:800] + "\nExample: /published title=Exact Reel Title; url=https://facebook.com/..."}, timeout=25)
            continue
        if not text_value.lower().startswith("/insights"):
            continue
        try:
            # The GitHub workflow may retry after a transient git/network failure.
            # Telegram update IDs prevent the same command being added twice.
            already_seen = any(
                isinstance(row, dict) and row.get("telegram_update_id") == update_id
                for row in history.get("performance", [])
            )
            if already_seen:
                telegram_post("sendMessage", data={"chat_id": chat_id, "text": "ℹ️ यह Insights update पहले ही save हो चुका है; duplicate entry नहीं बनाई गई।"}, timeout=25)
                continue
            record = _parse_insights_message(text_value, history, update_id=update_id)
            if record is None:
                continue
            history.setdefault("performance", []).append(record)
            history["performance"] = history["performance"][-200:]
            append_performance_csv(record)
            accepted_insights += 1
            history_changed = True
            telegram_post("sendMessage", data={"chat_id": chat_id, "text": f"✅ Insights saved for: {record['title']}\nPillar: {record['pillar']}\nFollows/1,000 views: {record['new_follows_per_1000_views']}\nThis data will inform future concepts after the next scheduled/manual run. It is a weak signal, not a viral prediction."}, timeout=25)
        except Exception as exc:
            telegram_post("sendMessage", data={"chat_id": chat_id, "text": "⚠️ Insights not saved: " + str(exc)[:800] + "\nUse /insights title=Your Reel Title; pillar=micro_story; views=1200; reach=900; watch=8.2; completion=24; shares=11; saves=6; comments=3; visits=18; follows=5"}, timeout=25)
    state["last_update_id"] = highest
    save_telegram_state(state)
    if history_changed:
        save_history(history)
    if accepted_insights:
        log(f"Saved {accepted_insights} owner-submitted insights record(s).")
    return accepted_insights

def telegram_post(method: str, data: dict[str, Any] | None = None, files: dict[str, Any] | None = None, timeout: int = 180) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    response = requests.post(url, data=data or {}, files=files, timeout=timeout)
    if not response.ok:
        raise RuntimeError(f"Telegram {method} failed (HTTP {response.status_code}): {response.text[:500]}")
    body = response.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram {method} reported failure: {body}")
    return body


def safe_caption(concept: dict[str, Any]) -> str:
    tags = " ".join(concept["hashtags"][:5])
    caption = concept["caption"].strip()
    # Label fiction-led posts only; don't mislabel useful lifestyle advice as fiction.
    if concept.get("pillar") in {"micro_story", "cinematic_moment"}:
        caption = f"{caption}\n\nकहानी काल्पनिक है।"
    return f"{caption}\n\n{tags}".strip()


def build_credits_text(concept: dict[str, Any], credits: list[dict[str, Any]], reel_dir: Path) -> str:
    lines = [
        f"BINA SHOR KE — {concept['title']}",
        "Primary visual source: original AI-generated scenes produced by the open-weight Wan2.2 TI2V-5B model; verify the current model/quantization licence notice in the project docs before commercial use.",
    ]
    if credits:
        lines.extend([
            "Optional third-party support shots: Pexels (free stock footage; check current terms before reuse).",
            "Please credit contributors when practical. Suggested first comment:",
        ])
        used = set()
        for item in credits:
            key = (item.get("creator", ""), item.get("creator_url", ""))
            if key in used:
                continue
            used.add(key)
            lines.append(f"• {item.get('creator', 'Pexels contributor')} — {item.get('video_url', 'https://www.pexels.com')} — Creator: {item.get('creator_url', 'https://www.pexels.com')}")
        lines.append("Pexels: https://www.pexels.com")
    else:
        lines.append("No third-party stock shots were used in this Reel.")
    content = "\n".join(lines) + "\n"
    (reel_dir / "credits.txt").write_text(content, encoding="utf-8")
    return content



def director_10k_readiness(concept: dict[str, Any], build: dict[str, Any]) -> dict[str, Any]:
    """Editorial readiness rubric for a 10k-view ambition; never a view forecast."""
    review = concept.get("editorial_review", {})
    scores = review.get("scores", {}) if isinstance(review, dict) else {}
    weights = {
        "hook_clarity": 12, "story_progression": 10, "payoff": 10,
        "originality": 10, "creative_contribution_beyond_stock": 8,
        "share_value": 8, "human_specificity": 9, "emotional_resonance": 9,
        "illustrated_visual_quality": 7, "continuity_coherence": 5,
        "voiceover_rhythm": 4, "readability": 3, "platform_safety": 5,
    }
    available = [(key, weight, scores.get(key)) for key, weight in weights.items()]
    missing = [key for key, _, value in available if not isinstance(value, (int, float)) or not 1 <= float(value) <= 5]
    if missing:
        return {"score": None, "band": "NOT_RATED", "missing_dimensions": missing,
                "meaning": "Insufficient valid editorial scores; this is not a prediction of views.",
                "10k_view_probability": None}
    score = sum((float(value) / 5.0) * weight for _, weight, value in available)
    technical = build.get("technical", {}) if isinstance(build, dict) else {}
    tech_ok = bool(technical.get("technical_checks_passed", technical.get("passed", technical.get("status") == "PASS")))
    visual = technical.get("rendered_frame_visual_qa", build.get("visual_qa", {})) if isinstance(build, dict) else {}
    visual_ok = visual.get("status") in {"reviewed", "PASS"}
    if not tech_ok:
        band = "BLOCKED_TECHNICAL_QA"
    elif score >= 88 and visual_ok:
        band = "STRONG_EDITORIAL_CANDIDATE"
    elif score >= 78:
        band = "PROMISING_BUT_REVIEW"
    else:
        band = "REVISE_BEFORE_PUBLISH"
    return {
        "score": round(score, 1), "band": band,
        "dimensions": {key: round(float(value), 1) for key, _, value in available},
        "technical_gate_passed": tech_ok, "visual_frame_review_passed": visual_ok,
        "10k_view_probability": None,
        "meaning": "A 0-100 editorial readiness index against a 10k-view ambition, not a probability, reach estimate, algorithm score, or guarantee. Real distribution depends on audience matching and actual viewer response.",
        "human_director_verdict_required": True,
    }

def write_pack(concept: dict[str, Any], build: dict[str, Any], reel_dir: Path, slot: datetime) -> dict[str, Any]:
    caption = safe_caption(concept)
    credits_text = build_credits_text(concept, build["credits"], reel_dir)
    readiness = director_10k_readiness(concept, build)
    quality = {
        "brand": "BINA SHOR KE",
        "director_10k_readiness": readiness,
        "title": concept["title"],
        "pillar": concept["pillar"],
        "theme": concept["theme"],
        "narrative_engine": concept.get("narrative_engine", "not supplied"),
        "emotional_aftertaste": concept.get("emotional_aftertaste", "not supplied"),
        "human_detail": concept.get("human_detail", "not supplied"),
        "character_contradiction": concept.get("character_contradiction", "not supplied"),
        "cost_of_choice": concept.get("cost_of_choice", "not supplied"),
        "planned_publish_at": slot.isoformat(),
        "planned_publish_label": slot.strftime("%A %d %B %Y, %I:%M %p IST"),
        "editorial_review": concept.get("editorial_review", {}),
        "technical_qa": build["technical"],
        "ai_voiceover": True,
        "original_sound_design": "Locally synthesized subtle tonal ambience; no downloaded music or sound-effect library.",
        "fiction_disclosure": concept.get("pillar") in {"micro_story", "cinematic_moment"},
        "visual_credits": build["credits"],
        "creative_contribution_notes": "Original Hindi script, scene-specific model prompts, separately generated story beats, curated shot sequencing, original editorial overlays, branded subtitles, sound pacing and human review. AI generation alone is not proof of platform originality; the editorial narrative and final result must add meaningful creative value.",
        "platform_eligibility_note": "Production safeguards can reduce low-value/reuse risk but cannot guarantee Meta recommendations or monetization eligibility.",
        "status": "READY_FOR_HUMAN_FINAL_CHECK; NOT PUBLISHED",
    }
    storyboard_lines = []
    for beat_i, beat in enumerate(concept["beats"], start=1):
        storyboard_lines.append(
            f"BEAT {beat_i}\n"
            f"Voice-over: {beat['voiceover']}\n"
            f"Voice direction: {beat.get('voice_direction', 'Natural, calm, restrained Hindi narration.')}\n"
            f"On-screen text: {beat['screen_text']}\n"
            f"Visual query: {beat['visual_query']}\n"
            f"Visual purpose: {beat['visual_direction']}\n"
            f"AI video prompt: {beat.get('video_prompt', '')}\n"
            f"Original overlay: [{beat.get('overlay_type', 'keyword')}] {beat.get('overlay_text', '')}\n"
        )
    (reel_dir / "publish.txt").write_text(
        f"BINA SHOR KE — PUBLISH KIT\n{'='*36}\n\n"
        f"TITLE: {concept['title']}\nSERIES: {concept.get('series_name', SERIES_BY_PILLAR.get(concept['pillar'], 'BINA SHOR KE'))}\nPILLAR: {PILLAR_LABELS.get(concept['pillar'], concept['pillar'])}\n"
        f"POSTING TEST SLOT: {slot.strftime('%A %d %B %Y, %I:%M %p IST')}\n\n"
        f"CAPTION (copy/paste):\n{caption}\n\n"
        f"COVER TEXT: {concept['cover_text']}\nHOOK: {concept['hook']}\n"
        f"TARGET AUDIENCE HYPOTHESIS: {concept.get('audience_reason', 'Test audience response using actual Page insights.')}\n"
        f"WHY THIS IS THE TEST: {concept.get('posting_note', 'Compare watch time, shares and follows.') }\n"
        f"NATURAL SHARE VALUE: {concept.get('share_reason', 'Test whether the human insight feels relevant enough to share naturally.')}\n"
        f"NARRATIVE DEVICE: {concept.get('narrative_engine', 'Not supplied')}\n"
        f"EMOTIONAL AFTERTASTE: {concept.get('emotional_aftertaste', 'Not supplied')}\n"
        f"HUMAN DETAIL: {concept.get('human_detail', 'Not supplied')}\n"
        f"CHARACTER CONTRADICTION: {concept.get('character_contradiction', 'Not supplied')}\n"
        f"COST OF CHOICE: {concept.get('cost_of_choice', 'Not supplied')}\n\n"
        f"SCRIPT + SHOT-BY-SHOT STORYBOARD\n{'-'*36}\n" + "\n".join(storyboard_lines) + "\n"
        f"AI EDITORIAL REVIEW: {json.dumps(concept.get('editorial_review', {}), ensure_ascii=False, indent=2)}\n\n"
        f"DIRECTOR 10K-AMBITION READINESS (NOT A VIEW PREDICTION): {json.dumps(readiness, ensure_ascii=False, indent=2)}\n\n"
        f"TECHNICAL + RENDERED-FRAME QA: {json.dumps(build['technical'], ensure_ascii=False, indent=2)}\n\n"
        f"VISUAL CREDIT NOTES:\n{credits_text}\n\n"
        "FINAL REVIEW (one-time owner decision; no editing expected unless QA flags a defect):\n"
        f"/approve title={concept['title']}\n"
        f"/reject title={concept['title']}; reason=brief reason\n"
        "Approval records your decision only; publish manually to Facebook, then send /published.\n\n"
        "OPTIONAL METRICS FEEDBACK (send to the connected Telegram bot after about 24 hours; missing fields stay unknown and are not treated as zero):\n"
        f"/insights title={concept['title']}; pillar={concept['pillar']}; views=1200; reach=900; watch=8.2; completion=24; shares=11; saves=6; comments=3; visits=18; follows=5\n"
        "Replace the example numbers with the actual Reel insights. This record is processed at the next scheduled/manual run.\n",
        encoding="utf-8",
    )
    (reel_dir / "quality_report.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    concept["final_caption"] = caption
    return quality


def send_to_telegram(
    concept: dict[str, Any], build: dict[str, Any], reel_dir: Path, slot: datetime,
    ordinal: int, total: int, progress: dict[str, Any] | None = None, on_progress=None,
) -> dict[str, Any]:
    """Deliver one Reel to the owner's pinned private chat, checkpointing each successful step."""
    chat_id = telegram_chat_id()
    title = concept["title"][:180]
    video_path = build["video_path"]
    steps = dict(progress or {})

    def checkpoint(step: str):
        steps[step] = True
        if callable(on_progress):
            on_progress(dict(steps))

    if not steps.get("video"):
        with video_path.open("rb") as handle:
            telegram_post("sendVideo", data={
                "chat_id": chat_id,
                "supports_streaming": "true",
                "caption": f"BINA SHOR KE | Reel {ordinal}/{total}\n{title}\n\nREADY TO REVIEW — NOT PUBLISHED",
            }, files={"video": (video_path.name, handle, "video/mp4")}, timeout=240)
        checkpoint("video")

    if not steps.get("cover"):
        with build["cover_path"].open("rb") as handle:
            telegram_post("sendPhoto", data={"chat_id": chat_id, "caption": f"Cover: {title}\nTest slot: {slot.strftime('%a %d %b, %I:%M %p IST')}"}, files={"photo": (build["cover_path"].name, handle, "image/png")}, timeout=90)
        checkpoint("cover")

    if not steps.get("message"):
        caption_message = (
            f"📌 CAPTION — copy/paste\n\n{safe_caption(concept)}\n\n"
            f"🕒 Proposed test slot: {slot.strftime('%A %d %B, %I:%M %p IST')}\n"
            f"🎯 Hypothesis: {concept.get('posting_note', 'Compare watch time, shares and follows.') }\n"
            f"✅ Technical QA: {build['technical']['duration_seconds']} sec | 1080×1920 | {build['technical']['file_size_mb']} MB\n"
            f"🗣 Hindi ASR check: {build['technical'].get('local_hindi_asr_transcript_qa', {}).get('status', 'not available')} | "
            f"CER: {build['technical'].get('local_hindi_asr_transcript_qa', {}).get('character_error_rate', 'n/a')}\n"
            f"🎞 Full-video scan: {build['technical'].get('rendered_frame_visual_qa', {}).get('full_video_motion_diagnostics', {}).get('status', 'not available')}\n"
            "🧾 Visual credits: open publish.txt; paste the suggested Pexels creator credit in the first comment where practical.\n"
            "🔎 Final check: watch once. If it passes, send /approve title=Exact Title; if not, send /reject title=Exact Title. No editing is expected unless the QA report flags a real defect.\n"
            "📤 After approval, upload manually to Facebook. The factory does not auto-publish.\n"
            "🤖 If Meta's current upload flow asks for AI disclosure for realistic synthetic media, disclose it accurately.\n"
            "📈 After 24h, use /insights in the connected private bot chat (format is in publish.txt) so next week's ideas can adapt."
        )
        telegram_post("sendMessage", data={"chat_id": chat_id, "text": caption_message[:4000], "disable_web_page_preview": "true"})
        checkpoint("message")

    if not steps.get("publish_kit"):
        kit = reel_dir / "publish.txt"
        with kit.open("rb") as handle:
            telegram_post("sendDocument", data={"chat_id": chat_id, "caption": "Caption, QA report and visual credits."}, files={"document": (kit.name, handle, "text/plain; charset=utf-8")}, timeout=90)
        checkpoint("publish_kit")
    return steps



def send_carousel_to_telegram(carousel: dict[str, Any], build: dict[str, Any], slot: datetime) -> None:
    """Send slide files as a Telegram album, with a separate copy-ready caption and kit."""
    from contextlib import ExitStack
    chat_id = telegram_chat_id()
    media = []
    with ExitStack() as stack:
        upload_files: dict[str, tuple[str, Any, str]] = {}
        for index, path in enumerate(build["slide_paths"], start=1):
            attach_name = f"slide_{index}"
            media_item: dict[str, Any] = {"type": "photo", "media": f"attach://{attach_name}"}
            if index == 1:
                media_item["caption"] = f"BINA SHOR KE — Carousel\n{carousel['title']}\nSlide order: 1 → 5"
            media.append(media_item)
            upload_files[attach_name] = (path.name, stack.enter_context(path.open("rb")), "image/png")
        telegram_post("sendMediaGroup", data={"chat_id": chat_id, "media": json.dumps(media, ensure_ascii=False)}, files=upload_files, timeout=180)

    message = (
        f"📚 CAROUSEL — publish as a 5-photo post\n\n{build['caption']}\n\n"
        f"🕒 Proposed test slot: {slot.strftime('%A %d %B, %I:%M %p IST')}\n"
        "Upload slides in numbered order. Please inspect Hindi typography and text fit once before publishing."
    )
    telegram_post("sendMessage", data={"chat_id": chat_id, "text": message[:4000], "disable_web_page_preview": "true"})
    with build["kit_path"].open("rb") as handle:
        telegram_post("sendDocument", data={"chat_id": chat_id, "caption": "Carousel caption and slide copy."}, files={"document": (build["kit_path"].name, handle, "text/plain; charset=utf-8")}, timeout=90)

def failure_alert(error: str) -> None:
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        chat_id = telegram_chat_id()
        message = "BINA SHOR KE Factory: a run failed. No Facebook post was published.\n\n" + error[:2500] + "\n\nOpen GitHub → Actions → failed run for details."
        telegram_post("sendMessage", data={"chat_id": chat_id, "text": message[:3900], "disable_web_page_preview": "true"}, timeout=25)
    except Exception as notify_error:
        log(f"Failure notification also failed: {notify_error}")



def self_test() -> int:
    """Offline render smoke test: no keys, no internet, no account billing."""
    missing = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool)]
    if missing:
        raise RuntimeError("Preflight needs system tools installed by the workflow: " + ", ".join(missing))
    OUT.mkdir(parents=True, exist_ok=True)
    smoke_video = OUT / "SMOKE_TEST_ONLY_DO_NOT_PUBLISH.mp4"
    ass_path = OUT / "preflight.ass"
    art_path = OUT / "preflight_original_scene.png"
    test_beat = {
        "screen_text": "हिंदी टेक्स्ट परीक्षण",
        "visual_query": "phone message notebook desk",
        "visual_direction": "An original fictional message scene with clear progression.",
        "overlay_type": "message",
        "overlay_text": "मौलिक संदर्भ",
    }
    create_original_scene_image(test_beat, 1, 5, art_path, clean_scene=True)
    write_ass(ass_path, "हिंदी टेक्स्ट परीक्षण\nकहानी की अगली कड़ी", 5.0,
              overlay_text="मौलिक संदर्भ", overlay_type="note", scene_index=1, scene_count=5)
    subtitles_filter = (
        "zoompan=z='min(zoom+0.00020,1.035)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30,"
        f"subtitles='{ass_path.as_posix()}':fontsdir={FONT_DIR}"
    )
    run_cmd([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", "30", "-i", str(art_path),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=48000",
        "-vf", subtitles_filter, "-t", "5", "-c:v", "libx264", "-preset", "ultrafast",
        "-crf", "28", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
        "-shortest", "-movflags", "+faststart", str(smoke_video),
    ], timeout=180)
    info = probe_media(smoke_video)
    duration = probe_duration(smoke_video)
    if info.get("width") != 1080 or info.get("height") != 1920 or not 4.5 <= duration <= 5.5:
        raise RuntimeError(f"Preflight render failed technical checks: {info}; duration={duration}")

    # Exercise the actual typography-first cover path too, still with no network/API use.
    cover_bg = OUT / "preflight_cover_background.png"
    create_cover_background(cover_bg, "एक अलग कहानी")
    cover_ass = OUT / "preflight_cover.ass"
    write_ass(cover_ass, "एक अलग कहानी", 1.0, is_cover=True)
    cover_smoke = OUT / "SMOKE_TEST_COVER_DO_NOT_PUBLISH.png"
    run_cmd(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(cover_bg),
             "-vf", f"subtitles='{cover_ass.as_posix()}':fontsdir={FONT_DIR}", "-frames:v", "1", str(cover_smoke)], timeout=90)
    with Image.open(cover_smoke) as cover_image:
        if cover_image.size != (1080, 1920):
            raise RuntimeError(f"Preflight cover render failed: unexpected dimensions {cover_image.size}")

    report = {
        "status": "PASS", "mode": "offline_preflight", "no_api_calls": True,
        "no_keys_required": True, "resolution": "1080x1920", "duration_seconds": round(duration, 2),
        "media": info, "cover_render": "PASS", "note": "Smoke-test Reel/cover are not publishable creator content.",
    }
    (OUT / "SMOKE_TEST_STATUS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "SMOKE_TEST_STATUS.txt").write_text("PASS: offline video render, Hindi subtitle filter, video/audio stream and dimensions verified. Do not publish the smoke-test file.\n", encoding="utf-8")
    log("OFFLINE PREFLIGHT PASSED. No API keys or network calls were used.")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and deliver BINA SHOR KE reels.")
    parser.add_argument("--batch", type=int, default=int(os.getenv("BATCH_SIZE", "1")), choices=[1, 2, 3], help="number of Reels to produce")
    parser.add_argument("--self-test", action="store_true", help="offline FFmpeg/Devanagari rendering test; uses no API keys")
    args = parser.parse_args()
    try:
        if args.self_test:
            return self_test()
        require_env()
        OUT.mkdir(parents=True, exist_ok=True)
        history = load_history()
        process_telegram_feedback(history)
        history = load_history()
        slots = next_post_slots(args.batch, rotation=int(history.get("generated_count", 0)) // 3, history=history)
        all_used_assets = set(str(x) for x in history.get("asset_ids", [])[-300:])
        generated_this_batch: list[dict[str, Any]] = []
        for index, slot in enumerate(slots):
            pillar = choose_pillar(history, 0)
            log(f"Starting Reel {index+1}/{args.batch}: pillar={pillar}; proposed slot={slot.isoformat()}")
            concept, _review = acquire_approved_concept(history, pillar, slot, index)
            stamp = datetime.now(TZ).strftime("%Y%m%d_%H%M")
            slug = re.sub(r"[^a-z0-9]+", "-", concept["title"].lower()).strip("-")[:36] or f"reel-{index+1}"
            reel_dir = OUT / f"{stamp}_{index+1}_{slug}"
            reel_dir.mkdir(parents=True, exist_ok=True)
            (reel_dir / "concept.json").write_text(json.dumps(concept, ensure_ascii=False, indent=2), encoding="utf-8")
            build = render_reel(concept, reel_dir, all_used_assets, all_used_assets)
            all_used_assets.update(build["asset_ids"])
            quality = write_pack(concept, build, reel_dir, slot)
            # Persist after each successfully rendered Reel. Workflow commits this file even if a later Reel fails.
            history.setdefault("topics", []).append({"title": concept["title"], "theme": concept["theme"], "pillar": pillar, "narrative_engine": concept.get("narrative_engine", ""), "emotional_aftertaste": concept.get("emotional_aftertaste", ""), "human_detail": concept.get("human_detail", ""), "generated_at": datetime.now(TZ).isoformat(timespec="seconds"), "planned_publish_at": slot.isoformat()})
            history["asset_ids"] = (history.get("asset_ids", []) + build["asset_ids"])[-600:]
            history["generated_count"] = int(history.get("generated_count", 0)) + 1
            save_history(history)
            send_to_telegram(concept, build, reel_dir, slot, index + 1, args.batch)
            generated_this_batch.append({"title": concept["title"], "directory": str(reel_dir.relative_to(ROOT)), "qa": quality})
            # Brief pause avoids hammering free-tier limits between reels.
            time.sleep(4)

        generated_carousel = None
        # A full weekly batch (3 Reels) also produces one 5-slide photo carousel.
        # Single-Reel manual runs stay fast for the first connection/API smoke test.
        if args.batch >= 3:
            carousel_slot = next_carousel_slot()
            log(f"Starting weekly carousel; proposed slot={carousel_slot.isoformat()}")
            carousel, _carousel_review = generate_carousel(history, carousel_slot)
            carousel_build = render_carousel(carousel, carousel_slot)
            history.setdefault("topics", []).append({
                "title": carousel["title"],
                "theme": carousel["theme"],
                "pillar": "carousel",
                "format": "photo_carousel",
                "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
                "planned_publish_at": carousel_slot.isoformat(),
            })
            history["carousel_count"] = int(history.get("carousel_count", 0)) + 1
            save_history(history)
            send_carousel_to_telegram(carousel, carousel_build, carousel_slot)
            generated_carousel = {
                "title": carousel["title"],
                "directory": str(carousel_build["out_dir"].relative_to(ROOT)),
                "planned_publish_label": carousel_slot.strftime("%a %d %b, %I:%M %p IST"),
                "editorial_review": carousel.get("editorial_review", {}),
            }

        summary_path = OUT / "weekly_summary.txt"
        lines = ["BINA SHOR KE — GENERATED CONTENT SUMMARY", f"Generated at: {datetime.now(TZ).isoformat(timespec='seconds')}", "", "No content has been automatically published to Facebook.", ""]
        for item in generated_this_batch:
            lines.append(f"• REEL: {item['title']} — {item['directory']} — QA: {item['qa']['status']} — slot: {item['qa']['planned_publish_label']}")
        if generated_carousel:
            lines.append(f"• CAROUSEL: {generated_carousel['title']} — {generated_carousel['directory']} — slot: {generated_carousel['planned_publish_label']}")
        summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log(f"Batch complete: {len(generated_this_batch)} Reel(s)" + (" plus 1 carousel" if generated_carousel else "") + " rendered and sent to Telegram.")
        return 0
    except Exception as exc:
        log(f"ERROR: {exc}")
        failure_alert(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
