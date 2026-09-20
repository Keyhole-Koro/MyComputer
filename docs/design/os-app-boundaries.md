# OS とアプリの境界 — 層と、層の間を越えるもの

2026-09-20。MyOS のデスクトップアプリを「カーネル image にリンクされた関数」から
「`/apps` 上の実行形式（プロセス）」へ持っていくための、層の定義と到達順序。
以後の判断の基準として置くもので、各段の細部は実装しながら詰める。

関連: `docs/design/toolchain-collected-sections.md`（アノテーション表）、
`docs/learn/annotations-and-metaprogramming.md`（`@app` の設計史）、
`system/MyAppFramework/docs/APP_FRAMEWORK.md`（アプリの書き方）、
`issues/tickets/MYOS-015_userspace-apps-and-wm.md`（コンソールプロセスの現状）。
チケット: MYOS-018 〜 MYOS-022。

---

## 1. 目標の形

```
アプリ (.mbin on /apps)
   │  リンクするのは SDK だけ
SDK        MyAppFramework: annotations / ui / elements（インターフェイス）、ハンドラ表 + イベントループ
   │  UI プロトコル（メッセージ。ノード id と i32 / char* のみ）
UI サーバ   MyOS/src/ui: dom / widgets / render / compositor  — 自分のタスク、DOM は 1 本
   │  サーバ API（MyLang の import）
シェル      MyOS/src/shell: レジストリ（/apps のヘッダ + 組み込み）、ランチャー、タスクバー、キー配送、ウィンドウ管理
   │  syscall（exit / write / read / spawn / sbrk + IPC）
カーネル    MyKernel: mm / scheduler / process / loader (MBIN, header v2) / syscall
```

### 原則

1. **境界はプロトコルで越える。import では越えない。** アプリ ↔ UI サーバは UI プロトコル、
   ユーザ空間 ↔ カーネルは syscall、ファイル ↔ ローダ／シェルは MBIN ヘッダのセクション表。
   SDK（MyAppFramework）は MyOS / MyKernel のファイルを import しない。
2. **依存は一方向。** アプリ → SDK → プロトコル → UI サーバ → カーネル。逆向きの通知は
   コールバック登録ではなくメッセージ（イベント）。
3. **DOM は 1 本、UI サーバ側。** ブラウザと同じ形（DOM はブラウザ、アプリは JS）。
   アプリはノード id とハンドラを持つだけで、木・レイアウト・ヒットテスト・描画・フォーカスは
   サーバに 1 つ。automation の `testId` ロケータ、`owner` による一括回収、damage 追跡は
   すべてこれを前提にしている。クライアント側ツールキット（Linux デスクトップ型）は
   「きれい」ではなく別のトレードオフで、採らない。自前描画が要るアプリには
   `<Canvas>` ノード + 共有ピクセルバッファを 1 種類足す（ブラウザの `<canvas>`）。

## 2. 各層の責務

| 層 | 場所 | 持つもの | 持たないもの |
| --- | --- | --- | --- |
| アプリ | `MyOS/src/apps`（→ 最終的に `/apps/*.mbin`） | struct、`@app` の付いた `view()`、ハンドラ | DOM の実装、他アプリの知識 |
| SDK | `MyAppFramework/src` | `annotations.mln`（宣言）、`protocol.mln`（メッセージ表）、`ui.mln` / `elements.mln`（要求を送るスタブ。markup の語彙とデフォルト）、`runtime.mln`（ハンドラ表、`start`、`pump`） | サーバの実装。MyOS への import |
| UI サーバ | `MyOS/src/ui` | dom / dom_widgets / dom_render / compositor、プロトコルの受け手（`ui_channel` / `ui_server` / `elements_server` / `ui_events`） | アプリの一覧、起動、ウィンドウ閉じの意味、アプリの関数ポインタ |
| シェル | `MyOS/src/shell` | レジストリ、`install()`、launch / open / single、`window_closed`、キー配送、ランチャー、タスクバーの内容 | DOM の実装 |
| カーネル | `MyKernel/src` | mm、scheduler、process、loader、syscall、（Phase C で）IPC | デスクトップの知識（`syscall.set_console` などの登録口だけ） |

## 3. インターフェイスの書き方

MyLang にはヘッダが無いが、**本体の無い export プロトタイプ**がそれに当たる：

```mylang
// MyAppFramework/src/protocol.mln — SDK。運び手の宣言。コードは出ない
package uiproto;
export i32 request(UiMsg *m);
export bool poll(UiEvent *out);

// MyOS/src/ui/ui_channel.mln — OS。同じ package 名 → 同じ link 名 (uiproto_request)
package uiproto;
export i32 request(UiMsg *m) { return ui_server.handle(m); }
```

