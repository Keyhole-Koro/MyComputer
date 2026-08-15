# Kernel UI Separation（compositor 抽出とデモアプリの apps 移動）

## 背景・目的

`system/MyKernel/src/kernel/main.dom.mln` は 185 行のうち約 120 行が UI で、
カーネルが**ウィンドウマネージャ兼デモアプリ**を兼ねている。

| 分類 | 内容 | 行数目安 |
|---|---|---|
| カーネル | boot banner / arch init / heap・dom・fs init / scheduler・IRQ / shell spawn | 〜60 |
| コンポジタ | `draw_cursor` / `present_frame` / `ui_loop` | 〜60 |
| アプリ | `g_clicks` / `g_click_buf[32]` / `on_button_click` / `build_ui` | 〜60 |

ファイル名が `.dom.mln` なのはこの混在の**症状**であって原因ではない。JSX を持つのは
`build_ui()` だけなので、アプリを追い出せば拡張子は `main.mln` に戻る。

MDT-001 で native DOM 構文へ移行した際、`.mlx` → `.dom.mln` の改名だけ行い
UI 分離は follow-up として残した。本チケットがその follow-up。

## 中心課題：`ui_loop` がボタン1個に密結合している

```mylang
void ui_loop(i32 btn) {          // ボタンの id を引数で受け取る
    ...
    if (dom.find_at(ex, ey) == btn) {   // その1個とだけ比較
        dom.set_pressed(btn, 1);
        dom.dispatch_click(btn);
    }
    ...
    if (dom.find_at(mx, my) == btn) { over_button = 1; }
    dom.set_hovered(btn, over_button);
}
```

これは**アプリのコードではなく、コンポジタ／イベントディスパッチャの仕事**。
特定ノードを知っている限り MyOS 側へは移せない。

幸い dom.mln 側の API は既に一般化されている:

- `find_at(x, y)` → ヒットしたノード id（ボタン限定ではない）
- `dispatch_click(id)` → そのノードの handler を間接呼び出し。handler が無ければ 0
- `get_on_click(id)` → handler の有無を事前に確認できる

したがって `btn` との比較を「`find_at` の戻り値をそのまま使う」へ置き換えれば一般化できる。
hover / pressed も「前回ヒットしたノード」を保持して差分を取る形にする。

## 段階

### フェーズ1: compositor の抽出

`system/MyOS/src/ui/compositor.mln`（新規）へ移す:

- `draw_cursor(mx, my)`
- `present_frame(mx, my)` — `dom.render_scene()` → cursor → `graphics.present()`
- `run()` — 現 `ui_loop` の一般化版。export する

一般化の要点:

- `i32 btn` 引数を削除。`find_at` の戻り値を直接使う
- press edge: `i32 hit = dom.find_at(ex, ey);` → `hit != 0` なら
  `set_pressed(hit, 1)` + `dispatch_click(hit)`
- release: 直前に pressed にしたノード id を保持しておき、それを戻す
- hover: `i32 hot = dom.find_at(mx, my);` が前回と変われば
  前回ノードを `set_hovered(.., 0)`、新ノードを `set_hovered(.., 1)`、dirty=1

### フェーズ2: デモアプリの apps 移動

`g_clicks` / `g_click_buf[32]` / `on_button_click` / `build_ui` を
`system/MyOS/src/apps/counter.dom.mln` へ寄せる。

既存の `counter.dom.mln` はほぼ同じ内容の別実装（`dispatch_click` を直接叩く単純版で
マウス処理を持たない）。**重複を残さず、カーネル版の内容へ統合する**こと。
`counter.dom.mln` 側の `main()` は不要になる。

`export i32 mount()` のような形で「ツリーを作って desktop に append し、
必要なら内部状態を初期化する」入口を1つ用意する。

### フェーズ3: カーネルを `main.mln` に戻す

`main.dom.mln` → `main.mln`（JSX が無くなるので `dom` modifier が不要になる）。

- `src/boot/stub.masm` の import パスを追従
- `qa/run_kernel.py` / `qa/run_system.py` の既定パスを追従
- `kernel_init()` は `counter.mount()` を呼び、compositor をタスクとして起動する

⚠️ **要検討**: 現在 `kernel_init()` の末尾で `ui_loop(btn)` を直接呼んでおり、
`while(1)` なので戻ってこない。`scheduler.spawn_task(shell.run)` と同じ形で
`scheduler.spawn_task(compositor.run)` にできるか、scheduler との噛み合わせを確認する。
UI タスクと shell タスクが両方 `sleep(1)` で回る形になる。

## 非目標

