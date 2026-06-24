# MyLang Compiler Diagnostics And Type Intelligence

## 背景・目的

DOM 的 OS オブジェクトモデルや mylang UI リテラルを作る前に、MyLangCompiler を
「壊れたコードや型の不整合を正確に説明できる」状態へ引き上げる。

現状の compiler は `lexer -> parser -> semantic -> codegen` の段階分離があり、
semantic stage も存在する。一方で、AST は役割情報を持つものの位置情報が薄く、
診断は「どこが、なぜ悪いか」を十分に伝えきれない。今後 UI literal、OS API、所有権、
イベントハンドラなどを足すと、診断の弱さが開発速度を直接落とす。

ゴールは、最適化や大きな新構文の前に、**位置つき AST・構造化診断・型チェック強化**を
compiler の土台として入れること。

## スコープ

最初の対象：

- AST node に `line` / `col` を確実に通す。
- semantic error に file / line / col / message を持たせる。
- 未定義シンボル、型不一致、関数呼び出し引数不一致を正確な位置で出す。
- `u8` / `u16` の型表現を拡張する。`i8` / `i16` は必要になってから追加する。
- fail fixture を追加して、診断が退化しないようにする。

このチケットでは IR 導入や大規模最適化は扱わない。IR は診断と型情報が安定してから
別チケットにする。

## 設計方針

### 1. AST 位置情報を標準化する

`ASTNode` には既に `line` / `col` がある。まず全 constructor がこの値を正しく埋める
ようにする。

重点箇所：

- identifier
- var decl
- fundef
- param
- call
- member access / arrow access
- typedef / struct / enum
- string / char / number literal

parser helper は可能なら Token を受け取り、`token->line` / `token->col` を AST へ通す。
名前だけ `char*` で渡して位置を落とす経路を減らす。

### 2. 診断を構造化する

semantic stage に診断蓄積 API を用意する。

```c
typedef struct SemanticDiagnostic {
    char *file;
    int line;
    int col;
    char *message;
} SemanticDiagnostic;
```

最初は warning/error の区別なしでもよい。複数エラーを溜められる形にして、
driver が最後にまとめて出力する。

### 3. 型チェックを semantic へ寄せる

codegen 中に暗黙に失敗するより、semantic で早く落とす。

最初に強化するもの：

- 未定義 identifier
- 未定義 function
- 関数呼び出しの引数個数不一致
- return 型の不一致
- assignment の左右型不一致
- pointer / ref / array の明らかな不整合

### 4. 小さい整数型を入れる

`u8` / `u16` は OS / device / framebuffer / binary protocol で必要になる。符号付きの
`i8` / `i16` は符号拡張や比較ルールを詰める必要があるため、必要になってから追加する。

実装候補：

- lexer の keyword に追加する。
- parser の primitive type に追加する。
- semantic type 表現に bit width と signedness を持たせる。
- codegen は当面 16/32bit word 上に載せる。メモリ load/store の幅は別途詰める。

## 段階移行

### フェーズ1: AST 位置情報の棚卸し

- `new_*` constructor の一覧を作る。
- line / col が 0 のままになる node をテストで可視化する。
- identifier / call / decl から優先して位置を埋める。

### フェーズ2: Semantic diagnostics API

- semantic context に diagnostic list を追加。
- `semantic_error_at(node, "...")` のような helper を作る。
- driver が semantic diagnostics を表示して非ゼロ終了する。

### フェーズ3: 型チェック強化

- symbol lookup の失敗を位置つき診断にする。
- function call の引数個数・基本型を検査する。
- assignment / return の型不一致を検査する。

### フェーズ4: 整数型拡張

- `u8` / `u16` を primitive type に追加。
- semantic type に width / signedness を保持する。
- 既存テストが壊れないことを確認する。

## 検証

1. `make -C toolchain/MyLangCompiler clean all`
2. `python3 qa/mlc-test.py`
3. `python3 toolchain/MyLangCompiler/tests/run_semantic_tests.py`
4. fail fixture で、未定義名・引数不一致・return 型不一致の位置が期待通り出ること。
5. 既存の succeed fixture がすべて通ること。

## 変更ファイル（想定）

- `toolchain/MyLangCompiler/inc/mylang/ast/AST.h`
- `toolchain/MyLangCompiler/src/ast/AST.c`
- `toolchain/MyLangCompiler/inc/mylang/frontend/parser_ast_internal.h`
- `toolchain/MyLangCompiler/src/frontend/parser/parser_ast_*.c`
- `toolchain/MyLangCompiler/src/frontend/parser/parser_expr_*.c`
- `toolchain/MyLangCompiler/src/frontend/parser/parser_decl.c`
- `toolchain/MyLangCompiler/inc/mylang/semantic/*`
- `toolchain/MyLangCompiler/src/semantic/*`
- `toolchain/MyLangCompiler/src/driver/*`
- `toolchain/MyLangCompiler/tests/fail/semantic/*`

## 関連

- `mylang-lsp-syntax-diagnostics.md`
- `dom-like-os.md`
