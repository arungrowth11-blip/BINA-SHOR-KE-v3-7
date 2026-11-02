# BINA SHOR KE v4 — Audio-first Story Engine (alpha.1)

यह v3.7 का patch नहीं है। यह `v4-rebuild` branch के लिए अलग, साफ़ project foundation है। v3.7 की पुरानी files, `.git` history, runtime JSON और scheduled GPU workflows इसमें कॉपी नहीं किए गए हैं।

## इस build में अभी क्या काम करता है

1. **Complete story first:** Gemini से पूरी, continuous Hindi narration और कहानी का causal arc बनता है। कोई fixed word-count, 6-scene limit या fixed Reel duration नहीं है।
2. **Independent editorial critic:** Writer से अलग configured provider कहानी को cold-reader की तरह जाँचता है। Completeness, clarity, causal logic, Hindi naturalness, originality, emotional truth, payoff और platform safety के gates हैं। असफल draft को अधिकतम एक बार revise किया जाता है; फिर रोक दिया जाता है। Editorial score views की prediction नहीं है।
3. **Human story approval:** कहानी पढ़े बिना TTS शुरू नहीं होती।
4. **Whole narration first:** पूरी कहानी एक ही Gemini TTS WAV में बनती है। Cache exact narration, voice, style और model पर आधारित है। WAV का format और duration verify होता है।
5. **Human voice approval:** पूरी WAV सुनने के बाद ही आगे बढ़ सकते हैं।
6. **Optional local ASR:** Faster-Whisper CPU पर Hindi transcript और segment/word timestamps बनाता है। Script-vs-ASR character error rate भी दर्ज होता है। Transcript को manually check और approve करना जरूरी है।
7. **Voice-timed storyboard:** Storyboard approved audio alignment के बाद बनता है। Scene boundaries measured ASR timestamps से निकलती हैं; कोई fixed 3.375-second shot या fixed six scenes नहीं हैं। हर shot में वास्तविक character action/gesture की माँग है।
8. **Safe state:** हर stage का अलग job state है; JSON atomic write होता है; saved artifacts SHA-256 से verify होते हैं। एक stage fail होने पर पुराने artifacts चुपचाप overwrite नहीं होते।

## इस alpha में जान-बूझकर क्या नहीं है

- Wan2.2, Kaggle GPU, ComfyUI या कोई automatic video dispatch नहीं।
- पुराना `poll-gpu.yml`, `weekly-factory.yml`, Scene 5/6 repair workflow और Telegram auto-sync नहीं।
- Facebook auto-publishing नहीं।
- अभी final animation renderer नहीं। पहले story + voice + measured timing + storyboard qualify होंगे। उसके बाद एक ही कहानी पर expressive 2D/2.5D, motion-comic और stylized-3D prototype की तुलना होगी। किसी visual style को अभी बिना test के lock नहीं किया गया है।

यह alpha एक पूरा production factory होने का दावा नहीं करता। यह नए pipeline का tested story/audio/timing core है। Final Reel export और animation अगली development milestone हैं।

## आवश्यक environment

- Windows 10/11
- Python 3.11
- Gemini API key
- Independent critique के लिए Gemini से अलग दूसरा provider जरूरी है। प्राथमिक सिफारिश Groq Free-tier key है; विकल्प के रूप में verified Mistral Free mode को explicit opt-in के बाद इस्तेमाल किया जा सकता है। कम-से-कम दो अलग configured text providers होने चाहिए।
- Mistral route default में बंद है; केवल अपना Free mode और pay-as-you-go स्थिति verify करने के बाद ही opt-in करो।
- ASR step पर ही Faster-Whisper install करना है; यह अलग optional requirement है।

## Setup (Windows)

### 1. API keys configure करो

Project root में `.env.example` की copy बनाकर उसका नाम `.env` रखो। उसमें `GEMINI_API_KEY` और `GROQ_API_KEY` भरो। Google AI Studio और Groq dashboard में Free tier की पुष्टि करो और paid billing/Developer tier enable मत करो। तभी `BSK_CONFIRM_FREE_ONLY=YES` सेट करो। यह acknowledgement है, account billing को code अपने आप verify नहीं कर सकता। `.env` Git में commit नहीं होगा। Keys को chat या screenshot में मत भेजना।

Mistral को default में use नहीं किया जाता। Mistral Free mode की actual monthly allowance और pay-as-you-go setting account-specific है; उसे verify किए बिना `BSK_ENABLE_MISTRAL_FREE_ONLY=YES` मत करना।

मॉडल defaults:

- Gemini text: `gemini-3.8-flash`
- Gemini TTS: `gemini-3.8-flash-tts`
- TTS voice: `Kore`

Models `.env` से बदले जा सकते हैं। कोई paid fallback configured नहीं है। Gemini TTS request वर्तमान Interactions API और WAV response format इस्तेमाल करती है।

### 2. Python install

PowerShell में project folder खोलकर चलाओ:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

यदि activation policy block करे तो सिर्फ उसी PowerShell session के लिए:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3. Configuration check

```powershell
python -m bsk.cli doctor
```

