# Cross-Package Types And Constants

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
