from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bsk.audio.asr import character_error_rate, transcribe_hindi
from bsk.audio.tts import GeminiTTS
from bsk.audio.wav import inspect_wav
from bsk.config import settings
from bsk.editorial.story import draft_and_review
from bsk.errors import GateError, StateError
from bsk.models import StoryDraft
from bsk.pipeline.state import JobStore, atomic_json
from bsk.providers.router import ProviderRouter


store = JobStore(settings.jobs_dir)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(f"Could not read valid JSON from {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise StateError(f"Expected a JSON object in {path.name}.")
    return value


def _job_file(job_id: str, relative: str) -> Path:
    root = store.job_dir(job_id).resolve()
    path = (root / relative).resolve()
    if root not in path.parents:
        raise StateError("Unsafe job artifact path.")
    return path


def create_job(brief_path: Path, job_id: str | None = None) -> str:
    brief = _load_json(Path(brief_path))
    topic = str(brief.get("topic", "story")).strip()
    if not topic:
        raise GateError("Brief topic is required.")
    if not job_id:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:24] or "story"
        job_id = f"{stamp}_{slug}"
    store.create(job_id, brief)
    return job_id


def draft_story(job_id: str) -> dict[str, Any]:
    store.require_stage(job_id, "created")
    job_dir = store.job_dir(job_id)
    brief = _load_json(job_dir / "brief.json")
    router = ProviderRouter()
    story, review = draft_and_review(brief, router)
    story_path = job_dir / "story.json"
    review_path = job_dir / "editorial_review.json"
    atomic_json(story_path, story.to_dict())
    atomic_json(review_path, review)
    store.add_artifact(job_id, "story", story_path)
    store.add_artifact(job_id, "editorial_review", review_path)
    store.transition(job_id, "created", "story_drafted", "Independent critic passed after 0 or 1 revision.")
    return {"title": story.title, "writer": review["writer_provider"], "critic": review["critic_provider"],
            "editorial_average": review["average_score"], "narration_characters": len(story.narration_text)}


def approve_story(job_id: str, note: str) -> None:
    if not note.strip():
        raise GateError("Add a short approval note after reading the complete narration.")
    state = store.require_stage(job_id, "story_drafted")
    review = _load_json(store.artifact_path(job_id, "editorial_review"))
    if not review.get("approved_by_editorial_gate"):
        raise GateError("Editorial gate did not approve this story; human approval cannot bypass the gate.")
    state.setdefault("approvals", {})["story"] = {"approved": True, "note": note[:1000],
                                                    "at_utc": datetime.now(timezone.utc).isoformat()}
    store.save(job_id, state)
    store.transition(job_id, "story_drafted", "story_approved", note)


def generate_voice(job_id: str) -> dict[str, Any]:
    store.require_stage(job_id, "story_approved")
    story = StoryDraft.from_dict(_load_json(store.artifact_path(job_id, "story")))
    job_dir = store.job_dir(job_id)
    audio_dir = job_dir / "audio"
    audio_path = audio_dir / "narration.wav"
    cache_status, audio_info = GeminiTTS().generate(story.narration_text, audio_path)
    meta_path = audio_dir / "voice_metadata.json"
    atomic_json(meta_path, {
        "provider": "gemini",
        "model": settings.gemini_tts_model,
        "voice": settings.tts_voice,
        "style": settings.tts_style,
        "cache_status": cache_status,
        **audio_info,
        "narration_sha256": __import__("hashlib").sha256(story.narration_text.encode("utf-8")).hexdigest(),
    })
    store.add_artifact(job_id, "narration_audio", audio_path)
    store.add_artifact(job_id, "voice_metadata", meta_path)
    store.transition(job_id, "story_approved", "voice_generated", f"Whole narration WAV ready; {audio_info['duration_seconds']:.2f}s.")
    return {"audio_path": str(audio_path), "duration_seconds": audio_info["duration_seconds"],
            "cache_status": cache_status, "format": "mono / 16-bit / 24 kHz WAV"}


def approve_voice(job_id: str, note: str) -> None:
    if not note.strip():
        raise GateError("Listen to the whole WAV and add a short approval note before continuing.")
    store.require_stage(job_id, "voice_generated")
    audio_path = store.artifact_path(job_id, "narration_audio")
    info = inspect_wav(audio_path)
    metadata = _load_json(store.artifact_path(job_id, "voice_metadata"))
    state = store.read(job_id)
    state.setdefault("approvals", {})["voice"] = {
        "approved": True,
        "note": note[:1000],
        "duration_seconds": info["duration_seconds"],
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "model": metadata.get("model"),
    }
    store.save(job_id, state)
    store.transition(job_id, "voice_generated", "voice_approved", note)


