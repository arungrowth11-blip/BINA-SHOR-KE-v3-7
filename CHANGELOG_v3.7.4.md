# BINA SHOR KE v3.7.4 — Bounded Rhythm Repair

- Adds a dedicated `repair-rhythm` action for a single QA rejection caused only by an AI scene speed ratio narrowly above 1.38x (up to 1.42x).
- Reuses the already completed Kaggle MP4 scenes; it does not dispatch another GPU job or change the story/video prompts.
- Applies at most 3% pitch-preserving FFmpeg `atempo` to the narration track only when the measured duration requires it; the final video speed ratio remains at or below 1.38x.
- Records the adjustment in technical QA metadata and still requires full ASR/visual/technical checks and human listening review.
- Refuses visual defects, too-short scenes, ratios above 1.42x, mismatched Kaggle identity, non-COMPLETE Kaggle jobs, and a second repair attempt.
- Does not alter `retry-finalize`, publish to Facebook, add paid providers, or dispatch GPU.
