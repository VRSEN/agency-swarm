#!/bin/bash
set -euo pipefail

# Environment setup
export CODEX_ENV_PYTHON_VERSION=3.13
export CODEX_ENV_NODE_VERSION=20

# Check directory
WORKSPACE_DIR="/workspace/agency-swarm"
if [ ! -d "${WORKSPACE_DIR}" ]; then
    echo "Error: ${WORKSPACE_DIR} does not exist"
    exit 1
fi
cd "${WORKSPACE_DIR}"

# Install uv if needed
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Install dependencies
export UV_FROZEN=1
make sync

# Install package in editable mode to ensure dependencies like openai-agents are available
pip install -e .

# Create .env if missing
if [ ! -f ".env" ]; then
    cat > .env << EOF
OPENAI_API_KEY=${OPENAI_API_KEY:-}
DEBUG=false
LOG_LEVEL=info
EOF
fi

echo "Setup complete. Run 'make test' to verify."
