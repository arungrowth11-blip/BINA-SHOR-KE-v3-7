# Changelog — v3.4 Resilient Annual Factory

## Reliability and recovery
- Telegram owner-update cursor now persists atomically, matching atomic history/pending-state writes.
- First successful GPU qualification now records key runtime package versions; future runs fail closed on silent runtime dependency drift.
- Added explicit owner-confirmed recovery actions for ambiguous Kaggle dispatch; no duplicate GPU job is automatically submitted.
- Kept `dispatch_unknown` locked until the owner checks Kaggle run history.
- GPU poll workflow performs a lightweight pending-state precheck before Python setup, FFmpeg installation and dependency setup; no-op polls skip the expensive steps.

## Learning and editorial quality
- Preserves recent narrative engine, emotional aftertaste, human detail, character contradiction and cost-of-choice in long-lived topic history through the production delivery path.
- Adds deterministic near-duplicate detection for distinctive lived-in story details, not just title/theme similarity.
- Aligns story-length prompts and provider quota messages with the actual multi-provider router.
- Missing insight dimensions remain unknown, not zero; median-based adaptation waits for at least five measured observations and keeps exploration.
- Provider circuit-breakers cool down rate-limited/transient providers for the rest of their cooldown; configuration errors disable them for the run.

## CI and maintenance
- Added GitHub Actions quality-gates workflow for syntax, unit tests and YAML validation.
- Added monthly Dependabot PRs for Python packages and GitHub Actions (manual review; no auto-merge).

## Not certified
- 49 local/offline unit and orchestration tests pass; workflows and local preflight pass. This is not a real Kaggle GPU, provider-key, Telegram delivery, audio listening or Facebook publishing certification.
