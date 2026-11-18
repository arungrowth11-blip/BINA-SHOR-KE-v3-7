# BINA SHOR KE — Voice-first production and isolated 3D pilot

## Status

This branch introduces the voice-first screenplay/timing path while preserving the current Wan2.2 production renderer. It does **not** promote Blender to production and does not claim a live Kaggle GPU render has passed.

The character registry stores metadata only. Binary Blender rigs, meshes, textures and licensed asset packs are not committed to Git. The Blender pilot is an isolated technical/visual experiment.

## Production order

1. **Screenplay and cast:** generate the complete Hindi story, all speaking characters, immutable character descriptions, and ordered speech segments. Each segment has one speaker ID, one complete line, an emotion cue and a stable segment ID. A beat may contain multiple turns or no speech.
2. **Speaker audio:** generate each dialogue turn with its assigned Gemini voice profile. Validate 24 kHz, mono, 16-bit PCM WAV and measure actual duration. Store transcript + performance direction + voice ID in the cache identity; two voices must never share a cache entry merely because their dialogue text is the same.
3. **Timeline:** place each actual WAV on the beat timeline with a short head handle and natural dialogue gaps. Calculate a 24 FPS shot length by rounding up to Wan's 4n+1 temporal frame shape. The screenplay is not shortened to fit a clip.
4. **Final storyboard:** only after all WAVs are measured, produce the final six video prompts using the cast bible, exact dialogue turns, audio start/end times, emotion and measured target duration. The storyboard is not allowed to rewrite the script or change the frame count.
5. **Video:** pass the voice-derived frame count into the Wan2.2 ComfyUI graph. The worker rejects invalid frame shapes and unsupported scene lengths before dispatching that scene.
6. **Finish:** reuse the exact cached speaker WAVs, assemble them in dialogue order with the measured lead-in, then run the existing subtitle, ASR, audio and visual QA gates.

### Timing bounds

- 24 FPS.
- Wan temporal shape: 4n + 1 frames.
- Minimum planned shot: 61 frames (about 2.54 seconds).
- Maximum planned shot: 193 frames (about 8.04 seconds).
- If a beat exceeds that duration after real audio is measured, planning fails before the video GPU job. It does not crop the dialogue, accelerate speech or freeze a frame to hide the mismatch. The story/shot plan must be split or re-authored without losing words. Automatic sub-shot splitting is a later capability, not claimed here.

## Speaker voice profiles

The initial mapping is a starting cast palette, not a promise that a model voice will sound exactly the listed age. Audition Hindi output before promoting any mapping:

| Profile ID | Gemini voice | Intended direction |
|---|---|---|
| hi_narrator_kore | Kore | Restrained narrator |
| hi_male_young_puck | Puck | Young adult masculine |
| hi_female_young_leda | Leda | Young adult feminine |
| hi_male_adult_charon | Charon | Mature masculine |
| hi_female_adult_aoede | Aoede | Mature feminine |
| hi_male_older_algenib | Algenib | Older masculine, slightly gravelly |
| hi_female_older_gacrux | Gacrux | Older feminine, measured |

Voice gender/character direction and actual Hindi acting quality require a human listening test. A text transcription pass is not a naturalness or acting test.

## Character identity and reuse

- data/characters/registry.json is the versioned metadata registry.
- Each newly cast character receives an identity scoped to its Reel. A reused asset must be selected explicitly using reuse_character_id; names such as protagonist are not global identities.
- The registry tracks appearance, personality, age/gender presentation, voice profile and rights-review state.
- Character rig binaries and textures belong under the ignored assets/characters/ directory or a private versioned asset store, not in the source repository.
- Current branch can preserve and look up character metadata; it does not yet generate, upload or restore a production Blender rig automatically.

## Blender pilot

scripts/blender_pilot.py creates an isolated, stylised two-character vertical dialogue preview with a small 3D environment, camera movement, lighting and character head motion.

Run it on a machine/Kaggle image with Blender installed:

    blender -b --python scripts/blender_pilot.py -- \
      --output output/3d_pilot/two_character_preview.mp4 \
      --audio-left output/voice/arjun.wav \
      --audio-right output/voice/meera.wav \
      --duration 6

