# MLC-026: 既存コードを新しいメモリモデルへ移す

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Proposed | - | - | 2026-11-05 |

## Summary

MLC-025 の参照数つきオブジェクトとモードができたら、既存のコードを移す。`heap.alloc` で
作っているものを `new` に、標準のコンテナをコピーオンライトに、モジュールごとにモードを
決める。生ポインタを unsafe に寄せる作業は MLC-023 で続ける。

## Background

2026-10-30 の時点の数:

- `heap.alloc` / `heap.free`: `system/` 以下で43箇所（DOM のノードなど）。
- `->`: 約1,190回。整数アドレス経由の `mem.read_word` など: 487回。キャスト: 約360回。
- 生ポインタの操作の警告 W0003: 57ファイル、約2000件（MLC-023）。多いのは
  `apps/files.dom.mln` 243、`ui/dom/dom.mln` 221、`dom_widgets.mln` 207。
- `Drop` を持つ型: `String`、カーネルの `ProcessSlot`・`AddressSpace`・`HeapBlock`、
  FS の `FileHandle`、DOM の `NewNode`。`String` 以外はガードで、そのまま所有する値として
  残せる。

## Design

### Proposed Design

1. **標準ライブラリ。** `String`・`Vec<T>`・`HashMap<K, V>` を、参照数つきのバッファと
   コピーオンライトで作り直す（規則 O7）。`as_str()` などの借用を返す API は残す。
2. **モジュールごとのモード。** 目安は、カーネル・FS・ドライバが owned、DOM・シェル・
   アプリが rc。
3. **DOM と FS から始める。** W0003 が多く、効果が大きい。
   - DOM のノードを `new` で作り、子は `Vec<Node^>`、親は `weak Node^` にする。
   - 整数のアドレスを読み書きしている所は、スライスや共有ポインタにする。
4. **NUL 終端をなくす。** syscall のパスや DOM のテキストを `str` で受け取り、`Text<N>` の
   NUL 用の1バイトを要らなくする。
5. 移し終えたら、W0003 をエラーにする（MLC-023 の段階3）。

### Non-Goals

- 構文の整理（MLC-028）。

## Progress

- [ ] `String`・`Vec`・`HashMap` のコピーオンライト化
- [ ] DOM のノードを `new` に
- [ ] FS
- [ ] 残りの `heap.alloc`
- [ ] モジュールごとのモードの宣言
- [ ] NUL 終端をなくす
- [ ] W0003 をエラーにする

## 完了条件

- `system/` の安全なファイルに `heap.alloc` / `heap.free` と W0003 が残っていない。
- `make build && make qa` が通る。

## 関連

- `docs/design/mylang-memory-model.md`
- MLC-023 `.unsafe.mln` と生ポインタの分離
- MLC-025 参照数つきオブジェクトと rc / owned モード
