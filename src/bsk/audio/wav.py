from __future__ import annotations

import wave
from pathlib import Path

from bsk.errors import GateError


def inspect_wav(path: Path) -> dict[str, float | int]:
    try:
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frames = wav.getnframes()
            duration = frames / float(sample_rate)
            if channels != 1 or sample_width != 2 or sample_rate != 24000:
                raise GateError(
                    f"Expected Gemini narration WAV as mono/16-bit/24kHz; got {channels}ch/{sample_width * 8}bit/{sample_rate}Hz."
                )
            if duration <= 0.5 or duration > 20 * 60:
                raise GateError(f"Narration duration is implausible: {duration:.2f} seconds.")
            return {
                "channels": channels,
                "sample_width_bytes": sample_width,
                "sample_rate_hz": sample_rate,
                "frames": frames,
                "duration_seconds": round(duration, 3),
            }
    except (wave.Error, EOFError, OSError) as exc:
        raise GateError(f"Audio is not a valid WAV file: {exc}") from exc
