# v4 alpha.1 — Architecture decisions based on the uploaded v3.7 source

## Verified source observations

The supplied `BINA-SHOR-KE-v3-7.7z` contained:

- `scripts/producer.py` combining provider routing, story generation, critique, TTS, ASR QA, FFmpeg rendering, Telegram, analytics and carousel code in one large module.
- `scripts/studio_pipeline.py` combining planning, Kaggle dispatch, polling, checkpoint recovery, finalization and scene-specific repair actions.
- `scripts/kaggle_gpu_runner.py` implementing the ComfyUI/Wan GPU worker.
- a GPU workflow scheduled every two hours and a weekly factory workflow with a scheduled batch path.
- `data/pending_gpu_job.json` with a `qa_rejected` state for the previous Reel; runtime state is not migrated into v4.
- The extracted archive Git checkout was `main...origin/main [behind 1]` and had local changes in `data/history.json`, `data/pending_gpu_job.json`, `data/telegram_state.json` and `data/toolchain_lock.json`. The archive's `.git` and these mutable state files are therefore intentionally excluded from the new branch package.

## Retain as design patterns

- Sequential provider routing with bounded attempts and no paid fallback.
- Separate writer and critic, topic-specific human details, originality and complete-story checks.
- Whole narration WAV cache keyed by exact content/style/model/voice.
- Local ASR transcript/timing review.
- Atomic JSON writes, per-job state and SHA-256 artifact verification.
- Offline tests and manual human approval.

## Remove from v4 default path

- fixed six-scene / fixed words-per-line schema;
- fixed 3.375-second clips;
- visual generation before voice generation;
- scene-number-specific repair workflows;
- Kaggle/Wan as a required production route;
- mutable global `pending_gpu_job.json` as the only job state;
- scheduled GPU polling and weekly batch dispatch.

## v4 alpha.1 stage order

`brief -> complete story -> independent critique -> human story approval -> whole narration WAV -> human voice approval -> local ASR alignment -> human alignment approval -> voice-timed storyboard`.

Animation is intentionally not included in alpha.1. The next qualification experiment compares small, matched 5–8 second prototypes across expressive 2D/2.5D, motion-comic and stylized 3D approaches before one is selected for the full pilot.
