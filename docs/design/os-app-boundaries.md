# MyStdLib / MyAppFramework / MyOS の境界

2026-09-20。MyOS のデスクトップアプリを「カーネル image にリンクされた関数」から
「`/apps` 上の実行形式（プロセス）」へ持っていくための、層の定義と到達順序。
以後の判断の基準として置くもので、各段の細部は実装しながら詰める。

関連: `docs/design/toolchain-collected-sections.md`（アノテーション表）、
`docs/learn/annotations-and-metaprogramming.md`（`@app` の設計史）、
`system/MyAppFramework/docs/APP_FRAMEWORK.md`（アプリの書き方）、
`issues/tickets/MYOS-015_userspace-apps-and-wm.md`（コンソールプロセスの現状）。
チケット: MYOS-018 〜 MYOS-022。

---

## 0. 現在の結論

この 3 つは一直線の 3 層ではない。**freestanding / hosted** と、**client / provider** を
分けて考える。

ソースコードの依存（`A → B` は A が B を import する）：

```text
                        contracts
                      ↗     ↑     ↖
アプリ ───────→ MyAppFramework    MyOS endpoints
   └──────────→ MyStdLib hosted ────────┘
                      ↓
                 MyStdLib core
```

- `MyStdLib` の通常モジュールは freestanding。`hosted/` は filesystem / process / log の
  一般プログラム向け client API、`platform/myos/` は syscall binding を持つ。
- `MyAppFramework` は UI アプリ用 SDK。UI/markup API、プロセス内 runtime、アプリ固有の
  client transportを持つ。filesystem 実装も一般 process API も持たない。
- `MyOS` は hosted API と app protocol の provider。`syscall/` がprocess境界、`ipc/`がtask境界を
  持ち、FS/processのsyscall endpointとUI/shellのprotocol endpointは各domain直下に置く。
- 共有する意味型・wire型・operation番号はルート`contracts/`に置く。ここはdata-onlyで、
  MyOS、MyAppFramework、MyStdLibのいずれにも依存しない。MyOSはMyAppFrameworkをimportしない。
- `MyOS/src/apps/*.dom.mln` は配置上 MyOS にあるが、層としては MyOS 実装ではなく
  **SDK のクライアント兼ディスクイメージ同梱物**である。

実行時は、StdLib hosted API と Framework stub がともに syscall で MyOS service を呼ぶ：

```text
app ─┬→ MyStdLib hosted API ───────────┐
     └→ MyAppFramework UI/runtime stub ├→ OS_CALL → MyOS endpoints → domain implementation
                                      ┘
```

### 置き場所の判定

| 置き場所 | 入れるもの | 入れないもの |
| --- | --- | --- |
| `contracts` | client/providerが共有する意味型、wire envelope、operation/service番号 | 関数実装、transport、handler、policy、mutable state、他層へのimport |
| `toolchain/MyStdLib` | core: コンテナ・文字列・`Result` / `Option`・toolchain形式。hosted: FS/process/log client API。platform: MyOS syscall binding | domain contract、UI/DOM、app lifecycle、service handler、MyOS policy |
| `system/MyAppFramework` | UI/markup API、annotation schema、アプリプロセスの lifecycle/handler、client transport、UI固有terminal連携 | 共有contract、filesystem API/実装、汎用process API、DOM、インストール済みアプリ一覧 |
| `system/MyOS` | `syscall/`: OS_CALL入口とuser-memory helper。`ipc/`: process/service-task transport。各domain直下: 境界endpointとdomain実装・policy | 汎用services層、アプリ内handler table、hosted APIのclient stub、汎用コンテナ |

迷ったときは、freestandingで再利用できるなら MyStdLib core、通常プログラム向けOS機能なら
MyStdLib hosted、複数層が共有する契約なら`contracts/`、UIアプリ作者向けの実装APIなら
MyAppFramework、その契約を実現する
trust-boundary処理・機構・ポリシーなら MyOS に置く。
`format/mbin.mln` と `meta/annotations.mln` が MyStdLib にあるのは、MBIN や row を読むだけで
`@app` の意味、ファイル探索、プロセス起動を一切持たないためである。UI/FS contractは
`contracts/`、そのclient APIはMyAppFramework/MyStdLib hosted、server handlerはMyOSという分割にする。

この規則は `make qa-boundaries`（`qa/tests/test-layer-boundaries.py`）で検査する。

---

## 1. 目標の形

```
アプリ (.mbin on /apps)
   │  SDK API / process runtime
MyAppFramework
   │  OS_CALL + UI protocol（ノード id と i32 / char* のみ）
MyOS service / UI server / shell
   │  kernel API
MyKernel: mm / scheduler / process / loader (MBIN, header v2) / syscall
```

### 原則

1. **境界はプロトコルで越える。import では越えない。** アプリ ↔ UI サーバは UI プロトコル、
   ユーザ空間 ↔ カーネルは syscall、ファイル ↔ ローダ／シェルは MBIN ヘッダのセクション表。
   SDK（MyAppFramework）は MyOS / MyKernel のファイルを import しない。
