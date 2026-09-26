# ユーザー空間スレッド

**Status:** Draft 1（2026-09-24）
**チケット:** 未作成（§10 の段ごとに切る）

関連: `docs/design/user-space-processes-and-syscalls.md`（PCB・syscall ABI）、
`docs/design/os-app-boundaries.md`（層の定義）、`contracts/README.md`（ABI の追加規則）。

1 つのプロセス（1 つのアドレス空間）の中で複数の実行の流れを走らせるための、
ISA・カーネル ABI・stdlib API の定義。実装順は §10。

---

## 0. 現状

- カーネルには既に「スレッド」の実体がある。`scheduler.mln` のタスク
  （`spawn_task` / `spawn_proc_task`）がそれで、`task_pid[]` は複数タスクが
  同じ pid を指す形をとれる。
- ただし `Process`（`kernel/process.mln`）は「1 プロセス = 1 タスク」を前提にしている。
  `task_id` は `Option<i32>` 一つで、`user_sp` / `kernel_stack_top` / `kernel_sp` は
  プロセスのフィールド。`reschedule` は `KERNEL_SP` と user sp を pid 単位で読み書きする。
- loader はユーザースタックを `0x7FFFC000` 固定 4 ページ、カーネルスタックを
  プロセスごとに 16 KB 確保する。
- `sys_exit` はプロセスのタスクが 1 つであることを前提に Zombie 化する。
- ISA にアトミック命令が無い。ユーザーモードでは `ei` / `di` が特権命令なので、
  割り込み禁止による排他もできない。
- スケジューラには app transport 用の `TASK_BLOCKED` と sticky notification がある。
  futex / join 用のキー付き待ち行列とタイムアウトはまだ無い。

## 1. 目的と非目的

**目的**

- 1 プロセス内で複数スレッドを生成・終了・join できる。
- ロックの取得・解放が、競合しない限り syscall なしで済む（futex 方式）。
- stdlib に `Thread` / `Mutex` / `Condvar` / atomic 操作を置き、アプリはそれだけで書ける。

**非目的（この段階ではやらない）**

- SMP。CPU は 1 コアのままとし、アトミック性は「1 命令で完結する」ことで得る。
- スレッドローカル変数の言語サポート（`thread.self()` + 配列で代用）。
- 型システムでのスレッド安全性の保証（`Send` / `Sync` 相当）。借用解析（MLC-002）の後。
- detach、スレッドの優先度、シグナル。

---

## 2. 層

```text
アプリ          thread.spawn / m.lock() / cv.wait()        MyStdLib  hosted/thread.mln, sync/*.mln
syscall stub    sys_thread_spawn / sys_futex_wait ...      MyStdLib  platform/myos/syscall.masm
カーネル ABI    Syscall::THREAD_* / FUTEX_*                 contracts/myos/syscall.contract.mln
                ThreadSpawnArgs / ThreadError              contracts/process/thread.contract.mln
ISA             swp（必須）, cas（任意）                     MyEmulator / MyAssembler / verilator
```

スレッドは `OS_CALL`（MyOS のサービス）ではなく **カーネルの syscall** にする。
スケジューリングはカーネルの責務であり、futex はタスクを直接ブロックする必要があるため。
MyOS 側は変更しない（§8）。

---

## 3. ISA

```text
swp rd, [rs]        ; tmp = mem[rs]; mem[rs] = rd; rd = tmp         Opcode 0x22
cas rd, rt, [rs]    ; old = mem[rs]; if old == rd { mem[rs] = rt }; rd = old   Opcode 0x23
```

- 割り込みは命令と命令の間でしか入らないので、1 命令で完結する読み書きは
  シングルコアではそれだけでアトミックになる。
- **最低限必要なのは `swp`**。mutex は §7.3 のとおり `swp` だけで書ける。
  `cas` は `fetch_add` や参照カウントなど、読んで計算して書く操作のため。
- どちらもユーザーモードで実行できる。アドレスがワード境界に揃っていない場合と
  ページフォルト・権限違反は、`ld` / `st` と同じ例外にする。
  `swp` は読み込みと書き込みの両方の権限を要求する（読み取り専用ページへの `swp` はフォルト）。
- **要確認:** `cas` はレジスタを 3 本使う。現行の命令エンコーディングで表せない場合は
  `cas` を諦め、`fetch_add` を stdlib 側で「`swp` ベースのスピンロック + 通常の読み書き」に落とす。

更新が必要な箇所: `runtime/MyEmulator/src/instruction.rs`（デコードと実行）、
アセンブラのニーモニック表、`hardware/verilator` の CPU。

