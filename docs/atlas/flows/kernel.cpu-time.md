# charge_elapsed の中
入口：read
はじめ：2

帯 body 関数の中／charge_elapsed（kernel）
  箱 read [[charge.read]] now = 時計 ｜説明 read_word(TIMER_ADDR)
  箱 charge [[kernel.charge]] charge(now − 前回) ｜説明 持ち主に足す
  箱 set [[charge.set]] 前回 = now ｜説明 g_clock_charged
帯 vars カーネルの変数／scheduler（kernel）
  箱 who [[kernel.charge-to]] g_charge_to ｜中身 枠, None
  箱 counters [[kernel.cpu-counters]] CPU 時間の置き場 ｜中身 cpu_time, kernel, idle
  箱 last [[kernel.clock-charged]] g_clock_charged ｜中身 前回の時刻
帯 hw エミュレータ／タイマー（emu）
  箱 clock [[emulator.timer.clock]] タイマーの時計 ｜ビット tick 数 24、進み 8

1. clock → read  読み書き「読む」 渡す clock=[[emulator.timer.clock]]{tick 数, 進み} [[charge.read]]
   時計を 1 語読む。tick 数 × 256 ＋ 進みが今の時刻
2. read → charge  呼び出し 渡す spent「i32 spent = now − g_clock_charged」 札なし [[kernel.charge]]
   now − 前回 を spent として charge に渡す
3. who → charge  読み書き「持ち主」
   今の時間の持ち主を読む（切り替えの時にスケジューラが決めた）
4. charge → counters  読み書き「足す」 渡す spent「i32 spent（時計の単位）」 [[kernel.cpu-counters]]
   ユーザスレッドならそのプロセスの cpu_time、カーネルスレッドなら kernel、無ければ idle に足す
   分かれる：g_charge_to がユーザスレッド → そのプロセスの cpu_time ／ カーネルスレッド → g_kernel_time ／ None（走るものが無い） → g_idle_time
5. charge → set  呼び出し [[charge.set]]
   charge から戻り、今を前回として覚える
6. set → last  読み書き「書く」 [[kernel.clock-charged]]
   g_clock_charged = now
