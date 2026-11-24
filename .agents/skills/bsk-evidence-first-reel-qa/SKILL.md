---
name: bsk-evidence-first-reel-qa
description: Evidence-first review and safe implementation workflow for BINA SHOR KE story, visual, audio, synthetic audience, human review, and release gates.
---

# BINA SHOR KE Evidence-First Reel QA

## Classify evidence before judging
Keep four independent layers:
1. Deterministic technical checks (render integrity, duration, frame/motion scan, OCR, audio presence, metadata).
2. AI editorial and visual assessments, each with provenance and bounded scores.
3. Deterministic synthetic audience simulation (explicitly synthetic; never human, reach, or virality prediction).
4. Independent real human review records, separate from AI/synthetic output and encrypted at rest.

## Review a Reel
- Verify the exact source artifacts and their hashes/IDs.
- Inspect the complete video, not only a storyboard or selected frames.
- Score hook, progression, payoff, originality, emotional resonance, visual-story match, continuity, typography/readability, voice rhythm, sound mix, platform safety, and metadata cleanliness.
- Identify strengths, weaknesses, severity, timestamps, and actionable edits.
- Missing or contradictory evidence blocks qualification; never fill gaps with invented scores.
- Report synthetic panel count, seed, cohort allocation, evidence coverage, failed gates, and the fact that simulated reactions are modeled preferences.
- Report actual human reviewer count separately, including panel threshold and owner-review status.

## Safety and privacy
- Never publish automatically.
- Never bypass technical critical gates with votes.
- Keep reviewer IDs pseudonymized and review payloads encrypted. Do not print secrets or private review data.
- Do not enable the real reviewer panel until repository privacy and required secrets are verified by the owner.
- Never trigger paid model fallbacks without explicit approval.

## Verification
Run compileall, the full unittest suite, workflow YAML validation, and the specific integration tests. Distinguish offline tests from a real end-to-end Reel, Telegram delivery, independent human votes, and owner approval. A passing test suite is not evidence that a real Reel has completed the human-review path.
