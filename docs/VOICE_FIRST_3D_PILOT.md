# BINA SHOR KE — Primary 2.5D production and isolated 3D pilot

## Status

The selected default is **image-first, primarily 2.5D illustrated motion-comic cinema**. Each narrative beat becomes one FLUX.1 Schnell still, then Depth Anything V2 estimates depth and the worker creates a real 30 FPS parallax video. The editorial plan uses depth-parallax for 100% of default shots; the primary path does not generate Wan source videos. Wan2.2 remains a backward-compatible legacy route for previously created jobs. This image-first branch has offline code/tests but **has not yet passed a live Kaggle GPU qualification**.

The character registry stores metadata only. Image prompts receive the same cast descriptions, wardrobe and visual bible, but true image-conditioned character-sheet locking across all new FLUX stills and across episodes is still outstanding. Binary Blender rigs, meshes, textures and licensed asset packs are not committed to Git. The Blender pilot is a separate technical/visual experiment, not the primary renderer.

## Production order

1. **Screenplay and cast:** generate the complete Hindi story, all speaking characters, immutable character descriptions, and ordered speech segments. Each segment has one speaker ID, one complete line, an emotion cue and a stable segment ID. A beat may contain multiple turns or no speech.
2. **Speaker audio:** generate each dialogue turn with its assigned Gemini voice profile. Validate 24 kHz, mono, 16-bit PCM WAV and measure actual duration. Store transcript + performance direction + voice ID in the cache identity; two voices must never share a cache entry merely because their dialogue text is the same.
3. **Timeline:** place each actual WAV on the beat timeline with a short head handle and natural dialogue gaps. The six source beats retain their measured duration; the final 30 FPS shot plan is calculated only after audio timing is locked. No Wan 4n+1 frame-count constraint applies to the primary still-image path.
4. **Final storyboard:** only after all WAVs are measured, produce the final editorial shot JSON with story role, causal link, state change, camera move, crop anchor, palette and lighting profile. The plan uses 100% depth-parallax shots in the default primary mode.
5. **Primary visual generation:** render one 704×1280 FLUX.1 Schnell Q4_K_S still for each of the six narrative beats. The worker validates image format, dimensions, size and SHA-256; derives a Depth Anything V2 map from the still itself; and creates a real parallax MP4 at the exact voice-beat duration. The primary path generates no Wan video and does not extract a keyframe from a video. Missing stills, depth maps, hash mismatches or unsupported ComfyUI nodes fail closed.
6. **Finish:** assemble the beat-level parallax videos into the timed 12–16 shot 1080×1920, 30 FPS editorial master; reuse the exact cached speaker WAVs; then run subtitle, ASR, audio, VLM, full-video motion and OCR QA gates.

### Timing bounds

- Primary editorial output: 30 FPS, 1080×1920, 9:16.
- GPU source stills: 704×1280 PNG, one per narrative beat; source stills are not delivered as a static slideshow.
- Depth parallax: every primary source beat becomes a separately encoded moving MP4 with eased camera translation/zoom and estimated foreground/midground/background displacement.
- The voice timeline is authoritative. If a beat exceeds the supported parallax encoder duration after real audio is measured, planning fails before the GPU job; the system does not crop dialogue or silently accelerate speech. The story/shot plan must be split or re-authored without losing words.

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
- Primary image-first FLUX prompts repeat the same per-Reel visual bible, character appearance, clothing, age band and distinctive features for every narrative beat. The generated stills are sampled together by VLM QA for face/clothing continuity; human review remains mandatory.
- **Not yet implemented/qualified:** the image-first FLUX graph does not currently feed a generated multi-angle character sheet into a true image-conditioning node (Redux/IPAdapter/reference conditioning). Prompt repetition is not equivalent to identity-locked image conditioning and does not guarantee identical faces/clothing across every still or future episodes.
- Character rig binaries and textures belong under the ignored assets/characters/ directory or a private versioned asset store, not in the source repository.
- Current branch preserves character metadata and can review continuity across shots within one Reel. It does not guarantee cross-episode identity or automatically generate/upload/restore a production Blender rig.

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

