# BINA SHOR KE v3.7.3 — ComfyUI KSampler API Compatibility Repair

## Root cause

The first live Kaggle GPU job downloaded the Wan2.2 UNet, text encoder and VAE, then failed before queuing scene 1. The current ComfyUI API KSampler schema did not contain the UI widget field `control_after_generate`; the worker sent that unsupported key even though a deterministic `seed` was already supplied.

## Changes

- Removed the UI-only `control_after_generate` field from the API KSampler node inputs. The explicit SHA-256-derived scene seed remains unchanged and deterministic.
- Updated offline graph preflight to mirror the KSampler API schema observed in the failed Kaggle log.
- Added regression tests for the KSampler schema and fixed-seed graph.
- Added a narrowly scoped `retry-gpu` action that reuses the exact saved Reel manifest once, only after Kaggle confirms the previous run is ERROR/CANCELLED, only when no verified scene checkpoint exists, and only when the saved failure is the known KSampler schema mismatch.
- Ambiguous push responses require owner confirmation; no blind duplicate dispatch is attempted.
- Invalid `pending_gpu_job.json` now fails the pre-check instead of being silently treated as an empty state.

## Safety boundaries

- The retry does not call the AI Story Director and does not generate a new title/story. It reuses the saved job ID, manifest, reel ID and prompts.
- Maximum one automatic owner-triggered corrective GPU retry.
- If verified scene checkpoints exist, use `resume-checkpoint` instead; the retry action refuses to overwrite/re-render them.
- No paid fallback and no automatic Facebook publishing.

## Verification

Offline tests, Python compilation and workflow YAML validation must pass before dispatch. A successful offline suite is not a live GPU certification; the next Kaggle run must still be inspected.
