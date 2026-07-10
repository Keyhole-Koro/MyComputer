# MyLang Diagnostic Source Ranges

## 背景・目的

現在の診断は主に line / column の一点を指す。ユーザーが実際に直したいのは、識別子、引数、式、型注釈などの範囲なので、
diagnostic に source range を持たせる必要がある。

LSP diagnostics や将来のエラー表示を考えると、開始位置だけでなく終了位置も保持したい。

## スコープ

- AST node に start / end range を持たせる方針を決める。
- token から AST range へ位置情報を伝播する。
- semantic diagnostic に range を持たせる。
- identifier / call argument / assignment rhs / return expr から優先して range を埋める。
- range を使う fail fixture を追加する。

## 非スコープ

- 複数 range diagnostic。
- fix-it / quick fix。
- LSP 実装への接続。
- formatter 実装。

## 実装方針

1. `SourceLocation` / `SourceRange` の小さい構造体を compiler 内に作る。
2. 既存の `line` / `col` と互換を保ちながら、段階的に range 化する。
3. parser constructor が token start/end を受け取れるようにする。
4. semantic diagnostic は range がある場合は range を使い、ない場合は従来の line / col に fallback する。
5. テストでは最初から全 AST node を要求せず、重要ノードから埋める。

## 優先ノード

- identifier
- function call
- call argument
- variable declaration name
- assignment left / right
- return expression
- binary expression
- member access / arrow access

## 完了内容

- AST node に `end_line` / `end_col` を追加した。
- parser helper に token/child から range を設定する関数を追加した。
- identifier / call / literal / binary / unary / assignment / return などの主要 node に range を伝播した。
- semantic location に end 位置を持たせた。
- diagnostic 出力に既存形式を保ったまま `[range line:col-line:col]` suffix を追加した。
- semantic test で undefined identifier の range を確認するようにした。

## 完了時の検証

```sh
make -C toolchain/MyLangCompiler all
python3 toolchain/MyLangCompiler/tests/run_semantic_tests.py
python3 qa/mlc-test.py
```

## 関連

- `compiler-diagnostics-and-type-intelligence.md`
- `compiler-diagnostic-codes.md`
- `mylang-lsp-syntax-diagnostics.md`