---

## 4. カーネル ABI

### 4.1 syscall 番号（`contracts/myos/syscall.contract.mln`）

`contracts/README.md` の規則に従い、既存の番号の後ろに追加する。

```mln
export enum Syscall {
    EXIT = 1,
    ...
    OS_CALL,        // 10
    WAIT_NOTIFICATION, // 11（app transportで実装済み）
    THREAD_SPAWN,   // 12 (ThreadSpawnArgs *args)                        -> tid (>0) | -ThreadError
    THREAD_EXIT,    // 13 (i32 code)                                     -> 戻らない
    THREAD_JOIN,    // 14 (i32 tid, i32 *code_out)                       -> 0 | -ThreadError
    THREAD_SELF,    // 15 ()                                             -> tid
    FUTEX_WAIT,     // 16 (i32 *addr, i32 expected, i32 timeout_ticks)   -> 0 | -ThreadError
    FUTEX_WAKE,     // 17 (i32 *addr, i32 count)                         -> 起こしたスレッド数
}
```

引数は既存と同じく `r5` / `r6` / `r7`、戻り値は `r1`。失敗は既存のカーネル syscall と同じく
負の値で返し、stdlib が `Result<_, ThreadError>` に直す（§4.3）。

### 4.2 引数とエラー（`contracts/process/thread.contract.mln`）

```mln
package process_types;

// THREAD_SPAWN の引数。カーネルは syscall の最中にこれを自分の側へコピーするので、
// 呼び出し側のスタックに置いてよい。
export struct ThreadSpawnArgs {
    i32 entry;        // 開始 PC（普通は stdlib の thread_trampoline）
    i32 arg0;         // 開始時の r5
    i32 arg1;         // 開始時の r6
    i32 stack_bytes;  // 0 = 既定値（16 KB）。ページ単位に切り上げる
};

export enum ThreadError {
    NoFreeSlot,        // プロセスあたりの上限、またはタスクテーブルが満杯
    OutOfMemory,       // スタック（ユーザー / カーネル）を確保できない
    InvalidTid(i32),   // 存在しない tid、または別プロセスの tid
    JoinSelf,          // 自分自身を join しようとした
    AlreadyJoined(i32),// 既に別のスレッドが join している / join 済み
    WouldBlock,        // FUTEX_WAIT: *addr != expected
    TimedOut,          // FUTEX_WAIT: timeout_ticks が経過した
    BadAddress,        // args / addr / code_out がユーザー領域外、または境界不整列
}
```

### 4.3 負の戻り値との対応

`ThreadError` はペイロードを持つので enum 値を直接番号にできない。
番号はこの表で固定し、カーネルと stdlib の両方がこれに従う（追加は末尾のみ）。

| 戻り値 | ThreadError | ペイロード |
|---|---|---|
| -1 | `NoFreeSlot` | |
| -2 | `OutOfMemory` | |
| -3 | `InvalidTid` | 呼び出し時の tid |
| -4 | `JoinSelf` | |
| -5 | `AlreadyJoined` | 呼び出し時の tid |
| -6 | `WouldBlock` | |
| -7 | `TimedOut` | |
| -8 | `BadAddress` | |

ペイロードはカーネルから返さず、stdlib が呼び出し時の引数から埋める。

### 4.4 振る舞い

| 項目 | 決めごと |
|---|---|
| tid | 全プロセスで一意な正の整数。join されるまで再利用しない。メインスレッドも tid を持つ |
| スタック | カーネルが `0x7F00_0000 .. 0x7FFF_FFFF` からスロットを割り当てる。各スロットの下端に、マップしないガードページを 1 枚置く（§5.3） |
| 開始時のレジスタ | `pc = entry`、`r5 = arg0`、`r6 = arg1`、`lr = 0`、`sp` = スロット上端、`SR = SR_USER \| SR_IE`、他は 0。トランポリンを通らずに return すると PC 0 で即フォルトする |
| `THREAD_EXIT(code)` | 呼んだスレッドだけを終える。プロセスの最後のスレッドなら、そのコードでプロセスが終わる |
| `SYS_EXIT(code)` | 呼んだスレッドに関係なくプロセス全体を終える。全スレッドを止めて Zombie にする |
| `main` からの return | 今と同じくプロセス終了（= `SYS_EXIT`）。C と同じ |
| join | 1 つのスレッドを join できるのは 1 回・1 スレッドだけ。対象が終わるまで呼び出し側はブロックする。`code_out` が 0 なら終了コードを書かない |
| join されないスレッド | 終了後は zombie として TCB とスタックが残り、プロセス終了時に回収される |
| スレッドが子プロセスを spawn | 子の親はプロセス。どのスレッドから reap してもよい |
| futex のキー | `(pid, 仮想アドレス)`。アドレスはワード境界に揃っていること |
| `FUTEX_WAIT` | カーネル内で `*addr == expected` を確認してからブロックする（確認とブロックの間に割り込みを入れない）。一致しなければ即 `WouldBlock`。`timeout_ticks = 0` は無期限 |
| `FUTEX_WAKE` | 同じキーで待っているスレッドを FIFO で最大 `count` 個起こす。`count <= 0` は何もしない |
| 待機中のプロセス終了 | futex や join で待っていたスレッドも、プロセス終了時にまとめて回収する |
| 上限 | プロセスあたり `MAX_THREADS_PER_PROC = 8`（`kernel_config.mln`）。全体の上限は既存の `MAX_TASKS` |

