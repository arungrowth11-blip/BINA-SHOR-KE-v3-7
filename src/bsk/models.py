from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class StoryDraft:
    title: str
    logline: str
    narration_text: str
    story_summary: str
    protagonist: str
    protagonist_want: str
    obstacle: str
    consequential_choice: str
    consequence: str
    resolution: str
    takeaway: str
    characters: list[dict[str, Any]]
    visual_motifs: list[str]
    story_type: str = "fiction"
    fact_check_notes: list[str] | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StoryDraft":
        if not isinstance(payload, dict):
            raise ValueError("Story draft must be a JSON object.")
        required = [
            "title", "logline", "narration_text", "story_summary", "protagonist",
            "protagonist_want", "obstacle", "consequential_choice", "consequence",
            "resolution", "takeaway",
        ]
        missing = [key for key in required if not isinstance(payload.get(key), str) or not payload[key].strip()]
        if missing:
            raise ValueError("Story is incomplete; missing fields: " + ", ".join(missing))
        narration = payload["narration_text"].strip()
        if len(narration) < 40:
            raise ValueError("Narration is too short to establish a complete story (minimum 40 characters).")
        if len(narration) > 12_000:
            raise ValueError("Narration exceeds 12,000 characters; reject and rewrite a focused story.")
        characters = payload.get("characters", [])
        motifs = payload.get("visual_motifs", [])
        if not isinstance(characters, list) or not characters:
            raise ValueError("Story must define at least one character.")
        character_ids = set()
        for index, character in enumerate(characters, start=1):
            if not isinstance(character, dict):
                raise ValueError(f"Character {index} must be a JSON object.")
            for key in ("id", "name", "role", "visual_identity"):
                if not isinstance(character.get(key), str) or not character[key].strip():
                    raise ValueError(f"Character {index} is missing {key}.")
            if character["id"] in character_ids:
                raise ValueError(f"Duplicate character id: {character['id']}")
            character_ids.add(character["id"])
        if not isinstance(motifs, list):
            raise ValueError("visual_motifs must be a list.")
        story_type = str(payload.get("story_type", "fiction")).strip().lower()
        if story_type not in {"fiction", "fact_based"}:
            raise ValueError("story_type must be 'fiction' or 'fact_based'.")
        fact_notes = payload.get("fact_check_notes", [])
        if story_type == "fact_based" and not fact_notes:
            raise ValueError("Fact-based stories require explicit fact_check_notes and supplied source material.")
        return cls(
            title=payload["title"].strip(),
            logline=payload["logline"].strip(),
            narration_text=narration,
            story_summary=payload["story_summary"].strip(),
            protagonist=payload["protagonist"].strip(),
            protagonist_want=payload["protagonist_want"].strip(),
            obstacle=payload["obstacle"].strip(),
            consequential_choice=payload["consequential_choice"].strip(),
            consequence=payload["consequence"].strip(),
            resolution=payload["resolution"].strip(),
            takeaway=payload["takeaway"].strip(),
            characters=characters,
            visual_motifs=[str(x).strip() for x in motifs if str(x).strip()],
            story_type=story_type,
            fact_check_notes=fact_notes,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