- ウィンドウの移動・リサイズ・z-order 管理。
- 複数ウィンドウのフォーカス管理。
- レイアウトエンジン。
- `dom.mln` のノード表現そのものの変更。

## 検証

1. `python3 qa/run_kernel.py` で boot し、serial に DOM tree が出る。
2. `python3 qa/gui_click_test.py` でボタンを実クリックし、ラベルが
   `clicks: 1` → `clicks: 2` と更新される（XTEST + フレームバッファ撮影）。
3. `make dom-test` — `.dom.mln` lowering の e2e が通ったままであること。
4. `system/MyKernel/src/kernel/main.mln` に UI コードが残っていない。

## 完了条件

- カーネルの `main` が `.mln` に戻り、UI コードを持たない。
- compositor が特定ノード id を知らずにクリック・hover を捌ける。
- カウンタのデモが `MyOS/src/apps/` 側の1ファイルに統合され、重複が無い。
- GUI クリックテストが通る。

## 実装状況（2026-08-15）

フェーズ1〜3 完了。`main.dom.mln` 185行 → `main.mln` 51行、UI コードはゼロ。
`ui_loop` は `compositor.run()` として一般化し、ノード id を一切持たない形になった。
検証は `make dom-test`（lowering + hit-dispatch の2 suite）が通ることと、
`qa/run_kernel.py` で boot して DOM tree が出ること。

⚠️ `qa/gui_click_test.py` は未実行。`python-xlib` が入っておらず、この環境の pip は
PEP 668 で外部インストールを拒否する。XTEST 自体は `libXtst` を ctypes で叩けば
使えるので（性能計測ではその方法でポインタを動かした）、テスト側をそちらに
移植すれば実行できる。

## 派生：カーソル追従が遅い件 → 別チケット（MYOS-010 予定）

UI 分離後、「マウスポインタの追従に 1.5 秒ほどのラグがある」という問題が判明。
測定した結果、**分離とは無関係**で、原因は2つに分かれた。

**ホスト側**（対処済み、MyEmulator `perf: scan out frames via MIT-SHM...`）

- minifb の `XPutImage` が毎フレーム 3MB を X ソケットへ転送していた（~7ms/frame）。
  MIT-SHM に変更して ~1ms/frame。
- `poll_input()` が 2ms ごとに `window.update()`（X イベントキューの drain、
  実測 0.5〜1.8ms）を呼び、実時間の半分以上を X の中で消費してゲスト CPU を
  枯渇させていた。表示周期に分離。
- ホスト I/O は実時間の 49% → 22%。ただし体感は「ちょっとマシ」止まりだった。

**ゲスト側**（未対処、これが本命）

`myemu --io-stats` に足したフレーム毎の命令数で切り分けた。ポインタを
XTEST で動かしながらの実測：

| 構成 | 命令/frame | frame 時間 | fps |
|---|---|---|---|
| 現状（シーン＋カーソル） | 960,292 | 283 ms | 3.5 |
| カーソルのみ除去 | 683,016 | 118 ms | 8.5 |
| シーン描画のみ除去 | 224,897 | 35 ms | 28.6 |

- `render_scene`: 約 735,000 命令/frame（≈59ms）。ポインタが 1px 動くたびに
  背景全画面クリア＋全ウィンドウ＋全グリフを描き直している。**差分描画なし**。
- カーソル（36 px の矢印）: 約 277,000 命令/frame（≈22ms）。`draw_line` が
  `put_pixel` を1ピクセルずつ呼ぶうえ、MyLang codegen が冗長（ローカル変数が
  レジスタに載らず、式が毎回 push/pop 経由）なため 1px あたり数千命令かかる。

対策候補（効果が大きい順）:

1. カーソルをエミュレータ側のオーバーレイにする。ゲストは座標を書くだけになり
   描画コストが消える。要 device 追加。
2. カーソルを damage rect 方式に（カーソル下の背景を退避・復元）。
3. `render_scene` の差分化（変更ノードの矩形だけ再描画）。

なお `scheduler_tick` も 1 tick 260 命令（21µs）と重いが、1ms 周期に対して 2.1%
なので体感には効かない。これも codegen の冗長さ由来で、根本は MLC-005（typed IR）。

## 関連

- MDT-001: native `.dom.mln` 化。本チケットはその follow-up。
- MYOS-004: DOM UI automation。フェーズ1の一般化は locator ベース操作の前提。
- MYOS-005: UI renderer phase2。差分描画はここに載せるのが自然。
- MLC-005: typed IR。描画ループの命令数を根本的に減らすのはこちら。
