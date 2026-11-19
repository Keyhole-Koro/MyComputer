# request_channel.submit の中
入口：encode
出口 [[gateway.full]]：send

帯 body 関数の中／submit・左から順に（os）
  箱 encode [[channel.encode]] encode_request_words ｜説明 24 語に詰める
  箱 words [[channel.words]] words[24] ｜中身 Request, reply_ch, 空き
  箱 send [[kernel.ipc-send]] ipc.send(ch, w) ｜説明 空きがあれば入れる
帯 ring 要求の列／全部のアプリで 1 本（os）
  箱 ring [[os.request-ring]] 要求の列 ｜中身 24 語, 24 語, 24 語
帯 sched スケジューラ／MyKernel（kernel）
  箱 notify [[kernel.notify-armed]] notify_armed(SERVICE) ｜説明 service task を起こす

1. encode → words  読み書き「書く」 渡す Request
   Request を 0〜12 語目に、返事の channel を 13 語目に書く
2. words → send  読み書き 渡す 24 語「i32 words[24]」 札なし
   24 語をまとめて ipc.send に渡す
3. send → ring  列を通す「入れる」 渡す 24 語「24 語の 1 通」 札なし
   列に空きがあれば入れる。満杯なら false を返し、アプリは REQUEST_SPACE を待ってやり直す
   分かれる：空きがある → 入れて true。続けて SERVICE を通知する ／ 満杯 → 入れずに false。通知もしない（呼んだ側がやり直す）
4. send → notify  呼び出し「入ったら」 [[kernel.notify-armed]]
   入ったら SERVICE を通知して、それを待つ service task を起こす
