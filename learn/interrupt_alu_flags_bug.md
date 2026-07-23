# エミュレータのALUフラグ退避漏れによるUIフリーズのバグ

## 現象
OS起動後、約2秒（タイマー割り込みが約2000回発生したあたり）で、マウスポインターが動かなくなる（UIスレッドがフリーズまたは異常なループに入る）バグが発生した。

## 原因究明
1. OS側でマウス座標の変更を検知する処理は以下のように記述されていた。
   ```c
   if (mx != prev_mx) { dirty = 1; }
   ```
2. これはコンパイラによって比較（`cmp`）と条件ジャンプ（`jz`など）に変換される。
3. MyEmulatorの割り込みディスパッチ（`try_dispatch_irq`）および割り込みからの復帰（`iret`命令）において、プログラムカウンタ(PC)やステータスレジスタ(SR)は退避・復元されていたが、計算結果のゼロフラグやキャリーフラグといった **ALUフラグが退避・復元されていなかった。**
4. そのため、`cmp`命令を実行した直後、条件ジャンプを行う前にハードウェア割り込み（タイマーやマウス）が発生した場合、割り込みハンドラ内で実行された計算によってALUフラグが上書きされ、元のタスクに戻った際に誤った分岐先へ飛んでしまうという状態になっていた。
5. この「フラグ破壊」によりUIのイベントループがおかしな状態に陥り、マウスの描画処理が永久にスキップされるか不正なループに入り込みフリーズしていた。

## 修正内容
エミュレータ側のRustコードを修正し、割り込み発生時にALUフラグをSR（ステータスレジスタ）にパックして退避し、`iret`実行時にアンパックして確実に復元するようにした。

### 1. `constants.rs` にSRの各フラグビット定義を追加
```rust
// Status register interrupt-enable bit.
pub const SR_IE: u32       = 0b0000_0001;
pub const SR_CARRY: u32    = 0b0000_0010;
pub const SR_ZERO: u32     = 0b0000_0100;
pub const SR_SIGN: u32     = 0b0000_1000;
pub const SR_OVERFLOW: u32 = 0b0001_0000;
```

### 2. `interrupts.rs` の `try_dispatch_irq` でパックして退避
```rust
                self.push(self.program_counter)?;
                
                let mut sr = self.status_register;
                if self.carry_flag { sr |= crate::constants::SR_CARRY; }
                if self.zero_flag { sr |= crate::constants::SR_ZERO; }
                if self.sign_flag { sr |= crate::constants::SR_SIGN; }
                if self.overflow_flag { sr |= crate::constants::SR_OVERFLOW; }
                self.push(sr)?;
```

### 3. `cpu_exec.rs` の `IRET` (0x20) 命令でアンパックして復元
```rust
            0x20 => {
                // Reverse of the interrupt entry push order (PC then SR).
                let sr = self.pop()?;
                self.program_counter = self.pop()?;
                // Restoring SR also restores the interrupt-enable state, so the
                // resumed code regains the IE it had when interrupted.
                self.set_interrupt_enable((sr & SR_IE) != 0);
                self.carry_flag = (sr & crate::constants::SR_CARRY) != 0;
                self.zero_flag = (sr & crate::constants::SR_ZERO) != 0;
                self.sign_flag = (sr & crate::constants::SR_SIGN) != 0;
                self.overflow_flag = (sr & crate::constants::SR_OVERFLOW) != 0;
                self.note_handler_return();
            }
```

## 教訓
仮想マシン（VM）やエミュレータを実装する際、割り込みコンテキストの切り替えでは「実行中のCPUステートを完全に保存し、全く同じ状態で復元する」必要がある。PCや汎用レジスタだけでなく、目に見えにくいALUの条件フラグなどの内部ステートが漏れていると、確率的に発生する極めて追跡困難なバグを引き起こす。
