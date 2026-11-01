# v3.7.4c — Scene 5 Repair Gate Fix (हिंदी निर्देश)

## समस्या
GitHub workflow का pre-check केवल `AI scene 5 would require ...` खोज रहा था, जबकि मौजूदा QA state में संदेश `AI scene would require ... (1.67x)` है। इसलिए `repair-scene-voiceover` action चुनने पर भी काम `work_required=False` होकर skip हो रहा था।

## बदली जाने वाली files
1. `.github/workflows/poll-gpu.yml`
2. `scripts/studio_pipeline.py`
3. `tests/test_studio_pipeline.py`
4. `tests/test_workflow_configuration.py`

## नई files
1. `CHANGELOG_v3.7.4c.md`
2. `PATCH_INSTRUCTIONS_v3.7.4c_HINDI.md`

बाकी files को न बदलें। विशेष रूप से `data/pending_gpu_job.json` को न खोलें/न बदलें। Secrets और Variables में कोई बदलाव नहीं।

## Commit
`Fix Scene 5 voiceover repair QA gate parsing`

Push के बाद GitHub Actions → `BINA SHOR KE — GPU Poll, Final Edit, QA and Telegram` → Run workflow → Action `repair-scene-voiceover` चुनें।

## सुरक्षा सीमाएँ
यह सुधार केवल मौजूदा exact Reel ID/title, छह-beat manifest, Scene 5 की मूल narration, एक पूर्व rhythm-repair attempt, 1.66x–1.68x QA ratio और एक-unused voiceover repair attempt पर चलेगा। यह existing completed Kaggle MP4s reuse करता है; नया Kaggle GPU job dispatch नहीं करता। यदि किसी guard की शर्त पूरी न हो तो action रुकेगा।