`doctor` कोई API call या GPU job नहीं चलाता। दो providers दिखने चाहिए, independent critic `ready` होना चाहिए और Free-only confirmation `confirmed` होना चाहिए।

## पहला story/audio pilot — step by step

### A. नया job बनाओ

पहले sample brief इस्तेमाल करने के लिए:

```powershell
python -m bsk.cli new-job --brief briefs/pilot_brief.json
```

Command एक Job ID देगा। उसी ID को नीचे हर command में लगाना है।

### B. Story बनाओ और independent review कराओ

```powershell
python -m bsk.cli draft-story --job-id JOB_ID
```

Output यहाँ मिलेगा:

- `data/jobs/JOB_ID/story.json`
- `data/jobs/JOB_ID/editorial_review.json`

पहले पूरी `narration_text` पढ़ो। कहानी clear और complete न लगे तो approve मत करो।

### C. Human story approval

```powershell
python -m bsk.cli approve-story --job-id JOB_ID --note "पूरी कहानी पढ़ी; causal flow और ending स्पष्ट हैं।"
```

### D. पूरी Hindi narration WAV बनाओ

```powershell
python -m bsk.cli generate-voice --job-id JOB_ID
```

यह **एक पूरी narration** बनाता है, scene-wise छह अलग आवाज़ें नहीं। File `data/jobs/JOB_ID/audio/narration.wav` में होगी। VLC या Windows Media Player में पूरा audio सुनो।

### E. Human voice approval

आवाज़, उच्चारण, pauses और ending सुनकर संतुष्ट होने के बाद:

```powershell
python -m bsk.cli approve-voice --job-id JOB_ID --note "पूरी आवाज़ सुनी; pronunciation और pacing स्वीकार्य हैं।"
```

आवाज़ reject हो तो approval मत दो। इस alpha में reject/regen loop को जान-बूझकर auto नहीं किया गया है; पहले script/style में निर्णय लेकर अलग job/revision बनाना होगा।

### F. Local ASR install और run

यह step optional dependency install करता है और Whisper model पहली बार download कर सकता है। CPU-only default है; GPU जरूरी नहीं।

```powershell
python -m pip install -r requirements-asr.txt
python -m bsk.cli align-audio --job-id JOB_ID
```

Review file खुलेगी:

`data/jobs/JOB_ID/audio/alignment_review.txt`

इसमें transcript के साथ timestamps हैं। पूरी WAV के साथ मिलाकर missing/गलत शब्द और timing जाँचो। ASR timestamps अनुमान हैं; इन्हें बिना सुने final truth न मानो।

### G. Alignment approval और storyboard

```powershell
python -m bsk.cli approve-alignment --job-id JOB_ID --note "WAV सुनी और transcript/timestamps जाँचे; alignment स्वीकार है।"
python -m bsk.cli build-storyboard --job-id JOB_ID
```

Storyboard यहाँ बनेगा:

`data/jobs/JOB_ID/storyboard.json`

इसमें हर scene का start/end measured audio timestamps से लिया जाता है। Scene count कहानी के हिसाब से तय होगा।

### H. Job status

```powershell
python -m bsk.cli status --job-id JOB_ID
```

## GitHub branch में इसे डालना

`APPLY_V4_TO_GITHUB_DESKTOP.ps1` package के बाहर वाले folder में है। इसे केवल तब चलाना जब GitHub Desktop में सही repository और `v4-rebuild` branch checked out हो। Script:

- सही repository remote और branch verify करेगी;
- working tree dirty होने पर रुक जाएगी;
- पुराने working files का sibling backup बनाएगी;
- `.git` directory को बचाकर केवल working-tree source को v4 project से replace करेगी;
- किसी API key को नहीं पढ़ेगी या upload नहीं करेगी।

फिर GitHub Desktop में changes review करके commit `Start BINA SHOR KE v4 audio-first foundation` और Push origin करो। इससे सिर्फ `v4-rebuild` branch बदलेगी; `main` और `legacy/v3.7-baseline-2026-11-01` untouched रहेंगे।

## Offline checks

इस package के साथ:

```powershell
python -m compileall -q src tests scripts
python -m unittest discover -s tests -v
python scripts/validate_workflows.py
```

ये API, GPU या Telegram नहीं चलाते। GitHub Action भी सिर्फ यही offline tests चलाती है।

## Important operating rules

- `main` और `legacy/v3.7-baseline-2026-11-01` को v4 setup के लिए edit मत करो।
- `.env`, voice WAV, ASR models, cache, job JSON और rendered media GitHub पर push न करो।
- GitHub Actions में कोई scheduled trigger नहीं है और कोई Kaggle/GPU secret नहीं माँगा जाता।
- Story/voice/alignment approval के बिना storyboard नहीं बनता।
- कोई automated system Facebook reach, views या virality guarantee नहीं कर सकता। Actual results pilot publish के बाद platform insights से मापे जाएँगे।

## API reference

- Gemini text generation: https://ai.google.dev/api/generate-content
- Gemini speech generation / Interactions API: https://ai.google.dev/gemini-api/docs/speech-generation
