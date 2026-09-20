# UI プロトコル — アプリと UI サーバの間を越えるもの

2026-09-20（MYOS-019）。`docs/design/os-app-boundaries.md` の段 2。定義は
`system/MyAppFramework/src/protocol.mln`（`UiMsg` / `UiEvent` / `UiOp` / `UiEventKind`）で、
SDK とサーバの**両方がこれを import** し、互いを import しない。

```
アプリ ──(ui.mln / elements.mln の呼び出し)──▶ SDK スタブ ──UiMsg──▶ uiproto.request ──▶ ui_server.handle
アプリ ◀──fn(owner, id, arg)── runtime.pump ◀──UiEvent── uiproto.poll ◀── ui_events ◀── dom.emit / shell
```

## 1. 形

**要求**（アプリ → サーバ、同期、戻り値 i32 1 つ）

```mylang
struct UiMsg { i32 op; i32 owner; i32 a0..a5; char *s0; char *s1; };
i32 request(UiMsg *m);          // uiproto — 今は関数呼び出し、段 3 で syscall
```

- `owner` は送ったインスタンス。要求が作るノードはすべてこれに所有される
  （サーバは `handle()` の間だけ `dom.current_owner` をこれにする）
- 文字列は今はポインタ。プロセス境界を越えるときは長さ付きでコピーする（段 3）

**イベント**（サーバ → アプリ、非同期）

```mylang
struct UiEvent { i32 owner; i32 id; i32 kind; i32 arg; i32 token; char *text; };
bool poll(UiEvent *out);        // uiproto — 今はリング、段 3 でチャネル
```

## 2. 要求の表（`UiOp`）

| op | 引数 | 戻り値 | SDK 側の入口 |
| --- | --- | --- | --- |
| SET_TEXT | id, s0 | – | `ui.set_text` |
| TEXT_OF | id | char\* | `ui.text_of` |
| SET_TEXT_FMT | id, s0=fmt, a1, a2 | – | `ui.set_text_fmt` |
| IS_CHECKED | id | 0/1 | `ui.is_checked` |
| SET_CHECKED | id, a1 | – | `ui.set_checked` |
| INPUT_SET | id, s0 | – | `ui.input_set` |
| AREA_APPEND / AREA_CLEAR / AREA_LINES | id, (s0) | (count) | `ui.area_*` |
| LIST_SET_ITEMS / LIST_COUNT / LIST_SELECTED | id, (s0) | (count / row or -1) | `ui.list_*` |
| LIST_ITEM | id, a1=row, a2=out, a3=cap | len or -1 | `ui.list_item` |
| FOCUS / FOCUS_WINDOW | id | – | `ui.focus*` |
| CLOSE | id | – | `ui.close`（自分で開いたダイアログ） |
| WINDOW_OF / WINDOW_X / WINDOW_Y | id | id / 論理座標 | `ui.window_*` |
| SHOW | id | – | `ui.show`（ダイアログをデスクトップへ） |
| TEST_ID | id, s0 | – | `ui.test_id` |
| SEND_KEY | a0=type, a1=code, a2=mods | – | `ui.send_key` |
| RGB | a0, a1, a2 | 色 | `ui.rgb` |
| OPEN | s0=path | 受けたアプリのウィンドウ or 0 | `ui.open` |
| CREATE_WINDOW | s0=title, x, y, w, h, s1=testId | id | `<Window>` |
| CREATE_BUTTON / CREATE_PRIMARY_BUTTON | s0=text, x, y, w, h, s1 | id | `<Button>` / `<PrimaryButton>` |
| CREATE_TEXT | s0, x, y, s1 | id | `<Text>` |
| CREATE_LABEL | s0, x, y, color, bold, s1 | id | `<Label>` |
| CREATE_BOX | x, y, w, h, background, border | id | `<Box>` |
| CREATE_PANEL | x, y, w, h, radius | id | `<Panel>` |
| CREATE_COLUMN / CREATE_ROW | x, y, w, h, padding, gap | id | `<Column>` / `<Row>` |
| CREATE_TEXT_INPUT | s0=placeholder, x, y, w, h, capacity, s1 | id | `<TextInput>` |
| CREATE_CHECKBOX | s0, x, y, checked, s1 | id | `<Checkbox>` |
| CREATE_SEPARATOR | x, y, w | id | `<Separator>` |
| CREATE_TIMER | a0=interval | id | `<Timer>`、`@timer` |
| CREATE_TEXT_AREA | s0=name, x, y, w, h, capacity, readonly, s1 | id | `<TextArea>` |
| CREATE_LIST | s0=name, x, y, w, h, capacity, s1 | id | `<List>` |
| APPEND_CHILD | a0=parent, a1=child | – | markup の子 |
| CLAIM_KEY | s0="Ctrl+S" | token | `@key`（runtime.start） |
| EXIT | – | – | CLOSE への返事（runtime） |

