#!/usr/bin/env python3
"""Live, low-volume connectivity check for BINA SHOR KE's configured text providers.

This test calls each configured provider directly once (Gemini may perform its
existing bounded retries). It does not plan stories, dispatch Kaggle, or use TTS.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import producer  # noqa: E402


SYSTEM = (
    "You are an API connectivity test. Respond with one valid JSON object only. "
    "Do not include Markdown or any explanation."
)
PROMPT = 'Return exactly this JSON object: {"status":"ok"}'
EXPECTED = {"status": "ok"}


def _run_one(name: str, configured: bool, model: str, request):
    if not configured:
        print(f"MISSING {name}: required GitHub Secret is not available")
        return False
    print(f"CHECK {name} model={model}", flush=True)
    try:
        result = request(SYSTEM, PROMPT, temperature=0.0, timeout=30)
        if result != EXPECTED:
            print(f"FAIL {name}: response was valid JSON but did not match the smoke-test response")
            return False
        print(f"PASS {name}: authenticated request returned valid JSON", flush=True)
        return True
    except Exception as exc:  # Keep diagnostics useful without printing credentials.
        message = str(exc).replace(producer.GEMINI_API_KEY, "[REDACTED]") if producer.GEMINI_API_KEY else str(exc)
        message = message.replace(producer.GROQ_API_KEY, "[REDACTED]") if producer.GROQ_API_KEY else message
        message = message.replace(producer.MISTRAL_API_KEY, "[REDACTED]") if producer.MISTRAL_API_KEY else message
        print(f"FAIL {name}: {type(exc).__name__}: {message[:500]}", flush=True)
        return False


def main() -> int:
    print("BINA SHOR KE live text-provider connectivity test", flush=True)
    print("This test does not run story planning, TTS, video generation, or Kaggle.", flush=True)

    checks = [
        _run_one("Gemini", bool(producer.GEMINI_API_KEY), producer.GEMINI_TEXT_MODEL, producer.gemini_json),
        _run_one("Groq", bool(producer.GROQ_API_KEY), producer.GROQ_TEXT_MODEL, producer.groq_json),
        _run_one("Mistral", bool(producer.MISTRAL_API_KEY), producer.MISTRAL_TEXT_MODEL, producer.mistral_json),
    ]
    passed = sum(checks)
    total = len(checks)
    print(f"RESULT: {passed}/{total} providers passed", flush=True)
    if passed == total:
        print("All three text providers passed direct live API checks.", flush=True)
        return 0
    print("One or more providers failed. Do not start plan-one until the failed provider is understood.", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