---

## 5. カーネル内部

### 5.1 Process と Thread の分離

`Process` に残すのはアドレス空間とリソース、スレッドごとのものは TCB へ移す。

| Process（共有） | Thread（TCB、スレッドごと） |
|---|---|
| `pid`, `pdbr`, `heap_break`, fd テーブル | `tid`, `pid`, `task_idx` |
| `state`（Ready / Zombie(code) など、プロセス全体としての状態） | `state`（Running / Ready / Blocked / Zombie(code)） |
| `thread_count`（生きているスレッド数） | `user_sp`, `kernel_stack_top`, `kernel_sp` |
| `main_tid` | `stack_slot`, `joiner_tid: Option<i32>`, `wait_key`, `wake_tick` |

- `Process.task_id` は `main_tid` に置き換える。
- `reschedule` は、次のタスクの TCB から `user_sp` / カーネルスタックを取って `KERNEL_SP` を書く。
  `PDBR` は今までどおり `task_pid[]` から引いたプロセスの `pdbr` で、同じ pid の中で
  切り替わるときは書き直さなくてよい。
- loader がプロセス生成時に作っているユーザー / カーネルスタックは、
  メインスレッドの TCB に属するものとして扱う。

### 5.2 カーネルスタック

スレッドごとに 16 KB を `heap.alloc` する。syscall はこのスタックの上で動くので
共有できない。スレッドが終わったら、join されて TCB を解放するときに一緒に返す。

### 5.3 ユーザースタックのスロット

```text
0x7F00_0000 ┌──────────────┐
            │ slot 7       │  ↑ 各スロット = ガードページ 1 枚（未マップ） + stack_bytes
            │ ...          │
            │ slot 1       │
            │ slot 0       │  メインスレッド（既存の 0x7FFFC000..0x7FFFFFFF）
0x7FFF_FFFF └──────────────┘
```

- スロットの大きさは固定（`16 MB / MAX_THREADS_PER_PROC = 2 MB`）。
  その中で下からガードページ、上端から `stack_bytes` をマップする。
  スタックの大きさがスロットを超えたら `OutOfMemory`。
- `sys_sbrk` のヒープとスタックの衝突判定（`USER_STACK_BASE`）は
  スタック領域全体の下端 `0x7F00_0000` に変える。

### 5.4 ブロック状態と待ち行列

app transport が追加した `TASK_BLOCKED` を使い、ブロック理由と timeout をスレッド TCB へ拡張する。

- `FUTEX_WAIT`: `wait_key = (pid, addr)`、タイムアウトがあれば `wake_tick` も設定する。
  待ち行列はキーごとの単方向リスト（固定サイズのプールで足りる）。
- `THREAD_JOIN`: 対象 TCB の `joiner_tid` に自分を書いて Blocked にする。
  対象が `THREAD_EXIT` するときに `joiner_tid` を起こす。
- タイムアウト: `reschedule` が既存の `TASK_SLEEPING` の起床確認と同じループで
  `wake_tick` を見る。期限で起きたスレッドの戻り値は `TimedOut`、
  wake されたスレッドの戻り値は 0 とする（TCB に戻り値を置いてから Ready にする）。

### 5.5 syscall 中の割り込み

syscall を割り込み禁止のまま処理しているなら、カーネル内のデータ構造は
シングルコアで自動的に直列化される。**要確認:** syscall の途中で有効化している箇所
（`OS_CALL` の長い処理など）があれば、同じプロセスの 2 スレッドが同時に
`Process` を触りうるので、その区間だけ `di` / `ei` で囲む。

