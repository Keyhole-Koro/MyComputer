# UI の要求
タスクマネージャの表示の変更が DOM に届くまで
はじめ：5

文脈 [[ctx.user]] view tick transport send next：タスクマネージャのプロセス（ユーザ空間）
文脈 [[ctx.service]] serve handle dom：service task ｜位置 br
文脈 [[ctx.syscall]] oscall gateway：OS_CALL の中（呼んだプロセスの代わりに走る） ｜短く OS_CALL の中 ｜位置 bl

箱 view [[app.tasks-view]] view() ｜名前空間 Tasks ｜説明 値を属性に束ねる
箱 tick [[app.tasks]] tick() ｜名前空間 Tasks ｜説明 @timer(1000)
箱 transport [[lib.transport]] request(m) ｜名前空間 app_transport ｜説明 送って返事を待つ
箱 send [[lib.send-text]] send_text(id, s) ｜略 send_text ｜名前空間 elements ｜説明 変わった時だけ送る
箱 next [[lib.next]] next() ｜名前空間 runtime ｜説明 イベントを 1 つ処理
箱 serve [[os.serve]] serve() ｜名前空間 request_channel ｜説明 取り出して振り分ける
箱 handle [[os.ui-protocol]] handle(m) ｜名前空間 ui_protocol ｜説明 op を実行する
箱 dom [[os.dom]] DOM ｜中身 Window, Label, Graph
箱 gateway [[os.gateway]] request(pid, req) ｜略 gateway ｜名前空間 request_gateway ｜説明 pid を入れてコピー
箱 ring [[os.request-ring]] 要求の列 ｜中身 Request, Request, Request ｜中身の形 [[schema.request]]
箱 oscall [[kernel.os-call]] OS_CALL ｜名前空間 syscall ｜説明 OS への入口

1. view → send  呼び出し「値が変わった」
   view() の Label が読む値が変わったので、属性のフック Label_text が send_text を呼ぶ
2. send → transport  呼び出し「詰める」 渡す Request{domain, op, owner, a0 … a5, *s0, s0_len}
   Request に UI・SET_TEXT・ノード・文字を詰め、runtime.send から app_transport.request へ
3. transport → oscall  syscall「OS_CALL(REQUEST)」 渡す &Request 札なし
   OS_CALL(REQUEST) で OS に入る
   渡す値：Request のアドレスだけを渡す。中身は [[os.gateway]] がユーザメモリから読む。
4. oscall → gateway  呼び出し「pid を付ける」
   カーネルが pid を付けて os_call_router に渡し、REQUEST は request_gateway.request へ
5. gateway → ring  列を通す「並べる」 渡す Request{owner, *s0, *s1, result_out}
   owner を pid で上書きし、文字列と出力先を OS 側にコピーして、列に並べる
   操作：[[os.request-ring]] 入れる
6. ring → serve  通知「SERVICE で起こす」
   並べたら、SERVICE の通知で service task を起こす
7. serve → handle  呼び出し 渡す Request{domain, op}
   列から取り出し、domain が UI なので ui_protocol.handle へ
   操作：[[os.request-ring]] 出す
   分かれる：domain が UI → [[os.ui-protocol]] の handle ／ domain が APP → shell_protocol.handle ／ ほか → INVALID_DOMAIN を返す
8. handle → dom  読み書き「書き換える」
   op が SET_TEXT なので、a0 のノードの文字を s0 に書き換える
9. serve → transport  戻り「結果と REPLY」 渡す i32「i32（runtime.send が RequestStatus に直す）」 札なし
   結果を返事の channel に入れ、REPLY でアプリを起こす。アプリは OS_CALL(REPLY) で受け取る
10. dom → next  列を通す「TIMER」 渡す Event{owner, id, kind} [[os.events]]
   時間が来ると、DOM のタイマーが TIMER の Event を持ち主の列へ送る。アプリは OS_CALL(POLL) で受け取る
11. next → tick  呼び出し「ハンドラを呼ぶ」
   next() が TIMER のハンドラ tick() を呼ぶ。tick() が値を変えると 1 に戻る
もし 満杯（5 の代わり）. gateway → oscall  戻り「false」 [[gateway.full]]
   列が満杯なら、gateway は REQUEST_SPACE の印を付けて false を返す
もし 満杯（5 の代わり）. oscall → transport  戻り「0 を返す」 [[lib.transport]]
   OS_CALL は 0 を返す。アプリの request は REQUEST_SPACE を待ってから出し直す。serve が列から 1 つ取り出すたびに REQUEST_SPACE を通知する
