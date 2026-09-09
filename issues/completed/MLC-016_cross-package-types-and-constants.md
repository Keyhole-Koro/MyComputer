# Cross-Package Types And Constants

> **[古い / STALE 2026-09-09] tickets/ から completed/ へ移動。本文は最新の実装状況を反映していません。**
> - 実装済み: 問題#2（`export i32 HEADER` のような定数の越境利用）は実機確認済み
>   ——export/import されリンクまで通る。
> - 未実装（残作業）: 問題#1（`sb.SB b;` のような型の越境）は依然
>   `error: expected ';' after expression` で失敗（実機確認済み）。[[MLC-017]] と
>   同じ穴が残っている。再着手する前に本文を書き直すこと。

## 背景

MyLang の `import pkg from "path.mln"` は **package 名前空間を登録するだけ**で、
import 側は相手の型も定数も学習しない。シンボルは `pkg_name` に mangle されて
リンクされるが、リンクされるのは関数だけ。

MLC-004 phase 0 の実装中に実測で確認した。

## 問題

### 1. 型が越境しない

```mylang
// sb.mln
export typedef struct { i32 cap; i32 len; } SB;

// main.mln
import sb from "sb.mln";
sb.SB b;                    // error: expected ';' after expression

import { SB } from "sb.mln";
SB b;                       // error: expected ';' after expression
```

`parser_dom_sig.c` のコメントも「imports only register a package namespace」と
書いている。

影響: library が struct を公開 API に置けない。MLC-004 phase 0 は全ての状態を
呼び出し側の配列に置き `i32*` / `char*` のハンドルとして渡す設計になったが、
これは型安全性を捨てている。`str` / `Vec` / `Option` は全てここで詰まる。

### 2. 定数が越境しない

```mylang
// ringbuf.mln
export i32 HEADER = 3;

// caller
ringbuf.HEADER              // Undefined symbol 'ringbuf_HEADER'
```

`MyOS/src/ui/dom.mln:27` が enum member について同じことを既に書いている
（"enum members do not survive cross-package linking"）。リポジトリ全体を見ても
package 修飾された定数参照は一件も存在しない。

影響: サイズ・タグ・enum が全て「呼び出し側にリテラルを書かせる」か
「関数で包む」しかない。`fs.mln` が `SEEK_SET` 等を export しているのは
実質デッドコード。

## generics を cross-package で使うための段取り

MLC-004 phase 0 の std library が generics を使えていないのは本チケットの制約が
理由。`src/lib/` に置いて `serial.mln` / `fs.mln` から呼ぶ以上 cross-package になる。
module-local な instantiation は実装済み（MyLangCompiler #18）だが、package を
またぐと `genlib.pick<i32>(7, 9)` が `error: expected primary` で落ちる。

### 段1: `pkg.func<T>(args)` の構文

`parser_expr_postfix.c` の DOT 分岐が `genlib.pick` を識別子 `genlib_pick` に畳んだ
あと、`<` を扱わずに抜ける。結果 `<` が比較演算子として解釈される。
`parse_identifier_primary` にある generic 呼び出しの処理と同じものが要る。

### 段2: import 先テンプレートの読み込み（本命の難所）

`parser_toplevel.c` の `import_path_declares_package` が既に `lexer_from_file` で
import 先を読んでいる。ここで generic 宣言も拾い、`g_generic_template_table` に
`pkg_name` で登録する。

問題は、これが「解析中に別の翻訳単位を読み込む」操作であること。パーサは単一
翻訳単位を前提にしたグローバル状態を持っており、退避・復元が要るものが23個ある。

```
token_head root g_struct_table g_func_table g_type_table
g_generic_template_table g_generic_decl_depth g_current_generic_function_name
g_stop_at_arrow g_unchecked_depth g_current_package g_current_package_heap
g_exports g_export_count g_imported_packages g_imported_pkg_count
g_hoisted_funcs g_hoisted_count g_funlit_counter g_parse_filename
g_enum_constants g_enum_constant_count
```

さらに import 先がまた import しているので、再帰の深さ制限と訪問済み集合が要る。

`parser_dom_sig.c` の TODO が同じ問題を指している ——
「cross-package lookup は DOM lowering・型チェック・import が共有する解決層に
属する。それが無いのでこれは DOM ローカルに留める」。段2 は事実上その共有解決層を
作る作業で、MLC-003 と同じ的。

### 段3: 特殊化シンボルの重複 — **完了**

MyLinker #2 で対応済み。`__mlg_` 接頭辞の重複定義は最初の1つを採用し、以降を
スキップする。C++ の COMDAT のシンボル側に相当する。捨てた側のコード実体は
イメージに残る（オブジェクト形式が関数ごとのセクションを持たないため）。
それ以外の名前の重複は今までどおりエラー。

### 段4: テンプレート本体が参照する package ローカル関数

`Vec.push<T>` が同じ package の `grow()` を呼んでいる場合、複製した本体は
importing 側に存在しない `grow` を参照する。複製時に自由識別子を元 package で
修飾する必要がある。

## 目標

- import 側が typedef / struct / enum のレイアウトを学習する
- export した定数と enum member がリンクされる
- `pkg.Type` と `import { Type } from` の両方の記法を決めて実装する

## 非目標

- 完全な module system の再設計。既存の path ベース import の形は変えない。

## 検証

- `toolchain/MyLangCompiler/tests/succeed/package/` に型と定数を跨いで使う
  fixture を追加する
- 非 export シンボルの import が fail fixture になる

## 完了条件

- 上記2つの再現コードがコンパイル・リンクを通る
- `export i32 HEADER` が消えている ringbuf 等の library で、export された定数を
  呼び出し側が使えるようになる
- MLC-015 phase 3 の前提が満たされる

## 依存

- MLC-003 Package Symbol Resolution（本チケットはその具体化）
