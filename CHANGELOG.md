# Changelog

## 4.0.0-alpha.1

- New clean audio-first codebase; no v3.7 patch chain copied.
- Complete variable-length Hindi narration and independent editorial review.
- Human story approval before voice generation.
- Whole-narration Gemini TTS WAV, hash cache and PCM format validation.
- Human voice approval before ASR.
- Optional local CPU Faster-Whisper timestamps and transcript CER.
- Human alignment approval before storyboard.
- Storyboard scene count and durations are derived from approved audio alignment.
- Per-job atomic state and SHA-256 artifact inventory.
- Offline-only GitHub quality gate; no schedule, GPU, Kaggle or publishing action.
