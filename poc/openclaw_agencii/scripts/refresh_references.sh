#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF_DIR="$ROOT_DIR/references"

mkdir -p "$REF_DIR"

clone_or_update() {
  local repo_url="$1"
  local target_dir="$2"

  if [[ -d "$target_dir/.git" ]]; then
    git -C "$target_dir" fetch origin --prune
    git -C "$target_dir" reset --hard origin/main
  else
    git clone --depth 1 "$repo_url" "$target_dir"
  fi
}

clone_or_update "https://github.com/openclaw/openclaw.git" "$REF_DIR/openclaw"
clone_or_update "https://github.com/agency-ai-solutions/agency-starter-template.git" "$REF_DIR/agency-starter-template"

echo "openclaw: $(git -C "$REF_DIR/openclaw" rev-parse HEAD)"
echo "agency-starter-template: $(git -C "$REF_DIR/agency-starter-template" rev-parse HEAD)"
