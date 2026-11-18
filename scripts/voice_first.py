"""Voice-first screenplay, speaker casting and duration planning for BINA SHOR KE.

This module intentionally uses only the Python standard library. Voice audio is generated
before GPU dispatch; this module never shortens dialogue to fit a pre-existing video clip.
"""
from __future__ import annotations

import json
import math
import re
import wave
from pathlib import Path
from typing import Any, Callable

FPS = 24
WAN_FRAME_MULTIPLE = 4
MIN_SCENE_SECONDS = 2.5
HEAD_HANDLE_SECONDS = 0.08
TAIL_HANDLE_SECONDS = 0.18
DEFAULT_DIALOGUE_GAP_SECONDS = 0.18

# Voice names are current Gemini prebuilt voice IDs. The profile direction controls
# perceived age/acting; a voice's display characteristic is not a guarantee of age.
VOICE_PROFILES: dict[str, dict[str, str]] = {
    "hi_narrator_kore": {
        "gemini_voice": "Kore",
        "direction": "Natural Hindi narrator; clear, grounded, restrained, conversational.",
    },
    "hi_male_young_puck": {
        "gemini_voice": "Puck",
        "direction": "Young adult masculine Hindi voice; natural, lively but not exaggerated.",
    },
    "hi_female_young_leda": {
        "gemini_voice": "Leda",
        "direction": "Young adult feminine Hindi voice; youthful, clear and emotionally natural.",
    },
    "hi_male_adult_charon": {
        "gemini_voice": "Charon",
        "direction": "Adult masculine Hindi voice; composed, conversational and measured.",
    },
    "hi_female_adult_aoede": {
        "gemini_voice": "Aoede",
        "direction": "Adult feminine Hindi voice; warm, conversational and expressive.",
    },
    "hi_male_older_algenib": {
        "gemini_voice": "Algenib",
        "direction": "Older masculine Hindi character; mature, slightly gravelly, slow but intelligible.",
    },
    "hi_female_older_gacrux": {
        "gemini_voice": "Gacrux",
        "direction": "Older feminine Hindi character; mature, warm and measured.",
    },
}
DEFAULT_VOICE_PROFILE_ID = "hi_narrator_kore"
_CHARACTER_ID = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")


def infer_voice_profile(gender_presentation: str, age_band: str) -> str:
    gender = str(gender_presentation or "").strip().lower()
    age = str(age_band or "").strip().lower()
    if gender not in {"male", "female"}:
        return DEFAULT_VOICE_PROFILE_ID
    if age in {"child", "young", "young_adult", "teen"}:
        return "hi_male_young_puck" if gender == "male" else "hi_female_young_leda"
    if age in {"older", "older_adult", "elder", "senior"}:
        return "hi_male_older_algenib" if gender == "male" else "hi_female_older_gacrux"
    return "hi_male_adult_charon" if gender == "male" else "hi_female_adult_aoede"


def resolve_voice_profile(profile_id: str) -> dict[str, str]:
    key = str(profile_id or DEFAULT_VOICE_PROFILE_ID).strip()
    if key not in VOICE_PROFILES:
        raise ValueError(f"Unknown voice_profile_id: {key}")
    return dict(VOICE_PROFILES[key])


