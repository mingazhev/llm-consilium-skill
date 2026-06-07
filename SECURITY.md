# Security and privacy

## What must never be committed

- API keys, OAuth tokens, cookies, model-provider credentials.
- `.env`, `.codex`, `.config/gh`, `hosts.yml`, shell history, private SSH keys.
- Live private configs unless deliberately sanitized.
- Raw consilium outputs from private tasks.
- Personal or customer data.

## Pre-push checklist

Run before publishing:

```bash
git status --short
python3 scripts/secret_scan.py
python3 -m pytest tests -q
```

If the scanner flags a match, inspect it manually. Remove real secrets; do not merely hide them in a later commit.

## Reporting

If you find a secret in this repository, rotate the credential first, then remove it from Git history if necessary.
