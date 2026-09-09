# MYOS-012: DOM Inspector CLI（MyDOMTester 拡張）

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| In Progress | - | claude-code:sonnet-5 | 2026-09-09 |

## Summary

`system/MyOS/tests/mydomtester` に、実行中の MyKernel DOM ツリーをターミナルから
ライブで覗ける `inspect` CLI を追加する。ブラウザ DevTools の Elements パネル相当を、
既存の `dom.snapshot` / control-stdio の上に薄く乗せる。

## Background

MYOS-004 で `dom.snapshot`（JSON Lines）と `mydomtester` の Playwright 風 locator API
（`system/MyOS/tests/mydomtester/__init__.py`）は整ったが、これはスクリプトテスト用で、
人間がその場でツリーを眺めたり状態を確認したりする手段ではない。今あるのは：

- `dom.dump()`（シリアルへの人間可読 dump、CLI 越しには見えない）
- `dom.snapshot` control-stdio コマンド（`runtime/MyEmulator/src/control_stdio.rs:87` 、
  内部は shell に `dom\r` を打って `---DOM-SNAPSHOT-BEGIN/END---` を capture するだけ）
- `Page.dom_snapshot()` / `Locator` （`mydomtester/__init__.py:141-237`、1回のスナップショット取得と
  locator 解決のみ）

いずれも「1回叩いて終わり」か「アサーションの裏側」で、継続的に見る・差分を追う UI はない。

**補足（2026-09-09、実機確認済み）**: 通常の `make run`（ウィンドウ表示あり、
`--control-stdio` なし）でも、`shell.mln:63` の `dom` コマンドはそのまま使える。
`execute_with_debug` パス（`runtime/MyEmulator/src/machine/interrupts.rs:12`
`start_serial_input()`）はターミナルの stdin をシリアル RX へフォワードするので、
ウィンドウを見ながら同じターミナルに `dom` と打つと、その場で JSON ツリーが
標準出力に印字される（`--control-stdio` はこのフォワーディングをスキップして
自前で stdin を握るので、ウィンドウ表示とは両立しない別モード）。
「本物のウィンドウを見ながら自分でクリックしつつ DOM も見たい」という用途は、
新規実装なしでこれで足りる。フェーズ1以降の CLI は「別プロセス・ヘッドレスで
継続的に監視/操作したい」（watch・自動クリック）用途を担う。

## Design

### Current State

- `dom.mln` は props を固定スロットで持つ（`id/kind/role/name/text/x/y/w/h/state`、
  `system/MyOS/docs/DOM_SPEC.md` のレイアウト）。読み取り系 API
  （`get_node`/`first_child`/`next_sibling`）と書き込み系 API
  （`set_bounds`/`set_text`/`set_role`/`set_state_flag`、`system/MyOS/src/ui/dom.mln:231-391`）
  は揃っているが、**書き込み系は mylang コード（`main.mln` 等）からしか呼べない**。
  shell コマンドや control-stdio からは呼べない。
- `control_stdio.rs` が実装しているコマンドは `mouse.move/down/up`・`frame.wait`・
  `dom.snapshot`・`screenshot` のみ（`control_stdio.rs:59-96`）。prop を書き込む
  コマンドは存在しない。
- `mydomtester.Page` は 1 回分の snapshot 取得・mouse 注入・screenshot しかできず、
  継続的な watch や対話的なノード選択はない。
- リポジトリ内に devtool/inspector 相当の既存実装なし（確認済み、重複なし）。

### Proposed Design

2 フェーズに分ける。フェーズ1はカーネル/エミュレータを一切変更せず、既存の
`dom.snapshot` だけで完結する。フェーズ2は書き込みを外部から叩けるようにする。

#### フェーズ1: 読み取り専用 watch/inspect CLI

`system/MyOS/tests/mydomtester/inspect.py`（新規）を追加。`mydomtester.launch()` を
そのまま使う。

```
python3 -m system.MyOS.tests.mydomtester.inspect build/firmware_linked.mbin \
    --disk build/disk.img [--watch] [--interval 0.5] [--node <id>]
```

- デフォルトは 1 回分の `dom_snapshot()` をインデント付きツリーとして標準出力に描画
  （`id / role / name / text / bounds / state flags` を1行1ノード）。