---

## 6. syscall stub（`platform/myos/syscall.masm`）

```text
i32  sys_thread_spawn(i32 args)
void sys_thread_exit(i32 code)
i32  sys_thread_join(i32 tid, i32 code_out)
i32  sys_thread_self()
i32  sys_futex_wait(i32 addr, i32 expected, i32 timeout_ticks)
i32  sys_futex_wake(i32 addr, i32 count)
i32  atomic_swap(i32 addr, i32 value)                 ; swp
i32  atomic_cas(i32 addr, i32 expected, i32 new)      ; cas

thread_trampoline:        ; r5 = fn, r6 = arg
  ; r1 = fn(arg); sys_thread_exit(r1)
```

`thread_trampoline` はスレッドの開始点になる。関数 `fn` の戻り値を
そのままスレッドの終了コードにする。

---

## 7. stdlib API

### 7.1 `hosted/thread.mln`

```mln
package thread;

export struct Thread { i32 tid; };

/** 新しいスレッドで entry(arg) を実行する。
 * @param entry i32 (i32 arg) の関数アドレス。戻り値がスレッドの終了コードになる。
 * @param arg entry に渡す値。
 * @return 生成したスレッド、または ThreadError。
 */
export Result<Thread, ThreadError> spawn(i32 entry, i32 arg);
export Result<Thread, ThreadError> spawn_sized(i32 entry, i32 arg, i32 stack_bytes);

/** スレッドの終了を待ち、終了コードを返す。 */
export Result<i32, ThreadError> (Thread *t) join();

export i32  self();              // 呼んだスレッドの tid
export void exit(i32 code);      // 呼んだスレッドだけを終える
export void yield();             // sys_yield（次の tick まで寝る）
```

`spawn` は `ThreadSpawnArgs { entry: thread_trampoline, arg0: entry, arg1: arg, stack_bytes }`
を作って `sys_thread_spawn` を呼ぶ。

### 7.2 `sync/atomic.mln`

```mln
export i32  load(i32 *p);                                   // シングルコアなので普通の ld
export void store(i32 *p, i32 value);                       // 普通の st
export i32  swap(i32 *p, i32 value);                        // swp
export i32  compare_exchange(i32 *p, i32 expected, i32 new);// cas。元の値を返す
export i32  fetch_add(i32 *p, i32 delta);                   // cas のループ。元の値を返す
```

`load` / `store` を関数として置くのは、将来 SMP やメモリバリアが必要になったときに
呼び出し側を変えずに済むようにするため。

### 7.3 `sync/mutex.mln`

```mln
export struct Mutex { i32 state; };   // 0 = 空き, 1 = ロック中, 2 = ロック中で待ちあり

export void (Mutex *m) init() { m->state = 0; }

export void (Mutex *m) lock() {
    if (atomic.swap(&m->state, 1) == 0) { return; }          // 競合なし: syscall なし
    while (atomic.swap(&m->state, 2) != 0) {
        sys_futex_wait((i32)&m->state, 2, 0);
    }
}

export bool (Mutex *m) try_lock() {
    return atomic.compare_exchange(&m->state, 0, 1) == 0;
}

export void (Mutex *m) unlock() {
    if (atomic.swap(&m->state, 0) == 2) {
        sys_futex_wake((i32)&m->state, 1);
    }
}
```

`cas` が無い場合、`try_lock` は `swap(&m->state, 1)` の結果が 0 以外なら
`swap` で元の値へ書き戻す形にする（待ちありの 2 を 1 に潰さないよう、元の値を書き戻す）。

MyLang にデストラクタが無いので、RAII のガードは作らない。`lock` と `unlock` は手動で対にする。

### 7.4 `sync/condvar.mln`

```mln
export struct Condvar { i32 seq; };

export void (Condvar *c) init();
export void (Condvar *c) wait(Mutex *m);
export Result<_, ThreadError> (Condvar *c) wait_ticks(Mutex *m, i32 ticks);  // Err(TimedOut)
export void (Condvar *c) notify_one();
export void (Condvar *c) notify_all();
```

`wait` は `seq` を読む → `m.unlock()` → `sys_futex_wait(&seq, 読んだ値, ticks)` →
`m.lock()`。`notify_*` は `fetch_add(&seq, 1)` してから `sys_futex_wake(&seq, 1 または大きな数)`。
見かけ上の起床（spurious wakeup）はありうるので、呼び出し側は条件をループで確かめる。

### 7.5 使用例

