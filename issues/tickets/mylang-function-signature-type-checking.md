# MyLang Function Signature Type Checking

## 背景

MyLangCompiler の semantic stage は、未定義 identifier、未定義 function、引数個数、
return / assignment / binary / condition の基本的な型不一致を検出できるようになっている。

一方で、関数 signature の semantic 表現はまだ薄い。現状の `SemanticFunctionSig` は
関数名、引数数、可変長引数、import 状態を中心に持っており、各 parameter の型や return 型を
semantic symbol table として十分には保持していない。

そのため、関数呼び出しで「個数は合っているが型が違う」ケースを早い段階で正確に落としにくい。
OS API、device API、test assertion library、DOM 的 object API が増えるほど、この弱さは
開発時のバグ発見を遅らせる。

## 問題

次のようなコードを semantic stage で明確に診断したい。

```mylang
i32 add(i32 a, i32 b) {
    return a + b;
}

i32 main() {
    char* p = "x";
    return add(p, 1);
}
```

期待する診断は「`add` の第 1 引数は `i32` が必要だが `char*` が渡された」というもの。
単に codegen で変な assembly が出る、emulator 実行時に壊れる、曖昧な type mismatch になる、
という状態は避ける。

## 目標

- `SemanticFunctionSig` に parameter type list と return type を保持する。
- 関数呼び出し時に、引数個数だけでなく各引数の型互換性を検査する。
- 戻り値型を call expression の型推論に使う。
- import / extern / package import でも、分かる範囲で signature 情報を扱えるようにする。
- fail fixture で診断 code、位置、expected / actual を固定する。

## 非目標

- overload resolution は入れない。
- generic / template は扱わない。
- ABI 変更や calling convention 変更は扱わない。
- package 間の完全な型情報解決は別チケットに分ける。

## 設計方針

### 1. Signature 表現を拡張する

`SemanticFunctionSig` に以下を追加する。

- `SemanticTypeInfo return_type`
- `SemanticTypeInfo param_types[N]`
- `const char *param_names[N]`
- `int param_borrow_kinds[N]`（by-value / `ref` / `ref mut` を区別する）
- `int has_return_type`
- `int has_param_types`

固定長配列で始めてよい。既存の semantic context も固定長 table なので、まずは現行設計に合わせる。
上限超過時は semantic diagnostic として落とす。

`param_borrow_kinds` は本チケットの型検査では直接は使わないが、
`mylang-flow-sensitive-borrow-analysis.md` のフェーズ4（function call effects）が
call site の borrow / move effect を signature から読むために必要とする。
ここで signature に持たせておくことで、後続の borrow 解析が別途 signature 拡張を
行わずに済むようにする。

### 2. Function definition から signature を収集する

`AST_FUNDEF` を collect する段階で、parameter AST と return type AST から
`SemanticTypeInfo` を作る。

この段階で型 AST の解決に失敗した場合は、signature を不完全として登録しつつ診断を出す。
不完全 signature は後続の call check で二重に noisy な診断を出さないようにする。

### 3. Call expression を型検査する

`semantic_infer_expr_type()` または call 専用 helper で、以下を検査する。

- callee が既知関数か。
- non-variadic なら引数個数が一致するか。
- variadic なら fixed parameter 数以上か。
- fixed parameter の各引数が `semantic_typeinfo_compatible()` を満たすか。

診断例:

```text
E0102: function argument type mismatch: parameter 1 of 'add' expected i32, got char*
```

既存 code との整合:

- `E0101`: argument count mismatch
- 新規 `E0102`: argument type mismatch

診断 code は既存のカテゴリ別採番（`E00xx`=名前解決、`E01xx`=関数呼び出し、
`E02xx`=return、`E03xx`=式の型）に従う。`E0102` は `E01xx`（関数呼び出し）カテゴリに収まる。
`E04xx` 帯は `mylang-package-symbol-resolution.md` が package 診断用に予約するため、
本チケットでは使わない。採番規則の明文化は `mylang-diagnostic-code-registry.md` で扱う。

診断メッセージ中の parameter index は 1-based（`parameter 1`）で表示する。
これは human-readable CLI 出力の規約であり、
`mylang-lsp-semantic-diagnostics-integration.md` の JSON 出力（0-based range）とは
base が異なる点に注意する。

### 4. Return type を call expression の型に使う

関数呼び出し式の型推論で、既知 signature の return type を返す。
これにより、assignment / return / binary expression 側の検査も強くなる。

## 段階移行

### フェーズ1: Signature table 拡張

- `SemanticFunctionSig` に return / param type 情報を追加する。
- `register_function_sig()` を拡張する。
- 既存テストを通す。

### フェーズ2: Call argument type check

- call expression の semantic check に型検査を追加する。
- `phase_callArgTypeMismatch_fail.mln` を追加する。
- variadic fixed parameter の型検査を追加する。

### フェーズ3: Return type propagation

- call expression の型推論に signature return type を使う。
- call result を assignment / return に渡す fixture を追加する。

## 検証

1. `make -C toolchain/MyLangCompiler clean all`
2. `python3 toolchain/MyLangCompiler/tests/run_semantic_tests.py`
3. `python3 qa/mlc-test.py simpleFunc`
4. `python3 qa/mlc-test.py`

## 変更ファイル（想定）

- `toolchain/MyLangCompiler/inc/mylang/semantic/semantic_internal.h`
- `toolchain/MyLangCompiler/src/semantic/semantic_walk.c`
- `toolchain/MyLangCompiler/src/semantic/semantic_types.c`
- `toolchain/MyLangCompiler/tests/fail/semantic/*`

## 完了条件

- 関数呼び出しの引数型不一致が semantic error として出る。
- 診断に parameter index、関数名、expected type、actual type が含まれる。
- 既存の variadic / import / package fixture が壊れない。
- call expression の戻り値型を後続の型検査に使える。
