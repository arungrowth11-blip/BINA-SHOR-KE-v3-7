from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from bsk.config import Settings, settings
from bsk.errors import ConfigurationError, GateError


def normalize_hindi_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).lower()
    text = re.sub(r"[^\w\u0900-\u097f]+", "", text, flags=re.UNICODE)
    return text


def character_error_rate(reference: str, hypothesis: str) -> float:
    ref = normalize_hindi_text(reference)
    hyp = normalize_hindi_text(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, char_ref in enumerate(ref, start=1):
        current = [i]
        for j, char_hyp in enumerate(hyp, start=1):
            current.append(min(
                current[j - 1] + 1,
                previous[j] + 1,
                previous[j - 1] + (char_ref != char_hyp),
            ))
        previous = current
    return previous[-1] / len(ref)


def transcribe_hindi(audio_path: Path, config: Settings = settings) -> dict[str, Any]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ConfigurationError(
            "Local ASR is not installed. Run: py -3.11 -m pip install -r requirements-asr.txt"
        ) from exc
    model = WhisperModel(config.asr_model, device=config.asr_device, compute_type=config.asr_compute_type)
    segments_iter, info = model.transcribe(
        str(audio_path), language="hi", beam_size=5, vad_filter=True, word_timestamps=True
    )
    segments: list[dict[str, Any]] = []
    transcript_parts: list[str] = []
    for segment in segments_iter:
        text = str(segment.text or "").strip()
        if not text:
            continue
        index = len(segments) + 1
        transcript_parts.append(text)
        words = []
        for word in (getattr(segment, "words", None) or []):
            words.append({
                "text": str(getattr(word, "word", "")).strip(),
                "start_seconds": round(float(getattr(word, "start", segment.start)), 3),
                "end_seconds": round(float(getattr(word, "end", segment.end)), 3),
            })
        segments.append({
            "segment_id": index,
            "start_seconds": round(float(segment.start), 3),
            "end_seconds": round(float(segment.end), 3),
            "text": text,
            "words": words,
        })
    if not segments:
        raise GateError("ASR returned no speech segments; audio alignment cannot continue.")
    return {
        "language": getattr(info, "language", "hi"),
        "language_probability": round(float(getattr(info, "language_probability", 0.0)), 4),
        "transcript_text": " ".join(transcript_parts),
        "segments": segments,
    }
