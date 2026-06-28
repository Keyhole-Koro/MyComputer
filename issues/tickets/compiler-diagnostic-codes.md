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

## 非スコープ

- warning code の完全設計。
- 詳細な help text / explain command。
- JSON diagnostic output。

## 検証

1. `make -C toolchain/MyLangCompiler all`
2. `python3 toolchain/MyLangCompiler/tests/run_semantic_tests.py`
3. 既存 semantic fail fixture が code 付き表示で通ること。

## 関連

- `compiler-diagnostics-and-type-intelligence.md`
- `compiler-type-mismatch-diagnostics.md`
- `mylang-lsp-syntax-diagnostics.md`
