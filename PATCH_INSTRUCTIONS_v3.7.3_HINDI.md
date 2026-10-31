# v3.7.3 Patch — हिंदी निर्देश

यह patch Kaggle log में मिले वास्तविक ComfyUI KSampler API schema error को ठीक करता है। पहली run में models download हुए थे, लेकिन scene 1 queue होने से पहले worker `control_after_generate` नाम के unsupported input पर रुक गया। `seed` पहले से explicit और deterministic है, इसलिए UI-only field हटाई गई है।

## ZIP से replace/add करें

Replace these existing files:
- `scripts/kaggle_gpu_runner.py`
- `scripts/studio_pipeline.py`
- `.github/workflows/poll-gpu.yml`
- `tests/test_studio_pipeline.py`
- `tests/test_workflow_configuration.py`

Add these new files:
- `CHANGELOG_v3.7.3.md`
- `PATCH_INSTRUCTIONS_v3.7.3_HINDI.md`

किसी `data/` file, pending manifest, Kaggle Secret या API Secret को patch से replace नहीं करना है।

## Commit

Summary: `Fix ComfyUI KSampler API schema and add safe same-Reel GPU retry`

## Failed job को सुरक्षित रूप से retry करने का क्रम

1. पहले verify करें कि GitHub `data/pending_gpu_job.json` में पुराना job `gpu_failed` है। यदि अभी `gpu_running` है तो corrected code commit के बाद `poll` एक बार चलाएँ ताकि पुरानी ERROR output और checkpoint inventory collect हो।
2. यदि status `gpu_checkpoint_saved` है, तो `retry-gpu` नहीं; `resume-checkpoint` इस्तेमाल करें।
3. यदि status `gpu_failed` है, no checkpoint saved है और `gpu_error` में KSampler schema mismatch है, तो GPU Poll workflow में `action=retry-gpu` चुनें। यह exact same manifest/story को अधिकतम एक बार corrected worker से push करेगा।
4. `retry-gpu` पहले Kaggle status ERROR/CANCELLED verify करेगा। अगर status active/unknown/complete है तो dispatch रोक देगा।
5. Push response ambiguous हो तो `resolve-dispatch-running`/`resolve-dispatch-not-started` owner द्वारा Kaggle UI जाँचने के बाद ही चुनें।

`plan-one` या `plan-week` चलाकर नई कहानी मत बनाएं। Facebook upload हमेशा manual रहेगा।
