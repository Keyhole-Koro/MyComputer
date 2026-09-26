# UI プロトコル — アプリと UI サーバの間を越えるもの

2026-09-20（MYOS-019）、2026-09-21 domain分離。定義は
`contracts/myapp/` の `message.contract.mln` / `ui.contract.mln` /
`lifecycle.contract.mln` で、SDKとMyOSのprotocol endpointがimportする。
contractはdata-onlyで、transport関数は`MyAppFramework/src/runtime/transport.mln`が実装する。
UI domain implementationはcontractをimportしない。

```
[アプリプロセス]                                              [MyOS service task]
アプリ ─▶ SDK stub ─▶ Request(domain, op) ─▶ gateway ─▶ channel ─┬▶ ui/protocol ─▶ UI domain
                                                               └▶ shell/protocol ─▶ shell
アプリ ◀▶ runtime.pump ◀──────── Event ◀──────── events ◀── event sink / shell
```

アプリは**プロセス**（段 5、MYOS-022）：運び手は `OS_CALL` syscall で、カーネルの
`ipc/gateway.mln` がユーザメモリをコピーしてチャネルへ渡す。DOMはservice taskでしか
触らない。

## 1. 形

**要求**（アプリ → サーバ、同期、scalarまたはcopy-outしたtyped result）

```mylang
struct Request { i32 domain; i32 op; i32 owner; i32 a0..a5; char *s0; char *s1; };
i32 request(Request *m);        // OS_CALL(REQUEST) → OS_CALL(REPLY) を待つ
```

- `domain`：`UI` はDOM/widget、`APP` はopen/key claim/lifecycle。受け手を分ける
- `owner`：アプリは自分のインスタンスを書くが、MyOS gatewayが **pid** に書き換える。
  要求が作るノードはすべて pid に所有される（サーバは `handle()` の間だけ `dom.current_owner`
  をこれにする）。イベントの `owner` も pid
- 文字列（`s0` ≤ 1024、`s1` ≤ 128）はカーネルがプロセスごとのバッファにコピーし、サーバは
  さらに自分のコピー（`dom.set_text_copy`、node の name）を持つ。出力バッファ（TEXT_COPY /
  LIST_ITEM の `out`、≤ 4096）はカーネル側のバッファに書かせ、返事のときにユーザメモリへ
  コピーバックする。**サーバのポインタをアプリに返す要求は無い**
- `LIST_SELECTED` / `LIST_ITEM`のtyped resultもprocessごとのkernel bufferへ書き、gatewayが
  同じ`Result<..., UiError>`をcopy-outする。選択なしは`Ok(None)`で、負数sentinelへの変換はない。
- `SET_TEXT_FMT` は使われない：`ui.set_text_fmt` はアプリ側で整形して SET_TEXT を送る
  （`%s` の引数はプロセスのポインタで、サーバには読めない）

**イベント**（サーバ → アプリ、非同期）

```mylang
struct Event { i32 owner; i32 id; i32 kind; i32 arg; i32 token; char text[64]; };
bool poll(Event *out);          // OS_CALL(POLL)：チャネルから1つ、inline textもコピー
void idle();                    // WAIT_NOTIFICATION(EVENT)：eventが届くまでtaskをblock
void exit();                    // sys_exit：EXIT を送ったあと
```

**運び手：カーネルのチャネル**（`MyKernel/src/kernel/ipc.mln`）

- チャネル = 24 ワード固定長メッセージ × 32 スロットのリング。要求チャネルは複数 producer だが、
  single-core の syscall handler は割り込み禁止で直列化される。`create / send / recv / pending / wait`
- application protocolは要求チャネル1本（全プロセス→service task。語13に返事先channel id）と、
  プロセスごとに返事channel・event channelを1本ずつ（gatewayが最初の要求で作り、
  `events.bind(pid, ch)` で結ぶ）。`channel.serve()` を1パスに1回呼んで
  全要求に答える
- 共有リングではなくチャネル + 固定長にしたのは、syscall 化で「カーネルがメッセージをコピーする」
  だけで済ませるため。実際そうなった（`ipc/gateway.request`）

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
| LIST_SET_ITEMS / LIST_COUNT | id, (s0) | (– / count) | `ui.list_set_items` / `ui.list_count` |
| LIST_SELECTED | id, a4=result out, a5=size | `Result<Option<i32>, UiError>` | `ui.list_selected` |
| LIST_ITEM | id, a1=row, a2=text out, a3=cap, a4=result out, a5=size | `Result<i32, UiError>` | `ui.list_item` |
| FOCUS / FOCUS_WINDOW | id | – | `ui.focus*` |
| CLOSE | id | – | `ui.close`（自分で開いたダイアログ） |
| WINDOW_OF / WINDOW_X / WINDOW_Y | id | id / 論理座標 | `ui.window_*` |
| SHOW | id | – | `ui.show`（ダイアログをデスクトップへ） |
| TEST_ID | id, s0 | – | `ui.test_id` |
| SEND_KEY | a0=type, a1=code, a2=mods | – | `ui.send_key` |
| RGB | a0, a1, a2 | 色 | `ui.rgb` |
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
`x, y, w, h` は `a0..a3`。`(id)` は `a0`。ハンドラ（`onClick` 等）は**表に無い**：
アプリの外へ出ない（§4）。

