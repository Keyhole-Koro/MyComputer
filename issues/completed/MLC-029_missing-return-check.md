# MLC-029: 値を返す関数の return 抜けを検出する

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Done | main | claude-code:opus-5.5 | 2026-11-07 |

## Summary

値を返す関数が `return` せずに末尾へ届いても、`mlc` は何も言わない。戻り値はレジスタに
残っていた値になる。到達可能性を判定して E0202 で止める。あわせて、戻らない関数を
`@noreturn` で宣言できるようにして、到達しない場所に書いていたダミーの `return` を
不要にする。

## Background

次のコードは `--Werror` を付けてもエラーにならない（2026-11-06 に `mlc` で確認）。

```c
i32 plain(i32 x) {
    if (x > 0) { return x; }
}
```

生成コードは `x <= 0` の時そのままエピローグへ落ちる。`Option` や `Result` を返す関数でも
同じことが起きるので、番兵値をやめても、`return` を書き忘れた経路には同じ種類のバグが残る。

逆に、到達しないのにコンパイラのために書いたように見える `return` もある。

- `toolchain/MyStdLib/sync/atomic.unsafe.mln:54`: `while (1)` の後の `return 0;`
- `system/MyKernel/src/kernel/thread.unsafe.mln:163`: `debug.panic(...)` の後の `return 0;`

## Design

### Current State

- `check_return_type`（`src/semantic/semantic_walk.c`）は、書かれた `return` の型しか見ない。
- `stmt_always_exits` は move の解析用で、`break` と `continue` も「抜ける」に含める。関数の
  末尾に届くかどうかの判定には使えない。
- `walk_block_items` の W0001 は、直前の文が `return`、`break`、`continue` の時だけ出る。
- `debug.panic` は `void` の関数で、戻らないことを型では表していない。本体の最後の
  `halt_cpu()` は `.masm` の関数なので、コンパイラからは中身が見えない。
- 列挙の網羅は、payload enum は `rewrite_payload_case`、数値の enum は
  `check_enum_case_coverage` が要求する。結果は AST に残っていない。
- `semantic_type_is_void` は `void *` も `void` と答えていた。このため `void *` を返す関数の
  `return (void *)x;` は E0201 になっていた。
- 関数リテラルは意味解析の前に `FUNDEF` へ下げられ、位置情報を持っていなかった。

### Proposed Design

`src/semantic/semantic_flow.c` に、文が次の文へ進めるかを返す判定を置く。

| 文 | 次へ進めるか |
| --- | --- |
| `return`、`break`、`continue` | 進めない |
| ブロック | 全部の文が進める時だけ |
| `if` | `else` が無いか、どちらかの枝が進める時 |
| `while (定数の真)`、条件のない `for`、`for (;定数の真;)` | その loop を抜ける `break` がある時だけ |
| `do ... while (定数の真)` | 同上 |
| その他の `do ... while` | 本体が進めるか、`continue` か `break` がある時 |
| `case` | `_` の腕も網羅も無い時と、進める腕がある時 |
| `@noreturn` の関数の呼び出し | 進めない |

- **E0202**: `void` でない関数の本体が末尾へ進める。関数リテラルも同じで、下げた
  `FUNDEF` に本体の位置を写す。名前は下げた後のもの（`g_lam0`）が出る。
- **E0203**: `@noreturn` の関数が戻れる（`return` がある、本体が末尾へ進める、`void` でない）。
- **W0001**: 同じ判定を使うので、`while (1)` の後や、両方の枝が `return` する `if` の後も
  到達しない文として報告する。消し忘れたダミーの `return` がこれで見つかる。
- `@noreturn` は `@safe` と同じく言語の属性で、メタデータの行にはならない。宣言の
  `fundef.is_noreturn` に載り、インポート先からは `SemanticFunctionSig.declaration` で読む。
- `case` は、網羅を確認した時に `case_expr.is_exhaustive` を立てる。
- `semantic_type_is_void` を `void` だけに直す。

### Alternatives Considered

- `never` 型: 式の型として扱うには型検査の全体に手が入る。今必要なのは「呼び出しの後へ
  進まない」ことだけなので、属性で足りる。
- 関数の末尾で trap するコードを生成する: 実行時まで分からず、書き忘れを防がない。
- `.masm` の関数にも `@noreturn` を付ける: `.masm` の import には宣言が無い。呼び出す
  `.mln` の関数の本体を `halt_cpu(); while (1) {}` にすれば足りる。

### Non-Goals

- ダミーの `return` の削除と、`debug.panic` などへの `@noreturn` の適用。検査が入った後の
  作業にする。mock や `--redirect-call` で差し替えた `panic` が戻ると、`@noreturn` の呼び出しの
  後へ進んでしまうので、適用の時にテストの差し替え方を確かめる。
- 番兵値から `Option` への移行（`Blob`、`hashmap.slot_of` など）。別の作業にする。
- 整数の `case` の網羅。`_` が無ければ、進めるものとして扱う。
- 定数畳み込みによる条件の判定。数値リテラルの条件だけを見る。
- generic の宣言への `@noreturn`。

## Progress

- [x] `semantic_flow.c` と E0202 / E0203
- [x] `@noreturn` の構文と、インポート先の関数への適用
- [x] W0001 の判定を同じものに置き換える
- [x] `void *` の判定の修正
- [x] fixture とドキュメント
- [x] `make -C toolchain/MyLangCompiler test-component`、`test-e2e`、`make qa`（2026-11-07）
- [x] コミット

検査を入れた時点で、`make build` の対象に E0202 は 0 件。W0001 は次の12文で、ダミーの
`return` を消す作業の対象になる。`debug.panic` の後の `return`（`thread.unsafe.mln:163`）は、
`@noreturn` を付けるまで出ない。

- `system/MyOS/src/fs/fs.unsafe.mln`: 382、743、744、841、842、878、973、974
- `system/MyKernel/src/kernel/thread.unsafe.mln`: 1025
- `system/MyOS/src/shell/app.unsafe.mln`: 715
- `system/MyOS/user/apps/echo.mln`: 22
- `toolchain/MyStdLib/sync/atomic.unsafe.mln`: 54

## Verification

```bash
make -C toolchain/MyLangCompiler test-component
make -C toolchain/MyLangCompiler test-e2e
make build
make qa
```

## 完了条件

- Background のコードが E0202 になる。
- `break` のない `while (1)` で終わる関数と、`@noreturn` の呼び出しで終わる関数は通る。
- `break` を持つ `while (1)` で終わる関数は E0202 になる。
- リポジトリ全体がビルドでき、`make qa` が緑になる。

## 関連

- MLC-023 `.unsafe.mln` と生ポインタの分離（`@safe`）
- MLC-028 構文の整理
