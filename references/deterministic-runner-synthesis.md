# Deterministic runner + synthesis lessons

Session-derived notes for maintaining and using `llm-consilium-run` and related wrappers.

## Current architecture

- `llm-consilium-run` handles route preflight, isolated workspaces, raw outputs, manifests, and currently exposes the deterministic synthesis function used by the wrapper.
- Candidate definitions and fast/full default model lists live in the deployed config; do not hard-code mode membership in Python.
- `llm-consilium-synthesize <run-dir>` is the deterministic model-consistency analysis layer: it reads successful raw outputs and writes:
  - `analysis/claims.json`
  - `analysis/repetition_report.json` plus compatibility copy `analysis/stance_matrix.json` (not full oppose/mixed stance detection)
  - `analysis/evidence_ledger.json`
  - `analysis/summary.md`
  - `final.md`
- Convenience wrappers exist for intent clarity:
  - `llm-consilium-fast ...`
  - `llm-consilium-full ...`

## Determinism requirements

- Preserve configured candidate order even when candidates finish out of order under concurrency.
- Run directories must not collide when two runs with the same slug start in the same second; suffix or otherwise make unique rather than merging artifacts.
- If a custom config mode references a missing candidate, fail with a clear config error rather than raw `KeyError`.
- Treat route preflight failures as exclusions, not as model opinions.

## Evidence-label discipline

The deterministic synthesizer does **not** verify facts. It only detects repeated claims across model outputs.

Use labels like:

- `single-model-only`
- `cross-model-repeated`
- `all-models-repeated`

Avoid labels like `verified` or `supported` unless an external evidence/source/test pass actually checked the claim.

User-facing phrasing should say `model-consistency-only` until evidence checks have run.

## Test command

```bash
python3 -m pytest tests/test_llm_consilium_run.py -q
```

Expected result in this workspace: all runner tests pass. Re-run the test command instead of trusting a stale count.

## Operational note from Dyatlov runs

In a factual consilium, final synthesis should distinguish:

- model consensus/repetition;
- source-verified claims;
- unresolved reconstruction/speculation.

Example: on the Dyatlov Pass question, fast/full runs converged on a local snow slab + hypothermia + ravine/snow compression scenario, but that conclusion was only model-consistency synthesis unless followed by source/evidence checks.