### App domain（`AppOp`）

| op | 引数 | 戻り値 | SDK側の入口 |
| --- | --- | --- | --- |
| OPEN | s0=path | 受けたアプリのwindow or 0 | `ui.open` |
| CLAIM_KEY | s0="Ctrl+S" | token | `@key`（runtime.start） |
| MAIN_WINDOW | a0=win | – | `@app` viewの戻り |
| EXIT | – | – | CLOSE処理後のruntime |

## 3. イベントの表（`EventKind`）

| kind | id | arg | token / text | 発生源 |
| --- | --- | --- | --- | --- |
| CLICK | ノード | 0 | – | `dom.dispatch_click`（Button, Checkbox） |
| CHANGE | ノード | 0 | – | `dom.fire_change`（TextInput 編集、Checkbox、List 選択） |
| ACTIVATE | List | 0 | – | 選択行のクリック / Enter |
| TIMER | タイマ | 0 | – | `dom_widgets.tick` |
| KEY | ウィンドウ | code \| mods << 16 | token = 一致した claim | シェル `dispatch_key` |
| CLOSE | ウィンドウ | 0 | – | シェル `window_closed`（× ボタン） |
| OPEN | ウィンドウ | 0 | text = path | シェル `open` |

- 所有ノード（`owner != 0`）に起きたことは `dom.emit` → UI domain event sink →
  `ipc/events` の順でチャネルに積む。UI domain coreはtransportをimportしない。サーバ自身の
  ノード（タスクバー、メニュー、時計）は従来どおり
  サーバ内の関数ポインタ（`push_event`）。**アプリのノードに関数ポインタは無い**
- CLOSE を受けたアプリは `@on_close` を走らせてから EXIT を送る。シェルはそれを受けて
  `remove_owned` と解放をする（順序が保証される）

## 4. 両端

**SDK**（`MyAppFramework/src`）
- `ui.mln` / `elements.mln`：1関数=1要求。UIは`runtime.send`、lifecycleは`app_send`
- `contracts/myapp/message.contract.mln`がenvelope/event、`ui.contract.mln`と
  `lifecycle.contract.mln`がdomain別op
- `runtime/transport.mln`がMyStdLib `platform/myos`のsyscall bindingで運ぶ
- `runtime/runtime.mln`：
  - ハンドラ表 `(owner, key, kind) → fn`。`elements` のスタブが `onClick` 等を `on(id, kind, fn)` で登録
  - `start(self, type)`：`@app` の view を呼び、`@timer` → CREATE_TIMER + 登録、`@key` → CLAIM_KEY + 登録、
    `@open` / `@on_close` → 登録。**アノテーションの意味はここ**（シェルが知るのは `@app` と「`@open` を持つか」だけ）
  - `pump()`：`poll` で取ったイベントを `fn(owner, id, arg)`（OPEN は `fn(owner, path)`）で配る。
  `run()` = `pump(); idle();` のループ。空の POLL が通知を arm し、`idle()` は event が
  enqueue されるまで task を block する

**provider**（`MyOS/src/syscall`, `ipc`, `ui`, `shell`, `fs`, `proc`）
- `ipc/gateway.mln`：user-memory copy、REQUEST / REPLY / POLL
- `ipc/channel.mln`：domainでUI / shell protocol endpointへdispatch
- `ui/protocol.mln` / `protocol_elements.mln`：UiOpをDOM操作へ変換
- `shell/protocol.mln`：AppOpだけをshellへ渡す。UI protocolはshellをimportしない
- `ipc/events.mln`：UI/shellのdomain eventをwire Eventへ変換し、process channelへ接続
- `syscall/router.mln`：OS_CALL登録。FS/processはdomain-local syscall endpointへdispatch
- `shell/app.mln`：`mount()` = `console.spawn_file`。プロセスの view() → MAIN_WINDOW →
  `window_ready` でデスクトップへ。CLOSE → EXIT → `instance_exited`、`reap_exited` タイマが
  終わったプロセスを回収（クラッシュしたものは所有ノードごと）
- 「OS → SDK」の呼び出しは無い。`runtime/app_main.mln`（SDK）がプロセスの `main`
- **DOM ロック**（`dom.lock` / `unlock`）：サーバのタスクが 1 パスの間持ち、sleep の前に手放す。
  automation のダンプが取る。待ちがいれば unlock はロックを**手渡す**（サーバがすぐ取り直して
  ダンプが飢えないように）。アプリのタスクは DOM に触らないので取らない
- **描画の間引き**：要求に答えたパスは描画を保留（view() の十数個の CREATE が 1 パスずつ
  来るので、毎パス描くと十数回描いてしまう）。8 パス続いたら描く

## 5. 決めたこと（2026-09-21 の追記）

- ノード id は再利用される（free list）。owner（pid）ごとに 96 ノードまで；超えると
  CREATE_\* は 0 を返す
- 1 プロセス 1 インスタンス。`app_main.mln` が `@app` 行の `size` だけ `sbrk` で取る（固定上限なし）
- イベントチャネルは 32 スロット。各 slot は text を 64 bytes inline で所有する。TIMER は「同じタイマの未消費の tick があれば積まない」
  （遅いアプリは追いつくだけで、遅れは溜まらない）。それでもあふれた分は捨てて数える
  （MyOS `ipc/events.mln` の `dropped()`）
