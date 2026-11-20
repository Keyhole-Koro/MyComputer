# OS サービス（MyOS）

## os.router  os_call_router.handle
関数・system/MyOS/src/syscall/router.unsafe.mln の handle
型：Result<i32, OsServiceError> handle(
型：    Pid pid, i32 service, UserAddress args)
引数 pid：呼んだプロセス（カーネルが付ける）
引数 service：OsService の 1 つ
引数 args：ユーザメモリの引数

MyOS がカーネルに登録した、OS_CALL の受け口。service で振り分ける。REQUEST・REPLY・POLL は [[os.gateway]]、PROC_* はプロセスの処理（[[os.proc-stats]] など）、FS_* はファイルの処理へ。

## os.gateway  request_gateway.request
関数・system/MyOS/src/ipc/gateway.unsafe.mln の request
中の紙：os.gateway
引数 pid：呼んだプロセス
引数 user_request：ユーザメモリの要求
返す：列に入ったら true。満杯なら false（アプリがやり直す）

owner を呼んだプロセスの pid で上書きし、文字列と出力先をプロセスごとの buffer にコピーしてから [[os.request-ring]] に並べる。service task が見るのは、OS 側にコピーした値だけ。例外は result_size が 0 以下の時の result_out で、アプリの番地のまま渡る（[[gateway.stage]]）。返事は reply が、イベントは poll が、同じようにコピーして返す。

## os.request-ring  要求の列
置き場・system/MyOS/src/ipc/channel.unsafe.mln の g_requests
形：[[kernel.channel]]

全部のアプリの要求が並ぶ 1 本の列（IPC の channel）。1 通は 24 語。[[os.submit]] が入れ、[[os.serve]] が取り出す。

## os.serve  request_channel.serve
関数・system/MyOS/src/ipc/channel.unsafe.mln の serve
返す：1 つ以上答えたら true

[[ctx.service]] の中で、列から要求を取り出し、domain で [[os.ui-protocol]] か shell に振り分ける。結果を返事の channel に入れ、owner のプロセスに REPLY を通知する。

## os.ui-protocol  ui_protocol.handle
関数・system/MyOS/src/ui/protocol.unsafe.mln の handle
引数 m：OS 側の要求

op（[[schema.uiop]]）を見て [[os.dom]] を変える。作ったノードは owner のプロセスのものになる。

## os.dom  DOM
置き場・system/MyOS/src/ui/dom/dom_model.model.mln
形：木（子 children、親 parent、節 Node、兄弟の順 描く順）
操作 [[os.dom-render]] 深さ優先：親を描いてから、子を兄弟の順に描く。後の兄弟ほど上に重なる｜O(節の数)
操作 [[os.dom-hit]] 最後に当たったもの：子を兄弟の順に全部たどり、点を含むもののうち最後に当たったもの（いちばん上に描いたもの）を残す｜O(節の数)

ブラウザと同じ形の DOM が、OS 側に 1 つだけある。触るのは [[ctx.service]] だけ。タイマーのノードは、時間が来ると [[os.events]] で TIMER を送る。

## os.events  app_events.push
関数・system/MyOS/src/ipc/events.unsafe.mln の push
型：void push(Pid owner, i32 id, i32 kind,
型：          i32 arg, i32 token, str text)
引数 owner：受け取るプロセス
引数 kind：EventKind の 1 つ

[[schema.event]] を owner のプロセスの列に入れる。まだ取り出されていない TIMER があれば、重ねて入れない。アプリは OS_CALL の POLL で受け取る。

## os.proc-stats  proc_stats.fill
関数・system/MyOS/src/proc/stats.unsafe.mln の fill
引数 out：書き込む先

集める前に [[kernel.cpu-time]] で今までの分を足すので、合計と内訳が合う。PROC_STATS の処理が、できた ProcStats をユーザメモリへ書き戻す。

## os.submit  request_channel.submit
関数・system/MyOS/src/ipc/channel.unsafe.mln の submit
中の紙：os.submit
引数 request：OS 側の値に差し替えた要求
引数 reply_channel：返事を入れる、プロセスごとの channel
返す：列に入ったら true。満杯なら false

[[schema.request]] を返事の channel と合わせて 24 語に詰め、[[os.request-ring]] に入れる。入ったら SERVICE を通知して [[ctx.service]] を起こす。

