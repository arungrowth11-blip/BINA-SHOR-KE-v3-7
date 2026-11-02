from __future__ import annotations

import json
from typing import Any

from bsk.errors import GateError
from bsk.models import StoryDraft
from bsk.providers.router import ProviderRouter


WRITER_SYSTEM = """You are the lead screenwriter of BINA SHOR KE, an original Hindi storytelling brand.
Write a complete, emotionally truthful short story for a broad Hindi-speaking audience.
Use natural spoken Hindi in Devanagari. Avoid translated-English syntax, melodrama, sermon-like morals,
poverty porn, manufactured tragedy, easy coincidences and recycled viral formulas.
The story must be fully understandable to a first-time viewer and have a real resolution.
Show a specific human detail, a believable contradiction, a consequential choice and its consequence.
Do not leave an accidental cliffhanger. The audience should understand what changed and why.
Do not copy, imitate or paraphrase a known film, story, creator or copyrighted character.
The narration is one continuous, performance-ready Hindi script. Add punctuation and natural pauses.
There is NO fixed word count, scene count, or target duration; choose the length the story needs,
while avoiding needless padding. Return JSON only."""

WRITER_SCHEMA = {
    "title": "short Hindi title",
    "logline": "one sentence",
    "narration_text": "complete continuous spoken Hindi narration",
    "story_summary": "complete plot summary including ending",
    "protagonist": "who the story follows",
    "protagonist_want": "what the protagonist wants",
    "obstacle": "what prevents it",
    "consequential_choice": "the decision that changes events",
    "consequence": "what follows from that decision",
    "resolution": "how the story resolves",
    "takeaway": "earned human insight, not a slogan",
    "characters": [{"id": "stable_id", "name": "name", "role": "role", "visual_identity": "stable age range, clothing, hair and distinguishing traits"}],
    "visual_motifs": ["specific story objects or visual motifs"],
    "story_type": "fiction or fact_based",
    "fact_check_notes": [],
}


CRITIC_SYSTEM = """You are an independent senior Hindi story editor and cold-reader.
You did NOT write this story. Assess only what a first-time viewer can understand from the supplied draft.
Do not reward cinematic wording if the causal chain is broken. Verify the protagonist, want, obstacle,
choice, consequence, resolution and takeaway. A story is incomplete if a key event is unexplained or
its ending depends on information that was never introduced. Check natural spoken Hindi, originality,
human specificity, emotional restraint, payoff, share value and platform safety.
Return one JSON object only. Scores are integers 1–5. This is an editorial gate, NOT a view prediction."""

CRITIC_SCHEMA = {
    "approved": True,
    "scores": {
        "completeness": 1, "clarity": 1, "causal_logic": 1, "natural_hindi": 1,
        "originality": 1, "human_specificity": 1, "emotional_resonance": 1,
        "ending_payoff": 1, "share_value": 1, "platform_safety": 1,
    },
    "cold_reader_recap": {
        "protagonist": "...", "want": "...", "obstacle": "...",
        "choice": "...", "consequence": "...", "resolution": "...",
    },
    "confusion_points": [],
    "missing_causal_links": [],
    "revision_notes": [],
    "main_risk": "...",
}

CORE_SCORES = (
    "completeness", "clarity", "causal_logic", "natural_hindi", "originality",
    "human_specificity", "emotional_resonance", "ending_payoff", "share_value", "platform_safety",
)


def validate_critique(review: dict[str, Any]) -> tuple[bool, float, list[str]]:
    errors: list[str] = []
    scores = review.get("scores") if isinstance(review, dict) else None
    if not isinstance(scores, dict):
        return False, 0.0, ["Critic response has no scores object."]
    values: list[float] = []
    for key in CORE_SCORES:
        value = scores.get(key)
        if not isinstance(value, (int, float)) or not 1 <= float(value) <= 5:
            errors.append(f"Invalid or missing 1–5 score: {key}")
        else:
            values.append(float(value))
    recap = review.get("cold_reader_recap", {})
    required_recap = ("protagonist", "want", "obstacle", "choice", "consequence", "resolution")
    if not isinstance(recap, dict) or any(not str(recap.get(k, "")).strip() for k in required_recap):
        errors.append("Cold-reader recap is incomplete; the story's full causal arc is not clear.")
    if review.get("confusion_points") and len(review.get("confusion_points", [])) > 0:
        errors.append("Critic identified viewer-confusion points.")
    if review.get("missing_causal_links") and len(review.get("missing_causal_links", [])) > 0:
        errors.append("Critic identified missing causal links.")
    average = sum(values) / len(CORE_SCORES) if len(values) == len(CORE_SCORES) else 0.0
    required_floor = ("completeness", "clarity", "causal_logic", "natural_hindi", "originality", "ending_payoff", "platform_safety")
    if any(not isinstance(scores.get(k), (int, float)) or float(scores[k]) < 4 for k in required_floor):
        errors.append("One or more mandatory story-quality scores are below 4/5.")
    if average < 4.1:
        errors.append(f"Editorial average {average:.2f}/5 is below the 4.1 gate.")
    approved = bool(review.get("approved")) and not errors
    return approved, average, errors


