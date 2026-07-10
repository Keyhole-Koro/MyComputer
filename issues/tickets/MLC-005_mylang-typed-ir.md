# MyLang Typed Intermediate Representation

## 背景

MyLangCompiler は現在、AST から直接 assembly を生成している。
この構成は小さい言語機能を素早く実装するには有効だが、型情報を使った lowering、最適化、
制御フロー解析、register / stack discipline の改善を進めるにつれて、backend に複雑さが集まりやすい。

semantic stage が強くなってきた今、次の段階として typed IR を検討する価値がある。

## 問題

AST 直結 codegen では、以下が難しくなりやすい。

- expression の型と値カテゴリを backend 全体で一貫して扱う。
- pointer arithmetic / array indexing / struct field access を低レベル操作へ整理する。
- short-circuit、case、statement expression、lambda lowering などを統一的に扱う。
- dead code elimination や constant folding を安全に入れる。
- codegen failure を semantic error と分離する。
- assembly emission 前に backend-level test を書く。

## 目標

- typed IR の最小設計を作る。
- AST から typed IR への lowering phase を追加する。
- 最初は最適化なしで、現行 assembly と同じ挙動を保つ。
- IR dump を debug / test 用に出せるようにする。
- 段階的に一部 construct だけ IR 経由へ移行できるようにする。

## 非目標

- 最初から SSA にしない。
- 高度な register allocation は扱わない。
- 全 backend を一気に置き換えない。
- VM / ISA 変更は扱わない。

## 設計方針

### 1. まずは低レベル typed tree / linear IR にする

最初から本格 SSA を作るより、以下を明示できる最小 IR で始める。

- typed temporary
- load / store
- address-of
- call
- branch / label
- return
- binary / unary op
- aggregate address calculation

### 2. Source location を保持する

IR node には source location を持たせる。
backend error や future warning を source 上の位置へ戻せるようにする。

### 3. AST lowering と assembly emission を分ける

新しい流れ:

```text
lexer -> parser -> semantic -> ir lowering -> ir validation -> asm emission
```

初期段階では feature flag または internal option で IR dump だけを出せるようにする。

### 4. 移行単位を小さくする

最初に IR 化する候補:

- scalar expression
- assignment
- return
- if / while

後回し:

- lambda / function literal
- complex package lowering
- aggregate initializer

## 段階移行

### フェーズ1: IR design doc

- IR instruction set
- type representation
- value category
- control flow representation
- dump format

### フェーズ2: IR data structures

- `inc/mylang/ir/`
- `src/ir/`
- memory management / dump helper

### フェーズ3: Expression lowering prototype

- number / identifier / binary / assignment / return を IR 化する。
- assembly output はまだ現行 codegen のままでよい。

### フェーズ4: IR-backed emission

- simple function fixture を IR 経由で assembly emission する。
- `simpleFunc` / `simpleBinop` / `simpleCondition` を通す。

### フェーズ5: Gradual migration

- array / pointer / struct
- call
- control flow
- aggregate

## 検証

1. `make -C toolchain/MyLangCompiler clean all`
2. `python3 qa/mlc-test.py simpleFunc`
3. `python3 qa/mlc-test.py`
4. IR dump golden tests を追加する。

## 変更ファイル（想定）

- `toolchain/MyLangCompiler/inc/mylang/ir/*`
- `toolchain/MyLangCompiler/src/ir/*`
- `toolchain/MyLangCompiler/src/driver/*`
- `toolchain/MyLangCompiler/src/backend/codegen/*`
- `toolchain/MyLangCompiler/tests/*`

## 完了条件

- typed IR の design doc がある。
- simple scalar function を AST から IR に lower できる。
- IR dump が deterministic に出る。
- 少なくとも 1 つの既存 integration fixture を IR 経由で実行できる。