def normalise_screenplay(concept: dict[str, Any]) -> dict[str, Any]:
    """Upgrade legacy single-narrator concepts and validate explicit multi-speaker scripts."""
    if not isinstance(concept, dict):
        raise ValueError("Screenplay must be a JSON object.")
    beats = concept.get("beats")
    if not isinstance(beats, list) or len(beats) != 6:
        raise ValueError("Voice-first screenplay must contain exactly six story beats.")

    characters = concept.get("characters")
    if not isinstance(characters, list) or not characters:
        characters = [{
            "character_id": "narrator",
            "display_name": "वाचक",
            "role": "narrator",
            "gender_presentation": "unspecified",
            "age_band": "adult",
            "appearance": "Voice-only narrator; no on-screen character identity implied.",
            "personality": "Grounded, observant, restrained.",
            "voice_profile_id": DEFAULT_VOICE_PROFILE_ID,
        }]
    clean_characters: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in characters:
        if not isinstance(raw, dict):
            raise ValueError("Each screenplay character must be an object.")
        char = dict(raw)
        char_id = str(char.get("character_id", "")).strip().lower()
        if not _CHARACTER_ID.fullmatch(char_id):
            raise ValueError(f"Invalid character_id: {char_id!r}")
        if char_id in seen:
            raise ValueError(f"Duplicate character_id: {char_id}")
        seen.add(char_id)
        char["character_id"] = char_id
        char["display_name"] = str(char.get("display_name") or char_id).strip()
        char["gender_presentation"] = str(char.get("gender_presentation") or "unspecified").lower()
        char["age_band"] = str(char.get("age_band") or "adult").lower()
        char["voice_profile_id"] = str(
            char.get("voice_profile_id") or infer_voice_profile(char["gender_presentation"], char["age_band"])
        )
        profile = resolve_voice_profile(char["voice_profile_id"])
        char["gemini_voice"] = profile["gemini_voice"]
        char["voice_direction"] = str(char.get("voice_direction") or profile["direction"])
        char["appearance"] = str(char.get("appearance") or "").strip()
        char["personality"] = str(char.get("personality") or "").strip()
        clean_characters.append(char)

    characters_by_id = {char["character_id"]: char for char in clean_characters}
    for beat_index, beat in enumerate(beats, start=1):
        if not isinstance(beat, dict):
            raise ValueError(f"Beat {beat_index} must be an object.")
        segments = beat.get("speech_segments")
        if segments is None:
            legacy_line = str(beat.get("voiceover") or "").strip()
            if not legacy_line:
                raise ValueError(f"Beat {beat_index} has neither voiceover nor speech_segments.")
            segments = [{
                "segment_id": f"beat_{beat_index:02d}_line_01",
                "speaker_id": "narrator" if "narrator" in characters_by_id else clean_characters[0]["character_id"],
                "text": legacy_line,
                "emotion": str(beat.get("voice_direction") or "natural, restrained delivery"),
            }]
        if not isinstance(segments, list):
            raise ValueError(f"Beat {beat_index} speech_segments must be a list.")
        normalised_segments = []
        for line_index, raw_segment in enumerate(segments, start=1):
            if not isinstance(raw_segment, dict):
                raise ValueError(f"Beat {beat_index} line {line_index} must be an object.")
            segment = dict(raw_segment)
            speaker_id = str(segment.get("speaker_id", "")).strip().lower()
            if speaker_id not in characters_by_id:
                raise ValueError(f"Beat {beat_index} references unknown speaker_id {speaker_id!r}.")
            text = str(segment.get("text") or "").strip()
            if not text:
                raise ValueError(f"Beat {beat_index} line {line_index} has empty speech text.")
            segment["segment_id"] = str(segment.get("segment_id") or f"beat_{beat_index:02d}_line_{line_index:02d}")
            segment["speaker_id"] = speaker_id
            segment["text"] = text
            segment["emotion"] = str(segment.get("emotion") or "natural, restrained delivery")
            speaker = characters_by_id[speaker_id]
            segment["voice_profile_id"] = speaker["voice_profile_id"]
            segment["gemini_voice"] = speaker["gemini_voice"]
            segment["voice_direction"] = speaker["voice_direction"]
            normalised_segments.append(segment)
        beat["speech_segments"] = normalised_segments
        # Compatibility field for existing subtitle, ASR and publish-kit code.
        beat["voiceover"] = " ".join(item["text"] for item in normalised_segments)
        beat.setdefault("voice_direction", "Natural Hindi; restrained and conversational.")
    concept["characters"] = clean_characters
    concept["screenplay_schema_version"] = 2
    return concept


def wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as handle:
            if handle.getnchannels() != 1 or handle.getsampwidth() != 2 or handle.getframerate() != 24000:
                raise ValueError(f"Voice WAV must be 24 kHz, mono, 16-bit PCM: {path}")
            frames = handle.getnframes()
            if frames <= 0:
                raise ValueError(f"Voice WAV is empty: {path}")
            return frames / float(handle.getframerate())
    except (OSError, EOFError, wave.Error) as exc:
        raise ValueError(f"Invalid voice WAV: {path}: {exc}") from exc


