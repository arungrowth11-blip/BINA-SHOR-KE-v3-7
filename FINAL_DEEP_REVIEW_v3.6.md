# BINA SHOR KE v3.6 — Final Integration Review

## Release decision
Use v3.6 as the launch baseline; do not start with v3.5. It carries the audited v3.5 factory plus a critical Telegram feedback-sync correction.

## Finding fixed after v3.5
The v3.5 code consumed `/approve`, `/reject`, `/published` and `/insights` only during planning. If these commands were sent after a batch and the next weekly plan happened more than 24 hours later, Telegram could expire the pending updates before ingestion. This could silently omit review/publication/measurement data.

## v3.6 correction
- Added a dedicated `.github/workflows/telegram-feedback-sync.yml` workflow, scheduled every six hours and available for manual dispatch.
- It processes only the already pinned private owner chat.
- It commits Telegram update cursor, story history and performance CSV to the private repo.
- It shares the same GitHub Actions concurrency group as planning and GPU finalization so state commits do not overlap.
- It safely skips before bot token configuration or private owner enrollment.
- A webhook must not be active for the bot because Telegram `getUpdates` and webhooks are mutually exclusive.

## Full workflow ownership boundary
- User performs one-time account setup: create service keys/tokens, enter GitHub Secrets and set workflow permissions. The system cannot obtain these credentials or link private accounts by itself.
- GitHub Actions orchestrates; Kaggle GPU runs ComfyUI/Wan2.2; Gemini handles text/TTS/vision; Groq/Mistral are optional text providers; Telegram is delivery and feedback.
- Facebook/Instagram publication remains manual. Meta Insights are not auto-read; the owner enters real metrics in `/insights`.
- Per Reel, watch/listen once and approve/reject. Per-scene editing is not the default workflow.

## Remaining live qualification
1. `preflight` in GitHub Actions.
2. `plan-one` with real Gemini, Kaggle GPU and Telegram credentials.
3. Verify private Kaggle kernel starts and finishes; confirm model/ComfyUI downloads, disk, VRAM, rendering time and checkpoints.
4. Verify Telegram receives MP4, cover, caption, visual prompts, credits and QA report.
5. Watch full Reel for natural Hindi, emotional performance, motion/flicker, character continuity and subtitle readability.
6. Test `/approve`, `/published`, `/insights`, then manually dispatch Telegram Feedback Sync and confirm private GitHub history/CSV changes.
7. Only after live one-Reel qualification, allow `plan-week`; otherwise continue one-Reel runs.

## Known limits
- No live user account/API/GPU test has been performed in this environment.
- Gemini remains the qualified production TTS and visual QA provider; free text backups do not replace those capabilities.
- Kaggle scene recovery is best-effort and depends on partial output availability.
- AI video quality, uninterrupted free quota, reach, virality and monetization cannot be guaranteed.
- A scheduled workflow may be delayed; the feedback-sync workflow can be manually run immediately. Telegram retains pending updates for no longer than 24 hours.

## Validation
- Unit/orchestration regression suite: 74 passed.
- Python compile: passed.
- Producer self-test: passed.
- Studio offline preflight: passed.
- All GitHub workflow YAML parsed successfully.
- ZIP integrity and manifest checks must pass after packaging.
