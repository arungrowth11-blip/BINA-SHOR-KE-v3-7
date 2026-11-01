# v3.7.4a — Kaggle CLI `six` Dependency Fix (Hindi)

## इस patch का कारण
GitHub Actions में Rhythm Repair के दौरान Kaggle CLI import पर `ModuleNotFoundError: No module named 'six'` आया। इसके कारण source run status `UNKNOWN` रहा और rhythm repair सुरक्षित रूप से रुक गया।

## Replace करने वाली files
1. `.github/workflows/poll-gpu.yml`
2. `tests/test_workflow_configuration.py`

## नई files
- `CHANGELOG_v3.7.4a.md`
- `PATCH_INSTRUCTIONS_v3.7.4a_HINDI.md`

बाकी files, विशेषकर `data/pending_gpu_job.json`, `data/history.json`, Kaggle notebook, Secrets और Variables को न बदलें।

## बदलाव
दोनों Kaggle CLI installation points पर `six>=1.16.0,<2` को स्पष्ट रूप से install किया जाएगा:
- Quick remote status check
- Full poll/finalization/rhythm repair dependencies

## Commit
`Fix missing six dependency for Kaggle CLI`

## Push के बाद
पहले उसी workflow में `repair-rhythm` action एक बार चलाएँ। यह पहले Kaggle source run का वास्तविक status जाँचेगा। अगर status अभी भी `UNKNOWN` या `RUNNING` हो, तो workflow फिर रुक सकता है; उस स्थिति में कोई GPU dispatch नहीं करना है और Kaggle notebook के latest run/status की जाँच करनी है।

यह patch नया GPU job शुरू नहीं करता और audio/video/manifest को सीधे edit नहीं करता।
