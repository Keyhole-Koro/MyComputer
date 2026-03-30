#!/usr/bin/env bash
set -euo pipefail

git submodule update --init --recursive

workspace_dir="/workspaces/MyComputer-1"
ext_src="$workspace_dir/tools/vscode-mylang"

if [ ! -d "$ext_src" ]; then
  echo "[post-create] Skip local MyLang extension setup: $ext_src not found."
  exit 0
fi

for ext_root in "$HOME/.vscode-server/extensions" "$HOME/.vscode/extensions"; do
  mkdir -p "$ext_root"
  ln -sfn "$ext_src" "$ext_root/mylang-syntax"
done

echo "[post-create] Linked local extension: $ext_src"
