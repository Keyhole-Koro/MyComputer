# アプリ transport のブロッキング化

**Status:** 最小構成を実装済み（2026-09-25）。ユーザースレッド対応と非同期 RPC は未実装。

関連: `docs/design/threads.md`、`docs/design/ui-protocol.md`、
`docs/design/os-app-boundaries.md`、`contracts/myapp/message.contract.mln`、
`contracts/myos/syscall.contract.mln`。

## 1. 実装した範囲

現在の MyAppFramework は 1 プロセスにつき 1 実行タスク、transport を使うスレッドも
1 本である。この前提のまま、次のポーリングをブロッキング待ちへ置き換えた。

```mln
request(m):  while (os_call(REQUEST, m) == 0)
                 sys_wait_notification(REQUEST_SPACE);
             while (os_call(REPLY, &r) == 0)
                 sys_wait_notification(REPLY);

run():       while (1) {
                 while (poll(&ev)) deliver(&ev);
                 sys_wait_notification(EVENT);
             }
```

実装箇所:

- `contracts/myos/syscall.contract.mln`: `WAIT_NOTIFICATION`
- `contracts/myapp/message.contract.mln`: `TransportSignal`
- `system/MyKernel/src/kernel/scheduler.mln`: `TASK_BLOCKED`、通知の arm / wait / wake
- `system/MyOS/src/ipc/gateway.mln`: 空・満杯を確認した syscall の中で通知を arm
- `system/MyOS/src/ipc/channel.mln`: request slot と reply の通知
- `system/MyOS/src/ipc/events.mln`: event の通知
- `system/MyAppFramework/src/runtime/transport.mln`: tick 単位の `sys_yield` を通知待ちへ変更

既存の `REQUEST` / `REPLY` / `POLL` は、データが無ければ 0 を返す操作のままにした。
待機だけをカーネル syscall に分けたため、返信の user-memory copy は従来どおり
呼び出し元プロセスのページテーブルが有効な `REPLY` / `POLL` 内で行われる。

## 2. 通知の正しさ

単純な「確認してから sleep」には、確認と sleep の間に通知が来る lost wakeup がある。
この実装は sticky notification と arm を使う。

1. `REQUEST` が full、または `REPLY` / `POLL` が empty だった場合、その OS_CALL の中で
   対応ビットを現在のタスクへ arm してから 0 を返す。
2. producer はリングへデータまたは空き状態を publish した後、arm 済みのタスクへ通知する。
3. `WAIT_NOTIFICATION(mask)` は保留中の通知があれば消費して即座に戻る。無ければ
   現在のタスクを `TASK_BLOCKED` にして別の runnable task へ切り替える。
4. producer が待機ビットを通知すると、タスクを `TASK_RUNNABLE` に戻す。

syscall dispatcher は保存済み interrupt frame を scheduler へ渡せるため、
`WAIT_NOTIFICATION` 自体はカーネル call stack を保持しない。起床後はユーザー側のループが
元の `REQUEST` / `REPLY` / `POLL` を再実行する。

通知ビットは次の 3 つ。

| bit | arm する条件 | 通知元 |
|---|---|---|
| `REQUEST_SPACE` | 共有 request ring が full | server が request を dequeue した直後 |
| `REPLY` | プロセスの reply channel が empty | server が reply を enqueue した直後 |
| `EVENT` | プロセスの event channel が empty | event を enqueue した直後 |

`REQUEST_SPACE` は共有リングなので、空きを待つ全タスクへ通知する。最大 16 プロセスの
単一コア構成では、この単純な broadcast を採用する。

## 3. イベント文字列の所有権

以前の `Event.text` はポインタで、次の 2 つの共有バッファに依存していた。

- server 側の `open_path[64]`: 複数の queued OPEN が同じポインタを持つ
- app 側の `g_event_text[64]`: 次の POLL が直前の Event.text を上書きする

後方互換を維持する必要がないため、`Event` を次の形へ変更した。

```mln
struct Event {
    i32 owner;
    i32 id;
    i32 kind;
    i32 arg;
    i32 token;
    char text[64];
};
```

カーネル IPC slot は 16 words から 24 words へ広げ、words 5..20 に text を inline で
格納する。enqueue 時点で文字列をコピーするので、それぞれの queued event が文字列を所有する。
ウィンドウ生成待ちの OPEN path も shell の instance slot ごとに保持する。

## 4. 解決した問題と残る遅延

| 問題 | 状態 |
|---|---|
| idle 中のアプリが毎 tick 起きる | 解決。event が届くまで `TASK_BLOCKED` |
| reply / event を `sys_yield` で再確認する | 解決。producer 通知で runnable になる |
| request ring が full のとき yield で再試行する | 解決。slot が空くまでブロック |
| queued event の文字列が共有バッファで上書きされる | 解決。Event と IPC slot に inline 所有 |
| server が request を確認するまでの遅延 | 未解決。compositor は各 pass の末尾で 1 tick sleep |
| runnable になった app が実際に schedule されるまでの遅延 | 最大 1 tick 残る |

したがって、この段階は CPU のポーリング除去が主目的である。往復時間をさらに短くする場合は、
compositor を request、input、次の timer deadline のいずれかで起こし、処理後に runnable task へ
即座に CPU を渡せる kernel-task wait/yield primitive が必要になる。

## 5. 並行要求とユーザースレッド

現在は transport を 1 タスクだけが使う。これは `docs/design/threads.md` の現行方針と一致する。
スレッドごとに reply channel だけを作っても十分ではない。gateway にはプロセスごとに 1 組の
`s0`、`s1`、`out`、`result` staging buffer と copy-out metadata があるためである。

複数スレッドからの同期要求を許可するときは、次をまとめて変更する。

1. request ごとの context を確保し、入力文字列、出力、typed result、user copy-out 先を所有させる。
2. context に token と要求元 tid を記録する。
3. reply completion が該当 tid だけを起こす。
4. thread exit / process exit で context と待機登録を回収する。
5. event channel の consumer は UI スレッド 1 本に固定する。

## 6. 非同期 RPC をまだ入れない理由

`REQUEST_ASYNC` は request 単位の context が無い現状では安全に実装できない。次の要求が
gateway の staging buffer を上書きするためである。また通常 event channel は満杯時に
イベントを捨てるため、RPC completion を同じチャネルへ載せると永久待ちになりうる。

非同期 RPC を追加する場合は以下を前提とする。

- token ごとの request context と所有 buffer
- 捨てない completion queue、または明示的な backpressure
- token の wrap、cancel、thread/process exit 時の寿命規則
- 複数 producer が submission ring を更新するための atomic 操作

共有メモリリングを使う場合も、サーバータスクから通常の user pointer は読めない。
文字列・出力 buffer を共有領域へ登録するか、pid の page table を指定してコピーする仕組みが要る。

## 7. 対象外

- stdin のブロッキング READ
- filesystem の非同期化
- ユーザースレッドの生成、join、futex

filesystem は同期 API のままだが、将来ワーカースレッドから並行して呼ぶ前に、
`fs/syscall.mln` の共有 scratch buffer と filesystem の global state を直列化する必要がある。
