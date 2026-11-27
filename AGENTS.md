# BINA SHOR KE — Engineering and QA Instructions

## Mission and hard boundaries
Produce reliable, human-first Hindi/Indian short-form video workflows. Priorities: safety and privacy, truthful QA evidence, story quality, visual/audio continuity, deterministic production, then throughput.
- Never auto-publish to Facebook/Instagram. A review-ready output is not a published output.
- Never claim synthetic reviewers are real people. The 10K panel is a deterministic synthetic audience simulation, not 10,000 humans, and not a reach/watch-time/virality predictor.
- Keep synthetic simulation, AI editorial/VLM evidence, deterministic technical QA, and independent human reviews as separate evidence classes.
- Never let audience votes override a critical technical, safety, privacy, rights, or policy defect.
- Do not weaken approval thresholds, reviewer allowlists, encryption, or deduplication to make a Reel pass.
- Never commit Telegram chat IDs, bot tokens, reviewer identities, Fernet keys, raw human review payloads, or private media. Treat the currently public repository/history exposure described in PR #11 as an unresolved security blocker until the owner changes repository visibility and rotates exposed identifiers as appropriate.

## Evidence model
- Every score must retain provenance and a valid 1–5 range.
- Missing evidence remains missing; do not impute scores or fabricate audience reactions.
- A completed simulation must state its deterministic seed/sample count and disclose its synthetic nature.
- Real human-review records must be independent, allowlisted, deduplicated, and encrypted at rest.
- Human review is not complete until the configured independent panel threshold and owner review requirements are met.
- Technical critical failures remain hard blockers.

## Required engineering loop
1. Inspect the active PR stack and exact branch before editing.
2. Add failing tests for the defect or acceptance criterion.
3. Keep provider calls bounded, retryable, and cost-safe; no paid fallback unless explicitly approved.
4. Run `python -m compileall -q scripts tests` and `python -m unittest discover -s tests -v`.
5. Validate every workflow YAML and test the affected workflow path without real publication.
6. Review encrypted-data handling, gitignore, secret references, Telegram allowlists, and publication gates.
7. Report exactly what ran, what remains untested, and whether any real Reel has completed the path.

## Human review and publication
A synthetic 10K report is decision-support only. Do not label it "10,000 human reviews". Human fallback may only operate through the configured private, consent-based, allowlisted reviewer workflow. Owner approval authorizes manual publishing only; it must not trigger auto-publishing.
