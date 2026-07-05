# MyLang Aggregate Initializers And Data Layout

## 背景

MyLangCompiler は `u8` / `u16` / `i32` などの scalar、array、struct を扱える。
global data emission も存在し、配列 initializer については要素幅に応じた `.byte` emission が
一部実装されている。

ただし、`codegen_data.c` には scalar 以外の global initializer がまだ素朴であることを示す
TODO が残っている。struct、nested array、array of struct、部分 initializer などを正しく扱うには、
型情報に基づく aggregate layout と initializer lowering が必要になる。

OS / device / framebuffer / filesystem の定数 table が増えるほど、global aggregate を安全に
初期化できることが重要になる。

## 問題

次のような initializer を正確に data section へ落としたい。

```mylang
struct Point {
    i32 x;
    i32 y;
};

Point origin = { 0, 0 };
u8 palette[4] = { 0, 64, 128, 255 };
Point points[2] = { { 1, 2 }, { 3, 4 } };
```

必要なこと:

- field order に沿った byte emission
- element width に沿った array emission
- 不足要素の zero fill
- 過剰要素の semantic error
- 型と initializer shape の mismatch 診断

## 目標

- aggregate initializer を型情報に基づいて flatten する。
- struct / array / nested aggregate の global initializer を扱う。
- initializer の要素数過不足を semantic stage で診断する。
- codegen は flatten 済みの byte列、または型 guided traversal で deterministic に emit する。
- data layout の fixture を追加する。

## 非目標

- designated initializer（`.x = 1`）は最初は扱わない。
- runtime expression を global initializer に許可しない。
- padding / alignment の高度な ABI 互換は別途扱う。まず現行 VM の layout に合わせる。

## 設計方針

### 1. Layout helper を共有する

backend には `TypeInfo` と size 計算 helper がある。aggregate initializer でも同じ規則を使う。

必要に応じて以下を整理する。

- scalar width
- array element size
- struct field offset
- total size

semantic と codegen で別々の layout 規則を持つとずれるため、まずは helper の責務を明確にする。

### 2. Semantic で shape を検査する

codegen で黙って zero fill する前に、semantic stage で明らかな mismatch を落とす。

- scalar に `{ ... }` が渡された。
- array initializer の要素が多すぎる。
- struct initializer の要素が多すぎる。
- field type と initializer type が合わない。

不足分は C と同じく zero fill として扱う方針でよい。

### 3. Codegen は型 guided に emit する

`emit_global_init()` を scalar 前提から、型情報を受け取る形へ寄せる。

候補:

```c
emit_global_init_for_type(StringBuilder *sb, TypeInfo *type, ASTNode *init)
```

array / struct は再帰的に要素を emit し、不足分を zero fill する。

## 段階移行

### フェーズ1: 現行 layout の fixture 化

- `u8[]` / `u16[]` / `i32[]` の global initializer fixture を追加する。
- 既存 behavior を固定する。

### フェーズ2: Semantic shape check

- array initializer の過剰要素を error にする。
- scalar / aggregate mismatch を error にする。

### フェーズ3: Struct initializer

- struct field order に沿って global data を emit する。
- struct initializer の不足分 zero fill を実装する。

### フェーズ4: Nested aggregate

- array of struct
- nested array
- struct with array field

## 検証

1. `make -C toolchain/MyLangCompiler clean all`
2. `python3 qa/mlc-test.py`
3. `python3 toolchain/MyLangCompiler/tests/run_semantic_tests.py`
4. data section 出力を確認する targeted fixture を追加する。

## 変更ファイル（想定）

- `toolchain/MyLangCompiler/src/backend/codegen/codegen_data.c`
- `toolchain/MyLangCompiler/src/backend/codegen/codegen_type_*.c`
- `toolchain/MyLangCompiler/src/semantic/semantic_walk.c`
- `toolchain/MyLangCompiler/tests/succeed/global/*`
- `toolchain/MyLangCompiler/tests/fail/semantic/*`

## 完了条件

- struct global initializer が正しい byte列になる。
- nested aggregate initializer が再帰的に emit される。
- 要素過剰や shape mismatch が semantic error になる。
- 不足要素は zero fill される。