def align_audio(job_id: str) -> dict[str, Any]:
    store.require_stage(job_id, "voice_approved")
    story = StoryDraft.from_dict(_load_json(store.artifact_path(job_id, "story")))
    audio_path = store.artifact_path(job_id, "narration_audio")
    audio_info = inspect_wav(audio_path)
    alignment = transcribe_hindi(audio_path)
    cer = character_error_rate(story.narration_text, alignment["transcript_text"])
    alignment.update({
        "job_id": job_id,
        "audio_duration_seconds": audio_info["duration_seconds"],
        "script_character_error_rate": round(cer, 4),
        "human_transcript_review_required": True,
        "alignment_note": "ASR timestamps are estimates. Listen to the complete narration and inspect this transcript before approving.",
    })
    out_dir = store.job_dir(job_id) / "audio"
    alignment_path = out_dir / "alignment.json"
    atomic_json(alignment_path, alignment)
    review_lines = [
        f"# Audio alignment review — {job_id}",
        "",
        f"Duration: {audio_info['duration_seconds']:.2f} sec",
        f"Character error rate vs script: {cer:.1%}",
        "",
        "## ASR timeline",
        "",
    ]
    for segment in alignment["segments"]:
        review_lines.append(
            f"{segment['start_seconds']:07.2f}s–{segment['end_seconds']:07.2f}s  {segment['text']}"
        )
    review_lines.extend(["", "## Original narration", "", story.narration_text, "",
                         "Manual action: listen to the WAV, compare every line, correct any ASR errors before approval."])
    review_path = out_dir / "alignment_review.txt"
    review_path.write_text("\n".join(review_lines) + "\n", encoding="utf-8")
    store.add_artifact(job_id, "audio_alignment", alignment_path)
    store.add_artifact(job_id, "alignment_review", review_path)
    store.transition(job_id, "voice_approved", "audio_aligned", f"ASR produced {len(alignment['segments'])} timed segments; CER {cer:.3f}.")
    return {"segments": len(alignment["segments"]), "cer": round(cer, 4),
            "review_file": str(review_path), "duration_seconds": audio_info["duration_seconds"]}


def approve_alignment(job_id: str, note: str) -> None:
    if not note.strip():
        raise GateError("Read alignment_review.txt and add a note confirming the transcript/timing review.")
    store.require_stage(job_id, "audio_aligned")
    alignment = _load_json(store.artifact_path(job_id, "audio_alignment"))
    if not alignment.get("segments"):
        raise GateError("No timed ASR segments exist; alignment cannot be approved.")
    state = store.read(job_id)
    state.setdefault("approvals", {})["alignment"] = {
        "approved": True, "note": note[:1000], "at_utc": datetime.now(timezone.utc).isoformat(),
        "transcript_cer": alignment.get("script_character_error_rate"),
    }
    store.save(job_id, state)
    store.transition(job_id, "audio_aligned", "alignment_approved", note)


STORYBOARD_SCHEMA = {
    "visual_bible": {
        "style_candidate": "not locked; recommend one of expressive 2D/2.5D, motion comic, stylized 3D",
        "characters": [{"character_id": "stable character id", "visual_identity": "repeatable appearance"}],
        "continuity_rules": ["stable hair, clothing, age range, proportions and palette"],
        "locations": [{"location_id": "stable location id", "description": "repeatable environment"}],
    },
    "scenes": [{
        "scene_id": 1,
        "segment_start_id": 1,
        "segment_end_id": 2,
        "visual_action": "one clear visible action that supports the exact narration",
        "motion_event": "specific character movement, expression or gesture; not static camera zoom",
        "character_ids": ["stable character id"],
        "camera_direction": "shot size, angle and motivated camera movement",
        "emotional_subtext": "what the acting should communicate without spelling it out",
        "transition": "motivated transition to the next scene",
    }],
}


