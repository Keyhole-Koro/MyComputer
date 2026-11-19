# CPU 時間
CPU 時間が数えられ、タスクマネージャに届くまで
はじめ：5

文脈 [[ctx.user]] tasks stats：タスクマネージャのプロセス
文脈 [[ctx.syscall]] fill：OS_CALL の中 ｜位置 r
文脈 [[ctx.irq]] dispatch ktick resched：割り込みの中

箱 tasks [[app.tasks]] tick() ｜名前空間 Tasks ｜説明 1 秒ごとに読む
箱 stats [[lib.process-stats]] stats() ｜名前空間 process ｜説明 MyStdLib
箱 fill [[os.proc-stats]] fill(out) ｜名前空間 proc_stats ｜説明 集めて書き込む
箱 dispatch [[kernel.irq-dispatch]] dispatch(sp) ｜名前空間 irq_dispatch ｜説明 原因を読む
箱 ktick [[kernel.tick]] tick(sp) ｜名前空間 scheduler ｜説明 追いつく
箱 resched [[kernel.reschedule]] reschedule(sp) ｜名前空間 scheduler ｜説明 次を選ぶ
箱 charge [[kernel.cpu-time]] charge_elapsed() ｜略 charge_elapsed ｜名前空間 scheduler ｜説明 前回からを足す
箱 counters [[kernel.cpu-counters]] CPU 時間の置き場 ｜中身 cpu_time, kernel, idle
箱 timer [[emulator.timer.clock]] タイマーの時計 ｜ビット tick 数 24、進み 8

1. timer → dispatch  通知「tick の割り込み」
   タイマーが tick の割り込みを上げる
2. dispatch → ktick  呼び出し「タイマーなら」
   原因がタイマーなので scheduler.tick(sp) を呼ぶ
3. ktick → resched  呼び出し「切り替えへ」
   tick 数を時計に追いつかせて、reschedule(sp) へ
4. resched → charge  呼び出し「区切る」
   切り替えの最初に charge_elapsed() で区切る
5. timer → charge  読み書き「時計を読む」 渡す clock=[[emulator.timer.clock]]{tick 数, 進み} [[kernel.cpu-time]]
   時計を読み、tick 数 × 256 ＋ 進みを今の時刻にする
6. charge → counters  読み書き「足す」 渡す spent「i32 spent（前回からの時間、1/256 tick 単位）」 [[kernel.cpu-counters]]
   前回からの時間を、それまで走っていたものに足す
7. tasks → stats  呼び出し「毎秒」
   タスクマネージャが 1 秒ごとに process.stats() を呼ぶ
8. stats → fill  syscall「OS_CALL(PROC_STATS)」 渡す &ProcStatsArgs「ProcStatsArgs { ProcStats *result_out; } のアドレス」 札なし
   OS_CALL(PROC_STATS) で OS に入り、router を通って proc_stats.fill へ
9. fill → charge  呼び出し「先に足す」
   fill はまず charge_elapsed() で今までの分を足す
10. counters → fill  読み書き「読む」 渡す CpuTimes
   プロセス・OS のスレッド・idle の時間を読み、CpuTimes と procs にまとめる
11. fill → stats  戻り「copy_out」 渡す ProcStats{cpu, procs[16]}
   できた ProcStats をユーザメモリへ書き戻す
12. stats → tasks  戻り 渡す ProcStats{cpu, procs[16]}
   ProcStats を受け取り、前回との差から % を出す