Image-first FLUX stills + Depth Anything V2 parallax is the selected primary visual path in this feature branch; Wan2.2 remains available only for older manifests and explicit legacy recovery. Older pending manifests without speaker segments keep their legacy single-narrator TTS path. The voice-first TTS path's live free-tier Hindi TTS plus owner listening gates passed on 2026-11-18. The new image-first renderer still requires a successful one-Reel Kaggle run, immutable image-toolchain lock, measured GPU benchmark, complete final VLM/OCR/motion QA, human visual review and verified Telegram delivery. A separate Blender pilot is not a prerequisite for promoting 2.5D because Blender is no longer the selected production renderer.

## Live Hindi TTS qualification

The feature-branch mode `live-tts-smoke` in the existing `.github/workflows/weekly-factory.yml` is the real API qualification step. Reusing the already-registered workflow keeps manual dispatch available without merging this PR.

1. In GitHub Actions, select **BINA SHOR KE — Director and AI Reel Dispatch**, choose branch `feature/voice-first-3d-foundation`, then choose mode `live-tts-smoke`.
2. Run it only after confirming that the configured Gemini project/key is on the Free Tier and paid billing is disabled. The required confirmation input defaults to false.
3. This mode skips FFmpeg/font setup and Kaggle installation, then calls the same production adapter, `producer.tts_wav`, for two short Hindi samples using the Puck and Aoede profiles (young adult masculine + adult feminine). It does not plan a Reel, push a Kaggle kernel, run Blender, or contact Telegram/Facebook.
4. Download the `bina-shor-ke-live-tts-<run>` artifact. It contains `arjun_puck.wav`, `meera_aoede.wav`, and `report.json` when both samples succeed. The report records the model, WAV format, duration, signal level, file size and SHA-256.
5. Listen to both files and compare each voice against the character's visible age in the storyboard/reference frame. Record accept/reject, pronunciation, naturalness, voice distinction, emotion and any age mismatch. A successful workflow proves only live API response and machine WAV checks; it does not pass the human listening gate.

The same guarded test can be run locally with `python scripts/tts_smoke_test.py --confirm-free-tier-only --output-dir artifacts/tts-smoke` after installing `requirements.txt` and setting `GEMINI_API_KEY`. The explicit flag is required; it must not be used unless the Gemini project/key is on the Free Tier and paid billing is disabled.

**Qualification status: PASS (2026-11-18).** Director workflow run #10 (`44276705851`, mode `live-tts-smoke`) generated the Puck and Aoede WAV samples; both passed machine format/non-silence checks, and the owner explicitly confirmed hearing and accepting both voices. Artifact `14415031915` contains the WAVs and report. The artifact's automated report predates the owner's decision, so the owner confirmation is the separate human listening evidence. This gate is complete; rerun live TTS only if the model, profile or acting direction materially changes. The next distinct gate is one `plan-one` Reel, which cannot substitute for final video visual QA.

## Release-readiness evidence register

Last code/workflow verification: 2026-11-18, PR evidence head `07dbdb2d37bc46a250a440f723b664bb8d664d95`; the latest archive-guard + workflow persistence source commit was `fee694fc4bcfcfc92477c22bed3dba00277fd464`.

