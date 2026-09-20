# UI プロトコル — アプリと UI サーバの間を越えるもの

2026-09-20（MYOS-019）。`docs/design/os-app-boundaries.md` の段 2。定義は
`system/MyAppFramework/src/protocol.mln`（`UiMsg` / `UiEvent` / `UiOp` / `UiEventKind`）で、
SDK とサーバの**両方がこれを import** し、互いを import しない。

```
[アプリのタスク]                                      [UI サーバのタスク]
アプリ ──(ui / elements)──▶ SDK スタブ ──UiMsg──▶ ipc チャネル ──▶ uiproto.serve ──▶ ui_server.handle
アプリ ◀──fn(owner,id,arg)── runtime.pump ◀──UiEvent── ipc チャネル ◀── ui_events ◀── dom.emit / shell
```

アプリは**プロセス**（段 5、MYOS-022）：運び手は `OS_CALL` syscall で、カーネルの
`os_calls` がユーザメモリをコピーしてチャネルへ渡す。DOM は**UI サーバのタスク**でしか
触らない。

## 1. 形

**要求**（アプリ → サーバ、同期、戻り値 i32 1 つ）

```mylang
struct UiMsg { i32 op; i32 owner; i32 a0..a5; char *s0; char *s1; };
i32 request(UiMsg *m);          // uiproto — OS_CALL(UI_REQUEST) → OS_CALL(UI_REPLY) を sys_yield しながら待つ
```

- `owner`：アプリは自分のインスタンスを書くが、カーネル（`os_calls`）が **pid** に書き換える。
  要求が作るノードはすべて pid に所有される（サーバは `handle()` の間だけ `dom.current_owner`
  をこれにする）。イベントの `owner` も pid
- 文字列（`s0` ≤ 1024、`s1` ≤ 128）はカーネルがプロセスごとのバッファにコピーし、サーバは
  さらに自分のコピー（`dom.set_text_copy`、node の name）を持つ。出力バッファ（TEXT_COPY /
  LIST_ITEM の `out`、≤ 4096）はカーネル側のバッファに書かせ、返事のときにユーザメモリへ
  コピーバックする。**サーバのポインタをアプリに返す要求は無い**
- `SET_TEXT_FMT` は使われない：`ui.set_text_fmt` はアプリ側で整形して SET_TEXT を送る
  （`%s` の引数はプロセスのポインタで、サーバには読めない）

**イベント**（サーバ → アプリ、非同期）

```mylang
struct UiEvent { i32 owner; i32 id; i32 kind; i32 arg; i32 token; char *text; };
bool poll(UiEvent *out);        // uiproto — OS_CALL(UI_POLL)：プロセスのチャネルから 1 つ、text はアプリのバッファへコピー
void idle();                    // sys_yield：次の tick まで CPU を手放す（runtime.run のループ）
void exit();                    // sys_exit：EXIT を送ったあと
```

**運び手：カーネルのチャネル**（`MyKernel/src/kernel/ipc.mln`）

- チャネル = 16 ワード固定長メッセージ × 32 スロットのリング。producer / consumer が 1 タスクずつ
  なのでロック不要（index はそれぞれ片側だけが書く）。`create / send / recv / pending / wait`
- UI プロトコルは要求チャネル 1 本（全プロセス → サーバ。語 10 に返事先のチャネル id）と、
  プロセスごとに返事チャネルとイベントチャネル 1 本ずつ（`os_calls` が最初の UI 呼び出しで作り、
  `ui_events.bind(pid, ch)` で結ぶ）。サーバは `ui_channel.serve()` を 1 パスに 1 回呼んで
  全要求に答える
- 共有リングではなくチャネル + 固定長にしたのは、syscall 化で「カーネルがメッセージをコピーする」
  だけで済ませるため。実際そうなった（`os_calls.svc_ui_request`）

## 2. 要求の表（`UiOp`）

| op | 引数 | 戻り値 | SDK 側の入口 |
| --- | --- | --- | --- |
| SET_TEXT | id, s0 | – | `ui.set_text` |
| TEXT_COPY | id, a1=out, a2=cap | len | `ui.text_copy`（サーバのポインタは返さない。`text_of` は無い） |
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
| CLAIM_KEY | s0="Ctrl+S" | token | `@key`（runtime.start）。シェルは spec を自分の表にコピーする |
| MAIN_WINDOW | a0=win | – | `@app` の view の戻り（runtime.start）。シェルがデスクトップに載せる |
| EXIT | – | – | CLOSE への返事（runtime）。このあとプロセスは `sys_exit` |

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
  - `pump()`：`poll` で取ったイベントを `fn(owner, id, arg)`（OPEN は `fn(owner, path)`）で配る。
    `run()` = `pump(); idle();` のループ = アプリのイベントループ

**サーバ**（`MyOS/src/ui`, `MyOS/src/shell`）
- `ui_channel.mln`（package `uiproto`）：`request` → 要求チャネル → `serve()`（サーバのパス内）→
  `ui_server.handle` → 返事チャネル。`poll` → イベントチャネル
- `ui_server.mln`：op で分岐して DOM を触る。CLAIM_KEY / MAIN_WINDOW / EXIT / OPEN はシェルへ
- `elements_server.mln`：CREATE_\*。`dom/dom_elements.mln` の `create_*` を呼ぶ
- `ui_events.mln`：イベントチャネルへの `push` / `poll`
- `proc/os_calls.mln`：`OS_CALL` のハンドラ。UI_REQUEST は UiMsg をコピーして owner を pid に
  し、文字列と出力バッファをカーネル側へ差し替えて要求チャネルへ。UI_REPLY は返事チャネルを
  見てコピーバック。UI_POLL はイベントチャネルから 1 つ。ほかに `FS_*` / `PROC_*` / `LOG`
- `shell/app.mln`：`mount()` = `console.spawn_file`。プロセスの view() → MAIN_WINDOW →
  `window_ready` でデスクトップへ。CLOSE → EXIT → `instance_exited`、`reap_exited` タイマが
  終わったプロセスを回収（クラッシュしたものは所有ノードごと）
- 「OS → SDK」の呼び出しは無い。`app_main.mln`（SDK）がプロセスの `main`
- **DOM ロック**（`dom.lock` / `unlock`）：サーバのタスクが 1 パスの間持ち、sleep の前に手放す。
  automation のダンプが取る。待ちがいれば unlock はロックを**手渡す**（サーバがすぐ取り直して
  ダンプが飢えないように）。アプリのタスクは DOM に触らないので取らない
- **描画の間引き**：要求に答えたパスは描画を保留（view() の十数個の CREATE が 1 パスずつ
  来るので、毎パス描くと十数回描いてしまう）。8 パス続いたら描く

## 5. まだのもの

- ノード id はサーバが払い出す（今もそう）が、256 で尽きる。owner（pid）ごとの上限と id の
  再利用
- 1 プロセス 1 インスタンス。`app_main.mln` の struct 領域は 4 KiB 固定
- イベントチャネルは 16 スロット。あふれたイベントは落ちる（TIMER が溜まるアプリで起こり得る）
