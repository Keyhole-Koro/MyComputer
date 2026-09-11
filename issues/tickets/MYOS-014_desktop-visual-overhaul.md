# MYOS-014: デスクトップ UI 刷新（描画プリミティブ・WM・キーボード・スクリーンショット）

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| In Progress | main | claude-code:opus-5 | 2026-09-11 |

## Summary

「綺麗な OS 画面」を作れる土台を一気に揃える。エミュレータの 2D アクセラレータ
（blit / alpha / グラデーション / A8 マスク）、キーボードデバイス、右クリック・
ホイール、PNG スクリーンショットを追加し、その上にアンチエイリアス付き
プロポーショナルフォント・角丸・影・テーマ・ウィンドウクローム・ドラッグ・
フォーカス・タスクバー・時計・TextInput 等を MyOS 側に実装する。

## Background

`make dom-script` で撮った 2026-09-11 時点の画面は、白い矩形＋8x8 ビットマップ
フォント 2 倍拡大＋灰色ボタンだけの状態だった。原因は各層の機能不足:

- `runtime/MyEmulator/src/machine/memory_bus.rs:422` DMA2D は `fill_rect` のみ。
  アルファも矩形コピーもない。
- `system/MyOS/src/ui/font8x8.mln` 8x8 固定幅ビットマップのみ。
- `system/MyOS/src/ui/dom.mln:792` `draw_node` に色が直書き。Window はタイトルバーも
  閉じるボタンも無い。z-order は兄弟順固定、`STATE_FOCUSED` 未使用。
- GUI 窓のキー入力は OS に届かない（stdin→serial のみ）。マウスは左ボタンのみ
  (`constants.rs:72`)。
- スクリーンショットは control-stdio 経由の PPM のみ。CLI から直接は撮れない。

## Design

### Current State

- 表示: 2048x1536 32bit VRAM、`DISPLAY_SWAP` でフロントへコピー。HW カーソル。
- DOM: `Window/Box/Column/Button/Text` の 5 種。`.dom.mln` のタグは dom.mln の
  同名関数へ、プロパティは同名パラメータへ lower される（全プロパティ必須）。
- 再描画: ダメージ矩形 1 つ、`render_scene` が領域内ノードのみ再描画。
- 入力: `mouse.mln` がソフトウェアキューを持ち、compositor が drain。

### Proposed Design

#### エミュレータ（MMIO 追加。`constants.rs` を正とする）

| レジスタ | オフセット | 用途 |
|---|---|---|
| `DMA2D_SRC_ADDR` | 0x90 | コピー元アドレス（RAM / VRAM） |
| `DMA2D_SRC_STRIDE_ADDR` | 0x94 | コピー元ストライド（COPY: ピクセル, MASK_A8: バイト） |
| `DMA2D_COLOR2_ADDR` | 0x98 | グラデーション終端色 |
| `DMA2D_RADIUS_ADDR` | 0x9C | 角丸半径 |
| `DMA2D_SPREAD_ADDR` | 0xB8 | 枠線の太さ / 影のぼかし幅 |
| `DMA2D_CLIP_X0/Y0/X1/Y1` | 0xC0-0xCC | シザー矩形（全コマンドに適用、X1<=X0 で無効） |
| `KBD_EVT_STATUS/TYPE/CODE/MODS/POP` | 0xA0-0xB0 | キーボードイベント FIFO |
| `MOUSE_EVT_WHEEL_ADDR` | 0xB4 | 先頭マウスイベントのホイール量 |

DMA2D コマンド: 1=FILL（既存）, 2=BLEND_FILL（COLOR=0xAARRGGBB）, 3=COPY,
4=COPY_BLEND（ソースのピクセル毎アルファ）, 5=MASK_A8（8bit カバレッジ × COLOR、
AA 文字用）, 6=GRADIENT_V, 7=GRADIENT_H（COLOR→COLOR2）, 8=ROUND_RECT,
9=ROUND_RECT_OUTLINE, 10=SHADOW（角丸・影はゲスト側で 1 px ずつ計算すると
最初のフレームに数千万命令かかったため、距離場をデバイス側で評価する）。

キーボード: minifb の `InputCallback` で押下/解放/文字入力を順序どおりに FIFO へ。
イベント type 1=down 2=up 3=char。`IRQ_CAUSE_KEYBOARD = 1<<7`。
マウス: bit1=右, bit2=中, ホイールはイベント毎の符号付きステップ数。
スクリーンショット: 依存クレート無しの PNG エンコーダ（stored deflate）。
`--screenshot <path>` CLI（`--step` 終了時 / halt 時に保存）と control-stdio の
`screenshot` が拡張子で PNG/PPM を選ぶ。

#### MyKernel

- `src/io/keyboard.mln`: mouse.mln と同型のドライバ（HW FIFO → ソフトキュー）。
- `irq_dispatch.mln`: `IRQ_CAUSE_KEYBOARD` で drain。
- `mouse.mln`: 右/中ボタン、ホイール。

#### MyOS graphics

- `rgba()` / `blend_rect()` / `copy_rect()` / `fill_gradient_v/h()`
- `fill_round_rect()` / `draw_round_rect()`（角は AA ブレンド）/ `draw_shadow()`
- `font_sans.mln`（生成物、`tools/gen_font.py`）: A8 カバレッジ + tight bbox の
  プロポーショナルフォント。Regular/Bold × 13/26/16/32px。
  `draw_label(x, y, s, color, style)` / `text_width(s, style)`。
