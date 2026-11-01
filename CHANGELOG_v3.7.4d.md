# BINA SHOR KE v3.7.4d — Scene 6 Voiceover Repair

- Adds a one-time `repair-scene-6-voiceover` workflow action for the known `सूखी छतरी` Reel (`reel_01_115742`).
- Requires the prior rhythm repair and Scene 5 voiceover rewrite to be recorded, and a generic or explicitly numbered Scene 6 speed-change rejection of 1.61x–1.63x.
- Replaces only Scene 6 narration with an 8-word line that respects the 7–12 spoken-word rule.
- Verifies the recorded Kaggle kernel identity and requires the Kaggle source run to be COMPLETE before continuing.
- Reuses all six completed Kaggle MP4s; does not dispatch a new GPU run, change prompts, or alter other scene voiceovers.
- Adds a one-attempt guard and tests for successful targeted repair and refusal outside the narrow target case.
- Does not enable paid fallback or automatic Facebook publishing.
