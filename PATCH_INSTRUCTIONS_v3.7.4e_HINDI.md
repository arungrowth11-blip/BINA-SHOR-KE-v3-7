# v3.7.4e — Scene 6 One-Time Follow-up Voiceover Repair (Hindi)

## उद्देश्य

पहली Scene 6 voiceover rewrite के बाद दर्ज 1.54x timing QA rejection के लिए एक अंतिम, सीमित narration shortening। यह केवल उसी Reel `reel_01_115742` (`सूखी छतरी`) पर लागू है। छहों पहले से बने Kaggle MP4 clips reuse होंगे; नया GPU dispatch नहीं होगा।

## बदली जाने वाली 4 मौजूदा files

1. `scripts/studio_pipeline.py`
2. `.github/workflows/poll-gpu.yml`
3. `tests/test_studio_pipeline.py`
4. `tests/test_workflow_configuration.py`

## जोड़ी जाने वाली 2 नई files

1. `CHANGELOG_v3.7.4e.md` (Repository root)
2. `PATCH_INSTRUCTIONS_v3.7.4e_HINDI.md` (Repository root)

`data/pending_gpu_job.json` को manually edit न करें। कोई Secret या Variable न बदलें।

## नई Scene 6 narration

`उसने छतरी टाँगी, मगर कमरा चुप रहा।`

यह 7 whitespace-separated शब्द हैं और Factory की 7–12 शब्दों की सीमा में है।

## Commit Summary

`Add one-time Scene 6 follow-up voiceover repair`

चारों replacement files सही जगह रखने और दो documentation files जोड़ने के बाद GitHub Desktop में Commit और Push Origin करें।

## Workflow चलाना

GitHub → Actions → `BINA SHOR KE — GPU Poll, Final Edit, QA and Telegram` → Run workflow.

Action में `repair-scene-6-voiceover-followup` चुनें।

यह action तभी चलेगा जब:
- Pending state `qa_rejected` हो;
- QA reason में generic या Scene 6-specific excessive speed change `1.53x–1.55x` हो;
- Reel ID `reel_01_115742` और title `सूखी छतरी` हों;
- Scene 5 की approved narration मौजूद हो;
- पहली Scene 6 replacement line अभी manifest में हो;
- पहली Scene 6 repair attempt ठीक एक हो और उसका status `qa_rejected_again` हो;
- follow-up attempt पहले इस्तेमाल न हुआ हो;
- Kaggle kernel identity match करे और remote status `COMPLETE` हो।

किसी guard के fail होने पर workflow सुरक्षित रूप से रुक जाएगा।

## महत्वपूर्ण

- `plan-one`, `retry-gpu`, `retry-finalize`, `repair-rhythm`, `repair-scene-voiceover` या पहले वाला `repair-scene-6-voiceover` न चलाएँ।
- Kaggle Notebook को rerun न करें।
- यह Scene 6 का एकमात्र follow-up rewrite है। यदि पूरी QA फिर reject होती है, तो इस action से एक और rewrite नहीं होगा।
- Facebook/Instagram पर कोई automatic publishing नहीं होगी।
