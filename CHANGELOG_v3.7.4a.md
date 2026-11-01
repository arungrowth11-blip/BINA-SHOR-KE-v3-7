# BINA SHOR KE v3.7.4a — Kaggle CLI dependency hotfix

- Installs `six>=1.16.0,<2` explicitly alongside the Kaggle CLI in both the quick remote status check and the full poll/finalization/repair dependency setup.
- Adds a workflow configuration regression test requiring both installation points to include `six`.
- Does not modify the pending Reel manifest, Kaggle notebook, scene files, secrets, or GPU dispatch state.
- This fixes the observed `ModuleNotFoundError: No module named 'six'` during Kaggle CLI import; it does not itself prove the remote Kaggle source run is `COMPLETE`.