## gateway.read  read_user_request
関数・system/MyOS/src/ipc/gateway.unsafe.mln の read_user_request
引数 user_request：アプリのメモリの Request
引数 request：書き込む、OS 側の Request

ユーザメモリから 15 語を 1 語ずつ読み、[[schema.request]] に戻す。

## gateway.owner  owner = pid
関数・system/MyOS/src/ipc/gateway.unsafe.mln の request
型：request.owner = (i32)pid;

アプリが owner に何を書いていても、OS_CALL を呼んだプロセスの pid で上書きする。ほかのプロセスは名乗れない。

## gateway.copy  copy_request_strings
関数・system/MyOS/src/ipc/gateway.unsafe.mln の copy_request_strings
引数 slot_index：呼んだプロセスの枠
引数 request：s0・s1 がまだアプリのアドレスの Request

s0（1,024 B まで）と s1（128 B まで）を [[gateway.slots]] に写し、Request の s0・s1 をその写しに差し替える。

## gateway.stage  stage_request_outputs
関数・system/MyOS/src/ipc/gateway.unsafe.mln の stage_request_outputs
引数 slot_index：呼んだプロセスの枠
引数 request：書き込み先を差し替える Request

結果の書き込み先を [[gateway.slots]] の受け皿に差し替え、アプリ側の元の場所を覚えておく。返事の時に、そこへ書き戻す。差し替えるのは TEXT_COPY の出力先と、0 でなく result_size が 1 以上の result_out（書き戻すのは 64 B まで）。result_size が 0 以下だと result_out はアプリの番地のまま渡り、結果を返す op では service task がそこへ書く。

## gateway.slots  gateway_slots[i]
置き場・system/MyOS/src/ipc/gateway.unsafe.mln の GatewaySlot
形：表（枠 gateway_slots、鍵 slot_index）
フィールド reply_ch：返事を入れる channel
フィールド event_ch：イベントを入れる channel
フィールド events_bound：イベントの channel を結んだか
フィールド s0：1 つ目の文字列の写し（1,024 B）
フィールド s1：2 つ目の文字列の写し（128 B）
フィールド out：TEXT_COPY の出力の受け皿（4,096 B）
フィールド out_user：出力を書き戻す、アプリ側の場所
フィールド out_cap：出力の上限
フィールド result：result_out の代わりの受け皿（64 B）
フィールド result_user：結果を書き戻す、アプリ側の場所
フィールド result_size：書き戻す長さ（64 B まで）

プロセスごとに 1 つ（16 個まで）ある、OS 側の受け皿。service task は、アプリのメモリではなくここを見る。

## gateway.full  満杯なら印を付けて false
関数・system/MyOS/src/ipc/gateway.unsafe.mln の request

[[os.submit]] が false を返したら（要求の列が満杯）、scheduler.arm_notification(REQUEST_SPACE) で印を付けて false を返す。OS_CALL は 0 を返し、アプリの [[lib.transport]] は REQUEST_SPACE を待って出し直す。[[os.serve]] は列から 1 つ取り出すたびに REQUEST_SPACE を通知する。

## channel.encode  encode_request_words
関数・system/MyOS/src/ipc/channel.unsafe.mln の encode_request_words

[[schema.request]] を 0〜14 語目に、返事の channel を 15 語目に書く。

## channel.words  words[24]
置き場・system/MyOS/src/ipc/channel.unsafe.mln の submit
フィールド words[0..14]（i32）：Request の 15 語
フィールド words[15]（i32）：返事を入れる channel
フィールド words[16..23]（i32）：使わない

IPC の 1 通は 24 語。submit の中だけで使う、その場の配列。

## os.dom-render  dom_render.render
関数・system/MyOS/src/ui/dom/dom_render.mln の render
引数 n：描く節

見えない節はその下ごと飛ばす。描き直す範囲（damage）に入る節だけ描き、子は範囲の外でも訪ねる。子を切り抜く節は、外ならそこで止める。

## os.dom-hit  dom_hit_test.hit_row
関数・system/MyOS/src/ui/dom/dom_hit_test.mln の hit_row
引数 n：調べる節
引数 px：点の x
引数 py：点の y
返す：いちばん上の、当たる節。無ければ None

入力をどの節に届けるかを決める。見えない節と、子を切り抜く節の外は飛ばす。