def create_storyboard(job_id: str) -> dict[str, Any]:
    store.require_stage(job_id, "alignment_approved")
    story = StoryDraft.from_dict(_load_json(store.artifact_path(job_id, "story")))
    alignment = _load_json(store.artifact_path(job_id, "audio_alignment"))
    segments = alignment.get("segments", [])
    if not segments:
        raise GateError("Alignment has no speech segments; storyboard cannot be timed.")
    prompt = (
        "Create a storyboard ONLY after this complete narration's WAV duration and ASR timing are known. "
        "Group consecutive ASR segments into visual scenes according to story transitions; choose the number "
        "of scenes the story needs. There is no fixed six-scene limit and no fixed seconds-per-shot rule. "
        "Every ASR segment ID must be used exactly once, in order, with no gaps or overlap. "
        "The visual action must be physically plausible and visibly animated: at least one meaningful character "
        "gesture, pose change, expression or interaction in each scene. Do not propose static artwork with only "
        "a slow zoom as the finished animation. Preserve exact character identity and clothing in the visual bible. "
        "Do not invent narration. Output JSON exactly following this schema:\n"
        + json.dumps(STORYBOARD_SCHEMA, ensure_ascii=False)
        + "\n\nSTORY:\n" + json.dumps(story.to_dict(), ensure_ascii=False)
        + "\n\nMEASURED AUDIO DURATION:\n" + str(alignment.get("audio_duration_seconds"))
        + " seconds\n\nTIMED ASR SEGMENTS:\n" + json.dumps(segments, ensure_ascii=False)
    )
    router = ProviderRouter()
    provider_name, result = router.generate_json(
        "You are a storyboard director for short-form character animation. Output valid JSON only.",
        prompt,
        temperature=0.35,
    )
    visual_bible = result.get("visual_bible")
    if not isinstance(visual_bible, dict):
        raise GateError("Storyboard is missing the visual continuity bible.")
    visual_characters = visual_bible.get("characters")
    if not isinstance(visual_characters, list):
        raise GateError("Storyboard visual bible has no character list.")
    story_character_ids = {str(item["id"]) for item in story.characters}
    visual_character_ids = {
        str(item.get("character_id")) for item in visual_characters
        if isinstance(item, dict) and item.get("character_id")
    }
    if not story_character_ids.issubset(visual_character_ids):
        raise GateError("Storyboard visual bible changed or omitted a story character identity.")
    if not isinstance(visual_bible.get("continuity_rules"), list) or not visual_bible["continuity_rules"]:
        raise GateError("Storyboard visual bible is missing continuity rules.")
    raw_scenes = result.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise GateError("Storyboard response has no scenes list.")
    expected = [int(s["segment_id"]) for s in segments]
    story_character_ids = {str(item["id"]) for item in story.characters}
    cursor = 0
    scenes: list[dict[str, Any]] = []
    by_id = {int(s["segment_id"]): s for s in segments}
    for index, scene in enumerate(raw_scenes, start=1):
        try:
            first = int(scene["segment_start_id"])
            last = int(scene["segment_end_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise GateError(f"Storyboard scene {index} has invalid ASR segment boundaries.") from exc
        group = list(range(first, last + 1))
        if not group or cursor + len(group) > len(expected) or group != expected[cursor:cursor + len(group)]:
            raise GateError("Storyboard must cover every consecutive ASR segment exactly once, without gaps or overlaps.")
        for field in ("visual_action", "motion_event", "camera_direction", "emotional_subtext"):
            if not str(scene.get(field, "")).strip():
                raise GateError(f"Storyboard scene {index} is missing {field}.")
        motion = str(scene.get("motion_event", "")).lower()
        static_only_markers = ("only slow zoom", "static image", "no movement", "still frame only", "केवल ज़ूम", "सिर्फ ज़ूम", "स्थिर चित्र")
        if any(marker in motion for marker in static_only_markers):
            raise GateError(f"Storyboard scene {index} relies on static zoom instead of character action.")
        scene_characters = scene.get("character_ids", [])
        if not isinstance(scene_characters, list) or not set(map(str, scene_characters)).issubset(story_character_ids):
            raise GateError(f"Storyboard scene {index} refers to an undefined character.")
        start = float(by_id[first]["start_seconds"])
        end = float(by_id[last]["end_seconds"])
        if end <= start:
            raise GateError(f"Storyboard scene {index} has invalid audio timing.")
        scenes.append({
            **scene,
            "scene_id": index,
            "start_seconds": round(start, 3),
            "end_seconds": round(end, 3),
            "duration_seconds": round(end - start, 3),
            "narration_excerpt_from_asr": " ".join(by_id[seg_id]["text"] for seg_id in group),
            "timing_source": "approved local ASR timestamps",
        })
        cursor += len(group)
    if cursor != len(expected):
        raise GateError("Storyboard left one or more ASR segments uncovered.")
    result["scenes"] = scenes
    result["audio_duration_seconds"] = alignment.get("audio_duration_seconds")
    result["storyboard_provider"] = provider_name
    result["timing_is_derived_from_voiceover"] = True
    result["visual_style_not_locked_before_prototype_comparison"] = True
    output_path = store.job_dir(job_id) / "storyboard.json"
    atomic_json(output_path, result)
    store.add_artifact(job_id, "storyboard", output_path)
    store.transition(job_id, "alignment_approved", "storyboard_created",
                     f"Timed storyboard has {len(scenes)} scenes; no GPU rendering was run.")
    return {"scenes": len(scenes), "provider": provider_name, "path": str(output_path),
            "audio_duration_seconds": result.get("audio_duration_seconds")}
