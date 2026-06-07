# Review hardening lessons for LLM Consilium

Session-derived checklist from hardening `llm-consilium` with independent external reviews.

## Durable lessons

- Treat the deployed workspace config and the package template as separate concerns. The package should remain self-contained: runner defaults should fall back from `$HOME/.config/llm-consilium/llm-consilium.json` to `templates/llm-consilium.json` when run from the skill directory.
- Keep candidate membership and concrete model IDs in config, not in prose. SKILL.md may describe roles/classes of routes, but exact default lists should be read from `templates/llm-consilium.json` or the deployed `$HOME/.config/llm-consilium/llm-consilium.json`.
- If a doc promises helper wrappers (`llm-consilium-fast`, `llm-consilium-full`), the install script must create them or the doc must not mention them.
- Deterministic synthesis should not overclaim: repeated model claims are `model-consistency-only`, and `stance_matrix.json` is only a compatibility filename unless a real contradiction detector exists. Prefer `repetition_report.json` for the honest artifact name.
- Use `agreement_level` for support-ratio heuristics. Do not call it composite confidence; real confidence requires evidence/tool checks, risk assessment, and unresolved-disagreement review.
- External-agent reviews can expose doc/code mismatches after a first fix pass. Run at least one fresh review after patching non-trivial skills, then close easy/high-signal findings immediately.

## Regression checks

- Package config contains `candidates`.
- Runner can use explicit `--config templates/llm-consilium.json`.
- `llm-consilium-fast` and `llm-consilium-full` wrappers exist after install.
- Tests pass in the configured workspace.
- No stale prose matches like `8 passed`, `fallback_used`, or hard-coded fast/full candidate lists in SKILL.md.
