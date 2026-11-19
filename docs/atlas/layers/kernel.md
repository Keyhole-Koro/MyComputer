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

## kernel.channel  Channel
置き場・system/MyKernel/src/kernel/ipc.unsafe.mln の Channel
形：リング（枠 SLOTS、読む head、書く tail、1 通 MSG_WORDS 語）
フィールド used：使っている channel か
フィールド head：次に読む枠
フィールド tail：次に書く枠
操作 send 入れる：tail の枠に書いて 1 進める。進めた先が head なら書かずに false（満杯）｜O(1)
操作 recv 出す：head の枠から読んで 1 進める。head == tail なら false（空）｜O(1)
不変：入っているのは tail − head 通（SLOTS で一周）。tail が head の 1 つ手前で止まるので、最大 SLOTS − 1 通

IPC の channel 1 本。channel ごとに SLOTS 枠のリングを持ち、1 枠は MSG_WORDS 語。中身は全部の channel の分を g_ring にまとめて置く。[[os.request-ring]] もこの 1 本。

## kernel.heap  カーネルのヒープ
置き場・system/MyKernel/src/mm/heap.unsafe.mln の g_free_head
形：リスト（先頭 g_free_head、次 block_next、頭 HDR_SIZE、順 アドレス）
操作 alloc_unlocked 先頭から探す：first-fit。空きを先頭からたどり、入る最初のブロックを取る。余りが HDR_SIZE + ALIGN B 以上なら、後ろを空きとして分ける｜O(空きの数)
操作 free_unlocked 順に差し込む：アドレス順の位置に戻し、すぐ後ろとすぐ前の空きが隣り合っていれば 1 つにまとめる｜O(空きの数)
不変：空きはアドレス順に並び、隣り合う空きは残らない（free_unlocked がまとめる）

カーネルが使うメモリ。どのブロックも、HDR_SIZE B の頭（中身の大きさと、次の空きの場所）の後ろに中身が続く。割り込みを止めてから、リストをたどって書き換える。

## kernel.frames  ページ枠
置き場・system/MyKernel/src/mm/frames.unsafe.mln の g_free
形：リスト（先頭 g_free、次 空いた枠の最初の語、繰り上げ g_next）
操作 alloc 先頭から取る：返された枠があれば先頭から 1 つ取る。無ければ g_next の枠を渡して 1 枠進める｜O(1)
操作 free 先頭に積む：枠の最初の語に今の先頭を書き、その枠を新しい先頭にする｜O(1)
不変：g_next より後ろの枠はまだ一度も渡していない。g_next は POOL_END を越えない

ページ表と、プロセスが使うページの 4 KiB の枠。返された枠は、その枠の最初の語でつないだリストに積むので、リストのためのメモリは要らない。

## kernel.threads  スレッドの表
置き場・system/MyKernel/src/kernel/thread.unsafe.mln の g_threads
形：表（枠 g_threads、鍵 tid、空き None）
操作 [[kernel.find-next]] 一周して探す：今のスレッドの次の枠から 1 つずつ見て、使った枠の数で一周するまでに最初の Runnable を選ぶ（ラウンドロビン）｜O(枠の数)
不変：使っている枠は g_thread_slot_high_water より手前にある

スレッドの制御ブロック（Thread）を枠ごとに 1 つ持つ。状態は [[kernel.thread-state]]。

## kernel.find-next  find_next_runnable
関数・system/MyKernel/src/kernel/scheduler.unsafe.mln の find_next_runnable
引数 start：見始める枠
引数 count：見る枠の数
返す：Runnable の枠。無ければ None

[[kernel.reschedule]] が、離れるスレッドの次の枠から一周させて呼ぶ。だから、どのスレッドも順番が回ってくる。

## kernel.thread-state  ThreadState
列挙・system/MyKernel/src/kernel/thread.unsafe.mln の ThreadState
状態の欄：Thread.state
移る はじめ → Runnable：publish_boot・publish_kernel・publish_user
移る Runnable → Running：make_running
移る Running → Runnable：switch_out
移る Running → Blocked：sleep_until・block_notification・block_notification_until・join_thread・futex_wait
移る Blocked → Runnable：notify・wake_due・wake_joiner・futex_wake
移る Running → Exiting：exit_current_thread・exit_process_threads
移る Runnable → Exiting：exit_process_threads
移る Blocked → Exiting：exit_process_threads
移る Exiting → Zombie：finish_deferred_cleanup
値 Runnable：走れる。[[kernel.find-next]] に選ばれるのを待つ
値 Running：今 CPU で走っている。1 つだけ
値 Blocked：待っている。理由（眠り・通知・join・futex）を 1 つ持つ
値 Exiting：終わる途中。次の切り替えで片付ける
値 Zombie：終わった。終了コードを受け取られるまで枠に残る

[[kernel.threads]] の各スレッドの一生。切り替えは [[kernel.reschedule]] が、離れるものを Runnable に戻し、選んだものを Running にする。
