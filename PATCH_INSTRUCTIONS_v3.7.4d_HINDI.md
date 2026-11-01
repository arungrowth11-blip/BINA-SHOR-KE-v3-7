# v3.7.4d — Scene 6 Voiceover Repair (Hindi Instructions)

## इस patch का उद्देश्य

`सूखी छतरी` Reel (`reel_01_115742`) में Scene 6 की 1.62x voice-timing QA rejection को ठीक करना। यह patch सिर्फ Scene 6 की narration बदलता है और पहले से बने छहों Kaggle MP4 clips को reuse करता है। कोई नया Kaggle GPU dispatch नहीं होता।

## बदली जाने वाली 4 मौजूदा files

1. `scripts/studio_pipeline.py`
2. `.github/workflows/poll-gpu.yml`
3. `tests/test_studio_pipeline.py`
4. `tests/test_workflow_configuration.py`

## जोड़ी जाने वाली 2 नई files

1. `CHANGELOG_v3.7.4d.md` (Repository root)
2. `PATCH_INSTRUCTIONS_v3.7.4d_HINDI.md` (Repository root)

`data/pending_gpu_job.json` को manually edit न करें। कोई Secret या Variable न बदलें।

## नई Scene 6 narration

`उसने सूखी छतरी टाँगी, मगर कमरा चुप रहा।`

यह 8 whitespace-separated शब्द हैं और Factory की 7–12 शब्दों की सीमा में है।

## Commit Summary

`Add guarded Scene 6 voiceover repair for same Reel`

चारों replacement files सही जगह रखने और दो documentation files जोड़ने के बाद GitHub Desktop में Commit और Push Origin करें।

## Workflow चलाना

GitHub → Actions → `BINA SHOR KE — GPU Poll, Final Edit, QA and Telegram` → Run workflow.

Action में `repair-scene-6-voiceover` चुनें।

यह action तभी चलेगा जब:
- Pending state `qa_rejected` हो;
- Reel ID `reel_01_115742` और title `सूखी छतरी` हों;
- Scene 5 की approved replacement narration पहले से manifest میں मौजूद हो;
- Scene 6 की मौजूदा narration exact expected source line हो;
- QA ratio 1.61x–1.63x हो;
- rhythm repair और Scene 5 repair attempts दर्ज हों;
- Scene 6 repair पहले इस्तेमाल न हुआ हो;
- Kaggle kernel identity match करे और remote status `COMPLETE` हो।

किसी guard के fail होने पर workflow सुरक्षित रूप से रुक जाएगा।

## महत्वपूर्ण

- `plan-one`, `retry-gpu`, `retry-finalize` या सामान्य `repair-scene-voiceover` न चलाएँ।
- Notebook को rerun न करें।
- Scene 6 rewrite के बाद पूरी Reel की QA दोबारा होगी। QA pass होना अभी सुनिश्चित नहीं है।
- Facebook/Instagram पर कोई automatic publishing नहीं होगी।
