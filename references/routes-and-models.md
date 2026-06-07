# Candidate route configuration

This repository is model-agnostic. Concrete candidate IDs, model names, providers, and commands belong in `templates/llm-consilium.json` or your deployed config.

## Preflight checklist

Before a long or expensive run:

```bash
# Verify every command referenced by your config exists.
# Examples only; replace with your actual CLIs.
command -v your-model-cli || true
your-model-cli --version || true
```

Run a small marker prompt for each route and require non-empty final output before including the candidate in a council.

## Candidate command tokens

- `{PROMPT}` — full prompt inserted as one argv value.
- `{WORKSPACE}` — isolated workspace for the candidate.
- `{PROMPT_FILE}` — file containing the prompt.

## Prompt transports

- `stdin`: safest for large prompts when the CLI supports stdin.
- `argv`: convenient, but avoid huge prompts that can exceed argv limits.
- `file`: useful for CLIs that accept a prompt/context file.

## Example candidate config

```json
{
  "my-primary-model": {
    "label": "Primary reasoning model",
    "route": "custom-cli",
    "command": ["my-model-cli", "--model", "primary", "--prompt", "{PROMPT}"],
    "timeout": 900,
    "preflight": true,
    "preflight_timeout": 90,
    "explicit_reasoning": "configured-by-cli",
    "prompt_transport": "argv"
  }
}
```

## Reliability rules

- Do not include a route that returns only reasoning/thinking events with no final answer.
- Save stdout and stderr separately.
- Treat preflight failures as exclusions, not model opinions.
- Keep provider credentials outside this repository.
- Do not encode secrets in command argv; use environment variables or local credential stores.
