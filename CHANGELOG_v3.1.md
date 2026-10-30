# Changelog — v3.1 Final AI Cinematic Studio

- Replaced the previous graphics-first workflow description with strict Wan2.2 TI2V-5B GGUF AI-video production on Kaggle's free GPU.
- Added `plan-one` workflow mode for a single end-to-end live test before enabling a three-Reel weekly batch.
- Moved weekly director schedule to Saturday 07:37 Asia/Kolkata to give Sunday's first publication slot more production runway.
- Added required-vs-optional ComfyUI node schema validation; the GPU worker now fails immediately if required nodes do not register.
- Added early GPU VRAM and disk checks, records ComfyUI/GGUF source commit SHAs, and rejects paid/CPU fallback.
- Preserved the model's native 24fps cadence in the final AI-video output instead of duplicating frames to 30fps.
- Expanded role-based critique dimensions to cover continuity and voiceover rhythm; this remains one model's structured review, not an independent expert committee.
- Added a Telegram `/published` command to record genuine manual publish confirmations and optional Facebook post URL.
- Added posting-window learning from real metrics: maintain controlled lunch/evening tests until both windows have four measured posts; then use a conservative explore/exploit schedule.
- Added hard visual/rhythm rejection status and clearer recovery instructions so a defective frame set is not blindly re-finalized.
- Added tests for missing required node inputs, Telegram published records, strict AI-video failure before TTS spend, sound-bed WAV validity, native-fps QA and Kaggle status parsing.
- No actual external Gemini/Kaggle GPU/Telegram integration test or GitHub repository deployment has been done without the owner's keys/account authorization.


## v3.1 final reliability pass
- Changed weekly director schedule to Saturday 07:37 IST so the GPU batch has runway before planned Sunday/Tuesday/Thursday post slots.
- Raised finalization job timeout to 180 minutes to accommodate slow free-tier API calls and full QA, without changing any paid fallback behavior.
- Added conservative pacing between TTS requests and a content-hash-validated WAV cache to lower rate-limit risk and prevent repeat voice-generation calls during a finalization retry.
- Added conservative TTS pacing, cross-run hash-validated WAV cache and an update marker so no-op polling does not create cache snapshots.
- Added first-success toolchain pinning for ComfyUI, GGUF and the three model revisions; later jobs reuse proven SHAs and stop on version drift. Upgrades require a deliberate reset and a passing one-Reel test.
- Re-ran full Python syntax checks and 32 unit/orchestration tests; all passed offline. Live provider APIs and Kaggle GPU remain unverified until the owner's secrets and quotas are connected.

## v3.2 final audit additions
- Added 10k-ambition editorial readiness index (explicitly not a view prediction).
- Added per-scene/worker timing telemetry and a benchmark gate: weekly 3-Reel run is blocked until a successful one-Reel benchmark estimates <=8h with 1.5x safety factor.
- Added `FINAL_AUDIT_v3.2.md` documenting remaining live-integration, static-image-model, GPU quota and human-review limitations.
