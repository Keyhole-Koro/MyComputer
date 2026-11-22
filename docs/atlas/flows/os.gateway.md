# request_gateway.request の中
入口：read
出口 [[os.request-ring]]：submit
出口 [[kernel.os-call]]：full
はじめ：2

帯 user アプリのメモリ／ユーザ空間（app）
  箱 ureq [[mem.user-request]] Request ｜中身 op, owner, s0, out ｜中身の形 [[schema.request]]
  箱 ustr [[mem.user-strings]] 文字列 ｜中身 s0, s1
帯 body 関数の中／request・左から順に（os）
  箱 read [[gateway.read]] read_user_request ｜説明 15 語を読む
  箱 owner [[gateway.owner]] owner = pid ｜説明 名乗りを上書き
  箱 copy [[gateway.copy]] copy_request_strings ｜説明 s0・s1 を写す
  箱 stage [[gateway.stage]] stage_request_outputs ｜説明 出力先を差し替え
  箱 full [[gateway.full]] 満杯なら印を付ける ｜説明 REQUEST_SPACE・false を返す
  箱 busy [[gateway.busy]] 返事待ちなら断る ｜説明 REQUEST_SPACE・false を返す
帯 kbuf OS 側／受け皿と列（os）
  箱 slot [[gateway.slots]] gateway_slots[i] ｜中身 s0, s1, out, result
  箱 submit [[os.submit]] submit(req, ch) ｜名前空間 request_channel ｜説明 列に並べる

1. ureq → read  読み書き「15 語」 渡す Request [[gateway.read]]
   アプリのメモリから、Request の 15 語を 1 語ずつ読む
2. read → owner  呼び出し 渡す Request{owner} [[gateway.owner]]
   owner を、呼んだプロセスの pid で上書きする
3. owner → copy  呼び出し [[gateway.copy]]
   次に、文字列を OS 側へ写す
4. ustr → copy  読み書き「読む」 渡す s0, s1「s0・s1 が指す文字（長さは s0_len・s1_len）」
   アプリのメモリから s0・s1 の文字を読む
5. copy → slot  読み書き「写す」 渡す Request{*s0, *s1} [[gateway.slots]]
   プロセスごとの受け皿に写し、Request の s0・s1 をその写しに差し替える
6. copy → stage  呼び出し [[gateway.stage]]
   次に、結果の書き込み先を用意する
7. stage → slot  読み書き「差し替え」 渡す Request{result_out, result_size}
   result_out を受け皿の場所に差し替え、アプリ側の元の場所を覚える
   分かれる：result_out が 0 でなく result_size が 1 以上 → 差し替える ／ それ以外 → 0 にする（結果を返す op は MISSING_RESULT）
8. stage → submit  呼び出し「並べる」 渡す Request [[os.submit]]
   OS 側の値だけになった Request を、要求の列に並べる（submit の中にも紙がある）
もし 満杯（8 の代わり）. submit → full  戻り「false」 [[gateway.full]]
   列が満杯なら submit は false を返す。request は REQUEST_SPACE の印を付けて、自分も false を返す
もし 返事待ち（1 の代わり）. slot → busy  読み書き「pending を見る」 [[gateway.busy]]
   前の要求の返事をまだ受け取っていなければ、何も読まずに REQUEST_SPACE の印を付けて false を返す
