#!/usr/bin/env python3
"""Make two real Gemini Hindi TTS requests and qualify the returned WAV files.

This is an opt-in live API smoke test. It is deliberately separate from offline CI,
story planning, Kaggle/GPU dispatch, Blender, Telegram and Facebook delivery.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import os
import re
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import producer  # noqa: E402
import voice_first  # noqa: E402


SAMPLES = (
    {
        "sample_id": "arjun_young_male",
        "filename": "arjun_puck.wav",
        "profile_id": "hi_male_young_puck",
        "text": "मीरा, मैंने तुम्हारी बात सुनी थी। मैं बस सही जवाब सोच रहा था।",
        "direction": "Natural conversational Hindi; young adult masculine delivery, restrained and sincere.",
    },
    {
        "sample_id": "meera_older_female",
        "filename": "meera_gacrux.wav",
        "profile_id": "hi_female_older_gacrux",
        "text": "अर्जुन, हर जवाब तुरंत देना ज़रूरी नहीं होता। कभी-कभी ध्यान से सुनना भी काफ़ी है।",
        "direction": "Natural conversational Hindi; mature feminine delivery, calm, warm and gently assertive.",
    },
)


def inspect_wav(path: Path) -> dict[str, Any]:
    """Validate the production WAV contract and reject empty or effectively silent audio."""
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            frame_count = handle.getnframes()
            pcm = handle.readframes(frame_count)
    except (OSError, EOFError, wave.Error) as exc:
        raise ValueError(f"Invalid WAV file {path.name}: {exc}") from exc

    if channels != 1 or sample_width != 2 or sample_rate != 24000:
        raise ValueError(
            f"{path.name} must be 24 kHz, mono, 16-bit PCM; "
            f"received {sample_rate} Hz, {channels} channel(s), {sample_width * 8}-bit."
        )
    if frame_count <= 0 or len(pcm) != frame_count * sample_width:
        raise ValueError(f"{path.name} is empty or has a truncated PCM payload.")

    samples = array.array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        raise ValueError(f"{path.name} contains no PCM samples.")

    peak = max(abs(value) for value in samples)
    rms = math.sqrt(sum(value * value for value in samples) / len(samples))
    if peak < 128 or rms < 32:
        raise ValueError(
            f"{path.name} is effectively silent (peak={peak}, RMS={rms:.1f}); "
            "refusing to qualify it as generated speech."
        )

    return {
        "duration_seconds": round(frame_count / sample_rate, 4),
        "sample_rate_hz": sample_rate,
        "channels": channels,
        "sample_width_bits": sample_width * 8,
        "frames": frame_count,
        "peak_amplitude": peak,
        "rms_amplitude": round(rms, 2),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "file_size_bytes": path.stat().st_size,
        "machine_audio_checks": "passed",
    }


def safe_error(exc: Exception) -> str:
    message = str(exc)
    for secret in (producer.GEMINI_API_KEY, os.getenv("GEMINI_API_KEY", "")):
        if secret:
            message = message.replace(secret, "[REDACTED]")
    message = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED_API_KEY]", message)
    return f"{type(exc).__name__}: {message[:800]}"


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def run(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    model = str(producer.GEMINI_TTS_MODEL).strip()
    report: dict[str, Any] = {
        "system": "BINA SHOR KE live Gemini TTS qualification",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "api": "Gemini Developer API Interactions API",
        "model": model,
        "status": "in_progress",
        "samples_expected": len(SAMPLES),
        "samples_attempted": 0,
        "samples": [],
        "human_listening_review": "required_pending",
        "human_listening_checks": [
            "Hindi pronunciation and diction",
            "naturalness and conversational rhythm",
            "distinct identity between the two voices",
            "emotional direction and suitability for the characters",
            "absence of clipping, glitches, artefacts or unexpected language switching",
        ],
        "not_performed_by_this_workflow": [
            "human listening approval",
            "storyboard or video generation",
            "Kaggle GPU or Blender rendering",
            "Telegram delivery",
            "Facebook publishing",
        ],
        "paid_fallback_used": False,
    }

    if not producer.GEMINI_API_KEY:
        report["status"] = "blocked_missing_secret"
        report["error"] = "GEMINI_API_KEY is not configured in the GitHub Actions secrets."
        write_report(output_dir / "report.json", report)
        print(report["error"], file=sys.stderr, flush=True)
        return 2

    try:
        if not model:
            raise RuntimeError("GEMINI_TTS_MODEL is empty; refusing an unspecified model.")
        for sample in SAMPLES:
            profile = voice_first.resolve_voice_profile(sample["profile_id"])
            voice_name = profile["gemini_voice"]
            destination = output_dir / sample["filename"]
            destination.unlink(missing_ok=True)
            report["samples_attempted"] += 1

            print(
                f"REQUEST {sample['sample_id']} model={model} voice={voice_name}",
                flush=True,
            )
            # This is the repository's real HTTP/API adapter; no mock or fixture is used.
            # It has bounded retries and no paid-provider fallback.
            producer.tts_wav(
                sample["text"],
                destination,
                voice_direction=sample["direction"] + " " + profile["direction"],
                voice_name=voice_name,
            )
            metrics = inspect_wav(destination)
            report["samples"].append(
                {
                    "sample_id": sample["sample_id"],
                    "profile_id": sample["profile_id"],
                    "gemini_voice": voice_name,
                    "spoken_text": sample["text"],
                    **metrics,
                }
            )
            print(
                f"PASS {sample['sample_id']} duration={metrics['duration_seconds']:.2f}s "
                f"bytes={metrics['file_size_bytes']} sha256={metrics['sha256']}",
                flush=True,
            )

        report["status"] = "live_api_audio_generated_machine_checks_passed_human_review_pending"
        report["human_listening_review"] = "required_pending"
        write_report(output_dir / "report.json", report)
        print(
            "RESULT: both live TTS requests returned non-silent, format-valid WAV files. "
            "Human listening approval is still required.",
            flush=True,
        )
        return 0
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = safe_error(exc)
        report["human_listening_review"] = "not_started_or_incomplete"
        write_report(output_dir / "report.json", report)
        print(f"FAIL {report['error']}", file=sys.stderr, flush=True)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-free-tier-only",
        action="store_true",
        help="Confirm the selected Gemini project/key is Free Tier and paid billing is disabled.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "tts-smoke",
        help="Directory for the generated WAV samples and qualification report.",
    )
    args = parser.parse_args()
    if not args.confirm_free_tier_only:
        parser.error(
            "Live TTS is opt-in. Pass --confirm-free-tier-only only after confirming "
            "the Gemini project/key is Free Tier with paid billing disabled."
        )
    return run(args.output_dir.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
