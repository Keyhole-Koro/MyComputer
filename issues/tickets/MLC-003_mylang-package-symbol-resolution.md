# MyLang Package Symbol Resolution

## 背景

MyLang には `package` / `import` / `export` があり、複数ファイルの compilation と symbol rewrite が
既に存在する。integration tests でも `import from` や package sample が通っている。

一方で semantic stage の package import 判定には、imported package 名と symbol prefix の
名前規約に依存する部分がある。関数 signature、型定義、struct / enum、global symbol が増えると、
名前文字列だけで扱う方式は診断と型検査の限界になる。

今後、OS API、library、UI object、test helper を package として整理するなら、package 単位の
symbol table と import/export 解決を compiler の土台として持ちたい。

## 問題

次のようなケースで、正確な診断と型情報が必要になる。

- import した関数の引数型を call site で検査したい。
- import した struct / enum 型を semantic type として解決したい。
- export されていない symbol を import した時に明確な error を出したい。
- package prefix rewrite 後の名前ではなく、source 上の名前で診断したい。
- 同名 symbol の衝突を package scope で説明したい。

## 目標

- package / file 単位の symbol table を設計する。
- export symbol と local symbol を区別する。
- import 解決時に signature / type 情報を semantic へ渡す。
- package prefix rewrite と source-level symbol identity の対応を保持する。
- package import の失敗診断を改善する。

## 非目標

- separate compilation cache は最初は扱わない。
- dynamic linking は扱わない。
- cyclic import の高度な解決は後回しにする。まず検出して error にする。

## 設計方針

### 1. Symbol identity を明示する

source 上の名前と lowered / rewritten name を分ける。

```text
source: math.add
lowered: math_add
kind: function
exported: true
```

semantic diagnostics は source name を優先して表示する。
codegen / linker symbol は lowered name を使う。

### 2. Symbol kind を持つ

最低限、以下を区別する。

- function
- global variable
- typedef
- struct
- enum
- enum member

function symbol は `mylang-function-signature-type-checking.md` の signature 情報を持つ。

### 3. Import resolution を parser-local rewrite から分離していく

現行の parser rewrite をすぐ捨てる必要はない。
まずは rewrite 結果を symbol table に記録し、semantic が名前規約ではなく table を見られるようにする。

### 4. Failure diagnostics を強くする

package 診断は `E04xx` カテゴリを予約して使う。既存の採番（`E00xx`=名前解決、
`E01xx`=関数呼び出し、`E02xx`=return、`E03xx`=式の型）と衝突しない新カテゴリとする。
`E04xx` 帯の予約は本チケットが確定させ、他チケット（ISSUE-016 等）はこの帯を使わない。
採番規則そのものの明文化は `mylang-diagnostic-code-registry.md` で扱う。

例:

```text
E0401: package 'math' does not export symbol 'mul'
E0402: ambiguous symbol 'init' imported from 'a' and 'b'
E0403: cyclic import detected: a -> b -> a
```

## 段階移行

### フェーズ1: 現行 import/export behavior の棚卸し

- 既存 package tests を整理する。
- source name と lowered name の対応を docs に書く。

### フェーズ2: Symbol table prototype

- function / type / global の export symbol を収集する。
- import from の解決結果を table に記録する。

### フェーズ3: Semantic integration

- imported function signature を call check で使う。
- imported type を `SemanticTypeInfo` 解決で使う。

### フェーズ4: Diagnostics

- unresolved import
- non-exported import
- duplicate import
- cyclic import

## 検証

1. `python3 qa/mlc-test.py`
2. `python3 toolchain/MyLangCompiler/tests/run_semantic_tests.py`
3. package fail fixture を追加する。

## 変更ファイル（想定）

- `toolchain/MyLangCompiler/inc/mylang/frontend/parser_state_internal.h`
- `toolchain/MyLangCompiler/src/frontend/parser/parser_state_*.c`
- `toolchain/MyLangCompiler/src/frontend/parser/parser_rewrite*.c`
- `toolchain/MyLangCompiler/src/semantic/semantic_walk.c`
- `toolchain/MyLangCompiler/tests/succeed/package/*`
- `toolchain/MyLangCompiler/tests/fail/semantic/*`

## 完了条件

- import した関数の signature が semantic call check に使われる。
- import した user type が semantic type として解決される。
- import/export の失敗が source-level name で診断される。
- 既存 package integration tests が通る。
