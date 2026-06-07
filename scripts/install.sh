#!/usr/bin/env bash
set -euo pipefail

# Install this standalone skill checkout into a local agent skills directory and deploy runner wrappers
# and deploy convenience runner wrappers. Existing config is preserved by default.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL_NAME="llm-consilium"
CATEGORY="autonomous-ai-agents"

SKILLS_ROOT="${AGENT_SKILLS_ROOT:-$HOME/.agent/skills}"
TARGET_SKILL_DIR="${LLM_CONSILIUM_TARGET_SKILL_DIR:-$SKILLS_ROOT/$CATEGORY/$SKILL_NAME}"
BIN_DIR="${LLM_CONSILIUM_BIN_DIR:-$HOME/.local/bin}"
CONFIG_DIR="${LLM_CONSILIUM_CONFIG_DIR:-$HOME/.config/llm-consilium}"
OVERWRITE_CONFIG="${LLM_CONSILIUM_OVERWRITE_CONFIG:-0}"

mkdir -p "$TARGET_SKILL_DIR" "$BIN_DIR" "$CONFIG_DIR"
rsync -a --delete   --exclude '.git'   --exclude '.github'   --exclude 'tests'   --exclude 'docs'   --exclude 'README.md'   --exclude 'LICENSE'   --exclude 'SECURITY.md'   --exclude '.gitignore'   "$REPO_DIR/" "$TARGET_SKILL_DIR/"

cp "$REPO_DIR/scripts/llm-consilium-run.py" "$BIN_DIR/llm-consilium-run"
cp "$REPO_DIR/scripts/llm-consilium-synthesize.py" "$BIN_DIR/llm-consilium-synthesize"

if [ "$OVERWRITE_CONFIG" = "1" ] || [ ! -f "$CONFIG_DIR/llm-consilium.json" ]; then
  cp "$REPO_DIR/templates/llm-consilium.json" "$CONFIG_DIR/llm-consilium.json"
fi

cat > "$BIN_DIR/llm-consilium-fast" <<'EOF'
#!/usr/bin/env bash
exec "${LLM_CONSILIUM_BIN_DIR:-$HOME/.local/bin}/llm-consilium-run" "$@" --mode fast
EOF
cat > "$BIN_DIR/llm-consilium-full" <<'EOF'
#!/usr/bin/env bash
exec "${LLM_CONSILIUM_BIN_DIR:-$HOME/.local/bin}/llm-consilium-run" "$@" --mode full
EOF
chmod +x "$BIN_DIR/llm-consilium-run" "$BIN_DIR/llm-consilium-synthesize" "$BIN_DIR/llm-consilium-fast" "$BIN_DIR/llm-consilium-full"

echo "Installed skill to: $TARGET_SKILL_DIR"
echo "Installed runner wrappers to: $BIN_DIR"
echo "Config path: $CONFIG_DIR/llm-consilium.json"
echo "Restart your agent/new session to reload the skill list if needed."
