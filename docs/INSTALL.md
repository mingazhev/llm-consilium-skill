# Installation

## Prerequisites

- An agent/runtime that can load skill-style instructions, or direct use of the runner scripts.
- Python 3.10+ for the runner.
- Optional candidate CLIs depending on your config.

## Standard install

```bash
git clone https://github.com/mingazhev/llm-consilium-skill.git
cd llm-consilium-skill
./scripts/install.sh
```

The installer is conservative:

- copies the skill package to `$HOME/.agent/skills/autonomous-ai-agents/llm-consilium/`;
- installs runner wrappers;
- writes the config template only if the target config does not already exist.

## Custom locations

```bash
AGENT_SKILLS_ROOT="$HOME/.agent/skills" LLM_CONSILIUM_BIN_DIR="$HOME/.local/bin" LLM_CONSILIUM_CONFIG_DIR="$HOME/.config/llm-consilium" ./scripts/install.sh
```

Add your chosen `BIN_DIR` to `PATH`.

## Update

```bash
cd llm-consilium-skill
git pull
./scripts/install.sh
```

Existing deployed config is preserved. To reset it from the template:

```bash
LLM_CONSILIUM_OVERWRITE_CONFIG=1 ./scripts/install.sh
```

## Verify

```bash
llm-consilium-run smoke --question 'dry run' --mode fast --dry-run
python3 -m pytest tests -q
```
