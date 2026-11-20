# 契約（データの形）（contracts/ の .contract.mln）

## schema.request  Request
構造体・contracts/myapp/message.contract.mln の Request
フィールド domain：UI か APP（shell）
フィールド op：UI なら UiOp の 1 つ
フィールド owner：gateway が呼んだプロセスの pid で上書きする。アプリは名乗れない
フィールド a0 … a5：op ごとの引数（6 語）。SET_TEXT は a0 = ノード
フィールド *s0：文字列。gateway が OS 側にコピーする（1,024 B まで）
フィールド *s1：2 つ目の文字列。同じくコピーする（128 B まで）
フィールド result_out：結果の書き込み先。0 でなく result_size が 1 以上なら、gateway が OS 側の buffer に差し替え、返事で書き戻す
フィールド result_size：書き戻す長さ（64 B まで）
フィールド s0_len：s0 の長さ。文字列は NUL で終わらない
フィールド s1_len：s1 の長さ

アプリが OS に出す要求の封筒。データだけで、関数は持たない。SDK と MyOS の両方がこの契約を import する（[[policy.sdk-no-myos]]）。

## schema.event  Event
構造体・contracts/myapp/message.contract.mln の Event
フィールド owner：受け取るプロセス
フィールド id：ノード（runtime では NodeId）
フィールド kind：CLICK・TIMER・KEY など
フィールド arg：種類ごとの値
フィールド token：KEY では、登録したキーの番号
フィールド text[64]：OPEN のパスなど。中に持つので、取り出した後も生きている

OS からアプリに届く知らせ。[[os.events]] が入れ、[[lib.next]] が取り出す。

## schema.procstats  ProcStats
構造体・contracts/myos/process-args.contract.mln の ProcStats
フィールド cpu：CPU の時間の内訳
フィールド total_pages：プロセスとページ表に使える 4 KiB ページ
フィールド free_pages：そのうち空いている数
フィールド count：procs の使っている数
フィールド procs[16]：プロセスごと。プロセス表の順

PROC_STATS が返す、全部のプロセスと CPU の時間とメモリ。

## schema.cputimes  CpuTimes
構造体・contracts/myos/process-args.contract.mln の CpuTimes
フィールド total：全部の時間
フィールド idle：走るものが無いか、OS のスレッドが待っているだけの時間
フィールド kernel：OS 自身のスレッド（デスクトップ、ファイルシステムなど）の時間
フィールド kernel_threads：OS 自身のスレッドの数

起動からの CPU の時間の行き先。単位は時計の 1/256 tick で、一周するので差で読む。

## schema.procinfo  ProcInfo
構造体・contracts/myos/process-args.contract.mln の ProcInfo
フィールド pid：
フィールド parent：親の pid
フィールド activity：何をしているか
フィールド threads：スレッドの数
フィールド cpu_time：始まってから走った時間（1/256 tick、一周する）
フィールド pages：使っている 4 KiB ページ
フィールド name：実行ファイルの名前

1 つのプロセスの様子と、かかっているもの。

## schema.event-kind  EventKind
列挙・contracts/myapp/message.contract.mln の EventKind
値 NONE：
値 CLICK：
値 CHANGE：
値 ACTIVATE：
値 TIMER：タイマーのノードの 1 回
値 KEY：token に登録したキー
値 CLOSE：
値 OPEN：text にパス
値 CARET：arg = 行 << 16 | 桁

[[schema.event]] の種類。

## schema.request-domain  RequestDomain
列挙・contracts/myapp/message.contract.mln の RequestDomain
値 NONE：
値 UI：UI の要求（[[os.ui-protocol]]）
値 APP：アプリの起動など（shell）

[[schema.request]] をどこが受けるか。

## schema.request-status  RequestStatus
列挙・contracts/myapp/message.contract.mln の RequestStatus
値 OK：
値 INVALID_DOMAIN：
値 INVALID_OPERATION：
値 MISSING_RESULT：

1 つの要求の結果。

## schema.uiop  UiOp
列挙・contracts/myapp/ui.contract.mln の UiOp
値 NONE：
値 SET_TEXT：(ノード, s0)
値 TEXT_COPY：
値 SET_CHECKED：
値 INPUT_SET：
値 AREA_APPEND：
値 LIST_SET_ITEMS：
値 LIST_SELECT：
値 GRAPH_SET：(ノード, a1 = 系列 0 か 1, s0 = % を空白で区切る)
値 …：ADD_STYLE、FOCUS、CREATE_WINDOW など
値 CREATE_TIMER：(a0 = 間隔) 1 回ごとに TIMER イベント
値 …：ほかの CREATE_*

UI の要求の op。[[schema.request]] の op に入る。

## schema.os-service  OsService
列挙・contracts/myos/services.contract.mln の OsService
値 NONE：
値 REQUEST：(Request*) → 1 で列に入った、0 で満杯
値 REPLY：(i32 *out) → 1 で返事あり
値 POLL：(Event*) → 1 でイベントあり
値 …：FS_OPEN から FS_IS_DIR まで、ファイルの 11 個
値 PROC_SPAWN：
値 …：PROC_BIND から PROC_FEED まで 5 個
値 PROC_STATS：(ProcStatsArgs) 全部のプロセスと CPU の時間
値 PROC_ARGS：
値 LOG：

OS_CALL で頼めることの一覧。アプリから見た OS の API はこれだけ。
