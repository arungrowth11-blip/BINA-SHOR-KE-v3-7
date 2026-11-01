# v3.7.4 — Rhythm-only Repair Patch (Hindi)

यह patch केवल इस विशिष्ट QA error के लिए है: `AI scene N would require excessive speed change (1.39x)`। यह वही completed Kaggle MP4 scenes दोबारा डाउनलोड करके इस्तेमाल करता है; कोई नया Kaggle GPU job dispatch नहीं करता।

## Replace these existing files
- `scripts/producer.py`
- `scripts/studio_pipeline.py`
- `.github/workflows/poll-gpu.yml`
- `tests/test_producer.py`
- `tests/test_studio_pipeline.py`
- `tests/test_workflow_configuration.py`

## Add this new file
- `CHANGELOG_v3.7.4.md`

किसी `data/` file, `pending_gpu_job.json`, Story/manifest, Kaggle notebook या Secret को manually edit न करें।

## Commit
Summary: `Add bounded same-scene rhythm repair for borderline AI timing QA`

## Run
GitHub → Actions → `BINA SHOR KE — GPU Poll, Final Edit, QA and Telegram` → Run workflow → action `repair-rhythm`।

यह action तभी चलेगा जब pending status `qa_rejected` हो, rejection सिर्फ excessive speed-change ratio का हो, ratio 1.38x से ऊपर और 1.42x तक हो, Kaggle source kernel `COMPLETE` हो, सही account/slug match करे, और पहले repair attempt न हुआ हो।

यह audio को अधिकतम 3% pitch-preserving `atempo` से adjust कर सकता है। यदि measured ratio इससे अधिक सुधार माँगे तो यह fail-closed रहेगा। पूरा ASR, visual QA और technical QA फिर से चलेगा। सफल होने पर भी Telegram में Reel देखकर सुनना जरूरी है। Facebook upload manual रहेगा।
