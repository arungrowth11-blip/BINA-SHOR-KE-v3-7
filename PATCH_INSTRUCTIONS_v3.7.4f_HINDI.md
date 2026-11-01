# v3.7.4f — Hindi Patch Instructions

यह patch उस state mismatch को ठीक करता है जिसमें पहली Scene 6 repair के बाद top-level status `qa_rejected` था, लेकिन nested `scene6_voiceover_repair.status` गलती से `in_progress` रह गया था। इसी कारण `repair-scene-6-voiceover-followup` का pre-check `work_required=False` कर रहा था।

## Replace these four existing files

| Patch file | Repository path |
|---|---|
| `scripts/studio_pipeline.py` | `scripts/studio_pipeline.py` |
| `.github/workflows/poll-gpu.yml` | `.github/workflows/poll-gpu.yml` |
| `tests/test_studio_pipeline.py` | `tests/test_studio_pipeline.py` |
| `tests/test_workflow_configuration.py` | `tests/test_workflow_configuration.py` |

`CHANGELOG_v3.7.4f.md` और `PATCH_INSTRUCTIONS_v3.7.4f_HINDI.md` नई files हैं; इन्हें repository root में add करें।

`data/pending_gpu_job.json` को edit न करें। कोई API Secret/Variable न बदलें।

## Commit

Summary: `Fix Scene 6 follow-up recovery state persistence`

फिर Commit और Push Origin करें।

## Run after push

GitHub Actions → `BINA SHOR KE — GPU Poll, Final Edit, QA and Telegram` → Run workflow → Action `repair-scene-6-voiceover-followup` चुनें।

यह action केवल तभी आगे बढ़ेगा जब exact existing Reel ID, QA reason 1.54x, prior repair attempt, exact Scene 5/6 voiceover state, Kaggle COMPLETE status और unused one-time follow-up सभी verify हों। यह पुराने छह MP4 reuse करेगा और नया GPU dispatch नहीं करेगा।

अगर अगली QA फिर fail होती है, कोई और automatic narration rewrite उपलब्ध नहीं होगा। तब output durations और actual audio durations को inspect करके manual decision लेना होगा। Facebook auto-publish नहीं होगा।