- クリップスタック: `push_clip()` / `pop_clip()` で親矩形と交差。

#### MyOS dom / compositor

- テーマ: `theme.mln` に色パレットを集約。`draw_node` はテーマ経由。
- Window: タイトルバー（高さ 32 logical px）、閉じるボタン、影、角丸。
  `STATE_FOCUSED` で見た目が変わる。`bring_to_front(id)` で兄弟末尾へ移動。
- ドラッグ移動: compositor が press→move で `move_node`。
- 新ノード: `Row`, `Label`（色付き Text）, `TextInput`, `Checkbox`, `Separator`,
  `Panel`（角丸 Box）。
- キーボードフォーカス: `set_focus(id)`、`dispatch_key(code)` / `dispatch_char(c)`。
- Timer: `dom.tick()` を compositor が毎パス呼び、時計等を更新。
- デスクトップ: グラデーション壁紙、下部タスクバー（起動中ウィンドウ一覧＋時計）。

### Alternatives Considered

- フォントを fs（disk.img）から読む: フォントが無いと画面が出ない依存になる上、
  fs の初期化順序に UI が縛られる。配列リテラル 100KB のコンパイルが 1 秒強で
  済むと実測したので、ソースへ埋め込む。
- 角丸/影をゲスト側のカバレッジマスクで描く: 最初に実装したが、半径 40px の
  影リング 24 本で 1 ウィンドウあたり数千万命令になり最初のフレームが出なかった。
  DMA2D に ROUND_RECT/SHADOW とシザーを足し、ゲストはレジスタ数個の書き込みだけにした。
- `.dom.mln` のプロパティ省略（デフォルト値）対応: コンパイラ変更が要るので
  本チケットでは見送り（Non-Goals）。

### Non-Goals

- `hardware/verilator` への DMA2D/キーボード実装。
- `.dom.mln` DSL の文法変更。
- ウィンドウのリサイズ（ドラッグ移動のみ）。
- 日本語フォント（ASCII 0x20-0x7E のみ）。

## 実装中に見つかった既存バグ（本チケットで修正）

- **エミュレータ: IRQ 進入時に古い条件フラグを push**（`registers.rs`）。
  `status_register` フィールドは ALU が更新しないので、前回 restore の
  Z/C/S ビットが残ったまま `sr | live flags` で push され、`iret` で
  誤ったフラグが復元されていた。cmp と分岐の間で割り込まれたコードが誤分岐し、
  描画が非決定的に化ける（`MYEMU_IRQ_CHECK=1` で検出、回帰テスト追加）。
- **コンパイラ: `.dom.mln` の 3 段以上のネスト**（`lexer.c`）。閉じタグの `>` が
  TEXT モードを余分に push し、`</Window>` 以降が MLX_TEXT として字句解析されて
  「unexpected toplevel construct」になっていた。`MODE_MLX_CLOSE_TAG` を追加。
- **コンパイラ: モジュールあたり 256 関数シグネチャの上限**（`semantic_internal.h`）。
  自前 + import 分で dom.mln が超えた。512 に拡張（SemanticContext は約 2.7 MB）。

## Non-Goals のうち残したもの / 既知の制限

- スクロールビュー、ウィンドウリサイズ、Tab によるフォーカス移動、右クリック
  メニュー（右ボタン・ホイールはデバイス〜ドライバまで実装済み、UI 未使用）。
- 時計は起動からの経過時間（RTC なし）。
- `hardware/verilator` は未対応。

## Progress

- [x] エミュレータ: DMA2D 拡張（BLEND/COPY/COPY_BLEND/MASK_A8/GRADIENT/ROUND_RECT/OUTLINE/SHADOW + シザー）
- [x] エミュレータ: キーボードデバイス + IRQ、右クリック・ホイール
- [x] エミュレータ: PNG スクリーンショット、`--screenshot` CLI、control-stdio 拡張（key.type/press/release、mouse.wheel、右ボタン、拡張子で PNG）
- [x] MyKernel: keyboard.mln、irq_dispatch、mouse.mln 拡張、`tests/io/input_queues.test.mln`
- [x] MyOS graphics: alpha/blit/gradient/round rect/shadow/clip stack（DMA2D シザー同期）
- [x] MyOS font: gen_font.py + font_sans.mln + draw_label/text_width
- [x] MyOS dom: theme、ウィンドウクローム、focus/bring_to_front/move/close、Row/Label/Panel/TextInput/Checkbox/Separator/Timer、キー配送、tick、複数ダメージ矩形
- [x] MyOS compositor: ドラッグ、フォーカス、release クリック、キーボード、タスクバー、時計
- [x] アプリ: counter を新 UI に、notes（TextInput/Checkbox）、ランチャーで複数起動
- [x] テスト: `make qa` 全スイート、dom_hit_dispatch 更新、graphics.test.mln 追加、dom_click_test.py（drag/close/type）、domscript DSL 拡張
- [x] ドキュメント: DOM_SPEC / readme / エミュレータ readme / `make screenshot` `make font`