def frames_for_duration(duration_seconds: float, fps: int = FPS) -> int:
    """Round up to Wan's 4n+1 temporal frame shape; never truncate requested duration."""
    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, (int, float)):
        raise ValueError("duration_seconds must be numeric.")
    if not math.isfinite(float(duration_seconds)) or duration_seconds <= 0:
        raise ValueError("duration_seconds must be a finite positive number.")
    if isinstance(fps, bool) or not isinstance(fps, int) or fps <= 0:
        raise ValueError("fps must be a positive integer.")
    required = max(MIN_SCENE_SECONDS, float(duration_seconds))
    frame_count = max(1, math.ceil(required * fps))
    return ((frame_count - 1 + WAN_FRAME_MULTIPLE - 1) // WAN_FRAME_MULTIPLE) * WAN_FRAME_MULTIPLE + 1


def build_scene_timing_plan(
    segments: list[dict[str, Any]],
    durations: dict[str, float],
    *,
    dialogue_gap_seconds: float = DEFAULT_DIALOGUE_GAP_SECONDS,
    head_handle_seconds: float = HEAD_HANDLE_SECONDS,
    tail_handle_seconds: float = TAIL_HANDLE_SECONDS,
    fps: int = FPS,
) -> dict[str, Any]:
    """Create a word-preserving voice-led timeline from measured TTS WAV durations."""
    if dialogue_gap_seconds < 0 or head_handle_seconds < 0 or tail_handle_seconds < 0:
        raise ValueError("Timing handles and dialogue gap cannot be negative.")
    cursor = float(head_handle_seconds)
    placed = []
    for index, segment in enumerate(segments):
        segment_id = str(segment.get("segment_id", ""))
        if segment_id not in durations:
            raise ValueError(f"Missing measured audio duration for {segment_id!r}.")
        duration = float(durations[segment_id])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError(f"Invalid measured duration for {segment_id!r}: {duration}")
        start = cursor
        end = start + duration
        placed.append({
            "segment_id": segment_id,
            "speaker_id": str(segment.get("speaker_id", "")),
            "start_seconds": round(start, 4),
            "end_seconds": round(end, 4),
            "duration_seconds": round(duration, 4),
        })
        cursor = end + (dialogue_gap_seconds if index < len(segments) - 1 else 0.0)
    speech_end = cursor
    requested = max(MIN_SCENE_SECONDS, speech_end + float(tail_handle_seconds))
    frames = frames_for_duration(requested, fps=fps)
    render_duration = frames / float(fps)
    return {
        "fps": fps,
        "speech_duration_seconds": round(sum(float(durations[item["segment_id"]]) for item in segments), 4),
        "dialogue_gap_seconds": round(dialogue_gap_seconds * max(0, len(segments) - 1), 4),
        "head_handle_seconds": round(head_handle_seconds, 4),
        "tail_handle_seconds": round(tail_handle_seconds, 4),
        "target_duration_seconds": round(render_duration, 4),
        "target_frames": frames,
        "segments": placed,
        "timing_source": "measured_tts_wav_before_gpu",
        "dialogue_truncated": False,
    }


def write_silence_wav(destination: Path, duration_seconds: float, sample_rate: int = 24000) -> None:
    if duration_seconds <= 0 or not math.isfinite(duration_seconds):
        raise ValueError("Silence duration must be finite and positive.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    frames = max(1, round(duration_seconds * sample_rate))
    with wave.open(str(temporary), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(b"\x00\x00" * frames)
    temporary.replace(destination)


def assemble_dialogue_wav(
    source_paths: list[Path],
    destination: Path,
    *,
    gap_seconds: float = DEFAULT_DIALOGUE_GAP_SECONDS,
    minimum_duration_seconds: float = 0.0,
) -> float:
    """Concatenate validated line WAVs and small natural gaps without tempo changes."""
    if not source_paths:
        write_silence_wav(destination, max(0.1, minimum_duration_seconds))
        return wav_duration(destination)
    params = None
    chunks: list[bytes] = []
    for path in source_paths:
        with wave.open(str(path), "rb") as source:
            current = source.getparams()
            if current.nchannels != 1 or current.sampwidth != 2 or current.framerate != 24000:
                raise ValueError(f"Incompatible voice WAV format: {path}")
            if params is None:
                params = current
            elif (current.nchannels, current.sampwidth, current.framerate) != (params.nchannels, params.sampwidth, params.framerate):
                raise ValueError("All dialogue line WAVs must share the same 24 kHz mono PCM format.")
            chunks.append(source.readframes(source.getnframes()))
    assert params is not None
    silence = b"\x00\x00" * round(gap_seconds * params.framerate)
    combined = bytearray()
    for index, chunk in enumerate(chunks):
        if index:
            combined.extend(silence)
        combined.extend(chunk)
    duration = len(combined) / (params.framerate * params.nchannels * params.sampwidth)
    if duration < minimum_duration_seconds:
        combined.extend(b"\x00\x00" * round((minimum_duration_seconds - duration) * params.framerate))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with wave.open(str(temporary), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(bytes(combined))
    temporary.replace(destination)
    return wav_duration(destination)


def registry_character_record(character: dict[str, Any], *, asset_root: str = "characters") -> dict[str, Any]:
    char_id = str(character.get("character_id", "")).strip().lower()
    if not _CHARACTER_ID.fullmatch(char_id):
        raise ValueError(f"Invalid character_id: {char_id!r}")
    profile_id = str(character.get("voice_profile_id") or DEFAULT_VOICE_PROFILE_ID)
    profile = resolve_voice_profile(profile_id)
    return {
        "character_id": char_id,
        "display_name": str(character.get("display_name") or char_id).strip(),
        "role": str(character.get("role") or "supporting"),
        "gender_presentation": str(character.get("gender_presentation") or "unspecified"),
        "age_band": str(character.get("age_band") or "adult"),
        "appearance": str(character.get("appearance") or ""),
        "personality": str(character.get("personality") or ""),
        "voice_profile_id": profile_id,
        "gemini_voice": profile["gemini_voice"],
        "asset_folder": f"{asset_root}/{char_id}",
        "asset_status": "metadata_only_pending_3d_pilot",
        "licence_review": {"source": None, "licence": None, "commercial_use_verified": False},
    }