- `--watch`: `frame.wait` → `dom_snapshot()` を `--interval` 秒間隔で繰り返し、前回との
  差分（追加/削除/props変化したノード）だけ色付け/マーク表示する。
- `--node <id>`: 指定ノードの全 props を詳細表示（snapshot の該当エントリをそのまま展開）。
- 既存の `Page`/`Locator` には変更不要。`inspect.py` は `Page.dom_snapshot()` を呼ぶだけの
  読み取り専用クライアント。

#### フェーズ2: prop 書き込み（ライブ編集）

control-stdio に prop 書き込みコマンドを追加する。実装は `dom.snapshot` と同じ
パターン（shell にコマンド文字列を `ingest_serial_bytes` で流し込み、ack を待つ）。

1. `shell.mln` に `set <id> <prop> <value>` コマンドを追加し、内部で
   `dom.set_bounds`/`set_text`/`set_state_flag` にディスパッチする（prop 名は
   `x/y/w/h/text/visible/enabled/hovered/pressed` の固定集合）。
2. `control_stdio.rs` に `dom.set_prop`（`{"cmd":"dom.set_prop","id":9,"prop":"text","value":"..."}`）
   を追加。内部は `set <id> <prop> <value>\r` を shell に注入し ack するだけ
  （`dom_snapshot` 関数と同じ「文字列を shell に打つ」方式を流用、新規パース経路は増やさない）。
3. `Page.set_prop(id, prop, value)` を `mydomtester/__init__.py` に追加。
4. `inspect.py` に対話モード（ノード選択 → prop 編集 → 即 watch 表示で反映確認）を追加。

ハイライト（画面上に選択ノードの枠を重ねる）はフェーズ2の範囲に含めない。理由は
Alternatives Considered を参照。

#### フェーズ3: クリック操作 DSL（実装済み、2026-09-09）

`system/MyOS/tests/mydomtester/dsl.py`（新規）を追加。既存の `Page`/`Locator` API
の上に薄い行指向スクリプト構文を乗せるだけで、新しいプロトコル・カーネル変更は
一切増やさない。

```
# system/MyOS/tests/dom/counter.domscript
dump
click role=button name="CLICK ME"
wait_for text="clicks: 1"
click role=button name="CLICK ME"
click role=button name="CLICK ME"
wait_for text="clicks: 3"
dump
```

```
make dom-script SCRIPT=system/MyOS/tests/dom/counter.domscript
```

コマンド一覧: `click role=/name=/text=`、`wait_for ...  [timeout=<秒>]`、
`dump`（`inspect.py` の `render_tree` を再利用）、`screenshot path=...`、
`sleep <秒>`。各行は `shlex.split(..., comments=True)` でトークン化するので
`name="CLICK ME"` のような空白入り文字列も安全に扱える。失敗時は
`<path>:<lineno>: <行内容>: <エラー>` の形式で止まる（サイレント失敗させない）。

### Alternatives Considered

- **ブラウザ風 DevTools Web UI**: 見た目は良いが、`MyEmulator` に HTTP/WebSocket サーバを
  追加する必要があり、`control_stdio.rs` の設計方針（「TCP/WebSocket は不要、CI で扱い
  やすい stdio を優先」、`issues/completed/MYOS-004_mykernel-ui-automation.md`）と逆行する。
  個人のデバッグ用途には過剰。
- **TUI（curses）+ 画面ハイライト**: 選択ノードを画面上に枠で重ねるには、エミュレータの
  描画パスに「inspector overlay」を割り込ませるか、renderer に専用 state bit を足す必要が
  あり、フェーズ1より実装コストが大きい。まずテキストベースの watch で十分な価値が出るか
  確認してから検討する。
- **既存の `STATE_HOVERED` を inspector のハイライトに流用**: button の hover 見た目
  ロジック（`system/MyOS/docs/DOM_SPEC.md` の `draw_node` 例、`hovered` 分岐）が
  `STATE_HOVERED` に依存しているため、inspector が同じビットを書き換えると実際の
  マウス hover 挙動と衝突する。専用ビット/オーバーレイが要るなら別チケットで検討する。
