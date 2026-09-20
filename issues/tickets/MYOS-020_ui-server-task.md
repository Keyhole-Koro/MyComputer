# MYOS-020: UI サーバを自タスクに — IPC チャネルと DOM ロック

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Proposed | - | - | 2026-09-20 |

## Summary

MYOS-019 のキューをカーネルの IPC チャネルに置き換え、UI サーバ（dom + compositor）を
自分のタスクで動かす。アプリのハンドラは別タスク上で走り、DOM はサーバのタスクだけが
触る。`docs/design/os-app-boundaries.md` の段 3。

## Background

`compositor.run()` は入力 → `dom.drain_events()`（アプリのハンドラを同じタスクで実行）→
paint の 1 ループ（`ui/compositor.mln:256`）。アプリが長く走ると描画が止まり、
プロセスにできない。

## Design

### Current State

- タスクは `scheduler.spawn_task`。プロセスは `loader.spawn_from_buffer` + syscall
  （exit / write / read / spawn / sbrk）。プロセス間通信は無い
- `dom.push_event` / `drain_events` が唯一の遅延実行点

### Proposed Design

- カーネル：チャネル syscall（create / send / recv、固定長メッセージ + 文字列はコピー）
- UI サーバ：自タスク。`run()` = 入力処理 + チャネル受信（要求の処理）+ paint。
  DOM を触るのはこのタスクだけなので、ロックは「サーバのタスク以外は DOM に触らない」
  という規約 + カーネル内呼び出し（automation 等）用の 1 本のロック
- SDK：`run()` がチャネルからイベントを受けてハンドラ表を引く
- 組み込みアプリ（image にリンク）は、当面サーバと同じ address 空間の別タスクとして動く

### Alternatives Considered

- 検討中（チャネル + 固定長 か 共有リング か。MYOS-019 の表を見て決める）

### Non-Goals

- プロセス（別 VA 空間）でのアプリ実行。段 5

## Progress

- [ ] IPC 設計（`docs/design/ipc.md`）
- [ ] チャネル syscall
- [ ] UI サーバのタスク化
- [ ] SDK のイベントループをチャネルに

## Verification

```
make qa
python3 system/MyOS/tests/app_framework_test.py
```

## 完了条件

- `dom.drain_events` がアプリのハンドラを呼ばない（アプリ側の `run()` が呼ぶ）
- アプリのハンドラで busy loop しても compositor の paint が続く（テスト追加）

## 関連

- MYOS-019（前段）、MYOS-022（次段）
