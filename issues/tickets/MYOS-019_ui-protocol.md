# MYOS-019: UI プロトコル — アプリ ↔ UI サーバをメッセージにする

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Proposed | - | - | 2026-09-20 |

## Summary

SDK の `ui` / `elements` の面を**メッセージ表**として定義し、SDK 側スタブ → キュー →
UI サーバ側ディスパッチで動かす。サーバがアプリの関数ポインタを持つのをやめ、イベントは
(node id, arg) で SDK 側のハンドラ表に返す。同一プロセス内で動かし、段 3 でプロセス境界へ
持ち出せる形にする。`docs/design/os-app-boundaries.md` の段 2。

## Background

MYOS-018 の後も、`ui_set_text` は link 名でサーバの関数に直結し、`onClick={c->click}` は
アプリの関数ポインタがサーバの DOM に入っている。プロセスにすると両方成り立たない。

## Design

### Current State

- `ui.mln` の面：`set_text` / `text_of` / `set_text_fmt` / `is_checked` / `set_checked` /
  `input_set` / `area_*` / `list_*` / `focus*` / `close` / `window_of` / `window_x/y` /
  `show` / `test_id` / `send_key` / `set_key_filter` / `rgb` / `open`
- `elements.mln` の面：`Window` … `List`、`Timer`、`append_child`。ハンドラは i32 の関数ポインタ
- `dom.push_event` / `dom.drain_events`：サーバ内のイベントキュー。ハンドラ ABI `(owner, id, arg)`

### Proposed Design

- メッセージ表を `docs/design/ui-protocol.md` に列挙（要求: 種別 + id + i32 引数 + 長さ付き文字列。
  応答: i32。イベント: kind + id + arg）
- SDK：`ui.mln` / `elements.mln` のプロトタイプに本体（メッセージを積む）が付く。
  `handlers.mln`：node id → 関数のハンドラ表と、イベントキューを回す `run()`。
  `view()` の戻り値・`ref={}` は id のまま
- サーバ：`ui_server.mln` / `elements.mln` がメッセージの受け手に。ノードのハンドラ欄には
  関数ポインタではなく「イベントを送る先（owner）」だけ残す
- 同一プロセス内では、キューは配列。段 3 でチャネルに差し替える

### Alternatives Considered

- 検討中（IPC の形は段 3 で決める。ここでは表と in-process 実装だけ）

### Non-Goals

- 別タスク化、DOM ロック（段 3）
- ノード id の再利用問題の解決（ここで id 払い出しをサーバに寄せ、直すのは別チケット）

## Progress

- [ ] メッセージ表（`docs/design/ui-protocol.md`）
- [ ] SDK スタブ + ハンドラ表 + イベントループ
- [ ] サーバ側ディスパッチ
- [ ] アプリのハンドラがサーバの関数ポインタ経由で呼ばれていないことの確認（grep + テスト）

## Verification

```
make build && make framework-test
python3 system/MyOS/tests/dom_click_test.py
python3 system/MyOS/tests/apps_e2e_test.py
```

## 完了条件

- `dom.mln` にアプリの関数ポインタを保持する欄が無い
- `ui.mln` / `elements.mln` の全関数がメッセージ表の行に対応している
- 既存 E2E が緑

## 関連

- `docs/design/os-app-boundaries.md`、MYOS-018（前段）、MYOS-020（次段）
