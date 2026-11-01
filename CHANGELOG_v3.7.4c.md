# BINA SHOR KE v3.7.4c — Scene 5 Repair Gate Fix

- Fixes the `repair-scene-voiceover` preflight and runtime guards to recognize the actual v3.7.4b QA message: `AI scene would require excessive speed change (1.67x)` (no scene number in the stored exception).
- Keeps the repair limited to Reel `reel_01_115742` / `सूखी छतरी`, the exact original Scene 5 voiceover, six-scene concept, one prior rhythm-repair attempt, a 1.66x–1.68x ratio, and one unused Scene 5 rewrite attempt.
- Does not change the Reel manifest, existing MP4 clips, other narration lines, Kaggle state, or GPU dispatch behavior.
- Enables the existing `repair-scene-voiceover` action to reach its guarded Scene 5 repair step instead of being silently skipped.