- **`dump()`（人間可読テキスト）をそのまま CLI に流用**: 出力フォーマットが安定した
  機械可読ではない（ISSUE-006 / DOM_SPEC の方針どおり `dump()` は人間用、`snapshot()` が
  機械可読用と役割分担済み）。CLI は `snapshot()` の上に作る。
- **毎フレーム自動で DOM をキャプチャする**: renderer は入力のたびに高頻度で走るため、
  render 呼び出しに素直に `dump_json()` を差し込むとシリアル出力が洪水になる。
  「変化を追いたい」というニーズは既にフェーズ1の `--watch`（スナップショット間 diff、
  指定間隔でポーリング）で満たせるため、フレーム同期のキャプチャは採用しない。
- **クリック DSL を MyLang 側の `.test.mln`（MLT-001/002）に寄せる**: カーネルの
  test framework と一体化できる利点はあるが、mylang / test runner 側の変更が要る。
  今回は既存の Python `Page`/`Locator` API に薄い構文を足すだけで済む Python 側 DSL
  （`dsl.py`）を選んだ。カーネルテスト基盤への統合は必要になったら別チケットで検討。

### Non-Goals

- CSS セレクタ的な汎用クエリ言語（`get_by_role`/`get_by_text` 以上のものは作らない）。
- 画面上への選択ノードのハイライト描画（フェーズ2に含めない、上記 Alternatives 参照）。
- ブラウザ/Web ベースの UI。
- 複数クライアントからの同時接続・リモート越しの inspector。

## Progress

- [x] フェーズ1: `mydomtester/inspect.py` の 1 回 dump モード（`make dom-inspect`）
- [x] フェーズ1: `--watch` モードとスナップショット間 diff 表示
- [x] フェーズ1: `--node <id>` の詳細表示
- [ ] フェーズ2: `shell.mln` に `set <id> <prop> <value>` コマンド追加
- [ ] フェーズ2: `control_stdio.rs` に `dom.set_prop` 追加
- [ ] フェーズ2: `Page.set_prop()` と `inspect.py` の対話編集モード
- [x] フェーズ3: `mydomtester/dsl.py`（`click`/`wait_for`/`dump`/`screenshot`/`sleep`）
- [x] フェーズ3: `make dom-script SCRIPT=...` と counter UI 用の example fixture

## Verification

```
# ビルド（既存の counter UI fixture を使う）
make build

# フェーズ1: 1回 dump
make dom-inspect

# フェーズ1: 特定ノードの詳細
make dom-inspect ARGS="--node 11"

# フェーズ1: watch しながら実機クリックでカウンタが動くのを確認
make dom-inspect ARGS="--watch"

# フェーズ3: DSL スクリプトでクリック操作を自動実行
make dom-script SCRIPT=system/MyOS/tests/dom/counter.domscript
```

## 完了条件

- フェーズ1: `inspect.py` の 1 回 dump 出力が `dom.snapshot` の内容（id/role/name/text/bounds/state）を
  欠落なくツリー表示する。
- フェーズ1: `--watch` 中に `button.click()`（`mydomtester` 経由、または自動化スクリプト）で
  `clicks: N` のテキストノードが変化したら、次の watch tick でその行が diff マークつきで表示される。
- フェーズ1: `--node <id>` が存在しない id を渡されたらエラーを返す（無言で落ちない）。
- フェーズ2: `dom.set_prop` で `text` を書き換えた直後の `dom.snapshot` に反映される。
- フェーズ2: 既存の `dom_click_test.py` / control-stdio 既存コマンドの挙動が変わらない（回帰なし）。
- フェーズ3: `counter.domscript` が `make dom-script` で最後まで実行され、
  `clicks: 3` の `wait_for` を通過する（実機確認済み、2026-09-09）。
- フェーズ3: 存在しないノードを指す `click`/`wait_for` は `<path>:<lineno>` 付きの
  エラーで止まる（サイレント失敗しない、実機確認済み）。

## 関連

- `issues/completed/MYOS-001_dom-like-os.md`
- `issues/completed/MYOS-004_mykernel-ui-automation.md`
- `issues/completed/MYOS-011_dom-click-test-control-stdio-timeout.md`（control-stdio の
  既知の不安定さ。フェーズ2の新コマンド追加時に同じタイムアウト経路を踏まないよう注意）
- `system/MyOS/docs/DOM_SPEC.md`
