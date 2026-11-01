# v3.7.4b Patch — हिंदी निर्देश

## उद्देश्य
यह patch केवल पहली Reel `सूखी छतरी` के Scene 5 narration को छोटा करता है। छहों Kaggle MP4 clips यथावत इस्तेमाल होते हैं; नया GPU job dispatch नहीं होता।

## बदली जाने वाली files
1. `scripts/studio_pipeline.py`
2. `.github/workflows/poll-gpu.yml`
3. `tests/test_studio_pipeline.py`
4. `tests/test_workflow_configuration.py`

## नई files
1. `CHANGELOG_v3.7.4b.md`
2. `PATCH_INSTRUCTIONS_v3.7.4b_HINDI.md`

अन्य किसी file, विशेषकर `data/pending_gpu_job.json`, को हाथ न लगाएँ।

## Commit
`Add guarded same-scene Scene 5 voiceover repair`

Push के बाद GitHub Actions → `BINA SHOR KE — GPU Poll, Final Edit, QA and Telegram` → Run workflow → Action `repair-scene-voiceover` चुनें।

यह action केवल `qa_rejected` state, exact Scene 5 1.67x rejection, सही Kaggle Kernel COMPLETE status, सही Reel ID/title, original narration text और zero prior attempts पर चलेगा। यह `retry-finalize` नहीं है और नया GPU job नहीं भेजता।

यदि यह action transient TTS/API error से रुके और state `finalize_failed` बने, तो पहले log देखें; उसके बाद ही सामान्य `retry-finalize` पर विचार करें। यदि QA दोबारा reject करे, दूसरा scene rewrite attempt उपलब्ध नहीं होगा—report देखकर निर्णय लें।
