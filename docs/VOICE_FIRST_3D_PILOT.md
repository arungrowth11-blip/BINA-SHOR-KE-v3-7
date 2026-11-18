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

The mapping is a controlled casting rule, not an age guarantee from the model. Select the character's visible age first; the same canonical age band determines both the visual-age anchor and the TTS profile. The final shot prompt receives this immutable age anchor. An explicit profile that conflicts with gender/age metadata is rejected before TTS or GPU dispatch. Voice timbre still requires human audition:

| Profile ID | Gemini voice | Intended direction |
|---|---|---|
| hi_narrator_kore | Kore | Restrained narrator |
| hi_male_young_puck | Puck | Young adult masculine (18–29 visual band) |
| hi_female_young_leda | Leda | Young adult feminine (18–29 visual band) |
| hi_male_adult_charon | Charon | Adult masculine (30–54 visual band) |
| hi_female_adult_aoede | Aoede | Adult feminine (30–54 visual band) |
| hi_male_older_algenib | Algenib | Older adult / elder masculine (55+ visual bands) |
| hi_female_older_gacrux | Gacrux | Older adult / elder feminine (55+ visual bands) |

Voice gender/character direction and actual Hindi acting quality require a human listening test. A text transcription pass is not a naturalness or acting test.

### Age-to-voice lock

- The normalized age band is the source of truth for both the canonical visual-age description and the voice profile. The final storyboard receives that same immutable age anchor with the cast and each speaking turn.
- Adult feminine characters use Aoede. Gacrux is reserved for visibly older-adult/elder feminine characters; an adult woman must not be given an older-sounding profile just because it is available.
- The male profiles follow the same age bands: Puck for young adults, Charon for adults, and Algenib for older adults/elders.
- Child and teen characters may appear as silent characters, with their visible age preserved. No child/teen Hindi TTS profile has passed qualification; assigning dialogue to them is rejected rather than silently using an adult voice.
- Explicit voice-profile overrides that conflict with the character's age/gender metadata fail closed before speaker audio, storyboard finalization or GPU dispatch. If the visual age changes, cast metadata and voice must be regenerated together.

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
3. This mode skips FFmpeg/font setup and Kaggle installation, then calls the same production adapter, `producer.tts_wav`, for two short Hindi samples using the Puck and Aoede profiles (young adult masculine + adult feminine). It does not plan a Reel, push a Kaggle kernel, run Blender, or contact Telegram/Facebook.
4. Download the `bina-shor-ke-live-tts-<run>` artifact. It contains `arjun_puck.wav`, `meera_aoede.wav`, and `report.json` when both samples succeed. The report records the model, WAV format, duration, signal level, file size and SHA-256.
5. Listen to both files and compare each voice against the character's visible age in the storyboard/reference frame. Record accept/reject, pronunciation, naturalness, voice distinction, emotion and any age mismatch. A successful workflow proves only live API response and machine WAV checks; it does not pass the human listening gate.

The same guarded test can be run locally with `python scripts/tts_smoke_test.py --confirm-free-tier-only --output-dir artifacts/tts-smoke` after installing `requirements.txt` and setting `GEMINI_API_KEY`. The explicit flag is required; it must not be used unless the Gemini project/key is on the Free Tier and paid billing is disabled.

**Qualification status:** adding this mode does not itself mean TTS has been auditioned. Until a successful live run artifact is produced and both age-aligned samples are human-reviewed, TTS remains **blocked pending live run and listening review**. Do not launch `plan-one` or `plan-week` as a substitute for this gate.

## Release-readiness evidence register

Last code verification: 2026-11-18, executable code head `28a295affa1bb20df48a5d7d3010108206976e6d`.

| Gate | Evidence status | Exact remaining action |
|---|---|---|
| Offline code, regression tests and workflow syntax | **Verified pass** — GitHub Offline Quality Gates run #56 completed successfully: compileall, 157 unit tests and all six workflow YAML files passed. | Re-run automatically on every PR head update; investigate any new failure from its logs. |
| Live Gemini Hindi TTS evidence | **User-reported audition accepted; API run provenance not attached to this PR.** The live adapter and smoke mode are implemented, but the exact run ID/report SHA were not supplied for this evidence register. | Verify the TTS artifacts attached to the one-Reel production run and retain its report; no need to repeat the listening sign-off unless that run changes voice profile/model/direction. |
| Human voice approval | **Owner-approved by user** — user confirms both male/female voice samples were heard and accepted. This is a human listening sign-off, not a CI quality judgment. | Preserve Puck/Aoede age mapping in the next one-Reel run; compare rendered character ages against the approved voice direction during final video review. |
| Wan2.2 variable-duration Kaggle render | **Next gate — not yet verified live.** Voice choice/listening approval is complete; no one-Reel Kaggle output is attached to this head. | Run exactly one `plan-one` Reel. Confirm Kaggle job identity/status, six expected scene clips, manifest SHA locks, measured durations, final technical/visual QA and Telegram review package. Do not launch a 3-Reel week before one-Reel qualification. |
| Blender Kaggle pilot | **Blocked: execution path missing** — `scripts/blender_pilot.py` is a real isolated Blender script, but the current Kaggle worker and GPU workflows contain no Blender installation or launch step. | Build a separate, isolated Kaggle Blender runner/job that installs or verifies Blender, supplies the two validated WAVs, renders the pilot, and returns MP4 + runtime/environment diagnostics. Then perform human visual review. Do not replace Wan2.2. |
| Human visual/video review | **Not performed** — no actual Blender/Kaggle pilot render or end-to-end Reel is available for review. | Review framing, anatomy, eye-lines, character consistency, mouth timing, lighting, motion artefacts and 9:16 composition after a real render exists. |
| Telegram delivery and end-to-end Reel | **Not verified live on this PR head** — implementation and mocked/offline tests are not a delivery receipt. | After the one-Reel GPU/QA gate, verify the actual video, cover, message and publish-kit receipt in the pinned Telegram chat. Facebook publication remains manual. |
| Age-to-voice consistency | **Verified in code/CI** — age metadata drives the canonical visual-age anchor and expected Gemini voice; conflicting profile IDs fail closed and free-form voice-timbre overrides cannot defeat the locked direction; child/teen dialogue is blocked until a dedicated age-appropriate voice is qualified. Unit tests cover adult female Aoede, mismatch rejection and child/teen behavior. | The final generated video still requires human visual review; prompting cannot guarantee the video model will obey age constraints. |
| Production promotion | **Blocked by policy** — Wan2.2 remains production; Blender stays experimental. | Complete the documented paired-sample/three-shadow-Reel quality programme and obtain explicit owner approval before any renderer promotion. |

Owner listening decision recorded: both auditioned voices accepted on 2026-11-18. Voice approval is complete; the next operational gate is one `plan-one` Reel, with final on-screen age/voice alignment still subject to human visual QA.

A successful offline run must never be substituted for a live API, Kaggle, Blender, human review or Telegram receipt. A gate stays blocked until its own evidence is recorded.
