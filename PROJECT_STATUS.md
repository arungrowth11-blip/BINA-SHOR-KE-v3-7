# Project Status — BINA SHOR KE v3.7 P0 Reliability

**Historical v3.5 baseline:** resilient recovery + automated QA. Current v3.7 release notes follow below. Live production is not certified.

- Historical baseline ZIP: `BINA_SHOR_KE_Studio_v3_5_Resilient_AutoQA.zip`
- Historical v3.5 baseline had 70 offline unit/orchestration tests.
- Python compile, all 3 GitHub workflow YAML files parse, producer self-test, studio preflight and model-lab CLI checks passed.
- Lightweight scheduled polling checks Kaggle status before full finalizer setup, skipping media/ASR dependencies while a GPU job remains active.
- Primary production video model remains Wan2.2 TI2V-5B Q4_K_M GGUF on Kaggle GPU.
- Gemini remains the currently qualified Hindi TTS and image-based visual reviewer. Groq/Mistral/Cloudflare routing is for text only.
- Local Whisper large-v3-turbo (CPU int8) checks transcript alignment; FFmpeg scans entire duration for black/frozen intervals; Gemini vision QA samples up to 18 beat-stratified frames. Human full playback and Telegram approve/reject remain required.
- Kaggle output recovery is best-effort: scenes are locally atomic/checksummed; on failure, if Kaggle exposes the partial outputs, verified scenes are uploaded to a private Kaggle dataset and restored. This is not a guarantee against hard infrastructure loss.
- Automatic resume budget: <=4h estimated; owner-triggered resume <=8h; maximum two attempts; ambiguous pushes require owner confirmation.
- HunyuanVideo-1.5, FLUX.1 schnell and Indic-Speak are isolated Model Lab candidates, not weekly workflow dependencies. No model promotion without paired baseline test and rights review.
- No paid fallback and no automatic Facebook publishing.
- No live Kaggle GPU, gated-model, API-key or Telegram acceptance test has been performed in this environment.
- See `FINAL_DEEP_REVIEW_v3.5.md`, `ANNUAL_OPERATIONS_PLAYBOOK_HINDI.md` and `docs/MODEL_LAB_BENCHMARK_HINDI.md`.


## v3.6 follow-up fix
A post-release integration review found that Telegram owner commands were only consumed during planning, not during idle periods. A dedicated six-hour scheduled `telegram-feedback-sync.yml` now drains updates independently of GPU activity and commits the private owner cursor/history/performance log. Manual `Run workflow` is available for immediate sync.


## Current release: v3.6
Use `BINA_SHOR_KE_Studio_v3_6_Continuous_Feedback.zip`. v3.6 corrects the v3.5 Telegram command ingestion gap with an independent six-hour scheduled/manual feedback sync. Offline verification: 74 tests, compile, producer self-test, studio preflight and workflow YAML parse passed. Live account/GPU qualification is still pending.


## Current release: v3.7 P0 Reliability

- Corrected generated Kaggle worker manifest injection and added non-empty manifest import integration test.
- Weekly batch now requires persisted one-Reel QA + complete Telegram delivery + owner `/approve`, in addition to the separate GPU benchmark/time gate.
- Telegram sync drain and commit steps require the bot token.
- Empty/unset Kaggle kernel slug safely resolves to the default.
- New plans are blocked while `gpu_checkpoint_saved` is present.
- Offline validation: 84 tests passed; compile, producer self-test, studio preflight and all four workflow YAML parses passed.
- Live account/API/GPU qualification remains pending; do not run `plan-week` until a real `plan-one` is reviewed and approved.
