# MyKernel DOM UI Automation（Playwright 風テスト基盤）

## 背景

MyKernel には `src/ui/dom.mln` に軽量な Kernel Object Tree があり、`Window` / `Text` /
`Button` などの UI ノードへ拡張していく設計がある。MyEmulator 側にも `--headless`、
VRAM、mouse MMIO、serial/debug log があるため、外部テストから UI を起動・操作・検証
するための土台は揃いつつある。

一方で、現状のクリックカウンター UI は `kernel/main.mln` 内に座標、描画、イベント処理が
直接書かれており、DOM ツリーから「button を探して click する」「text が表示されたことを
検証する」といった Playwright 風の E2E テストはできない。

このチケットでは、ブラウザ互換ではなく **MyKernel DOM 専用の UI automation 基盤**を作る。

## 目標

ヘッドレスエミュレータ上で MyKernel UI を起動し、テストコードから DOM / Accessibility
Tree を問い合わせ、locator で要素を取得し、クリックなどの入力を注入し、DOM 状態や画面
状態を検証できるようにする。

最初の目標 API:

```python
page = launch("system/MyKernel/build/kernel_linked.mbin")

page.get_by_role("button", name="CLICK ME").click()
expect(page.get_by_text("clicks: 1")).to_be_visible()
```

## 方針

Playwright の完全再現ではなく、次の 2 層に分ける。

1. MyKernel / MyEmulator 側の制御プロトコル
2. Python 側の薄い client library

DOM の問い合わせは CSS selector よりも、まず `role` / `name` / `text` ベースにする。
MyKernel DOM は HTML DOM ではないため、`get_by_role("button", name="CLICK ME")` の
ような accessibility tree 的 locator の方が安定する。

## DOM / Accessibility Tree

`Node` に UI automation で必要な metadata を追加する。

```text
id
kind
role
name
text
parent
first_child
next_sibling
x
y
w
h
state flags
```

最初に必要な role:

- `root`
- `desktop`
- `window`
- `button`
- `text`

最初に必要な state:

- `visible`
- `enabled`
- `hovered`
- `pressed`
- `focused`

## カーネル側タスク

### 1. `dom.mln` の拡張

- `Node` に `role` / `text` / `bounds` / `state` を追加する。
- `set_bounds(node, x, y, w, h)` を追加する。
- `set_text(node, text)` を追加する。
- `set_role(node, role)` または role 別 create helper を追加する。
- `find_at(x, y)` のような hit-test helper を追加する。

### 2. UI を DOM 駆動へ寄せる

`kernel/main.mln` のクリックカウンター UI を DOM node として表現する。

```text
Window "MyKernel Window"
  Button "CLICK ME"
  Text "clicks: 0"
```

- button の bounds を DOM node に持たせる。
- counter text も DOM node として表現する。
- mouse event は固定座標判定ではなく DOM hit-test 経由で処理する。
- button click handler で counter state を更新する。

### 3. DOM snapshot を機械可読にする

外部テストが現在の DOM / accessibility tree を取得できる形式を用意する。

MVP では serial/debug 経由の line-based dump でもよいが、client 側で tree に復元できる
安定した形式にする。

例:

```json
{"id":4,"role":"button","name":"CLICK ME","text":"CLICK ME","x":120,"y":130,"w":150,"h":60,"visible":true,"enabled":true}
```

## エミュレータ側タスク

### 1. Control mode を追加する

`runtime/MyEmulator` に `--control-stdio` を追加し、stdin / stdout の JSON Lines で
テスト制御できるようにする。

入力例:

```json
{"cmd":"dom.snapshot"}
{"cmd":"mouse.move","x":195,"y":160}
{"cmd":"mouse.down","button":"left"}
{"cmd":"mouse.up","button":"left"}
{"cmd":"frame.wait"}
{"cmd":"screenshot","path":"out.png"}
```

MVP では TCP / WebSocket は不要。CI で扱いやすい stdio を優先する。

### 2. Mouse injection

- control command を `Machine::set_mouse_state(...)` 相当へ流す。
- mouse move / down / up で IRQ が発火し、既存の mouse MMIO 経由で kernel に届くようにする。
- `locator.click()` が node bounds の中心を click できるようにする。

### 3. Frame / screenshot

- `frame.wait` で kernel が入力を処理し、描画が落ち着くまで進められるようにする。
- `screenshot` で front buffer または scanout buffer を画像として保存できるようにする。

## Python client

`qa/mykernel_playwright/` のような場所に薄い client library を置く。

最小 API:

```python
page = launch(binary_path)
page.get_by_role(role, name=None)
page.get_by_text(text)
locator.click()
expect(locator).to_be_visible()
```

内部では:

- emulator を `--headless --control-stdio` で起動する。
- JSON Lines で command / response をやり取りする。
- `dom.snapshot` を tree に復元する。
- locator が node を探す。
- `click()` は node bounds の中心に mouse event を注入する。

## 検証

クリックカウンター UI を対象に E2E テストを追加する。

```python
page = launch("system/MyKernel/build/kernel_linked.mbin")
page.get_by_role("button", name="CLICK ME").click()
expect(page.get_by_text("clicks: 1")).to_be_visible()
```

## Acceptance Criteria

- `--headless --control-stdio` で MyKernel を起動できる。
- テストコードから `role=button, name=CLICK ME` の node を取得できる。
- `locator.click()` が mouse move / down / up を注入する。
- click 後に counter の DOM / text state が更新される。
- 実ウィンドウ表示に依存しない E2E テストが追加されている。
- CI で実行できる。

## Non-goals

- CSS selector 完全互換
- Playwright API の完全再現
- HTML DOM 互換
- WebSocket protocol
- 複数 page / browser context
- 高精度 visual regression

## リスク・メモ

- 現状は DOM と描画・イベント処理が分離していないため、最初に UI state を DOM 側へ寄せる
  必要がある。
- 画面ピクセルだけで検証すると壊れやすい。MVP は DOM / accessibility snapshot を主軸にする。
- serial log 経由の snapshot は実装が簡単だが、応答同期が粗くなりやすい。
- 将来的には専用 MMIO または emulator internal protocol へ寄せる方が安定する。

## 関連

- `dom-like-os.md`
- `ui-renderer-phase2.md`
- `emulator-display-minifb.md`
- `mylang-test-framework.md`
