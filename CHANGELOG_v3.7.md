# BINA SHOR KE v3.7 — P0 Reliability Release

## P0 corrections

- Fixed Kaggle worker manifest injection: manifest JSON is encoded once, parsed into a Python dictionary, and type-checked at worker startup.
- Weekly 3-Reel batch now requires a persisted qualification record created only after a Reel passes technical QA, all Telegram delivery steps complete, and the owner sends `/approve title=Exact Reel Title`. The independent GPU benchmark and <=8-hour conservative estimate remain required.
- Telegram feedback sync drain and state persistence steps are conditional on `TELEGRAM_BOT_TOKEN` being configured.
- Unset, empty, or whitespace-only `KAGGLE_KERNEL_SLUG` values resolve to `bina-shor-ke-studio-video`.
- `gpu_checkpoint_saved` is now an active pending state and blocks new planning to prevent recovery metadata from being overwritten.

## Integration coverage

- Added `tests/test_p0_reliability.py` covering generated worker import with a non-empty manifest, owner approval qualification, same-invocation Telegram approval reload before `plan-week`, token-conditional workflow steps, default kernel slug, QA/delivery fail-closed behavior, and checkpoint protection.
- Existing tests remain in place.

## Validation boundary

This is an offline reliability release only. Passing tests do not certify Gemini, Groq, Mistral, Telegram, Kaggle, ComfyUI, Wan2.2 or real GPU rendering. No live GPU/API/Telegram run was performed as part of this release. First live run must be `plan-one`; `plan-week` remains locked until the real one-Reel qualification is recorded.
