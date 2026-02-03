# MyLang VS Code Syntax

Minimal VS Code extension that colors the MyLang sources in this repo.

## Install locally (no packaging)
1. Copy this folder to your user extensions dir (e.g. `~/.vscode/extensions/mylang-syntax`) or run `ln -s /workspaces/MyComputer/tools/vscode-mylang ~/.vscode/extensions/mylang-syntax`.
2. Reload VS Code. Files ending in `.ml` or `.mylang` should pick up the grammar (`MyLang` in the status bar).

## Optional: package as VSIX
If you have `vsce`, run:
```bash
cd /workspaces/MyComputer/tools/vscode-mylang
vsce package
code --install-extension mylang-syntax-0.0.1.vsix
```
