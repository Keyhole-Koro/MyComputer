# Tasks.tick の中
入口：stats

帯 body 関数の中／tick・左から順に（app）
  箱 stats [[lib.process-stats]] process.stats() ｜説明 今の読み
  箱 share [[app.tasks-share]] share(part, span) ｜説明 差の比を % に
  箱 show [[app.tasks-show]] t.show() ｜説明 属性に移す
帯 state Tasks の状態／t の中（app）
  箱 last [[app.tasks-last]] t.last ｜中身 cpu, procs ｜中身の形 [[schema.procstats]]
  箱 series [[app.tasks-series]] グラフの系列 ｜中身 CPU, OS, 選んだ行

1. stats → share  呼び出し 渡す ProcStats{cpu, procs[16]} [[app.tasks-share]]
   今の読みと t.last の差から、CPU 全体・OS・各プロセスの割合を出す
2. last → share  読み書き「前回」 渡す ProcStats 札なし
   前回の読み t.last を使う
3. share → series  読み書き「足す」 渡す %「i32（0〜100）」 [[app.tasks-series]]
   t.record で、割合をグラフの系列に 1 つ足す
4. stats → last  読み書き 渡す ProcStats [[app.tasks-last]]
   t.last = now（次の差のために覚える）
5. share → show  呼び出し「移す」 [[app.tasks-show]]
   t.show() で、系列と表を view() の属性が読む値に移す。変わった値だけが送られる