| Gate | Evidence status | Exact remaining action |
|---|---|---|
| Offline code, regression tests and workflow syntax | **Verified pass** — GitHub Offline Quality Gates run #63 on source commit `fee694fc4bcfcfc92477c22bed3dba00277fd464` completed successfully: compileall, **160 unit tests**, and all six workflow YAML files passed. Run #61 exposed a temp-path bug in the new archive test; it was corrected, with run #62 and then the final #63 both passing. | Re-run automatically on every PR head update; inspect any new failure logs before changing code. |
| Live Gemini Hindi TTS evidence | **Verified live API + machine checks** — Director workflow run #10 (`44276705851`, mode `live-tts-smoke`, source head `b136f5004cde63172f6efcc2ce9beffcb553e308`) generated Puck male WAV (5.36s) and Aoede adult-female WAV (6.64s), both 24 kHz mono 16-bit, non-silent and format-valid. Artifact `14415031915`; ZIP SHA-256 `12e235f1384a67945cf9b8203dde8ffc8974c9d21ec9422f17545c1aa235a0d9`; no paid fallback. | Keep the accepted Puck/Aoede profile mapping. Re-run live TTS only if the voice model/profile/direction changes or the one-Reel plan produces materially different speech. |
| Human voice approval | **PASS — owner-confirmed 2026-11-18** — user explicitly confirmed both voices from the Puck/Aoede audition were heard and accepted. The artifact report was generated before this manual decision and therefore still says human review pending; the owner confirmation is the separate human sign-off. | Preserve the approved sample/profile mapping; compare rendered character ages and acting against the locked profile during final video review. |
| Wan2.2 variable-duration Kaggle render | **Not started on the current qualification** — saved job `20261031_115742` reached finalization, but scene 6 failed the 1.20s end-hold quality cap (it needed 1.34s). | `plan-one` now identifies this exact terminal QA failure, checks the saved Kaggle kernel, and archives the old record only after Kaggle explicitly reports `COMPLETE`. RUNNING/QUEUED/ERROR/UNKNOWN or any non-COMPLETE response retains the pending lock. A fresh plan is then allowed; the rejected footage is never reused. Verify new job identity/status, six scene clips, manifest SHA locks, measured durations, final QA and Telegram review package. Do not launch a 3-Reel week. |
| Blender Kaggle pilot | **Blocked: execution path missing** — `scripts/blender_pilot.py` is a real isolated Blender script, but the current Kaggle worker and GPU workflows contain no Blender installation or launch step. | Build a separate, isolated Kaggle Blender runner/job that installs or verifies Blender, supplies the two validated WAVs, renders the pilot, and returns MP4 + runtime/environment diagnostics. Then perform human visual review. Do not replace Wan2.2. |
| Human visual/video review | **Not performed** — no actual Blender/Kaggle pilot render or end-to-end Reel is available for review. | Review framing, anatomy, eye-lines, character consistency, mouth timing, lighting, motion artefacts and 9:16 composition after a real render exists. |
| Telegram delivery and end-to-end Reel | **Not verified live on this PR head** — implementation and mocked/offline tests are not a delivery receipt. | After the one-Reel GPU/QA gate, verify the actual video, cover, message and publish-kit receipt in the pinned Telegram chat. Facebook publication remains manual. |
| Age-to-voice consistency | **Verified in code/CI** — age metadata drives the canonical visual-age anchor and expected Gemini voice; conflicting profile IDs fail closed and free-form voice-timbre overrides cannot defeat the locked direction; child/teen dialogue is blocked until a dedicated age-appropriate voice is qualified. Unit tests cover adult female Aoede, mismatch rejection and child/teen behavior. | The final generated video still requires human visual review; prompting cannot guarantee the video model will obey age constraints. |
| Production promotion | **Blocked by policy** — Wan2.2 remains production; Blender stays experimental. | Complete the documented paired-sample/three-shadow-Reel quality programme and obtain explicit owner approval before any renderer promotion. |

Owner listening decision recorded: both auditioned voices accepted on 2026-11-18 against the Puck/Aoede live TTS samples from run #10. The next operational gate is one `plan-one` Reel; the current workflow-dispatch history contains only live-TTS smoke runs #9 and #10, not a GPU plan. Final on-screen age/voice alignment remains subject to human visual QA.

### Terminal failed GPU batch recovery

A stale `finalize_failed` record is not blindly deleted or treated as safe to ignore. For the recorded scene-end-hold rejection only, `plan-one` checks the original saved Kaggle kernel identity. It writes the complete failed job to `data/job_archive/<job_id>.json` and changes the pending state to terminal `qa_rejected` only after Kaggle reports `COMPLETE`. A live, failed, queued or unknown Kaggle status preserves the original pending state and prevents a duplicate dispatch. Unclassified finalization failures remain locked for the normal recovery/inspection path. The weekly workflow commits the archive JSON alongside the updated pending state.

A successful offline run must never be substituted for a live API, Kaggle, Blender, human review or Telegram receipt. A gate stays blocked until its own evidence is recorded.
