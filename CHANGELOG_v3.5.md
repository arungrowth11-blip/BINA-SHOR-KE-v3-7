# Changelog — v3.5 Resilient AutoQA

- Added per-scene atomic MP4 write + SHA-256 checkpoint inventory in Kaggle worker.
- Added partial-output discovery, validation, private Kaggle dataset checkpoint upload, SHA-verified restore and bounded resume dispatch.
- Added fail-closed ambiguous resume dispatch locking; counts a resume attempt only after owner confirms a remote run was accepted.
- Added explicit `resume-checkpoint` workflow action and conservative runtime guardrails (automatic <=4h, manual <=8h, max two).
- Added local Hindi narration transcript QA using faster-whisper large-v3-turbo CPU int8; advisory only.
- Added full-video FFmpeg black/freeze diagnostics and beat-stratified visual sampling (up to 18 frames).
- Added Telegram `/approve` and `/reject` for one-tap final owner review; no auto-publishing.
- Added isolated Model Lab for HunyuanVideo-1.5, FLUX.1 schnell and Indic-Speak with 10 paired prompts, rights gates, baseline comparison and runtime threshold.
- Added recovery, candidate lab, ASR and motion QA tests.
- Production baseline remains unchanged: Wan2.2 video + Gemini Hindi TTS/vision QA; candidates not promoted without live benchmark.
- Optimized scheduled GPU polling: install only the minimal Kaggle CLI to inspect remote status; skip FFmpeg, Whisper, media dependencies and finalization caches while the kernel remains active.
- Added Telegram owner approval/rejection status; approval never auto-publishes.


## v3.6 follow-up reliability fix
- Added independent six-hour Telegram feedback sync so owner approvals, rejections, manual publication records and insights are persisted even when no GPU batch is running.
- Added a manual dispatch option for immediate command sync.
- Added tests for missing token, unenrolled owner and normal update drain.