`x, y, w, h` は `a0..a3`。`(id)` は `a0`。ハンドラ（`onClick` 等）は**表に無い**：
アプリの外へ出ない（§4）。

## 3. イベントの表（`UiEventKind`）

| kind | id | arg | token / text | 発生源 |
| --- | --- | --- | --- | --- |
| CLICK | ノード | 0 | – | `dom.dispatch_click`（Button, Checkbox） |
| CHANGE | ノード | 0 | – | `dom.fire_change`（TextInput 編集、Checkbox、List 選択） |
| ACTIVATE | List | 0 | – | 選択行のクリック / Enter |
| TIMER | タイマ | 0 | – | `dom_widgets.tick` |
| KEY | ウィンドウ | code \| mods << 16 | token = 一致した claim | シェル `dispatch_key` |
| CLOSE | ウィンドウ | 0 | – | シェル `window_closed`（× ボタン） |
| OPEN | ウィンドウ | 0 | text = path | シェル `open` |

- 所有ノード（`owner != 0`）に起きたことは `dom.emit(n, kind, handler, arg)` が
  `ui_events` に積む。サーバ自身のノード（タスクバー、メニュー、時計）は従来どおり
  サーバ内の関数ポインタ（`push_event`）。**アプリのノードに関数ポインタは無い**
- CLOSE を受けたアプリは `@on_close` を走らせてから EXIT を送る。シェルはそれを受けて
  `remove_owned` と解放をする（順序が保証される）

## 4. 両端

**SDK**（`MyAppFramework/src`）
- `ui.mln` / `elements.mln`：1 関数 = 1 要求。`runtime.send(op, a0..a5, s0, s1)`
- `runtime.mln`：
  - ハンドラ表 `(owner, key, kind) → fn`。`elements` のスタブが `onClick` 等を `on(id, kind, fn)` で登録
  - `start(self, type)`：`@app` の view を呼び、`@timer` → CREATE_TIMER + 登録、`@key` → CLAIM_KEY + 登録、
    `@open` / `@on_close` → 登録。**アノテーションの意味はここ**（シェルが知るのは `@app` と「`@open` を持つか」だけ）
  - `pump()`：`poll` で取ったイベントを `fn(owner, id, arg)`（OPEN は `fn(owner, path)`）で配る

**サーバ**（`MyOS/src/ui`, `MyOS/src/shell`）
- `ui_channel.mln`（package `uiproto`）：`request` → `ui_server.handle`、`poll` → `ui_events.poll`
- `ui_server.mln`：op で分岐して DOM を触る。CLAIM_KEY / EXIT / OPEN はシェルへ
- `elements_server.mln`：CREATE_\*。`dom/dom_elements.mln` の `create_*` を呼ぶ
- `ui_events.mln`：リング。`dom.drain_events()` の末尾で consumer（`shell/host.pump`、`main.mln` が登録）が空にする
- `shell/host.mln`：in-process の起動と pump。段 5 で消える唯一の「OS → SDK」依存

## 5. 段 3 で変わるもの

- `request` / `poll` が syscall になる。`UiMsg` はユーザ空間のポインタ、文字列はカーネルがコピー
- `ui_events` はアプリごとのチャネルに。`set_consumer` と `host.pump` は消え、各アプリの
  `runtime.pump()` が自分のタスクで回る
- `TEXT_OF` の char\* 戻りは `text_copy(id, out, cap)` にする（ポインタが越えられない）
- ノード id はサーバが払い出す（今もそう）。owner ごとの上限と id の再利用はここで
