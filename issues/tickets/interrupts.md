# 割り込み機構（ISA拡張 + タイマー割り込み）

現状の MyEmulator には割り込み・例外・トラップが一切無く、CPUループは `halt`
まで素直に fetch→exec するだけ（`runtime/MyEmulator/src/machine/mod.rs`）。
`status_register` は存在するが、表示と読み書きに使われるのみで制御には使われて
いない。割り込みは「panic を本物のCPU例外にする」「対話シェルなどの入力駆動機能」
の前提インフラになる。

ゴール: **最小の割り込み土台**を作る。タイマー割り込みでカーネルのハンドラが定期的
に呼ばれることを確認する。後でシリアルRX割り込みやソフトウェア例外へ拡張できる形
にする。

## 確定した設計判断（合意済み）

- **状態退避**: 割り込み時に PC/SR をスタックに push、`IRET` で pop。ネスト割り込み
  や通常の関数呼び出しと相性が良い。
- **最初の割込源**: タイマー。命令数カウンタで N命令ごとに発火。
- **ベクタ**: 単一の固定IRQハンドラ（ベクタテーブルはまだ作らない）。
- **ベクタ格納先**: 専用I/Oレジスタ `IRQ_VECTOR_ADDR = IO_BASE + 0x80`
  （`0x2400_0080`）。I/O領域内なのでRAM/ヒープと完全に分離され衝突しない。既存の
  バスI/O処理が任意のI/Oアドレスを `self.io` に読み書きするので、そこへハンドラ
  アドレスを `store` し、割り込み時に `bus_read` で取得するだけで動く（特別扱いの
  追加コード不要）。

## 調査で判明している事実

- opcode は6bit（`>>26 & 0x3F`）。使用中: 0x01–0x1D, 0x3F。**空き: 0x1E, 0x1F,
  0x20–0x3E**（`runtime/MyEmulator/src/instruction.rs`）。
- 命令フォーマット: `[opcode:6][reg1:5][reg2:5][imm:16]`。
- 特殊レジスタのindex: pc=0x08, sp=0x09, bp=0x0A, **sr=0x0B**, lr=0x0C
  （`machine/mod.rs`）。push/pop は `self.push()/self.pop()`。
- アセンブラの命令表は1箇所に集約（`toolchain/MyAssembler/src/instructions.c`）。
  オペランド無し命令は `halt` と同じ経路（`parser.c` の `instrNoOperand`）で処理
  される。Rust側のmnemonic表は `instruction.rs`。
- カーネルから新命令を呼ぶには masm ラッパーを使う（`system/MyKernel/src/libs/halt.masm`
  と同じ `export 名前: <命令>; mov pc,lr` パターン）。

## 実装の概要

### MyEmulator（Rust）
- `constants.rs`: `IRQ_VECTOR_ADDR = IO_BASE + 0x80`、`SR_IE = 0x1`。
- `machine/mod.rs`: `interrupt_enable: bool`、`timer_counter: u64`、
  `timer_interval: Option<u64>`、`pending_irq: bool` を追加。
- `machine/cpu_exec.rs`: 新命令
  - `EI`（0x1E）: `interrupt_enable = true`（SRのIEビットも立てる）
  - `DI`（0x1F）: `interrupt_enable = false`
  - `IRET`（0x20）: `sr = pop(); pc = pop()`（退避時の push と逆順）
- フェッチループ（`mod.rs`）: 各 fetch の前（break チェックの後）にタイマー
  カウンタを進め、interval に達したら `pending_irq` をセット。
  `interrupt_enable && pending_irq` なら PC→SR の順に push し、
  `interrupt_enable` をクリア（多重割り込み防止）、`pc = bus_read(IRQ_VECTOR_ADDR)`、
  `pending_irq` をクリア。
- `cli.rs`: `--timer-interval N` を追加（`parse_u64_value` を流用）。`app.rs` で
  Machine に渡す。
- `instruction.rs`: トレース表示用に EI/DI/IRET を mnemonic表へ追加。

### MyAssembler（C）
- `instructions.c` に `{"ei",0x1E}, {"di",0x1F}, {"iret",0x20}` を追加。オペランド
  無しなので既存の `halt` 解析経路でそのまま処理される。

### MyKernel
- `src/libs/interrupt.masm`: `irq_enable`/`irq_disable` ラッパー（ei/di）。
- `src/libs/irq_trampoline.masm`: レジスタ退避 → MyLangの `irq_handler()` を call
  → レジスタ復帰 → `iret`。（MyLang関数は `mov pc,lr` で返るため、そのままでは
  ハンドラにできない。）
- `src/libs/irq.mln`（`package irq;`）: `enable()`、`set_handler()`（トランポリンの
  アドレスを `IRQ_VECTOR_ADDR` に store）等を export。
- `kernel_main.mln`: `kernel_init` でベクタ登録 + `irq.enable()`。最小ハンドラは
  カウンタを増やして `debug.printf` するだけ。

### ビルド配線
- `qa/run_kernel.py`: エミュレータ起動に `--timer-interval` を渡せるようにする
  （`--trace` 等と同様）。デフォルトは無効。

## 実装時に詰める点

- トランポリンでのレジスタ退避範囲（r0–r7 全部か、ハンドラが使う分だけか）。最小版は
  全部 push/pop で安全側。
- ベクタ未登録（`0x2400_0080` が 0）のままタイマー割り込みが来た場合のガード
  （pc=0 へ飛ばないよう、ベクタが0なら割り込みを起こさない/無視する）。

## 検証

1. **エミュレータ単体**: EI/DI/IRET を含む小さな .masm を手書きし、`--timer-interval`
   付きで実行。ベクタに置いたハンドラが定期的に呼ばれ、`iret` で元の流れに復帰する
   ことを `--trace` で確認。
2. **カーネル**: `python3 qa/run_kernel.py --timer-interval <N>` で、ハンドラが
   カウンタを複数回出力し、起動が `kernel: init complete` まで到達する。
3. **回帰**: タイマー無効時に既存のカーネル出力が不変であること。コンパイラ/heap/
   linker のテストが緑のまま。
4. **多重割り込み防止**: ハンドラ実行中は EI されるまで次の割り込みが入らないこと
   （`interrupt_enable` がハンドラ中クリアされている）。

## 変更ファイル

- 新規: `system/MyKernel/src/libs/interrupt.masm`、`irq_trampoline.masm`、
  `src/libs/irq.mln`。
- 変更: `runtime/MyEmulator/src/{constants.rs,machine/mod.rs,machine/cpu_exec.rs,cli.rs,app.rs,instruction.rs}`、
  `toolchain/MyAssembler/src/instructions.c`、
  `system/MyKernel/src/kernel_main.mln`、`qa/run_kernel.py`。
- 不変: MyLangCompiler（新命令は masm 経由なのでコンパイラ変更不要）、MyLinker。
