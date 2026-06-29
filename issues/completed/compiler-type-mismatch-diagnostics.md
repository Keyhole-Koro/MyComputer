# MyLang Type Mismatch Diagnostics

## 背景・目的

MyLangCompiler の意味解析は、未定義識別子・関数呼び出し・return の一部を診断できるようになってきた。
次は型不一致を semantic stage で明確に検出し、codegen まで進んでから壊れるケースを減らす。

このチケットでは、代入・二項演算・条件式を中心に「期待した型」と「実際の型」を出す。

## スコープ

- 代入の左右型不一致を診断する。
- 変数初期化の型不一致を診断する。
- 二項演算の operand 型不一致を診断する。
- `if` / `while` / 三項演算子など、条件式に使える型を検査する。
- 診断メッセージに expected / actual を含める。
- fail fixture を追加する。

## 非スコープ

- 暗黙変換ルールの大規模設計。
- `i8` / `i16` の追加。
- optimizer / IR 導入。
- LSP 表示形式の変更。

## 実装方針

1. semantic の型推論・型取得 helper を整理する。
2. `semantic_types_compatible(expected, actual)` のような比較 API を作る。
3. 型名を診断用文字列へ変換する helper を用意する。
4. assignment / initializer / binary op / condition の順に検査を足す。
5. 既存 succeed fixture が壊れた場合は、暗黙変換として許可すべきか、テストが緩すぎたかを切り分ける。

## 期待する診断例

```text
error: type mismatch: expected i32, got *u8
error: invalid operands to '+': i32 and *u8
error: condition must be integer-like, got struct Button
```

## 検証

1. `make -C toolchain/MyLangCompiler all`
2. `python3 toolchain/MyLangCompiler/tests/run_semantic_tests.py`
3. `python3 qa/mlc-test.py`
4. 型不一致の fail fixture で expected / actual が出ること。

## 完了内容

- semantic binding に宣言型を保持するようにした。
- semantic walker に簡易式型推論を追加した。
- initializer / assignment / binary op / condition / return の型不一致診断を追加した。
- expected / actual 付きの型名表示を追加した。
- 既存の enum 整数利用、配列添字 lowering、文字列 literal、pointer-as-int 用途を壊さない互換ルールを入れた。
- 型不一致 fail fixture を追加した。

## 完了時の検証

```sh
make -C toolchain/MyLangCompiler all
python3 toolchain/MyLangCompiler/tests/run_semantic_tests.py
python3 qa/mlc-test.py
```

## 関連

- `compiler-diagnostics-and-type-intelligence.md`
- `compiler-diagnostic-codes.md`
- `compiler-diagnostic-ranges.md`
