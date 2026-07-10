# MyDOMTranspiler `.mlx` UI DSL Compiler

## 背景・目的

OS DOM を MyLang から直接手続き的に組み立てると、UI の構造が読みにくくなりやすい。
MyLangCompiler 本体へ JSX 風構文をすぐ入れる代わりに、`toolchain/MyDOMTranspiler` を前段として使い、
`.mlx` の宣言的 UI 記述を通常の `.mln` source に変換する。

変換後の `.mln` は既存の MyLangCompiler / linker / emulator pipeline に流す。
また、MyLang source に JSX-like return を含めたい場合も入力は `.mlx` とし、
`return <Window ...>;` の部分だけを展開して、周辺の MyLang source を保持した `.mln` を生成する。

```text
app.mlx
  -> mydomc
app.generated.mln
  -> mlc
app.masm
```

```mylang
DomNode* screen() {
    return <Window title="Settings">
        <Button text="OK" />
    </Window>;
}
```

上は次のように、`return <...>;` の部分だけが DOM construction statement へ置き換わる。

```mylang
DomNode* screen() {
    DomNode* node0 = dom.create_node("Window");
    dom.set_str(node0, "title", "Settings");
    DomNode* node1 = dom.create_node("Button");
    dom.set_str(node1, "text", "OK");
    dom.append_child(node0, node1);
    return node0;
}
```

## 名前

- Project: `MyDOMTranspiler`
- Repository: `https://github.com/Keyhole-Koro/MyDOMTranspiler.git`
- Tool path: `toolchain/MyDOMTranspiler`
- Source extension: `.mlx`
- Initial command name: `mydomc`

`.mlx` は JSX-like DOM syntax を含められる MyLang source として扱う。

## 最小構文

最初は静的 DOM tree だけを対象にする。

```mlx
<Window title="Settings" width={320} height={200}>
    <Button id="ok" text="OK" onClick={handle_ok} />
</Window>
```

初期段階では、以下を扱う。

- JSX-like opening / closing tags
- self-closing tags
- string props
- `{number}` / `{identifier}` props
- nested children
- event handler symbol reference

## 変換イメージ

```mylang
DomNode* root = dom.create_window("Settings", 320, 200);
DomNode* ok = dom.create_button("ok", "OK");
dom.set_on_click(ok, handle_ok);
dom.append_child(root, ok);
```

実際の出力 API 名は `system/MyOS/src/ui/dom.mln` または `system/MyKernel/src/...` 側の
DOM API に合わせて決める。

## 段階移行

### フェーズ1: MyDOMTranspiler tool skeleton

- `toolchain/MyDOMTranspiler` を build できる状態にする。
- `mydomc input.mlx -o output.mln` の CLI を用意する。
- 最小 parser / diagnostics / golden test を追加する。

### フェーズ2: Static DOM lowering

- `Window` / `Button` / `Text` など最小 element を `.mln` に落とす。
- props を DOM node の属性設定に変換する。
- children を `append_child` に変換する。

### フェーズ3: Build integration

- `qa/build_toolchain.py` が `.mlx` を見つけたら先に `mydomc` を実行する。
- generated `.mln` を既存の MyLangCompiler 入力に含める。
- generated file の出力先を `qa/outputs/` 配下などに固定する。
- `qa/run_mylang.py` / `qa/test-all.py` が MyDOMTranspiler を通常 toolchain として build / test する。

### フェーズ4: OS DOM integration

- MyOS / MyKernel の小さい UI sample を `.mlx` で書く。
- DOM renderer / event dispatch と接続する。
- `onClick` の handler symbol が既存 MyLang 関数へ解決されることを確認する。

### フェーズ5: Editor / LSP integration

- VS Code extension が `.mlx` を MyLang family の source として開く。
- LSP server が `.mlx` を MyDOMTranspiler で検証し、diagnostics を publish する。
- `.mlx` の JSX-like tag / prop / number / operator を semantic token として返す。
- `.mlx` の top-level DOM tags を document symbol として返す。

## 非目標

- MyLangCompiler 本体への JSX 構文追加。
- HTML / CSS / JavaScript 互換。
- 条件分岐、ループ、component state、style cascade。
- full LSP support。まずは CLI diagnostics と golden tests を優先する。

## 検証

1. `make -C toolchain/MyDOMTranspiler all`
2. `toolchain/MyDOMTranspiler/build/mydomc sample.mlx -o sample.generated.mln`
3. `make -C toolchain/MyLangCompiler all`
4. `toolchain/MyLangCompiler/mlc sample.generated.mln sample.masm`
5. `.mlx -> .mln` の golden output test を追加して通す。

## 変更ファイル（想定）

- `toolchain/MyDOMTranspiler/*`
- `qa/build_toolchain.py`
- `system/MyOS/src/**/*.mlx`
- `system/MyOS/docs/*`
- `issues/tickets/dom-like-os.md`
- `issues/tickets/mykernel-ui-automation.md`

## 完了条件

- `.mlx` から `.mln` へ deterministic に変換できる。
- 静的 DOM tree の最小 sample が MyLangCompiler で compile できる。
- build pipeline が `.mlx` を自動変換できる。
- OS DOM sample が MyDOMTranspiler 経由で構築される。
