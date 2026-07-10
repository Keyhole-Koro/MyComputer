# MyLang VS Code Extension

Minimal VS Code extension for the MyLang sources in this repo, with highlighting driven by LSP semantic tokens.

Ownership-oriented tokens are exposed through semantic tokens:
- `ownershipRef` for `ref` and `&`
- `ownershipMut` for `mut` and `&mut`

`mymasm` files use a TextMate grammar and highlight:
- `import ...`
- `import ... from "..."`
- `export ...`
- imported symbol names
- exported symbol names
- import path strings

## Install locally (no packaging)
1. Copy this folder to your user extensions dir (e.g. `~/.vscode/extensions/mylang-syntax`) or run `ln -s /workspaces/MyComputer-1/tools/vscode-mylang ~/.vscode/extensions/mylang-syntax`.
2. Reload VS Code. Files ending in `.mln` or `.mlx` should open as `MyLang` in the status bar.

`.mlx` files may contain MyDOMTranspiler JSX-like returns such as:

```mylang
DomNode* screen() {
    return <Window title="Settings">
        <Button text="OK" />
    </Window>;
}
```

## Optional: package as VSIX
If you have `vsce`, run:
```bash
cd /workspaces/MyComputer-1/tools/vscode-mylang
vsce package
code --install-extension mylang-syntax-0.0.1.vsix
```
