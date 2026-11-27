# ECC integration — BINA SHOR KE

## Integration model
ECC is an optional development-time agent workflow layer. It is not a video-generation provider, a human-review panel, or a runtime dependency of the BSK factory. Project-local QA rules in `AGENTS.md` and `.agents/skills/bsk-evidence-first-reel-qa/SKILL.md` are the source of truth for this repository.

## Safe Codex setup
Official source: https://github.com/affaan-m/ECC

For a compatible Codex CLI, follow the official ECC `.codex-plugin/README.md`:
```sh
codex plugin marketplace add affaan-m/ECC
codex plugin add ecc@ecc
codex plugin list --json
```
Install once in the active CODEX_HOME. Do not stack the native plugin with the deprecated legacy sync flow. Restart Codex, inspect `/plugins`, and separately review/trust only understood hooks in `/hooks`. Do not add optional MCP servers or credentials just to use the project-local QA guidance.

## Existing QA engine — do not duplicate
The active Human Reality QA work is tracked in PR #11. It already introduces deterministic 10K synthetic audience simulation, evidence coverage/provenance, separate allowlisted Telegram human reviews, deduplication, encrypted-at-rest review storage, and approval gates. ECC should improve engineering discipline around this implementation, not replace it or describe synthetic profiles as real humans.

## Required offline verification
```sh
python -m compileall -q scripts tests
python -m unittest discover -s tests -v
```
Also validate workflow YAML and run affected workflow integration tests. Never report an offline pass as a real Reel qualification.

## Production blockers
PR #11 itself records that no actual Reel has completed the new human-review path, independent human votes and required secrets are not yet configured, and the public-repository/history privacy issue must be addressed before enabling the reviewer panel. These are hard blockers for enabling real reviewer delivery or promoting the Human Reality QA production workflow. They do not make this documentation-only ECC layer executable or enable the reviewer panel; merging this isolated engineering-guidance change does not authorize reviewer delivery, production qualification, or publishing. No Facebook auto-publishing and no paid provider fallback.
