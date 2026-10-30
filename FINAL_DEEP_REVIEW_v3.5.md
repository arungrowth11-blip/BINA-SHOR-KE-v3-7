# BINA SHOR KE v3.5 — Final Deep Review

## Executive decision
The safest upgrade is not to swap the production model stack. Keep Wan2.2 TI2V-5B as the qualified-by-design video path and Gemini for currently qualified Hindi TTS/vision review; introduce local transcript QA, full-video technical scan, recoverable scene inventory and an isolated candidate lab. This reduces routine manual correction without silently increasing model/runtime dependencies.

## Changes in this release
1. Kaggle worker writes each scene to a `.partial.mp4`, validates it via ffprobe and atomically renames it to its final scene path. After every completed scene it writes a JSON checkpoint inventory including bytes, duration and SHA-256.
2. Finalizer attempts to collect only expected, duration-validated scenes from the output bundle after a failed GPU run. It uploads a flat private Kaggle dataset (no `--public` flag), then worker mounts it as a dataset source and restores only files matching expected reel/scene identities, byte count, SHA-256 and duration. Checkpoint job ID must match.
3. Resume estimates use median observed scene time (or locked first-run benchmark), 2x safety and a 60-minute bootstrap buffer. One automatic resume is permitted at <=4h estimate; owner-triggered resume at <=8h; maximum two attempts. Ambiguous push responses lock the batch until owner confirms. A resume attempt increments only after confirmed acceptance.
4. Hindi ASR checks dry voice track against the narration via local faster-whisper large-v3-turbo CPU int8. It reports CER and language probability. It is advisory; Whisper may mishear Hindi, code-mixed words, names and numerals. It does not judge intonation, naturalness or emotion.
5. Full-duration FFmpeg black/freeze scan and up to 18 frame samples across beats supplement visual QA. The Gemini vision component remains a dependency; if it is unavailable, QA flags manual review rather than pretending success. The frame sampler is not full-frame temporal defect detection.
6. Telegram owner `/approve` and `/reject` records final decision. `/approve` only marks readiness for manual upload and never publishes to Facebook/Instagram.
7. Model Lab scorecards test HunyuanVideo-1.5, FLUX.1 schnell and Indic-Speak in isolation. Ten paired prompts, quality and runtime metrics, explicit license review, human review, candidate >=4.20/5 and >=0.25 mean uplift are mandatory. Promotion also needs three successful shadow production runs.
8. Scheduled GPU polling first installs only the minimal Kaggle CLI and queries remote kernel status. While the kernel remains queued/running, it skips FFmpeg, Whisper, media dependencies and finalization caches; full setup runs only when finalization is required. This reduces idle Actions setup time, but a small scheduled runner is still used for status checks.

## Candidate decisions
- **HunyuanVideo-1.5:** serious competitor, but not a drop-in replacement. Official repository reports 8.3B DiT and 14 GB minimum GPU memory with offloading. 480p T2V optimal setup is 50 steps; 8/12-step step-distilled model applies to 480p I2V, not general T2V. Test on same prompts, aspect ratio and comparable evaluation raster; record native settings, RAM/VRAM and total runtime.
- **FLUX.1 schnell:** still-image candidate for covers/keyframes, not a video generator. It must beat current cover baseline after identical crop/title-safe constraints. Keep outside weekly GPU job until separately qualified.
- **Indic-Speak:** Hindi is listed as production language. Hugging Face files are gated behind acceptance; model card calls out upstream Llama/SNAC/Vocos conditions and describes style control as preview-quality. It is not installed as a silent fallback; run a local test on separate resources and listen to all lines.
- **Whisper large-v3-turbo:** local ASR only. Model card is MIT, multilingual (99 languages). No external per-Reel ASR API call is made.

## What still requires the owner

- No per-scene editing is part of the normal workflow. The owner should watch one complete finished Reel, then send Telegram `/approve` or `/reject`. This catches tone, pacing and subtle motion issues that current automated checks cannot certify.
- Facebook/Instagram upload remains manual. After publishing, `/published` and real 24-hour `/insights` data keep the learning loop grounded.

## Important boundaries
- Private Kaggle dataset creation is the intended checkpoint store. Kaggle CLI docs confirm dataset `create` defaults to private; absence of `--public` is intentional. This does not mean Kaggle will always expose partial outputs after abrupt hardware loss. No durable remote checkpoint can be guaranteed unless output is actually available to the poller.
- GPU queue/weekly free quota/session resources can change. Resume can still fail if model bootstrap/download itself overruns the limit, account access changes, or dataset upload cannot complete.
- Gemini remains only verified voice synthesis in this factory and image QA remains Gemini-based. Text providers cannot replace visual modality. There is no fully independent Hindi TTS fallback in production.
- One final full-playback approval and manual Facebook upload remain necessary. The design eliminates per-scene manual editing as the default, not human responsibility for a public post.
- No live Kaggle account, GPU render, private dataset mount, gated model access, Gemini API call or Telegram delivery test was performed in this environment. Offline tests prove local logic/contracts only.

## Test status
`python -m unittest discover -s tests -q` — 70 tests passed. Python compile, workflow YAML parse, producer self-test, studio offline preflight and isolated model-lab template/score CLI passed.


## v3.6 follow-up finding and fix
A post-release integration review found that process_telegram_feedback was called during planning but not independently while idle. Because Telegram retains pending updates for no more than 24 hours, owner commands could be missed before the next weekly plan. v3.6 adds a separate six-hour Telegram feedback sync workflow, plus manual dispatch, serializes it with the other factory workflows, and commits the Telegram cursor/history/performance log. This is a functional v3.6 correction; do not treat v3.5 as the final launch baseline.
