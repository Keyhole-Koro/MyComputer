# MYOS-015: ユーザー空間アプリ・GUI ターミナル・ファイラ/エディタ・WM 仕上げ

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| In Progress | main | claude-code:opus-4.8 | 2026-09-12 |

## Summary

既にあったユーザー空間基盤（MMU・特権モード・PCB・`.mbin` ローダ・syscall）を
実際に使えるようにし、デスクトップから独立プロセスとしてアプリを起動できるように
した。GUI ターミナル（プロセスの stdout を受けるウィンドウ）、ファイルマネージャ、
テキストエディタを追加し、ウィンドウマネージャに最小化/最大化/リサイズ・
右クリックメニュー・タスクバーからのアプリランチャ・Tab フォーカス移動を足した。

## Background

MYOS-014 で描画・ウィンドウ・入力の土台はできたが、
- ユーザー空間で動くアプリが 1 つも無く、シェルもカーネル内タスクだった。
- `SYS_SPAWN` は番号だけ定義され dispatch されていなかった。
- プロセスの `SYS_WRITE` はシリアルにしか出せず、GUI に出す口が無かった。
- MFS は `ls` 以外に使い道がなく、ホスト側でディスクイメージを作る手段も無かった。

## Design

### プロセス ↔ デスクトップの接続（`system/MyOS/src/proc/console.mln`）

- カーネルの syscall 層はデスクトップを知らない。`syscall.set_console(write, read)` と
  `syscall.set_spawn_handler(h)` で MyOS がハンドラを登録する（未登録時は従来どおり
  シリアルにフォールバック、SPAWN は `UnknownSyscall`）。
- 各プロセスをコンソールスロットに束ね、stdout を TextArea へ、stdin を 1 行ずつ
  積むリングバッファへ流す。`on_write` は syscall 実行中（プロセス自身のページ
  テーブルが有効）に `dom.append_bytes` でユーザバッファを直接読んで DOM に書く。
- `SYS_SPAWN`: ユーザ空間のパス文字列 → `fs.open`/`read` → `loader.spawn_from_buffer`。

### ユーザーランド（`system/MyOS/user/`）

- `lib/sys.masm`（syscall スタブ）、`lib/start.masm`（`app_main` を呼び exit）、
  `lib/ulib.mln`（stdio・文字列・`readline`）。
- アプリ: `hello`（一発出力）、`echo`（stdin エコー）、`count`（yield しながら計数）。
- `qa/runners/build_user_apps.py` が各アプリを MBIN v2 実行形式にビルド。
  **MyLang は 21bit 即値でシンボルアドレスを載せるため、ユーザプログラムは 2MB 未満
  （`0x20000`）にリンクする。** ローダはリンク先アドレスにマップする（下記）。

### ディスクイメージ（`tools/mkfs.py`）

- ホスト側で MFS（`system/MyOS/src/fs/fs.mln` のオンディスク形式そのまま）を生成。
  ユーザアプリと `readme.txt`/`todo.txt` を収め、カーネルを block 16000 に埋める。
- `qa/runners/run_system.py` がビルド時に呼ぶ（旧: カーネルだけを空ディスクに埋める）。
- `fs.mln` に `dir_next`/`entry_size`（ディレクトリ列挙）を追加。

### GUI アプリ

- `apps/terminal.dom.mln`: 出力 TextArea ＋ コマンド行。`help/ls/cat/clear/run`、
  プログラム名で起動。100ms タイマでプロセスを回収し終了コードを表示。
- `apps/files.dom.mln`: List でディスクを一覧、Open/New/Delete（確認ダイアログ）/Refresh。
- `apps/editor.dom.mln`: TextArea で 1 ファイルを編集、Save で書き戻し（MFS は追記のみ
  なので remove→create→write）。

### DOM / WM 追加（`system/MyOS/src/ui/dom.mln`, `compositor.mln`, `theme.mln`）

- 新ノード: `TextArea`（複数行・スクロール・読取専用コンソール可）、`List`、`Menu`（ポップアップ）。
- WM: `minimize_window`/`maximize_window`/`resize_window`、タイトルバー 3 ボタン
  （閉じる・最小化・最大化）、右下リサイズグリップ、右クリックの
  ウィンドウ/デスクトップメニュー、タスクバーのアプリランチャ、Tab フォーカス移動、
  ボタン/チェックボックスの Enter/Space とフォーカスリング、ホイールスクロール。

### エミュレータ・カーネル修正

- `enable_kernel_paging()`（`boot/main.mln`）でカーネルも恒常的にページングで走る。
  VRAM identity マッピングを 12MB（実解像度分）へ拡大（`mmu.mln`）。
- ローダは MBIN v2 をリンク先アドレスにマップ（`entry_point & ~0xFFF`）。
  syscall がコンソールフックからデスクトップへ降りるのでカーネルスタックを 4KB に。

## 実装中に見つけて直したバグ

- **エミュ: `run_frame_budget` が命令ごとに `Instant::now()`** を呼び、control-stdio
  実行が ~10倍遅く、ページング有効化中に os.ready がタイムアウトしていた。
  バッチ境界でのみ時刻チェックするよう修正。control-stdio は常に headless に。
- **エミュ: スタック境界チェックが物理 RAM 前提** で、ユーザスタック（仮想
  `0x7FFFF000`）への push が偽陽性で弾かれた。ページング時は MMU に委ねる。
- **コンパイラ: グローバル `char* = "リテラル"` が null ポインタになる**（リロケーション
  未対応）。メニュー文字列は関数返り値に変更して回避。
- **DOM: TextArea 描画が共有バッファを一時 NUL 終端**していて、プロセスの
  stdout 書き込みと競合して文字化け。行をローカルバッファへコピーして描画。
- **競合: `append_text` がコンポジタタスクとプロセス syscall の両方から呼ばれる**。
  コンポジタ側（ターミナルのエコー）を irq off で囲み相互排他に（プロセス側は
  syscall 中で既に割込み禁止）。

## Non-Goals / 既知の制限

- スクロールバーの描画（ホイール/キーで動くが可視バーは無い）、コピー&ペースト、
  複数選択、パイプ/リダイレクト、ユーザ空間 heap を使うアプリ。
- MFS 追記のみ（エディタ保存は remove→create→write）。

## Progress

- [x] syscall: console/spawn フック、`SYS_SPAWN` dispatch
- [x] proc/console.mln（stdout→TextArea, stdin, spawn, 回収）
- [x] user/ ランタイム＋ hello/echo/count、build_user_apps.py
- [x] tools/mkfs.py、run_system.py 統合、fs.dir_next/entry_size
- [x] terminal / files / editor アプリ
- [x] DOM: TextArea/List/Menu、WM（min/max/resize/menu/tab/wheel/focus ring）
- [x] エミュ/カーネル修正（budget, stack bounds, paging, loader base）
- [x] `make qa` 全 21 スイート green、graphics/input-queue 等は不変
- [ ] apps_e2e_test.py: 実装済み・ロジック検証済みだが、本セッションのサンドボックス
      が python から spawn した myemu を kill するため green 確認は未（既存の
      dom-tester-test も同条件で走らない＝環境要因）。スクリーンショットで動作確認済み。
- [x] ドキュメント（readme / エミュレータ readme / このチケット）更新
