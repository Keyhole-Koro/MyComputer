# MLC-028: 構文の整理

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Proposed | - | - | 2026-11-05 |

## Summary

メモリモデルの作業（MLC-024〜027）とは別に、同じことに書き方が複数ある所と、使われて
いない構文を整理する。急がない。

## Background

2026-10-30 の時点の数:

- 文式 `({ ... })` が510回。うち約210回は、`case` の腕から `return` するためだけに
  使われている。
- 使われていない C の予約語: `switch`、`union`、`auto`、`register`、`static`、`long`、
  `short`、`float`、`double`、`typedef`、`do`。
- 変数とパラメータの先頭の `mut` は、文法にあるが使われていない（規則 B1 で不要にした）。
- DOM のハンドラは「`on` + 大文字で始まる引数名」で特別扱いされ、「呼び出し規約が
  余分な引数を無視する」ことに頼っている。

## Design

### Proposed Design

1. `case` の腕にブロックと入れ子のパターンを書けるようにし、`({ ... })` と `yield` を
   なくす。
2. 使われていない予約語と、先頭の `mut` を削る。
3. DOM のハンドラを、普通の関数値（rc ならクロージャ）にする。

## Progress

- [ ] `case` の腕のブロックと入れ子のパターン
- [ ] 予約語と先頭の `mut` の削除
- [ ] DOM のハンドラを関数値に

## 関連

- `docs/design/mylang-memory-model.md`
- MLC-018 型付き関数値とコールバック