2. **実行時の要求は一方向。** アプリ → SDK stub → syscall → MyOS。逆向きの通知は
   コールバック登録ではなくメッセージ（イベント）。ソース依存は §0 の DAG に従う。
3. **DOM は 1 本、UI サーバ側。** ブラウザと同じ形（DOM はブラウザ、アプリは JS）。
   アプリはノード id とハンドラを持つだけで、木・レイアウト・ヒットテスト・描画・フォーカスは
   サーバに 1 つ。automation の `testId` ロケータ、`owner` による一括回収、damage 追跡は
   すべてこれを前提にしている。クライアント側ツールキット（Linux デスクトップ型）は
   「きれい」ではなく別のトレードオフで、採らない。自前描画が要るアプリには
   `<Canvas>` ノード + 共有ピクセルバッファを 1 種類足す（ブラウザの `<canvas>`）。

## 2. 各層の責務

| 層 | 場所 | 持つもの | 持たないもの |
| --- | --- | --- | --- |
| アプリ | `MyOS/src/apps`（source package）、実行時は `/apps/*.mbin` | struct、`@app` の付いた `view()`、ハンドラ | DOM の実装、他アプリの知識、MyOS 実装への import |
| Contract | `contracts` | `FsError` / `UiError` / `SeekWhence`、OS service番号、Request/Event、UiOp/AppOp | import、関数実装、transport、handler、policy、state |
| Hosted stdlib | `MyStdLib/hosted`, `platform/myos` | FS/process/log client、syscall binding | contract定義、service handler、UI、MyOS内部型 |
| SDK | `MyAppFramework/src` | アプリ向け `annotations.mln` / `ui.mln` / `elements.mln` / `terminal.mln`。`runtime/`: handler表・transport・entry | 共有contract、FS API、サーバ実装、MyOSへのimport |
| UI domain | `MyOS/src/ui` | DOM / widgets / render / compositor / graphics / theme / config。外向き通知は登録されたevent sinkへ | syscall、user pointer、app protocol、アプリ一覧 |
| Process境界 | `MyOS/src/syscall`, `fs/syscall.mln`, `proc/syscall.mln` | OS_CALL router、user-memory copy、domain syscall dispatch | domain policy、アプリ関数ポインタ |
| Task境界 | `MyOS/src/ipc` | request/reply/event channel、processごとのstaging buffer | DOM、shell policy |
| Protocol endpoint | `MyOS/src/ui/protocol*.mln`, `shell/protocol.mln` | UiOp/AppOpからdomain APIへのdispatch | transport、user pointer |
| シェル | `MyOS/src/shell` | レジストリ（ディスクの `.mbin` のヘッダから）、`install()`、launch（spawn）/ open / single、`window_ready` / `window_closed` / EXIT、キー claim、ランチャー、reap | DOM の実装、アプリのコード |
| カーネル | `MyKernel/src` | mm、scheduler、process、loader、syscall（`OS_CALL` は登録されたハンドラへ）、`ipc.mln` チャネル | デスクトップの知識（`syscall.set_console` / `set_os_handler` などの登録口だけ） |

## 3. インターフェイスの書き方

共有contractはルートでdomainごとに分ける：

```mylang
contracts/myapp/message.contract.mln    RequestDomain + Request + Event + EventKind
contracts/myapp/ui.contract.mln         UiOp（DOM/widget操作だけ）
contracts/myapp/lifecycle.contract.mln  AppOp（OPEN / CLAIM_KEY / MAIN_WINDOW / EXIT）
contracts/myos/services.contract.mln    OS_CALL service番号
contracts/io/fs.contract.mln            FsError + SeekWhence
contracts/ui/widget.contract.mln        UiError
```

- Frameworkの `runtime.send()` はUI domain、`runtime.app_send()` はAPP domainのRequestを作る。
- `runtime/transport.mln` がMyStdLibのMyOS syscall bindingを使い、REQUEST / REPLY / POLLを運ぶ。
- MyOS `ipc/gateway.mln` がuser pointerをkernel bufferへコピーし、`channel.mln`へ積む。
- `ipc/channel.mln` はdomainを見て `ui/protocol.mln` または `shell/protocol.mln` へ送る。
  UI serverはshellをimportせず、app serverだけがshell policyを呼ぶ。
- UI domainとshellはtransportもapp protocolもimportしない。内側にevent sinkとdomain型を
  定義し、外側のIPC endpointがwire型へ変換する実装をboot時に登録する（dependency inversion）。
- filesystem / process / logはこのcontractに混ぜない。MyStdLib hosted APIと
  `contracts/myos/services.contract.mln`がclient/provider間のwire番号、MyOS
  `fs/syscall.mln` / `proc/syscall.mln`がprovider endpointになる。
  FSの意味上のerror型は`contracts/io/fs.contract.mln`に一度だけ定義し、providerもclientも同じ
  `Result<T, FsError>`を使う。syscall endpointはその値をコピーするだけで、負数sentinelや
  `error_of`のような変換表を持たない。
