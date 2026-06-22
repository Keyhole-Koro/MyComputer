# シリアルRX入力（割り込み駆動）

タイマー割り込みの土台（`docs/implemented/interrupts.md`）の上に、**入力**を追加した。
これまでエミュレータは `SERIAL_TX_ADDR`（出力）しか持たず、対話ができなかった。本機能
で「キーを打つ → RX割り込み → カーネルのハンドラが読み取り → エコー」の経路が通り、
対話シェル（次段）の前提が揃う。

ゴール: ホストの stdin を仮想 UART の受信器に繋ぎ、バイト到着で**既存の単一IRQ
ベクタ**にディスパッチする。ハンドラは LSR の Data-Ready ビットで「タイマーか入力か」
を判別する（ベクタテーブルはまだ作らない）。

## 確定した設計判断

- **単一ベクタに相乗り**: RX も既存の `pending_irq`/IRQ ベクタを使う。タイマーとは
  独立に、入力到着で `pending_irq` を立てる（タイマー無効でも入力で発火する）。
- **要因判別は LSR**: 受信バイトが待っていると LSR の **Data-Ready(DR=0x01)** が立つ。
  ハンドラは `while (rx_ready()) { read_rx(); ... }` でドレインする。
- **RX読みは消費を伴う**: `SERIAL_RX_ADDR` の読みは FIFO 先頭を1バイト取り出す副作用が
  ある。命令フェッチやスタック読みに使う `bus_read(&self)` とは別に、LOAD命令専用の
  `bus_load(&mut self)` を通す（フェッチ等は RX を消費しない）。
- **入力供給はバックグラウンドスレッド**: stdin をブロッキングで読む専用スレッド →
  mpsc チャネル → CPUループが各サイクルで `try_recv` してFIFOへ。CPUループはブロック
  しない。EOF でスレッドは終了する。

## I/O レジスタ（`constants.rs`／`irq.mln` で一致）

| アドレス | 名前 | 向き | 意味 |
|---|---|---|---|
| `IO_BASE+0x00` | SERIAL_TX | 書き | 1バイト送信（既存） |
| `IO_BASE+0x04` | SERIAL_RX | 読み | 受信FIFOから1バイト取り出し（消費） |
| `IO_BASE+0x05` | SERIAL_LSR | 読み | bit0 DR=データあり / bit5 THRE=送信可 |
| `IO_BASE+0x80` | IRQ_VECTOR | — | ハンドラアドレス（既存・タイマーと共用） |

## 実装の概要

### MyEmulator（Rust）
- `constants.rs`: `SERIAL_RX_ADDR = IO_BASE+0x04`、`SERIAL_LSR_DR = 0x01`。
- `machine/mod.rs`: `rx_queue: VecDeque<u8>` と `rx_recv: Option<Receiver<u8>>` を追加。
- `machine/interrupts.rs`:
  - `start_serial_input()`: stdin 読みスレッドを起動（実行開始時に1回、冪等）。
  - `poll_serial_input()` → `ingest_serial_bytes()`: チャネルをドレインして FIFO へ入れ、
    `pending_irq` を立てる。`service_timer_interrupt` の先頭で毎サイクル呼ぶ。
- `machine/memory_bus.rs`:
  - `serial_lsr()`: THRE | (FIFO非空なら DR)。LSR 読みはこれを返す（無副作用）。
  - `bus_load()/bus_load_byte()`: `SERIAL_RX_ADDR` なら FIFO を pop、それ以外は
    `bus_read` に委譲。
- `machine/cpu_exec.rs`: LOAD 命令（`0x03` word / `0x1C` byte / `0x16` io-imm）を
  `bus_load*` に切替（RX を消費するのはこの経路だけ）。
- `machine/run_loop.rs`: 実行開始時に `start_serial_input()`。

### MyKernel（MyLang）
- `src/libs/irq.mln`: `read_word(addr)`、`rx_ready()`（LSR&DR）、`read_rx()`（RX&0xFF）、
  `putc(c)`（TXへ書き）を export。アドレスはエミュと一致。
- `src/kernel_main.mln`: `irq_handler` で `while (rx_ready()) { c = read_rx(); ... }` と
  受信をドレインしてエコー。`'q'`(0x71) を受けたら改行＋`halt_cpu()` で停止（デモ/テスト
  の決定的終了）。

## 検証

- **エミュ単体（Rust, `make test`）**: `machine::interrupts::tests`
  - LSR が無入力で THRE のみ／入力で DR が立つ。
  - RX が FIFO 順に消費され、空読みは 0。
  - 入力で `pending_irq` が立つ。
  - IE 有効＋ベクタ登録＋入力で `service_timer_interrupt` が PC をハンドラへ向け、
    IE をマスクする。
  - `bus_read`（フェッチ経路）は RX を消費しない。
- **エンドツーエンド（`system/MyKernel/tests/run_serial_rx_test.py`）**: カーネルと
  エミュをビルドし、`"PINGq"` を流し込み、`PING` がエコーされ `'q'` でクリーン停止
  （exit 0）、かつ `kernel: heap ready` まで起動することを確認。`qa/serial-rx-test.py`
  はこれへ委譲する薄いラッパー（`qa/as-test.py` 等と同型）。CI（mytester）で実行。

## 既知の留保・次段

- ハンドラ内でエコー＝**割り込みコンテキストで処理**している。本来はリングバッファに
  溜め、**シェルタスクが消費**すべき（次の「シェル」で対応）。
- 端末が canonical モードだと入力は行単位（Enter で流れる）。1文字ずつ欲しい場合は
  raw モードが要る。
- パイプ入力だと起動直後に割り込みが発火し、起動バナーより先に処理されることがある
  （実打鍵は起動後なので問題なし・体裁のみ）。

## 変更ファイル

- 変更: `runtime/MyEmulator/src/{constants.rs,machine/mod.rs,machine/interrupts.rs,
  machine/memory_bus.rs,machine/cpu_exec.rs,machine/run_loop.rs}`、
  `system/MyKernel/src/libs/irq.mln`、`system/MyKernel/src/kernel_main.mln`。
- 新規: `system/MyKernel/tests/run_serial_rx_test.py`（本体）、`qa/serial-rx-test.py`
  （委譲ラッパー）、`runtime/MyEmulator/src/machine/interrupts.rs` のテストモジュール。
- CI: `.github/workflows/mytester.yml` に `qa/serial-rx-test.py` を追加。
