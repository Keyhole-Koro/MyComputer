# MYOS-020: UI サーバを自タスクに — IPC チャネルと DOM ロック

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Done | main | claude-code:opus-5 | 2026-09-20 |

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

- 共有リング → 段 5 で syscall にするとき、カーネルがメッセージをコピーするだけで済む
  「チャネル + 固定長（16 ワード）」にした
- ブロッキング primitive（wait queue）→ `scheduler.sleep(1)` の poll で十分（1 kHz tick）。
  要求 1 つ ≈ 2〜3 tick
- IPC の syscall（`SYS_UI_REQUEST` 等）を今足す → 使うプロセスがまだ無く試せないので段 5 へ
- 毎パス描画 → view() の CREATE が 1 パスずつ届くので、要求に答えたパスは描画を保留（最大 8 パス）

### Non-Goals

- プロセス（別 VA 空間）でのアプリ実行。段 5

## Progress

- [x] IPC 設計 — `docs/design/ui-protocol.md` §1 と `MyKernel/src/kernel/ipc.mln` の冒頭（別 doc にはしなかった）
- [x] チャネル（`ipc.mln`: create / send / recv / pending / wait）。syscall 化は段 5
- [x] アプリのタスク（`shell/host.mln`、64 KiB スタック `spawn_task_sized`）。UI サーバは task 0 のまま、`serve()` で答える
- [x] SDK：`runtime.run()`（pump + idle）、`text_of` → `text_copy`、MAIN_WINDOW
- [x] DOM ロック（手渡し付き）、automation がダンプで取る
- [x] シェル：`mount` 非同期化（`window_ready`）、OPEN の保留
- [x] 3 つの E2E、`make qa` 21 suites 緑（apps_e2e は exit code を待つように修正）

## Verification

```
make qa
python3 system/MyOS/tests/app_framework_test.py
```

## 完了条件

- `dom.drain_events` がアプリのハンドラを呼ばない（アプリ側の `run()` が呼ぶ）— 済
- アプリのハンドラで busy loop しても compositor の paint が続く — 構造上そうなる
  （アプリのコードはアプリのタスクにしかない）が、自動テストは足していない。ハンドラで
  busy loop するテスト用アプリを置く必要があり、段 5 の `/apps` の .mbin で作るほうが自然

## 関連

- MYOS-019（前段）、MYOS-022（次段）