- UI list APIも`contracts/ui/widget.contract.mln`の`UiError`を使い、選択なしは
  `Ok(None)`、不正node/index/capacityは`Err(UiError)`として返す。gatewayはtyped resultを
  copy-outし、`-1`へ変換しない。

## 4. 到達順序

各段は単独でテスト緑のまま終わる。壊れる範囲が 1 層に閉じるように切ってある。
1 と 4 は独立、2 → 3 → 5 は直列。順序は 1 → 2 → 4 → 3 → 5。

| # | チケット | 何を | 越える境界 | 終わった判定 |
| --- | --- | --- | --- | --- |
| 1 | MYOS-018 | **SDK / シェル分離** | リポジトリ | MyAppFramework が MyOS / MyKernel を import しない。`app.mln` が `MyOS/src/shell` に。`ui` / `elements` がプロトタイプ + サーバ実装。既存 E2E がすべて緑 |
| 2 | MYOS-019 | **UI プロトコル**（済） | メッセージ | `ui` / `elements` の面がメッセージ表（`docs/design/ui-protocol.md`）になり、SDK stub → request transport → server dispatchで動く。ハンドラはSDK側の表から(owner, id, arg)で呼ばれ、アプリのノードに関数ポインタは無い。`@timer` / `@key` / `@open` / `@on_close` の実行はSDK runtime、shellはinstalled appのための`@app`と`@open`有無だけを読む |
| 3 | MYOS-020 | **UI サーバをタスクに**（済） | タスク | カーネルにチャネル（`ipc.mln`）。要求・返事・イベントがチャネルを通り、UI サーバのタスクが `serve()` で答える。アプリのコードはアプリのタスクでしか走らず、DOM はサーバのタスク（+ ロックを取った automation）でしか触らない。`text_of` → `text_copy`（サーバのポインタを返さない）。syscall 化は段 5 |
| 4 | MYOS-021 | **MBIN ヘッダ v2 + ディスク上のアプリ**（済） | 実行形式 | ヘッダに `sections_offset`（`__sections` と同じディレクトリ）。MyStdLib `format/mbin.mln` / `annotations.in_image()` がファイルから表を読む。シェルは起動時にディスクの MBIN ファイルのヘッダから `@app` 行を読んでランチャーに載せ、起動はプロセス spawn。MFS は平坦なので「`/apps` ディレクトリ」ではなく「`@app` 行を持つ実行形式」が installed の定義 |
| 5 | MYOS-022 | **GUI アプリを .mbin に**（済） | 完成 | 5 アプリを個別ビルド（`build_user_apps.py`：`.dom.mln` + SDK の `app_main`）してディスクへ。`OS_CALL` syscall（UI / fs / プロセス）、per-pid チャネル、ユーザメモリのコピー、`text_of` 廃止（`text_copy`）。`boot/main.mln` の明示 import と in-process 経路（`host.mln`）を削除。レジストリはディスクのヘッダだけを見る。副産物：mlc がグローバルを `.data` に出し、ユーザプロセスのテキストが RX に戻った |

### 二系統の期間

3 が終わるまで GUI アプリは image にリンクされたまま動いた（Phase A）。5 で 5 本まとめて
プロセスに移し、in-process 経路は同じコミットで消した（二系統を束ねる期間は結局置かなかった）。

## 5. 決めていないこと

- ~~**IPC の形**~~（3 で決めた）：チャネル + 24 ワード固定長メッセージ（`docs/design/ui-protocol.md` §1）。
  Event の text 64 bytes は slot 内に保持する
- ~~**文字列の渡し方**~~（5 で決めた）：`ipc/gateway.mln` が NUL 終端 + 上限（s0 1024 / s1 128 /
  TEXT_COPY 4096 / イベント 64）でコピーする
- ~~**ノード id 空間**~~（済）：id は `remove_node` で free list に戻り再利用される。owner
  （pid）ごとに `NODES_PER_OWNER` = 96 まで、超えると CREATE は 0 を返す（panic しない）
- ~~**FS のディレクトリ**~~（済）：MFS にディレクトリが入り、`/bin` にコンソールプログラム、
  `/apps` にデスクトップアプリ。シェルは `/apps` を列挙し、`spawn_file` は裸の名前を
  `/bin` → `/apps` の順に探す
- **`<Canvas>`**：自前描画の逃げ道。必要になるまで作らない

## 6. やらないこと

- クライアント側 DOM（アプリごとのツールキット）
- ELF 互換の実行形式。リロケーション・動的リンク・シンボル表は要らない（プロセスごとに
  VA 空間があり、固定ベースで足りる）。MBIN はヘッダにセクション表のオフセットを足しただけ
- コンソールプログラム（hello / echo / count）の作り直し。既にプロセスで、そのまま
