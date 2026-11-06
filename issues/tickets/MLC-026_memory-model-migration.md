# MLC-026: 既存コードを値だけのモデルへ移す

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| In Progress | main | - | 2026-11-06 |

> `mylang-values.md` を採用した。共有値（MLC-025）を待たずに進められる部分を先に移した。

## Summary

MLC-025 の共有値・`Box`・プールができたら、既存のコードを移す。`heap.alloc` で作っている
ものを `new`・`Vec`・`Pool` に、ポインタでつないでいるものをハンドルに、`char *` の文字列を
`str`・`Text<N>`・`String` に置き換える。生ポインタを unsafe に寄せる作業は MLC-023 で続ける。

## Background

2026-10-30 の時点の数:

- `heap.alloc` / `heap.free`: `system/` 以下で約25箇所（DOM のノード、要素のバッファなど）。
- `->`: 約1,170回。整数アドレス経由の `mem.read_word` など: 487回。キャスト: 約360回。
- 生ポインタの操作の警告 W0003: 57ファイル、約2000件（MLC-023）。多いのは
  `apps/files.dom.mln` 243、`ui/dom/dom.mln` 221、`dom_widgets.mln` 207。
- `Drop` を持つ型: `String`、カーネルの `ProcessSlot`・`AddressSpace`・`HeapBlock`、
  FS の `FileHandle`、DOM の `NewNode`。`String` 以外はガードで、所有値のまま残せる。
- カーネルのスレッド表（`Option<Thread> g_threads[256]` と slot 番号）は、すでにプールの形。

## Design

### Proposed Design

1. **標準ライブラリ。** `String`・`Vec<T>`・`HashMap<K, V>` を共有値に（MLC-025）。
   `IntrusiveList<T>` は生ポインタなので、プールに置き換えて廃止する。
2. **DOM サーバから始める。** ノードを `Pool<Node, 512>` に入れ、`u16` の番号と `Node *` を
   `Handle<Node>` に。`heap.alloc`、キャスト、ゼロ埋めが消える。W0003 がいちばん多い。
3. **FS。** 整数のアドレスで読み書きしている所を、配列と借用にする。
4. **アプリ。** ハンドラの receiver を `T *` から `borrow T` に。`char *` を `str`・
   `Text<N>`・`String` に。
5. **カーネル。** 共有値を使わず、プールと固定長の値で書く。MMIO・ページ表・コンテキスト
   切り替えは `.unsafe.mln` に切り出す。
6. **NUL 終端をなくす。** syscall のパスや DOM のテキストを `str` で受け取り、`Text<N>` の
   NUL 用の1バイトを要らなくする。
7. 移し終えたら、W0003 をエラーにする（MLC-023 の段階3）。

### Non-Goals

- 構文の整理（MLC-028）。

## Progress

- [ ] `String`・`Vec`・`HashMap` を共有値に、`IntrusiveList` を廃止
- [x] DOM サーバをモデル拡張の表に（`dom_model.model.mln`、2026-11-06）
- [ ] FS
- [x] アプリのハンドラと文字列（2026-11-06）
- [x] カーネルの unsafe の切り出し（ファイル単位。小さく割るのは今後）
- [ ] NUL 終端をなくす（OS_CALL のパスとログ、`fs`・`shell`・`debug`・`annotations`・`mbin` は
  `str` に。残りは SYS_SPAWN のパス、`Text.as_ptr()`、`hosted/fs` の読み書きの出力先。2026-11-07）
- [x] W0003 をエラーにする（E0701）

## 完了条件

- `system/` の安全なファイルに `heap.alloc` / `heap.free`、`->`、W0003 が残っていない。
- `make build && make qa` が通る。

## 関連

- `docs/design/mylang-values.md`
- MLC-023 `.unsafe.mln` と生ポインタの分離
- MLC-025 値だけのメモリモデル
