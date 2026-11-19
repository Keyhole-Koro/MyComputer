# カーネル（MyKernel）

## kernel.os-call  OS_CALL
関数・system/MyKernel/src/kernel/syscall.unsafe.mln の dispatch
型：syscall OS_CALL(i32 service, i32 args)
引数 service：[[schema.os-service]] の 1 つ
引数 args：ユーザメモリの引数のアドレス
返す：service ごとの 1 語

アプリから OS への入口は、この syscall 1 つだけ。カーネルは呼んだプロセスの pid を付けて、MyOS が登録した [[os.router]] に渡す。

## kernel.irq-dispatch  irq_dispatch.dispatch
関数・system/MyKernel/src/kernel/irq_dispatch.unsafe.mln の dispatch
引数 sp：割り込まれた文脈を保存した所

割り込みの原因を読んで、タイマーなら [[kernel.tick]] を呼ぶ。入力などがスレッドを起こした時は、次の tick を待たずに切り替える。

## kernel.tick  scheduler.tick
関数・system/MyKernel/src/kernel/scheduler.unsafe.mln の tick
引数 sp：割り込まれた文脈
返す：次に走らせる文脈の sp

tick 数を時計に追いつかせる。時計の tick は 2^24 で一周するので、前回からの差で数える。止めていたタイマーを毎 tick に戻して、[[kernel.reschedule]] へ進む。

## kernel.reschedule  scheduler.reschedule
関数・system/MyKernel/src/kernel/scheduler.unsafe.mln の reschedule
引数 sp：離れる文脈
返す：次に走らせる文脈の sp

最初に [[kernel.cpu-time]] で区切る。離れるスレッドを保存し、期限の来たスレッドを起こして、次に走らせるものを選ぶ。

## kernel.cpu-time  CPU 時間の数え方
関数・system/MyKernel/src/kernel/scheduler.unsafe.mln の charge_elapsed
中の紙：kernel.cpu-time
型：void charge_elapsed()
型：void charge(i32 spent)
引数 spent：足す時間（時計の 1/256 tick 単位）

切り替えのたびに時計を読み、前回からの時間を、それまで走っていたものに足す。

![[emulator.timer.clock]]

足し先は [[kernel.cpu-counters]]。WFI で待つカーネルスレッドは [[kernel.wfi-wait]]。

![[fig.charge-before-after]]

## kernel.cpu-counters  CPU 時間の置き場
置き場・system/MyKernel/src/kernel/scheduler.unsafe.mln の g_idle_time
フィールド Process.cpu_time（i32）：プロセスのスレッドが走った時間
フィールド g_kernel_time（i32）：OS 自身のスレッドが走った時間
フィールド g_idle_time（i32）：走るものが無かった時間

単位はどれも時計の 1/256 tick（既定の 1 ms tick で約 4 µs）。数は一周するので、差で読む。[[os.proc-stats]] が [[schema.cputimes]] にまとめる。

## kernel.wfi-wait  WFI で待つカーネルスレッド
関数・system/MyKernel/src/kernel/scheduler.unsafe.mln の wait_in_wfi
型：void charge_wait()
型：void wait_in_wfi(i32 slot)

sleep と await_notification は、待ちに入るまでを自分の時間にし、待っている間を idle にする。戻ったら、また自分の時間に戻す。

## kernel.idle-hold  待機中はタイマーを止める
関数・system/MyKernel/src/kernel/scheduler.unsafe.mln の hold_until_due

走らせるスレッドが無い間、idle は次の期限まで割り込みを止めて WFI で待つ。期限は sleep、futex、通知待ちのうち一番早いもの。止めていた間は idle の時間になる（[[kernel.cpu-time]]）。

## kernel.ipc-send  ipc.send
関数・system/MyKernel/src/kernel/ipc.unsafe.mln の send
引数 ch：入れる channel
引数 words：24 語
返す：空きがあって入れたら true

channel の列に空きがあれば 24 語を写す。満杯なら何もせず false。

## kernel.notify-armed  scheduler.notify_armed
関数・system/MyKernel/src/kernel/scheduler.unsafe.mln の notify_armed
引数 mask：知らせる通知（ここでは SERVICE）

その通知を待つと予約したスレッドを起こす。service task は SERVICE を待っている。

## charge.read  now = 時計
関数・system/MyKernel/src/kernel/scheduler.unsafe.mln の charge_elapsed
型：i32 now = mem.read_word(TIMER_ADDR);

[[emulator.timer.clock]] を 1 語読む。tick 数 × 256 ＋ 進みが、今の時刻になる。

## kernel.charge  scheduler.charge
関数・system/MyKernel/src/kernel/scheduler.unsafe.mln の charge
引数 spent：足す時間（時計の単位）

[[kernel.charge-to]] を見て、ユーザスレッドならそのプロセス、カーネルスレッドなら kernel、無ければ idle に足す（[[kernel.cpu-counters]]）。

## charge.set  前回 = now
関数・system/MyKernel/src/kernel/scheduler.unsafe.mln の charge_elapsed
型：g_clock_charged = now;

足し終えた時刻を [[kernel.clock-charged]] に覚える。次の切り替えでは、ここからの時間を足す。

## kernel.clock-charged  g_clock_charged
置き場・system/MyKernel/src/kernel/scheduler.unsafe.mln の g_clock_charged
フィールド g_clock_charged（i32）：前に足し終えた時刻

時計は一周するが、差を取るので困らない。

## kernel.charge-to  g_charge_to
置き場・system/MyKernel/src/kernel/scheduler.unsafe.mln の charge_to
フィールド g_charge_to（Option<i32>）：今の時間の持ち主：スレッドの枠。None なら idle

切り替えの時にスケジューラが charge_to で決める。WFI で待つカーネルスレッドは、待つ間を idle に渡す（[[kernel.wfi-wait]]）。

## fig.charge-before-after  切り替えごとに足す（前と今）
図
図：figures/fig.charge-before-after.svg

前は、tick の瞬間に走っていたものへ 1 tick を丸ごと足していた。A と B は tick の間だけ動いたので 0 だった。

今は切り替えのたびに 1/256 tick（既定で約 4 µs）単位で足すので、A と B の分も数えられる（[[kernel.cpu-time]]）。
