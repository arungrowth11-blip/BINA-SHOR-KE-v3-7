"""Deterministic, fail-closed recovery policy for BINA SHOR KE."""
from __future__ import annotations

import re

ACTIVE_KAGGLE_STATUSES = {"QUEUED", "RUNNING", "COMPILING", "CREATED"}
TERMINAL_KAGGLE_STATUSES = {"COMPLETE", "FAILED", "ERROR", "CANCELLED", "CANCELED"}
_INTEGRITY_OR_QA_MARKERS = (
    "voice cache mismatch", "voice cache is missing", "exact director-run voice cache is missing",
    "locked voice asset", "voice asset sha-256 mismatch", "voice asset is missing",
    "gpu output identity validation failed", "scene inventory count mismatch",
    "scene identities do not exactly match", "critical visual defect",
    "local visual fallback did not pass", "metadata ocr is", "full-video motion diagnostics are",
    "forbidden prompt labels", "true peak", "final audio qa", "technical qa did not pass",
    "excessive speed change", "too short", "black frame", "freeze defect",
)
_TRANSIENT_MARKERS = (
    "temporarily unavailable", "service unavailable", "connection reset", "connection aborted",
    "connection refused", "read timed out", "connect timeout", "request timed out",
    "deadline exceeded", "resource exhausted", "rate limit",
)


def normalize_kaggle_status(status: str) -> str:
    value = str(status or "").strip().upper()
    return value.rsplit(".", 1)[-1] if "." in value else value


def classify_finalization_failure(error: str) -> str:
    """Integrity/hard-QA errors outrank transient HTTP/provider markers."""
    text = str(error or "").lower()
    if any(marker in text for marker in _INTEGRITY_OR_QA_MARKERS):
        return "non_retryable_integrity_or_qa"
    if re.search(r"\b(?:429|500|502|503|504)\b", text) or any(
        marker in text for marker in _TRANSIENT_MARKERS
    ):
        return "transient_provider"
    return "non_retryable"


def finalization_retry_delay_seconds(completed_attempt: int) -> int | None:
    """Two bounded retries after the first attempt."""
    return {1: 30, 2: 90}.get(int(completed_attempt))


def exact_tts_cache_key(runner_os: str, planning_run_id: str, planning_run_attempt: int | str) -> str:
    run_id = str(planning_run_id or "").strip()
    if not run_id.isdigit():
        raise ValueError("A numeric Director workflow run ID is required for exact TTS cache restore.")
    attempt = int(planning_run_attempt)
    if attempt < 1:
        raise ValueError("Director workflow run attempt must be at least 1.")
    os_name = str(runner_os or "").strip()
    if not os_name or any(ch.isspace() for ch in os_name):
        raise ValueError("Runner OS is missing or invalid.")
    return f"bsk-tts-{os_name}-{run_id}-{attempt}"


def next_watch_action(status: str, *, chunk_elapsed_seconds: float,
                      total_elapsed_seconds: float, chunk_limit_seconds: float,
                      total_limit_seconds: float) -> str | None:
    normalized = normalize_kaggle_status(status)
    if normalized in ACTIVE_KAGGLE_STATUSES:
        if total_elapsed_seconds >= total_limit_seconds:
            return "stop"
        if chunk_elapsed_seconds >= chunk_limit_seconds:
            return "watch"
        return None
    if normalized in TERMINAL_KAGGLE_STATUSES:
        return "poll"
    return "stop"
