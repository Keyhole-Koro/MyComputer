# MyLang Native String (`str` / `String`)

> **[古い / STALE 2026-09-09] tickets/ から completed/ へ移動。本文は最新の実装状況を反映していません。**
> - 実装済み: フェーズ1「struct の値渡し・値返し」は commit `301b160
>   "Implement MLC-015: struct and array by-value parameters and returns"`
>   （2026-09-06）で実装済み。本文はまだ「値渡し・値返しは codegen error」と
>   記述しており矛盾している。
> - 未実装（残作業）: フェーズ2以降（aggregate initializer、cross-package 型解決、
>   `str` 自体の言語組み込み）は未着手。再着手する前に本文を書き直すこと。

## 背景

現在の MyLang の文字列は data セクションの NUL 終端バイト列へのポインタ（`char*`）
しかない。長さを持たないため `len` は毎回 O(n)、部分文字列はコピーなしに取れず、
NUL を含む文字列も表現できない。

実際の痛みはコードに出ていた。`MyOS/src/apps/counter.dom.mln` はラベル文字列を
手書きの10進バイト値で組み立てていたし、`str_eq` は `shell.mln` にローカル実装
されていた。MLC-004 phase 0（`str` / `strbuf` 等）でここは回収したが、それは
library で殴っただけで、言語としては何も変わっていない。

設計の全体像は `docs/design/mylang-stdlib-and-string.md` を参照。

## 問題

phase 0 の API 設計は compiler の制約で歪んでいる。実測で確認済み。

- **struct が package 境界を越えない。** import 側は typedef を学習しないので、
  `sb.SB b;` も `import { SB }` 後の `SB b;` も構文エラーになる。そのため
  `{ptr, len}` のような fat pointer を公開 API に置けない。
- **struct は値渡し・値返しができない。** 現状ポインタ経由のみ。2ワードを返す
  関数が書けない。
- **export した定数がリンクされない。** `ringbuf.HEADER` は
  `Undefined symbol 'ringbuf_HEADER'` になる。

この3つがある限り、`str` は library としても言語機能としても導入できない。

## 実測: struct 周りは「黙って間違える」状態だった

phase 1 の調査中に、エラーも警告も出さずに誤ったコードを吐く箇所が3つ見つかった。
いずれもビルドは通り、実行結果だけが違う。

```mylang
typedef struct { i32 x; i32 y; } P;

P a; a.x = 3; a.y = 4;
P b;
b = a;
return b.x + b.y;        // 7 のはずが 3
```

`gen_assign` が右辺を scalar として1ワードだけ load / store していた。
2番目以降のメンバは代入先の元の値が残る。

```mylang
i32 take(P p) { return p.x + p.y; }
take(a);                 // 7 のはずが 0x1FFFFFFB（スタックアドレス）
```

呼び出し側が1ワードしか渡さず、呼ばれた側はフレーム上の後続バイトを読む。

struct の値返しも同様に1ワードに切り詰められる。

**対応済み**（MyLangCompiler `fix/mlc-aggregate-assignment`）:

- 集約の代入は全バイトをコピーするようにした
- 値渡し引数・値返しは codegen error にした。呼び出し規約に memory argument
  形式と隠し戻り先ポインタが無い以上、黙って間違えるより落ちる方がよい

したがって本チケットのフェーズ1は「未実装を実装する」ではなく
「現在エラーにしてある2つを、正しい呼び出し規約とともに解禁する」作業になる。

## 目標

`str`（借用スライス）と `String`（所有）を導入する。

| layer | 表現 | 所有 |
| --- | --- | --- |
| `char*` | NUL 終端ポインタ | なし。FFI / MMIO 用に残す |
| `str` | `{u8* ptr; i32 len;}`（Copy） | 借用 |
| `String` | `{u8* ptr; i32 len; i32 cap;}` | 所有・heap |

## 非目標

- Unicode の正規化や grapheme cluster。`len` はバイト数、エンコーディングは
  UTF-8 とだけ決める。`chars()` イテレータは後続。
- `String` 本体（所有型）は本チケットの範囲外。drop フックと generics が要るので
  MLC-017 / MLC-018 に分ける。

## 段階

### フェーズ1: struct の値渡し・値返し

- 2ワードまではレジスタ返し、それ以上は sret ポインタ、といった呼び出し規約を決める
- 引数として struct を値で渡せるようにする
- **これが全ての前提。** 単独で先に入れて回帰を見る

### フェーズ2: aggregate initializer

- MLC-001 に依存。`str{ p, n }` を構築できるようにする

### フェーズ3: cross-package な型解決

- MLC-003 に依存。import 側が typedef と struct レイアウトを学習する
- ここまで来ないと `str` は宣言した package の外で使えない

### フェーズ4: `str` の言語組み込み

- 文字列リテラルの型を `str` にする
- **リテラルは NUL 終端を維持したまま長さを持たせる。** そうすれば同じリテラルが
  `str` としても `char*` としても妥当で、`debug.print("...")` を始めとする既存の
  カーネルコードが一行も壊れずに移行できる。コストはリテラルあたり1バイト
- `==` を `str` に対してバイト比較へ落とす
- 添字とスライスに境界チェック

### フェーズ5: std 側の追随

- `str` package を `char*` 版と `str` 版の両対応にし、段階的に寄せる

## 検証

1. `toolchain/MyLangCompiler/tests/run_integration_tests.py`
2. `python3 system/MyKernel/tests/libs/run_std_test.py`
3. `python3 system/MyOS/tests/fs/run_fs_smoke_test.py`
4. カーネル全体がビルド・起動すること

## 完了条件

- struct を値で渡し・返せる
- `str` が package をまたいで使える
- 文字列リテラルが `str` 型で、かつ既存の `char*` 呼び出しが壊れていない
- `docs/design/mylang-stdlib-and-string.md` の phase 1 が実装済みとして更新される

## 依存

- MLC-001 Aggregate Initializers
- MLC-003 Package Symbol Resolution
- MLC-005 Typed IR（先に入れると全体がかなり楽になる。必須ではない）