def _review(router: ProviderRouter, story: StoryDraft, writer_name: str) -> tuple[str, dict[str, Any]]:
    router.require_independent_critic(writer_name)
    prompt = (
        "Review the following complete Hindi story. The output JSON must follow this schema:\n"
        + json.dumps(CRITIC_SCHEMA, ensure_ascii=False)
        + "\n\nSTORY:\n"
        + json.dumps(story.to_dict(), ensure_ascii=False)
    )
    critic_name, review = router.generate_json(
        CRITIC_SYSTEM, prompt, temperature=0.15, exclude={writer_name}
    )
    approved, average, errors = validate_critique(review)
    review["critic_provider"] = critic_name
    review["average_score"] = round(average, 2)
    review["gate_errors"] = errors
    review["approved_by_editorial_gate"] = approved
    return critic_name, review


def draft_and_review(brief: dict[str, Any], router: ProviderRouter) -> tuple[StoryDraft, dict[str, Any]]:
    if not isinstance(brief, dict) or not brief.get("topic"):
        raise GateError("Brief must be a JSON object containing a non-empty 'topic'.")
    factual_mode = str(brief.get("fiction_or_fact", "fiction")).strip().lower() in {"fact", "fact_based", "factual"}
    supplied_sources = brief.get("sources") or brief.get("reference_material")
    if factual_mode and not supplied_sources:
        raise GateError("Fact-based stories require source material in the brief; use fiction mode for invented stories.")
    writer_prompt = (
        "Create one complete original Hindi story for this production brief.\n"
        "Output JSON according to this schema:\n"
        + json.dumps(WRITER_SCHEMA, ensure_ascii=False)
        + "\n\nPRODUCTION BRIEF:\n"
        + json.dumps(brief, ensure_ascii=False)
    )
    writer_name, raw_story = router.generate_json(WRITER_SYSTEM, writer_prompt, temperature=0.7)
    story = StoryDraft.from_dict(raw_story)
    if story.story_type == "fact_based" and not supplied_sources:
        raise GateError("Writer labelled the draft fact-based but no source material was supplied. Stopped safely.")
    critic_name, review = _review(router, story, writer_name)

    if not review["approved_by_editorial_gate"]:
        revision_prompt = (
            "Revise the COMPLETE story using the independent critic's concrete notes. Preserve only the "
            "useful core; repair missing causal links and remove any confusing or unearned ending. "
            "Do not add a twist merely to create surprise. Keep natural spoken Hindi. Return the full story JSON "
            "in the same schema.\n\nORIGINAL STORY:\n"
            + json.dumps(story.to_dict(), ensure_ascii=False)
            + "\n\nCRITIQUE:\n"
            + json.dumps(review, ensure_ascii=False)
            + "\n\nSCHEMA:\n"
            + json.dumps(WRITER_SCHEMA, ensure_ascii=False)
        )
        revised_payload = router.generate_with(writer_name, WRITER_SYSTEM, revision_prompt, temperature=0.45)
        story = StoryDraft.from_dict(revised_payload)
        critic_name, review = _review(router, story, writer_name)
        review["revision_passes"] = 1
    else:
        review["revision_passes"] = 0

    review["writer_provider"] = writer_name
    review["critic_provider"] = critic_name
    if not review.get("approved_by_editorial_gate"):
        raise GateError(
            "Story was rejected after one targeted revision. No voice or visual production was started. "
            + "; ".join(review.get("gate_errors", []))
        )
    return story, review
