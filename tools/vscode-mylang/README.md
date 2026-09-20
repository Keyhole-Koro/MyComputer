# MyLang VS Code Extension

VS Code extension for the MyLang sources in this repo. It uses the standard
`vscode-languageclient` package to connect to the Python language server.

Current editor features include syntax diagnostics, semantic tokens, document
symbols, Go to Definition, function Hover, and Signature Help with
`/** ... */` or `///` parameter documentation. Ctrl+click resolves local and
imported functions, structs, enums, type aliases, and enum members. Annotation
names such as `@param` and `@return` use a dedicated vermilion `docTag` token.

A lightweight TextMate grammar colors comments, strings, keywords, built-in
types, literals, numbers, functions, and operators immediately. Semantic
tokens then refine those colors; documentation/index analysis stays lazy until
Hover or Signature Help requests it.

Ownership-oriented tokens are exposed through semantic tokens:
- `ownershipRef` for `ref` and `&`
- `ownershipMut` for `mut` and `&mut`

Generic declarations and named imports are supported by the LSP. In particular,
`Vec<Node>` type arguments are highlighted as types, and uses such as
`vec_init<i32>(...)` do not produce syntax diagnostics. Completion is not
implemented yet.

`mymasm` files use a TextMate grammar and highlight:
- `import ...`
- `import ... from "..."`
- `export ...`
- imported symbol names
- exported symbol names
- import path strings

## Install locally (no packaging)
1. Run `npm install` in this directory.
2. Copy this folder to your user extensions dir (e.g. `~/.vscode/extensions/mylang-syntax`) or run `ln -s /workspaces/MyComputer-1/tools/vscode-mylang ~/.vscode/extensions/mylang-syntax`.
3. Reload VS Code. Files ending in `.mln` or `.mlx` should open as `MyLang` in the status bar.

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
