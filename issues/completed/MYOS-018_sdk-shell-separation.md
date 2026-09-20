# MYOS-018: SDK / シェル分離 — MyAppFramework から MyOS への import をゼロに

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Done | main | claude-code:opus-5 | 2026-09-20 |

## Summary

MyAppFramework を「アプリがリンクする SDK」だけにする。アプリを管理する側の
`app.mln`（レジストリ・起動・終了・キー配送）を `MyOS/src/shell/` へ移し、`ui.mln` と
markup の語彙（`dom_elements`）を「SDK 側のプロトタイプ + UI サーバ側の実装」に分ける。
`docs/design/os-app-boundaries.md` の段 1。

## Background

`system/MyAppFramework/src/app.mln:3-14` が heap / dom / compositor / dom_render を import し、
`ui.mln:3-9` が dom / dom_widgets / graphics を直叩きしている。アプリが呼ぶのは
`annotations.mln` と `ui.mln` だけなのに、framework のビルドが compositor まで巻き込み、
`MyOS/src/apps → MyAppFramework → MyOS/src/ui` の循環になっている
（`APP_FRAMEWORK.md` 既知の制限）。アプリをプロセスにするとき、`app.mln` はカーネル／シェル側、
`ui.mln` はアプリ側に分かれるので、今のうちにリポジトリの境界を合わせる。

## Design

### Current State

- `app.mln`：`install()` / `launch*` / `open` / `window_closed` / `dispatch_key` /
  `menu_items` / `on_menu` / `count` / `app_name` / `owner_of_window`。呼ぶのは
  `boot/main.mln`、compositor、dom（× ボタン、キーフィルタ）、タスクバー。アプリからは
  `ui.open` 経由の `app.open` だけ
- `ui.mln`：i32 / char\* の面。実装は dom を直接呼ぶ
- `MyOS/src/ui/dom/dom_elements.mln`：`create_*`（サーバ内部）と markup の語彙
  `Window` … `List`（デフォルト引数付き）が同居。アプリは後者のために import する

### Proposed Design

```
MyAppFramework/src/            MyOS/src/
  annotations.mln  (そのまま)     shell/app.mln         ← app.mln を移動、import 修正
  ui.mln           プロトタイプ    ui/ui_server.mln      ← package ui、旧 ui.mln の本体
  elements.mln     プロトタイプ    ui/elements.mln       ← package elements、markup 語彙の実装
                                  ui/dom/dom_elements.mln  create_* だけ残す
```

- 同じ package 名を SDK とサーバで使い、link 名（`ui_set_text`, `elements_Window`）で結ぶ
  （設計書 §3。プロトタイプ側はコードを出さず、デフォルト引数は宣言から取られる — 検証済み）
- アプリの import は `dom_elements` → `MyAppFramework/src/elements.mln`、`ui` は変わらず
- `dom_widgets` / `dom_render` の未使用な `{ Window, ... } from "dom_elements.mln"` は削除

### Alternatives Considered

- `ui.mln` に本体を残し `import ui_server from MyOS` で委譲 → SDK が MyOS を import する
  ままで、境界が見えない。却下
- `app.mln` を MyAppFramework に残し「framework = SDK + シェル」と定義 → .mbin 化のときに
  結局同じ切り方をする。先に切る

### Non-Goals

- UI プロトコル（メッセージ化）。この段では in-process の直接呼び出しのまま
- 機能変更。アプリのソースは import 1 行以外変えない

## Progress

- [x] `ui.mln` をプロトタイプに、本体を `MyOS/src/ui/ui_server.mln` へ
- [x] `elements.mln`（SDK）と `MyOS/src/ui/elements.mln`（実装）に分割、`dom_elements.mln` は `create_*` のみ
- [x] `app.mln` → `MyOS/src/shell/app.mln`
- [x] アプリ / `main.mln` の import 修正（automation は `dom_elements.role_name` のみで変更なし）
- [x] SDK に import が 1 行も無い（`grep -n "^import" system/MyAppFramework/src/*.mln` が空）
- [x] docs（APP_FRAMEWORK.md、README、DOM_SPEC.md）更新
- [x] `make build` / 3 つの E2E / `make qa` 21 suites 緑

## Verification

```
make build
python3 system/MyOS/tests/app_framework_test.py
python3 system/MyOS/tests/dom_click_test.py
python3 system/MyOS/tests/apps_e2e_test.py
make qa
```

## 完了条件

- `system/MyAppFramework/src/*.mln` に MyOS / MyKernel への import が無い
- `app.mln` が `MyOS/src/shell/` にあり、`main.mln` がそこを import する
- 上の 4 テストが緑

## 関連

- `docs/design/os-app-boundaries.md`
- MYOS-019（次の段）、MYOS-017（アノテーション）
