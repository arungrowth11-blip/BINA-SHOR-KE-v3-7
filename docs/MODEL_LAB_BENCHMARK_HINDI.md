# BINA SHOR KE — Model Lab और Candidate Promotion नियम

यह अलग qualification lab है। **इससे कोई model अपने-आप weekly production में नहीं जुड़ता।** इससे production के Wan2.2 + Gemini workflow का GPU environment, model cache या quota प्रभावित नहीं होना चाहिए। यह utility कोई model download नहीं करती और किसी API को call नहीं करती।

## 1. Candidate की वास्तविक भूमिका

| Candidate | क्या कर सकता है | अभी फैसला | कारण |
|---|---|---|---|
| HunyuanVideo-1.5 | Video T2V/I2V | Lab only | 8.3B DiT; official minimum 14 GB VRAM with offloading. 480p T2V optimal config 50 steps; 8/12-step distilled model केवल 480p I2V track के लिए है. Kaggle पर CPU RAM, disk, startup downloads और वास्तविक scene time benchmark करना होगा. |
| FLUX.1 schnell | Stills, covers, keyframes | Lab only | Video model नहीं है. Cover/keyframe workflow के लिए उपयोगी हो सकता है, पर Hugging Face gated terms/access स्वीकारना और model/license review जरूरी है. 1–4 steps का दावा सिर्फ़ model की inference steps के बारे में है, complete production runtime का नहीं. |
| Indic-Speak | Hindi सहित Indic-language TTS | Lab only | Hindi production language बताई गई है, लेकिन weights gated हैं; use करने से पहले license gate स्वीकारना और base Llama 3.2, SNAC, Vocos सहित upstream terms देखना होगा. Style control अभी preview-quality बताया गया है. |
| Whisper large-v3-turbo | ASR/transcript QA | QA stage में enabled | यह TTS नहीं है. तैयार आवाज़ में बोले गए शब्दों को script से मिलाने के लिए local CPU int8 inference है. MIT model card है; transcript comparison naturalness/acting नहीं जाँचता. |

## 2. Hunyuan और Wan का निष्पक्ष benchmark

पहला benchmark **480p T2V, 50 steps** होगा—10 समान prompts, समान aspect ratio, fixed seed policy, no prompt rewriting, same output length where supported. Existing Wan baseline के लिए original prompt और render settings freeze रहें. Hunyuan 720p 50-step run अलग test हो; उसे 480p result से सीधे compare न करें.

Hunyuan 480p I2V step-distilled 8/12-step variant को अलग I2V track में जाँचें. उस तुलना में दोनों systems को समान reference stills दें. I2V result को T2V baseline के बराबर बताना गलत होगा.

हर clip का runtime, peak VRAM, system RAM, download size, successful completion, anatomy, motion stability, scene coherence और prompt adherence दर्ज करें. Kaggle GPU में 14 GB का minimum fit होना पर्याप्त नहीं: यदि runtime या memory headroom नहीं बचता, इसे reject करें.

## 3. FLUX.1 schnell का उपयोग

इसे केवल 10 still-image prompts पर current cover/key-art method से compare करें. Evaluate face/hand anatomy, photorealism, prompt fidelity, typography-safe negative space, lighting और crop-safe composition. Video motion score यहाँ लागू नहीं होगा. जब तक image model वास्तव में cover quality में सुधार न दे और GPU/disk budget पर स्वीकार्य न हो, procedural cover pipeline कायम रहेगी.

## 4. Indic-Speak Hindi TTS test

दस standard lines में conversational Hindi, code-mixing, numbers/currency/date, emotional restraint और long-vowel/consonant pronunciation शामिल हैं. Gemini baseline से उसी text, same target loudness और comparable voice gender/register पर A/B तुलना करें. तीन स्वतंत्र listeners naturalness, clarity, emotion और pronunciation को 1–5 score दें. Whisper CER केवल सहायक संकेत है; अच्छी transcription का अर्थ अच्छी acting नहीं है.

## 5. Standard scorecard कैसे बनाएँ

Windows PowerShell:

```powershell
python scripts/model_lab.py template --candidate hunyuanvideo-1.5 --output output/model_lab/hunyuan.json
python scripts/model_lab.py template --candidate flux.1-schnell --output output/model_lab/flux.json
python scripts/model_lab.py template --candidate indic-speak --output output/model_lab/indic-speak.json
```

हर prompt पर candidate और production baseline दोनों को समान 1–5 rubric पर score करें. Actual run time, device, peak VRAM, system RAM, downloads/settings दर्ज करें. Rights section में weights, upstream components, commercial-use terms और attribution की जाँच पूरी किए बिना सब fields `true` न करें.

Score करें:

```powershell
python scripts/model_lab.py score --submission output/model_lab/hunyuan.json
```

## 6. Promotion gate — model को production में कब लाना है?

Candidate को केवल तभी **eligible_for_production_trial** मिलता है जब:

- सभी दस paired samples पूरे हों और human review हो;
- rights + upstream components + commercial permission + attribution सत्यापित हों;
- catastrophic defects शून्य हों और कम-से-कम 90% samples clean हों;
- average candidate quality कम-से-कम 4.20/5 हो और baseline से कम-से-कम +0.25 बेहतर हो;
- median runtime baseline के 1.25× के भीतर हो; यदि 1.25× से धीमा हो तो quality uplift कम-से-कम +0.50 हो.

यह केवल production trial की eligibility है, automatic promotion नहीं. Promotion से पहले तीन shadow production runs पास करने होंगे; पुराने pipeline को rollback के लिए सुरक्षित रखें.

## 7. Recovery और human review

- हर successful Wan scene को atomic MP4 और SHA-256 inventory में दर्ज किया जाता है.
- GPU failure पर उपलब्ध output से valid scenes चुनकर Kaggle पर private dataset checkpoint बनाने की कोशिश की जाती है. Kaggle dataset create default private होता है; code में public flag नहीं है.
- एक bounded automatic resume केवल तब जब conservative estimate 4 घंटे के भीतर हो. Manual `resume-checkpoint` ceiling 8 घंटे है. कुल दो resume attempts से अधिक नहीं.
- Kaggle output उपलब्ध न हो, dataset upload fail हो या session/runtime अनुमान बड़ा हो, recovery fail-closed रहेगी—कोई duplicate job या paid fallback नहीं.
- Finalizer dry voice को Whisper से transcribe करता है, black/freeze scan पूरी video पर चलता है और visual QA हर beat से दो sampled frames (अधिकतम 18) देखता है. इनमें से कोई भी human eye/ear का विकल्प नहीं.
- Telegram पर `/approve title=...` या `/reject title=...; reason=...` owner review state दर्ज करता है. यह Facebook पर auto-publish नहीं करता. Manual Facebook upload और post insights entry अभी भी आवश्यक हैं.

## 8. अभी क्या guarantee नहीं है

Free Kaggle GPU availability, maximum throughput, uninterrupted session, Gemini/Mistral/Groq quotas और third-party model access guaranteed नहीं हैं. इस release के offline tests architecture और local code paths validate करते हैं; वास्तविक Kaggle account, gated model access, GPU render और Telegram delivery का live acceptance test अलग से करना होगा. कोई score views/virality की probability नहीं है.
