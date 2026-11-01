# BINA SHOR KE v3.7.4f — Scene 6 Follow-up State Recovery

## Fixes
- Accepts the persisted `scene6_voiceover_repair.status="in_progress"` only when the same pending Reel is `qa_rejected`, the QA rejection is the recorded 1.54x Scene 6 timing case, the first Scene 6 voiceover attempt is recorded, Scene 5 and Scene 6 source/replacement lines match exactly, the completed Kaggle kernel identity matches, and the one-time follow-up counter is still unused.
- Keeps the follow-up strictly limited to `reel_01_115742` and the existing completed AI scene MP4s. No new Kaggle GPU dispatch is permitted.
- Persists `scene6_voiceover_followup.status` as `qa_rejected_again` or `finalize_failed_retryable` if final QA raises, instead of leaving the state stuck as `in_progress`.
- Preserves the one-time follow-up limit and all visual/audio QA gates. This patch does not bypass QA or auto-publish.

## Why
`poll_and_finalize()` records the top-level `qa_rejected` state and then re-raises the QA exception. The prior Scene 6 repair wrapper therefore exited before changing its nested state from `in_progress` to `qa_rejected_again`. The follow-up guard was stricter than the persisted state and returned `work_required=False`.
