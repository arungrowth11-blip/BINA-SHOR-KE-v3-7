# BINA SHOR KE v3.7.4e — Scene 6 One-Time Follow-up Voiceover Repair

- Adds a single follow-up action for the same `सूखी छतरी` Reel (`reel_01_115742`) after the first Scene 6 rewrite is recorded as `qa_rejected_again` at the observed 1.54x timing ratio.
- Changes only Scene 6 narration from `उसने सूखी छतरी टाँगी, मगर कमरा चुप रहा।` to `उसने छतरी टाँगी, मगर कमरा चुप रहा।` (7 whitespace-separated words).
- Requires the original rhythm repair, the approved Scene 5 replacement, exactly one previous Scene 6 rewrite, the exact current Scene 6 line, the exact Reel identity, the 1.53x–1.55x QA window, and an unused follow-up attempt.
- Verifies Kaggle account/kernel identity and requires the existing Kaggle source run to be `COMPLETE`.
- Reuses all six already-completed Kaggle MP4 scenes; does not dispatch another GPU job, regenerate video, or change any visual prompt.
- Reruns the full audio/video QA. A second QA rejection is recorded safely; no further automatic rewrite is allowed.
- Does not enable paid fallback or automatic Facebook publishing.
