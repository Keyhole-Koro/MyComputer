# MyLang Warning Diagnostics

## 背景・目的

コンパイラが error だけを出す段階から、warning も扱える段階へ進める。
OS や UI のコード量が増える前に、未使用変数や到達不能コードを早めに検出できると、言語と標準ライブラリの開発速度が上がる。

## スコープ

- diagnostic severity に `warning` を正式追加する。
- warning count を持つ。
- warning を表示するが、デフォルトではコンパイル成功扱いにする。
- `--Werror` 相当のオプションを検討・実装する。
- 最初の warning として未使用ローカル変数、または到達不能コードを追加する。

## 初期 warning 候補

- unused local variable
- unreachable statement after `return`
- unused function parameter
- implicit narrowing conversion
- shadowed variable

最初は false positive が少ないものから入れる。候補としては `unreachable statement after return` が最も安全。

## 実装方針

1. `SemanticDiagnosticSeverity` の表示と集計を整理する。
2. driver の終了コードを `error_count > 0` 基準にする。
3. warning 用 helper を追加する。
4. `--Werror` または `--warnings-as-errors` を driver option として追加する。
5. fail ではなく warning fixture のテスト分類を作る。

## 非スコープ

- lint 専用サブコマンド。
- warning suppression annotation。
- 全 warning の一括実装。
- LSP warning 表示への接続。

## 検証

1. `make -C toolchain/MyLangCompiler all`
2. `python3 toolchain/MyLangCompiler/tests/run_semantic_tests.py`
3. warning fixture がコンパイル成功しつつ warning を出すこと。
4. `--Werror` 指定時に warning が非ゼロ終了になること。
5. `python3 qa/mlc-test.py`

## 関連

- `compiler-diagnostics-and-type-intelligence.md`
- `compiler-diagnostic-codes.md`
- `compiler-diagnostic-ranges.md`
