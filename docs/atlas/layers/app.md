# アプリ（/apps の .mbin）

## app.tasks  Tasks.tick
関数・system/MyOS/src/apps/tasks.dom.mln の tick
中の紙：app.tasks
型：@timer(1000)
型：void (borrow Tasks t) tick()
引数 t：タスクマネージャの状態（読み書きする）

1 秒ごとの TIMER イベントで [[lib.next]] から呼ばれる。[[lib.process-stats]] で読み、前回との差の比を % にして、状態とグラフの値を変える。変えた値は [[app.tasks-view]] の属性が読む。

## app.tasks-view  Tasks.view
関数・system/MyOS/src/apps/tasks.dom.mln の view
返す：画面の宣言（Window・Label・Graph など）

画面を .dom.mln に宣言する。属性に書いた値（{t.chosen} など）は束ねられ、イベントのたびに、変わった属性だけを [[lib.send-text]] などが送る。アプリは MyOS を知らない（[[policy.sdk-no-myos]]）。

## mem.user-request  アプリのメモリの Request
置き場・system/MyAppFramework/src/runtime/runtime.unsafe.mln の send

アプリが詰めた [[schema.request]]。OS_CALL で渡るのはこのアドレスだけで、中身は [[gateway.read]] が読みに来る。

## mem.user-strings  アプリのメモリの文字列
置き場

s0・s1 が指す文字。NUL で終わらず、長さは s0_len・s1_len で渡る。[[gateway.copy]] が OS 側に写す。

## app.tasks-share  share
関数・system/MyOS/src/apps/tasks.dom.mln の share
引数 part：その間に使った時間
引数 span：その間の全部の時間
返す：0〜100 の %

1 秒は 256,000 単位。part × 100 が i32 に収まるよう、両方を半分ずつにしてから割る。

## app.tasks-last  t.last
置き場・system/MyOS/src/apps/tasks.dom.mln の tick
フィールド last（ProcStats）：前回の読み

次の tick で差を取るために、今回の読みを覚えておく。

## app.tasks-series  グラフの系列
置き場・system/MyOS/src/apps/tasks.dom.mln の record

CPU 全体、OS、選んだ行の割合。1 秒に 1 つずつ、1 分ぶんを持つ。

## app.tasks-show  t.show
関数・system/MyOS/src/apps/tasks.dom.mln の show

系列と表を、[[app.tasks-view]] の属性が読む値に移す。値が変わった属性だけが送られる（[[lib.send-text]]）。