```mln
import thread from "hosted/thread.mln";
import { Thread } from "hosted/thread.mln";
import { Mutex } from "sync/mutex.mln";

Mutex g_lock;
i32 g_count = 0;

i32 worker(i32 n) {
    i32 i = 0;
    while (i < n) {
        g_lock.lock();
        g_count++;
        g_lock.unlock();
        i++;
    }
    return n;
}

i32 main() {
    g_lock.init();
    Thread t = case thread.spawn((i32)worker, 1000) of {
        Ok(t) -> t;
        Err(_) -> ({ return 1; });
    };
    worker(1000);
    t.join();
    return g_count;   // 2000
}
```

---

## 8. 既存コードへの影響

| 対象 | 扱い |
|---|---|
| `sys_sbrk` とアロケータ（`memory/arena.mln` など） | 当面「スレッド安全ではない」と明記する。`Mutex` ができた後、グローバルアロケータを 1 本のロックで守る |
| MyOS の `OS_CALL` router | `(pid, service, args)` の形は変えない。結果は呼び出し側が用意した `result_out` に書くので、複数スレッドが別々に呼んでも混ざらない。UI の `REPLY` / `POLL` のようにプロセス単位のキューを読むサービスは、1 スレッドだけが呼ぶことをアプリ側の規約にする |
| `SYS_SPAWN` / `PROC_*` | 変更なし。子プロセスの親はプロセス単位 |
| MyAppFramework | 変更なし。イベントループは 1 スレッドで回す前提のまま |

## 9. テスト

- **ISA**: emulator の単体テストで `swp` / `cas` の値と、読み取り専用ページ・
  未マップページ・境界不整列でのフォルト。
- **カーネル**（`system/MyKernel/tests/scheduler` に追加）: spawn → join で終了コードが返る、
  上限を超えた spawn が `NoFreeSlot`、自分自身の join が `JoinSelf`、二重 join が `AlreadyJoined`、
  最後のスレッドの `THREAD_EXIT` でプロセスが Zombie になる、`SYS_EXIT` で他スレッドも止まる、
  スタックのガードページに触れるとフォルトする。
- **futex**: 値が違えば `WouldBlock`、タイムアウトで `TimedOut`、`FUTEX_WAKE` の戻り値と FIFO 順。
- **stdlib**（`.mbin` アプリとして `qa/tests` から起動）: §7.5 のカウンタが 2 スレッド × N 回で 2N になる。
  `Condvar` を使った生産者・消費者で、全要素が一度ずつ届く。

## 10. 実装順

| 段 | 内容 | 終わりの判定 |
|---|---|---|
| 1 | TCB の分離、スレッドごとのユーザー / カーネルスタック、`THREAD_SPAWN` / `THREAD_EXIT` / `THREAD_SELF` | 2 スレッドが交互にシリアルへ書ける |
| 2 | 既存 `TASK_BLOCKED` の TCB 対応、`THREAD_JOIN`、`SYS_EXIT` の全スレッド停止 | §9 のカーネルテストが通る |
| 3 | `swp`（と `cas`）命令、`FUTEX_WAIT` / `FUTEX_WAKE` | §9 の ISA / futex テストが通る |
| 4 | stdlib の `thread` / `atomic` / `Mutex` / `Condvar` | §9 の stdlib テストが通る |
| 5 | グローバルアロケータのロック | 複数スレッドからの確保で壊れない |

段 3 の前に段 4 を試したい場合、`Mutex` を一時的に「毎回 syscall する」実装にすれば
アトミック命令なしでも正しく動く（カーネル内がシングルコアで直列なため）。

## 11. 未決

1. **`cas` のエンコーディング**: レジスタ 3 本を今の命令形式で表せるか（§3）。
2. **型付き関数ポインタ**: `spawn` の `entry` は今 `i32` のアドレス。MyLang に関数ポインタ型が入れば
   `spawn(i32 (i32) entry, i32 arg)` にできる。コンパイラ側の別チケット。
3. **スタックの確保者**: この案はカーネルが確保する（ガードページのため）。
   ユーザーが `sbrk` した領域を渡す方式ならカーネルは簡単になるが、スタックのあふれを検出できない。
4. **syscall 中の割り込み**（§5.5）: 実装前に確認する。
5. **transport notification との統合**: アプリ transport はキー付き待ち行列ではなく、
   task ごとの sticky notification を採用した。futex / join の待ち行列は `(pid, addr)` と
   tid のまま実装し、将来 wait-any が必要になった時点で複数登録と解除規則を含めて再設計する。