- 呼ぶ側は SDK を import し `uiproto.request(&m)` と書く。mlc は宣言（デフォルト引数を含む）を
  SDK 側から取り、`uiproto_request` を import する。リンカが OS 側の定義に結ぶ
- 段 1（MYOS-018）では `ui.mln` / `elements.mln` 自体をこの形（プロトタイプ + サーバ側の同名
  package）にして、段 2（MYOS-019）でそれらに**本体**（`UiMsg` を送るスタブ）を付け、サーバ側を
  `ui_server.handle(m)` / `elements_server.create(m)` というメッセージの受け手にした。
  同名 package の仕組みが残っているのは運び手 `request` / `poll` だけで、段 3 でこれが
  syscall になる。表は `docs/design/ui-protocol.md`
- 同じ package 名のファイルが SDK と OS に 1 つずつある。ビルドはパスで区別する
  （`build_toolchain.py` の出力キーはリポジトリ相対パス）

## 4. 到達順序

各段は単独でテスト緑のまま終わる。壊れる範囲が 1 層に閉じるように切ってある。
1 と 4 は独立、2 → 3 → 5 は直列。順序は 1 → 2 → 4 → 3 → 5。

| # | チケット | 何を | 越える境界 | 終わった判定 |
| --- | --- | --- | --- | --- |
| 1 | MYOS-018 | **SDK / シェル分離** | リポジトリ | MyAppFramework が MyOS / MyKernel を import しない。`app.mln` が `MyOS/src/shell` に。`ui` / `elements` がプロトタイプ + サーバ実装。既存 E2E がすべて緑 |
| 2 | MYOS-019 | **UI プロトコル**（済） | メッセージ | `ui` / `elements` の面がメッセージ表（`docs/design/ui-protocol.md`）になり、SDK 側スタブ → `uiproto.request` → サーバ側ディスパッチで動く（同一プロセス内）。ハンドラは SDK 側のハンドラ表から (owner, id, arg) で呼ばれる。アプリのノードに関数ポインタは無い。`@timer` / `@key` / `@open` / `@on_close` の意味は SDK の `runtime.mln` に移り、シェルは `@app` だけを知る |
| 3 | MYOS-020 | **UI サーバをタスクに**（済） | タスク | カーネルにチャネル（`ipc.mln`）。要求・返事・イベントがチャネルを通り、UI サーバのタスクが `serve()` で答える。アプリのコードはアプリのタスクでしか走らず、DOM はサーバのタスク（+ ロックを取った automation）でしか触らない。`text_of` → `text_copy`（サーバのポインタを返さない）。syscall 化は段 5 |
| 4 | MYOS-021 | **MBIN ヘッダ v2 + ディスク上のアプリ**（済） | 実行形式 | ヘッダに `sections_offset`（`__sections` と同じディレクトリ）。MyStdLib `format/mbin.mln` / `annotations.in_image()` がファイルから表を読む。シェルは起動時にディスクの MBIN ファイルのヘッダから `@app` 行を読んでランチャーに載せ、起動はプロセス spawn。MFS は平坦なので「`/apps` ディレクトリ」ではなく「`@app` 行を持つ実行形式」が installed の定義 |
| 5 | MYOS-022 | **GUI アプリを .mbin に** | 完成 | アプリを個別ビルドして `/apps` へ。`boot/main.mln` の明示 import と Phase A 経路を削除。レジストリは `/apps` のヘッダだけを見る |

### 二系統の期間

3 が終わるまで、GUI アプリは image にリンクされたまま動く（Phase A）。5 でも「組み込み
（image にリンク）」と「インストール済み（`/apps`）」をレジストリが束ねる形を一度通る。
移行が終わったら前者を消す。

## 5. 決めていないこと

- ~~**IPC の形**~~（3 で決めた）：チャネル + 16 ワード固定長メッセージ（`docs/design/ui-protocol.md` §1）
- **文字列の渡し方**（5）：同一アドレス空間では `char*` で足りるが、プロセス境界では
  syscall がコピーする。長さは NUL 終端 + 上限で決める
- **ノード id 空間**：256 で尽きる既知の制限と、owner ごとの上限。2 で id の払い出しを
  サーバに寄せるときに直す
- **`<Canvas>`**：自前描画の逃げ道。必要になるまで作らない

## 6. やらないこと

- クライアント側 DOM（アプリごとのツールキット）
- ELF 互換の実行形式。リロケーション・動的リンク・シンボル表は要らない（プロセスごとに
  VA 空間があり、固定ベースで足りる）。MBIN はヘッダにセクション表のオフセットを足しただけ
- コンソールプログラム（hello / echo / count）の作り直し。既にプロセスで、そのまま
