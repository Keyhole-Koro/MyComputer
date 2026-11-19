# ライブラリ（SDK・MyStdLib）

## lib.send-text  elements.send_text
関数・system/MyAppFramework/src/elements.mln の send_text
引数 id：変えるノード
引数 value：新しい文字

Label_text などの属性のフックが、値が変わった時だけ呼ぶ。[[schema.request]] を UI・SET_TEXT で作り、a0 にノード、s0 に文字を入れて、runtime.send から [[lib.transport]] へ渡す。

## lib.transport  app_transport.request
関数・system/MyAppFramework/src/runtime/transport.unsafe.mln の request
引数 m：送る要求
返す：返事の 1 語。runtime.send が RequestStatus に直す

[[kernel.os-call]] の REQUEST で列に入れ、REPLY で返事を待つ。列が満杯なら REQUEST_SPACE の通知を待ってやり直す。

## lib.next  runtime.next
関数・system/MyAppFramework/src/runtime/runtime.unsafe.mln の next
返す：Idle・Handled・Open・Close のどれか

OS_CALL の POLL で [[schema.event]] を 1 つ受け取り、ノードと種類から登録されたハンドラを探して呼ぶ。

## lib.process-stats  process.stats
関数・toolchain/MyStdLib/hosted/process.unsafe.mln の stats
返す：全部のプロセスと CPU の時間

OS_CALL の PROC_STATS で OS に聞く。何も変えないので、どのプロセスからでも、全部のプロセスについて答える。
