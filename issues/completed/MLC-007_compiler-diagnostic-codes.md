# MyLang Diagnostic Error Codes

## 背景・目的

診断メッセージが増えると、文字列だけでテスト・ドキュメント・LSP 連携を維持するのが難しくなる。
エラーに安定した code を付けることで、ユーザー向け説明、回帰テスト、エディタ連携を扱いやすくする。

## スコープ

- semantic diagnostic に `code` を持たせる。
- 最初の code table を定義する。
- 既存の semantic error に code を割り当てる。
- テストで code とメッセージの両方を確認できるようにする。
- code 一覧を docs または issues 内に置く。

## 初期コード案

| Code | Meaning |
| --- | --- |
| E0001 | undefined identifier |
| E0002 | undefined function |
| E0101 | function argument count mismatch |
| E0102 | function argument type mismatch |
| E0201 | return type mismatch |
| E0301 | assignment type mismatch |
| E0302 | invalid binary operand types |
| E0303 | invalid condition type |

番号は最初から完璧にしない。後で増やせるように、カテゴリ単位で余白を残す。

## 実装方針

1. `SemanticDiagnostic` に code field を追加する。
2. `semantic_error_at` とは別に、code 付き helper を追加するか、既存 helper の引数を拡張する。
3. 表示形式を決める。

例:

```text
main.mln:2:13: error[E0001]: undefined identifier 'foo'
```

4. 既存 fail fixture の期待値を必要最小限更新する。
5. code table の重複を避けるため、enum または定数定義に寄せる。

## 完了内容

- `SemanticDiagnostic` に `code` field を追加した。
- `semantic_error_code_at(ctx, loc, code, ...)` を追加した。
- 表示形式を `error[E0001]: ...` にした。
- 既存の主要 semantic diagnostics に初期コードを割り当てた。
- semantic fail tests の期待値を code 付き表示へ更新した。

## 実装済みコード

| Code | Meaning |
| --- | --- |
| E0001 | undefined identifier |
| E0002 | undefined function |
| E0101 | function argument count mismatch |
| E0102 | function argument type mismatch |
| E0201 | return type mismatch |
| E0301 | assignment / initializer type mismatch |
| E0302 | invalid binary operand types |
| E0303 | invalid condition type |

`E0102` は ISSUE-016 で実装済み。

## 非スコープ

- warning code の完全設計。
- 詳細な help text / explain command。
- JSON diagnostic output。

## 完了時の検証

```sh
make -C toolchain/MyLangCompiler all
python3 toolchain/MyLangCompiler/tests/run_semantic_tests.py
python3 qa/mlc-test.py
```

## 関連

- `compiler-diagnostics-and-type-intelligence.md`
- `compiler-type-mismatch-diagnostics.md`
- `mylang-lsp-syntax-diagnostics.md`