You can omit the audio paths to render a simple visual smoke test. Input WAVs must be 24 kHz mono 16-bit PCM. The mouth movement in this pilot is **amplitude-driven only**. It does not understand Hindi phonemes, visemes, syllables or word boundaries and is not acceptable as final lip-sync quality. The MP4 is a visual test; audio is retained separately for the normal FFmpeg edit.

### Blender qualification gate

Do not replace Wan2.2 on the basis of a single successful Blender launch. Before production promotion:

1. Run the same pilot on the actual Kaggle GPU image and record Blender version, render backend, accelerator visibility, peak RAM/VRAM (where reported), startup/download time and render time.
2. Human-review lighting, facial appeal, anatomy, eye-lines, character continuity, cloth/hair intersections, shadows and 9:16 composition.
3. Add phoneme/viseme lip-sync and per-character animation/gesture rigs; the amplitude mouth driver is only a pipeline smoke test.
4. Complete 10 paired samples against the existing Wan baseline with identical stories, voice tracks and shot-duration targets. Review failures, median runtime, rights/licences and total storage.
5. Run three shadow production Reels and retain Wan rollback. No model is promoted by a visual demo alone.

## Asset and licence controls

- The pilot's meshes and materials are created procedurally; it downloads no third-party assets.
- Optional MPFB/MakeHuman or Quaternius assets must be checked pack-by-pack for the actual asset licence, attribution, commercial-use permission and dependencies before use. Do not assume an entire library has one universal licence.
- Blender itself is open source, but each extension, character model, texture, rig and sound asset still has its own terms.
- Keep unverified or gated models out of the free production path. Do not add paid fallback APIs.

## Cache and workflow boundary

The weekly planning workflow and the later GPU finalizer are separate GitHub Actions runs. weekly-factory.yml saves newly generated data/tts_cache entries after script/voice planning; poll-gpu.yml restores that cache before finalization. The cache key includes transcript, voice direction and Gemini voice ID. Only the metadata registry is committed; audio WAV cache is held in GitHub Actions cache.

## Rollback and current limitations

Wan2.2 remains the active video backend. Older pending manifests without speaker segments keep their legacy single-narrator TTS path. The new voice-first path is guarded by offline tests, but this branch still requires a real free-tier TTS audition, a successful Kaggle Wan duration-variable render, and a separate Blender Kaggle pilot before it can be considered production-qualified.

## Live Hindi TTS qualification

The feature-branch mode `live-tts-smoke` in the existing `.github/workflows/weekly-factory.yml` is the real API qualification step. Reusing the already-registered workflow keeps manual dispatch available without merging this PR.

1. In GitHub Actions, select **BINA SHOR KE — Director and AI Reel Dispatch**, choose branch `feature/voice-first-3d-foundation`, then choose mode `live-tts-smoke`.
2. Run it only after confirming that the configured Gemini project/key is on the Free Tier and paid billing is disabled. The required confirmation input defaults to false.
3. This mode skips FFmpeg/font setup and Kaggle installation, then calls the same production adapter, `producer.tts_wav`, for two short Hindi samples using the Puck and Gacrux profiles. It does not plan a Reel, push a Kaggle kernel, run Blender, or contact Telegram/Facebook.
4. Download the `bina-shor-ke-live-tts-<run>` artifact. It contains `arjun_puck.wav`, `meera_gacrux.wav`, and `report.json` when both samples succeed. The report records the model, WAV format, duration, signal level, file size and SHA-256.
5. Listen to both files and record a separate human decision for pronunciation, naturalness, voice distinction, emotion and audio artefacts. A successful workflow proves only live API response and machine WAV checks; it does not pass the human listening gate.

The same guarded test can be run locally with `python scripts/tts_smoke_test.py --confirm-free-tier-only --output-dir artifacts/tts-smoke` after installing `requirements.txt` and setting `GEMINI_API_KEY`. The explicit flag is required; it must not be used unless the Gemini project/key is on the Free Tier and paid billing is disabled.

**Qualification status:** adding this mode does not itself mean TTS has been auditioned. Until a successful live run artifact is produced and both samples are human-reviewed, TTS remains **blocked pending live run and listening review**. Do not launch `plan-one` or `plan-week` as a substitute for this gate.
