# LLM Consilium Skill

A standalone, agent-agnostic skill package for running a deliberately triggered multi-LLM council (“consilium”): independent model opinions, claim-level comparison, preserved dissent, and honest model-consistency synthesis.

The skill is designed for practical decision support and usable as a generic agent skill. It emphasizes:

- independent first pass: candidates answer before seeing each other;
- consensus is not truth: repeated claims are not marked as verified;
- model diversity before role diversity;
- no endless debate: targeted review only for contested high-impact claims;
- auditable artifacts: prompts, raw outputs, logs, manifests, and repetition reports.

## Repository layout

```text
SKILL.md                         # portable skill entrypoint
references/                      # route caveats, synthesis lessons, optional visualizations
scripts/llm-consilium-run.py      # deterministic runner
scripts/llm-consilium-synthesize.py
scripts/install.sh                # optional local installer
templates/llm-consilium.json      # self-contained default candidate config
templates/full-output-schema.json
tests/                           # local tests for the runner
```

## Quick install

```bash
git clone https://github.com/mingazhev/llm-consilium-skill.git
cd llm-consilium-skill
./scripts/install.sh
```

By default this installs:

- skill files to `$HOME/.agent/skills/autonomous-ai-agents/llm-consilium/`;
- runner wrappers to `$HOME/.local/bin/`;
- config to `$HOME/.config/llm-consilium/llm-consilium.json` if it does not already exist.

Override paths when needed:

```bash
AGENT_SKILLS_ROOT="$HOME/.agent/skills" LLM_CONSILIUM_BIN_DIR="$HOME/.local/bin" LLM_CONSILIUM_CONFIG_DIR="$HOME/.config/llm-consilium" ./scripts/install.sh
```

To replace an existing deployed config with the template:

```bash
LLM_CONSILIUM_OVERWRITE_CONFIG=1 ./scripts/install.sh
```

## Usage

Dry run without calling models:

```bash
llm-consilium-run smoke --question 'Route check' --mode fast --dry-run
```

Fast/simplified consilium:

```bash
llm-consilium-fast product-decision --question-file question.md
```

Full/expanded candidate set:

```bash
llm-consilium-full architecture-choice --question-file question.md --concurrency 2
```

Re-run deterministic synthesis only:

```bash
llm-consilium-synthesize ./artifacts/llm-consilium/<run-dir>
```

## Important caveats

- `templates/llm-consilium.json` contains route/model definitions, but model catalogs drift. Verify routes with preflight before long or expensive runs.
- Deterministic synthesis is **model-consistency-only**. It does not verify facts. Run a separate source/tool evidence pass before calling claims verified.
- `analysis/stance_matrix.json` is kept as a compatibility filename; semantically the runner currently writes a repetition report. Prefer `analysis/repetition_report.json`.
- External model/agent CLI credentials are not included in this repository. Configure candidate routes locally.

## Tests

```bash
python3 -m pytest tests -q
```

The tests use dry-run/local fake candidates and do not call external models.

## Security / privacy

This repository intentionally includes only reusable skill code, templates, and documentation. It must not contain:

- live private configs unless deliberately sanitized;
- API keys, OAuth tokens, cookies, or model-provider credentials;
- raw consilium outputs from private tasks;
- local `.env`, `.codex`, `.config/gh`, or terminal history files.

See [`SECURITY.md`](SECURITY.md) for the pre-push checklist.

## License

MIT. See [`LICENSE`](LICENSE).
