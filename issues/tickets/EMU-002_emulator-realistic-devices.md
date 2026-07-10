# エミュレータのデバイス挙動をリアル化（非同期DMA / 実時間タイマー / VBlank同期）

現状の MyEmulator はいくつかのデバイスを「コマンドを書いた瞬間に全部終わる」
同期・即時完了で実装している。動作はするが、実ハードウェアの
「CPU がステータスをポーリングして待つ」「転送中は並行動作」「完了で割り込み」
「フレーム境界に同期して表示する」といった挙動が無く、リアルさに欠ける。

このチケットは 3 つのデバイス挙動を実 HW に近づける。相互に独立しているので
段階的に実装・検証できる。**推奨順は ③ → ① → ②**（低リスク→影響大→タイミング
全体に波及）。

## 対象と現状（調査済み）

| # | 箇所 | 現状の簡易実装 | ファイル |
| --- | --- | --- | --- |
| ① | DMA2D fill / SSD DMA | コマンド書き込みで**その場で全転送完了**。BUSY 状態も完了割込も無い | `machine/memory_bus.rs::service_dma2d`, `machine/ssd.rs::service_ssd_dma` |
| ② | タイマー | **命令数ベース**（N 命令ごとにカウンタ++）。命令の重さで実時間がブレる | `machine/interrupts.rs::service_timer_interrupt` |
| ③ | DISPLAY_SWAP | swap 書き込みで**即コピー**。フレーム境界（VBlank）と無関係 | `machine/memory_bus.rs`（DISPLAY_SWAP_ADDR ハンドラ） |

参考までに現状「妥当」で対象外のもの: マウス（60Hz ポーリング＋変化時 IRQ は概ね
実 HW 的）、RAM（`Vec<u8>` フラットアクセス、エミュとしては普通）。

---

## ③ SWAP を VBlank 同期に（低リスク・独立）

### 現状
`DISPLAY_SWAP_ADDR` への書き込みで即座に `front.copy_from_slice(&vram)`。
表示リフレッシュ（60Hz）とは無関係なタイミングでコピーされる。

### 設計案
- swap 書き込みでは即コピーせず `swap_pending = true` を立てるだけにする。
- `maybe_refresh_display`（`machine/run_loop.rs`、60Hz = VBlank 相当のフレーム境界）
  で `swap_pending` なら back→front をコピーしてから front をスキャンアウトし、
  `swap_pending = false` に戻す。
- カーネルの `graphics.present()` は「次の VBlank で表示してほしい」という要求を
  出すだけになる。実際の表示はフレーム境界に揃う。

### 影響
小。既存のダブルバッファ構造に素直に乗る。tearing が完全に消え、フレームレートが
表示リフレッシュに揃う。

---

## ① DMA の非同期化（BUSY→DONE→完了割込）— 最重要

### 現状
`service_dma2d` / `service_ssd_dma` はコマンド書き込みハンドラ内で全転送を実行し
即完了。SSD は `status` が即 `DONE` になり、CPU に「待つ」概念が無い。

### 設計案
- ステータスに **BUSY** を導入する。SSD は既に `IDLE(0)/DONE(2)/ERROR(0xFF)` が
  あるので `SSD_STATUS_BUSY`（例: 1）を追加。DMA2D にも同様のステータスレジスタを
  設ける（新規 IO レジスタ）。
- コマンド書き込み時は転送を**予約**する: 転送パラメータを保持し、`status = BUSY`、
  `完了予定 = now + 転送量に比例した遅延`（バイト数 or ピクセル数ベース）を記録。
- `run_loop` の毎バッチ（既存の service ポイント）で「完了予定を過ぎた予約があれば
  実際の転送を実行 → `status = DONE` → 完了 IRQ（`pending_irq = true`）」。
- カーネル側は `while (status == BUSY) {}` のポーリング、または完了割込で待つ、
  という実 HW 的な流れになる。

### 影響（要注意）
- `system/MyKernel/src/fs/fs.mln` は現状 SSD が「即 DONE」である前提で書かれている
  可能性が高い。**BUSY ポーリングの追加**が要る。後方互換のため BUSY を経ずに
  すぐ DONE になっても壊れないようにするか、fs 側を更新するか要判断。
- `run_scheduler_test` / `run_fs_smoke_test` など既存 E2E への影響を確認する。
- `service_ssd_dma` は既に「デバイスが転送を決める / バスが RAM 側を担う」形に
  分離済み（`begin_command` が `SsdOp` を返す設計）なので、予約→後で実行への
  改造はしやすい。

---

## ② タイマーを実時間ベースに（タイミング全体に波及・最後）

### 現状
`service_timer_interrupt` が `timer_counter` を命令ごとに++ し、`timer_interval`
命令数に達したら IRQ。命令の重さで実時間がブレる（過去に scheduler test が
タイミング依存で壊れた原因もこれ）。

### 設計案
- `Instant` ベースへ移行。`timer_interval` を「マイクロ秒」等の実時間として解釈し、
  `last_timer.elapsed() >= interval` で IRQ 発火。
- **課題**: headless の高速実行（テスト）で実時間だと待ちが入り遅くなる。
  「実時間モード」と「命令数モード」を切り替え可能にするのが安全
  （CLI フラグ or 既存 `--timer-interval` の意味を明示的に分ける）。

### 影響（リスク中）
- `run_scheduler_test` は `--timer-interval 3000`（命令数）を前提にしている。
  実時間化すると意味が変わり、**全テストのタイミング再調整**が要る。
- scheduler のタイミング脆さ（`tickets` 未記載だが既知）も併せて見直す好機。

---

## 実装順とテスト

1. **③ VBlank 同期**: 低リスク。`run_loop` のリフレッシュに swap を畳み込む。
   ダブルバッファのユニットテストを VBlank 経由に更新。
2. **① DMA 非同期化**: BUSY 導入 → 予約 → run_loop で完了 → 完了 IRQ。
   `fs.mln` の BUSY ポーリング対応。SSD/fs の E2E で回帰確認。ユニットテストで
   BUSY→DONE 遷移を検証。
3. **② タイマー実時間化**: モード切替を入れてから移行。scheduler/serial を含む
   全 E2E のタイミングを再確認。

各ステップ後に kernel（heap/fs/scheduler/serial）+ compiler スイートで回帰する。
