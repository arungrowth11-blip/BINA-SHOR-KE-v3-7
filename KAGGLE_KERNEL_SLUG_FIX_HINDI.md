# BINA SHOR KE — Kaggle Kernel Slug Dispatch Fix (v3.7.x)

## What this patch changes

Replaces `.github/workflows/weekly-factory.yml` with the same workflow plus one environment mapping:

`KAGGLE_KERNEL_SLUG: ${{ vars.KAGGLE_KERNEL_SLUG }}`

The poll workflow already reads this repository variable. The Director/dispatch workflow did not, so it silently used the default slug `bina-shor-ke-studio-video`.

## Apply

1. Extract this ZIP.
2. Copy `.github/workflows/weekly-factory.yml` into the same path in your existing local repository, replacing that one file only.
3. In GitHub: Repository → Settings → Secrets and variables → Actions → Variables → New repository variable.
   - Name: `KAGGLE_KERNEL_SLUG`
   - Value: `bina-shor-ke-private-cinematic-scene-worker`
4. Verify the existing Secret `KAGGLE_USERNAME` has the value `arunkumar12051990` (do not share its value publicly). The `KAGGLE_KEY` must belong to the same Kaggle account.
5. Commit and push the workflow change.

## Important

- Do not run `plan-one` again yet.
- Do not run `retry-finalize`, `resume-checkpoint`, or any dispatch-resolution action yet.
- After applying the fix, use only the existing pending job state and inspect whether the old dispatch exists in Kaggle. The previous dispatch may have targeted the old default slug, so updating the variable does not retroactively move that run.
- The correct notebook URL currently provided by the user is `https://www.kaggle.com/code/arunkumar12051990/bina-shor-ke-private-cinematic-scene-worker`.
- This patch does not alter GPU model settings, API keys, TTS, QA, or publishing behavior.
