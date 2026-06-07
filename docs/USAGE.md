# Usage

## When to use

Use `llm-consilium` only when the user explicitly asks for a multi-model council/consilium or when the task is high-stakes enough to justify independent model opinions.

Do not auto-trigger it for ordinary questions.

## Modes

- `fast`: smaller candidate set, practical Karpathy-style independent opinions.
- `full`: expanded candidate set and stronger artifact discipline. This does not automatically mean factual verification; use a separate evidence pass for that.

## Output artifacts

A run creates:

```text
./artifacts/llm-consilium/<slug>-<timestamp>/
  question.md
  prompts/candidate.md
  inputs/<candidate>/prompt.md
  raw/<candidate>.md
  logs/<candidate>.err
  council_run.json
  route_status.json
  analysis/claims.json
  analysis/repetition_report.json
  analysis/stance_matrix.json   # compatibility copy
  analysis/evidence_ledger.json
  final.md
```

## Evidence discipline

The deterministic runner can show repeated claims across models. It cannot prove that those claims are true.

Use these labels honestly:

- `single-model-only`
- `cross-model-repeated`
- `all-models-repeated`
- `model-consistency-only`
- `verified-after-tool-check` only after an external source/tool/test pass
