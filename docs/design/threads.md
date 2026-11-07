# Process / Thread Boundary and User-Space Threads

**Status:** Draft 2（2026-10-08）

**Scope:** Process、Thread、Scheduler の責務境界、カーネル内部契約、ユーザー向け thread ABI

**Supersedes:** Draft 1（2026-09-24）および
`user-space-processes-and-syscalls.md` の「1 process = 1 schedulable context」を前提とする箇所

関連文書:

- `docs/design/user-space-processes-and-syscalls.md`: 仮想アドレス空間と基本 syscall ABI
- `docs/design/app-transport-blocking.md`: notification と app transport の待機規則
- `contracts/README.md`: 共有 contract の配置と ABI 更新規則
- `docs/design/mylang-owned-values-and-drop.md`: カーネル内リソースの所有と失敗時 cleanup

初めて読む場合は、§2（用語）→ §3（所有権）→ §4（状態）→ §5（構造体）の順に読むと、
後半のABIとlifecycleが追いやすい。§7はuser/kernel境界の公開contract、§8はそのcontractを
実現する内部手順である。

---

## 1. この設計が解決すること

現在のカーネルでは、一つのユーザープロセスに一つの scheduler task しかない。
そのため `Process` が次の二種類の責務を同時に持っている。

1. アドレス空間、heap break、fd table、終了状態など、プロセス全体で共有する資源
2. user SP、kernel stack、実行状態など、一つの実行コンテキストだけに属する情報

一方、`scheduler.mln` も task ごとの SP、PID、実行状態、待機情報を持つ。
したがって、現在は Process と scheduler task の間に同じ情報が二重に存在する。

この設計では、カーネル内部の scheduler task を **Thread Control Block (TCB)** に置き換える。
Thread と task を別々のオブジェクトにはしない。

```text
Process   = アドレス空間と共有資源の所有単位
Thread    = CPU が実行・停止・再開するコンテキスト
Scheduler = 次に Running にする Thread を選ぶ機構
```

ユーザーから見える `Thread` handleは、カーネルがスケジュールするuser threadのTIDを指す。
handleとTCBは別の値だが、別のscheduler task objectを間に作らない。
カーネル内部では kernel thread も同じ TCB table に格納する。idle context だけは、通常の
runnable set に入らない scheduler の fallback context として別に保持してよい。

### 1.1 目的

- Process と Thread の所有物を一意に決める。
- 実行状態、SP、待機理由を TCB の一か所だけに置く。
- 一つの Process に複数の user thread を所属させる。
- thread の生成、終了、join、process 全体の終了を定義する。
- sleep、notification、join、futex を同じ blocking model で表す。
- stdlib に `Thread`、atomic、`Mutex`、`Condvar` を提供できるABIを定義する。

### 1.2 非目的

- SMP。最初の実装は一つのCPUを前提とする。
- `Send` / `Sync` 相当の静的なスレッド安全性。
- 言語組み込みのthread-local storage。
- detach、priority、signal、thread cancellation。
- async task / coroutine。将来追加する場合も、CPU threadとは別の概念にする。
- MyAppFramework のイベントループを複数threadで動かすこと。

---

## 2. 用語

### 2.1 Process

Process は保護と資源所有の単位である。同じ Process に属する Thread は、次を共有する。

- page directory と user address space
- executable text、globals、heap
- fd table と process-level I/O state
- MyOS の process endpoint
- process exit status

Process 自体はCPU上で実行されない。したがって Process に `Running` や `Blocked` を付けない。
同じ Process の一つのThreadがRunningで、別のThreadがBlockedという状態が普通に存在するためである。

### 2.2 Thread

Thread はプリエンプト可能な実行コンテキストである。Threadごとに次を持つ。

- register context と saved stack pointer
- kernel stack
- user threadならuser stack
- Runnable / Running / Blocked / Zombie状態
- 一度に一つの待機理由
- thread exit code とjoin関係
- notificationのarmed/pending bits

### 2.3 Kernel thread と user thread

両者は同じスケジューリング規則を使うが、ownerが異なる。

```text
Kernel thread: Processに属さず、user SPとuser stackを持たない
User thread:   一つのpidに属し、そのProcessのpage directoryで実行する
```

### 2.4 Taskという語を使わない理由

既存の `spawn_task` はスケジューラの実行枠を意味するが、本設計ではその実体がTCBになる。
別の `Task` 型を残すと、ThreadとTaskのどちらがstateやSPを所有するか再び曖昧になる。

実装名は次のように移行する。

| 旧名 | 新名 |
|---|---|
| scheduler task | kernel内部の `Thread` / TCB |
| `spawn_task` | `spawn_kernel_thread` |
| `spawn_proc_task` | Process生成時は `create_main_thread`、追加時は `spawn_user_thread` |
| `task_*[]` | `g_threads[]` 内のfield |
| `current_task` | `current_thread_slot` |

async runtimeを将来追加する場合は、そのwork itemに `Task` という名前を使える。

---

## 3. 所有権の境界

| 情報・資源 | 所有者 | 備考 |
|---|---|---|
| `pid`、process state | Process table | PIDはprocess slotとは別の論理IDとして扱ってよい |
| page directory、user mapping | Process | Threadは参照するだけ |
| `heap_break` | Process | `sbrk`はprocess全体への操作 |
| fd table | Process | 全Threadで共有 |
| process exit status | Process | 親がreapするまで保持 |
| `tid`、thread state | Thread table | scheduler slotとは別の安定ID |
| saved register frame / kernel SP | Thread | context switchのsource of truth |
| user SP | User thread | Processには置かない |
| kernel stack | Thread | syscallとinterruptを実行するためThreadごとに必要 |
| user stack mapping | User thread | 同じaddress space内でThreadごとに分離 |
| user stack slot bitmap | Process | 同じaddress space内のslot予約を直列化 |
| wait reason / deadline | Thread | 一度に一つだけ |
| runnable選択、current slot | Scheduler | Threadの寿命やProcess資源は所有しない |
| idle context | Scheduler | runnable Threadが無い場合だけ使用 |

### 3.1 絶対に守る不変条件

1. 実行状態のsource of truthは `Thread.state` 一つだけである。
2. `Process` は `Ready`、`Running`、`Blocked` を持たない。
3. tableへ公開済みのuser threadの `owner` は、`Alive` または `Exiting` のProcessを指す。
4. `Running` のThreadは現在のCPUにつき高々一つで、schedulerのcurrent slotと一致する。
5. `Blocked` のThreadは必ず一つの `WaitReason` を持つ。
6. `Runnable` / `Running` のThreadはwait reasonを持たない。
7. user SP、kernel SP、kernel stackはProcessではなくThreadに属する。
8. syscall中のcurrent PID/TIDはcurrent TCBから導出し、別のglobalへ複製しない。
9. Processが `Zombie` になった後、そのPIDをownerとするTCBは残らない。
10. schedulerはProcessやThreadをfreeしない。寿命の終了はthread/process lifecycle APIが行う。
11. `live_threads` はlive TCB数、`retained_threads` はZombieを含む未reap TCB数と一致する。
12. `user_stack_slots` のbitは、対応するProcess内でstack mappingを所有するThreadがいる時だけ立つ。

---

## 4. 状態モデル

### 4.1 Process state

```mln
export enum ProcessState {
    Loading,
    Alive,
    Exiting(ProcessExitStatus),
    Zombie(ProcessExitStatus),
    Released(ProcessExitStatus),
}
```

```text
free slot
   │ reserve
   ▼
Loading ── commit main thread ──▶ Alive
   │ load failure                    │ SYS_EXIT / fatal user fault
   └──────── rollback                ▼
                                Exiting
                                    │ all TCBs and process resources released
                                    ▼
                                Zombie
                                    │ MyOS releases what it holds under the PID (console.sweep)
                                    ▼
                                Released
                                    │ parent reap
                                    ▼
                                free slot
```

- `Loading`: PIDは予約済みだが、外部から実行・参照できない。
- `Alive`: thread spawnと通常syscallを受け付ける。
- `Exiting`: 新しいthreadやProcess資源操作を拒否し、全Threadと待機登録を回収中。
- `Zombie`: アドレス空間、fd、Threadは既に回収済み。MyOSはまだこのPIDでイベント、DOMノード、
  key claim、コンソール、gateway slotを持っている。
- `Released`: exit statusだけを保持する。slotの解放だけが残っている。

Processは親を持つ（`Process.parent`。`None` はOS自身で、シェルが起動したアプリがこれにあたる）。
親だけが子をreap・feed・bind・queryできる。親でないcallerへの答えは `InvalidPid`、つまり
「そのような子はいない」である。親が終わると、MyOSは子を `scheduler.terminate` で終わらせて
回収する（hangup）。親はそれが済むまで `Released` にならないので、存在しない親を指すProcessは無い。

`Exiting` を置くのは、process exitの途中でnotificationや別Threadのsyscallが入っても、
新しい仕事を追加させないためである。

### 4.2 Thread state

```mln
export enum ThreadState {
    Runnable,
    Running,
    Blocked(WaitReason),
    Exiting(i32),
    Zombie(i32),
}
```

空きslotは `Option<Thread>::None` で表すため、`Empty` variantは作らない。

```text
             preempt / yield
Runnable ◀────────────────── Running
   │                            │
   │ dispatch                   │ wait
   └──────────────────────────▶ Blocked(reason)
                                  │ wake
                                  └────────▶ Runnable

Running ── THREAD_EXIT ──▶ Exiting ── switch-away後のcleanup ──▶ Zombie
                                                                       │ join
                                                                       ▼
                                                                  free slot
```

`Exiting` が必要なのは、Threadが自分自身のkernel stack上で `THREAD_EXIT` を処理するためである。
現在使用中のkernel stackは、そのThreadから別のThreadまたはidleへ切り替えた後でなければfreeできない。

Process全体が終了する場合、joinされていないZombie TCBもすべて回収する。
### 4.3 Wait reason

```mln
export struct SleepWait {
    i32 deadline_tick;
};

export struct NotificationWait {
    i32 mask;
};

export struct JoinWait {
    i32 target_tid;
};

export struct FutexWait {
    i32 addr;           // owner Process内のaligned user virtual address
    i32 deadline_tick;  // 0ならtimeoutなし
};

export enum WaitReason {
    Sleep(SleepWait),
    Notification(NotificationWait),
    Join(JoinWait),
    Futex(FutexWait),
}
```

別々の `TASK_SLEEPING`、`TASK_BLOCKED`、`wake_tick[]`、`wait_mask[]` を増やさず、
「なぜ実行できないのか」を一つの値で表す。

---

## 5. カーネル内部の構造体

以下は論理layoutである。MyLangの実装では固定長tableを使うが、fieldの所有者と意味は
この定義に従う。

### 5.1 Process Control Block

```mln
export struct Process {
    Pid pid;
    ProcessState state;

    // Address-space ownership
    i32 pdbr;
    i32 heap_break;
    i32 user_stack_slots;  // slot nを使用中ならbit nが1

    // Thread accounting
    i32 live_threads;      // Runnable / Running / Blocked
    i32 retained_threads;  // live + joinされていないZombie
};
```

開いたファイルはProcessではなくMyOSの`fs`が全体の表で持ち、各ファイルが開いたプロセスを
`owner`に記録する。他のプロセスのファイルは`BadFd`で拒否し、プロセスが終わると
`fs.close_all_of`が閉じる。

```mln
Option<Process> g_processes[MAX_PROCS];
```

`user_entry` はmain TCBの初期contextを作る間だけ必要であり、Processへ永続保存しない。
`main_tid` も保存しない。`main` のreturnはuser stubが `SYS_EXIT` を呼ぶため、kernelがmain
Threadを特別扱いする必要はない。

### 5.2 Thread Control Block

```mln
export enum ThreadOwner {
    Kernel,
    User(Pid),
}

export struct KernelStack {
    i32 base;
    i32 bytes;
    bool owned; // boot contextの借用stackならfalse
};

export struct UserStack {
    i32 slot;
    i32 mapped_base;
    i32 mapped_bytes;
};

export struct Thread {
    i32 tid;
    ThreadOwner owner;
    ThreadState state;

    // Saved execution context
    i32 saved_kernel_sp;       // interrupt-style register frame
    i32 saved_user_sp;         // 0 for kernel thread
    KernelStack kernel_stack;
    Option<UserStack> user_stack;

    // Join lifecycle
    Option<i32> joiner_tid;

    // App transport notification state
    i32 notification_pending;
    i32 notification_armed;

    // Success value or error payload placed in saved r2 when a syscall wakes.
    i32 wake_result;
};

Option<Thread> g_threads[MAX_THREADS];
```

`saved_kernel_sp` は現在の `task_sps[]` と `Process.kernel_sp` を統合する。
`saved_user_sp` は現在の `Process.user_sp` から移す。

Threadが `Zombie` になった後は、exit codeとjoin状態だけが必要である。kernel/user stackは
switch-away後に回収し、対応fieldを0/Noneへクリアする。これによりjoinされないThreadが
16 KiB以上のstackを保持し続けることを避ける。boot contextのkernel stackは借用品なので、
`KernelStack.owned == false` の場合はfreeしない。

### 5.3 Scheduler state

```mln
// Thread tableを所有しない。slotはg_threadsへのindex。
i32 current_thread_slot;
i32 thread_slot_high_water;
i32 ticks;

// 通常のTCBではなく、runnable threadが無いときだけ使うfallback。
i32 idle_sp;
KernelStack idle_stack;
```

Schedulerが保持するのは選択アルゴリズムに必要なindexとclockだけである。

`kernel_config.mln` には次の上限を置く。

```mln
export const i32 MAX_THREADS = 256;           // kernel + user threads
export const i32 MAX_THREADS_PER_PROC = 8;    // Zombie TCBも上限に含む
export const i32 DEFAULT_USER_STACK_BYTES = 16384;
export const i32 DEFAULT_KERNEL_STACK_BYTES = 16384;
```

### 5.4 TIDとtable slot

TIDとtable slotを同じ値にしてはならない。join後にslotを再利用すると、古いThread handleが
新しいThreadを指すABA問題になるためである。

- TIDは正の `i32`。0はinvalid。
- `g_next_tid` を単調増加させる。
- wrap時は0と現在liveなTIDをskipする。
- lookupは `tid -> slot` のtable scanでよい。上限256ならcontrol pathのcostとして十分小さい。
- scheduler hot pathはslotを使い、毎tick TID lookupをしない。

古いTIDがcounter一周後まで永続する保証はしないが、通常のslot再利用では別Threadを指さない。

---

## 6. カーネルmodule間の内部契約

型名と細かなerror型は実装時に調整できるが、依存方向と責務は固定する。

```text
loader/syscall/irq
       │ lifecycle操作
       ▼
thread.mln ─────────▶ process.mln
    │                    │
    │ TCB参照             │ PDBR参照
    ▼                    ▼
scheduler.mln ─────────▶ mmu.mln
```

- `process.mln` はschedulerをimportしない。
- `thread.mln` はProcessへの所属確認とcount更新を行う。
- `scheduler.mln` はTCBを選択・保存・復元するが、TCBをfreeしない。
- `loader.mln` はProcessとmain Threadを一つのtransactionとして生成する。
- `syscall.mln` はABI decodeを行い、lifecycle処理をthread/process APIへ委譲する。

### 6.1 Process API

```mln
Result<Pid, ProcessError> reserve_process(Option<Pid> parent);
Result<_, ProcessError> commit_process(Pid pid, i32 pdbr, i32 heap_break);
Result<_, ProcessError> begin_process_exit(Pid pid, ProcessExitStatus status);
Result<_, ProcessError> finish_process_exit(Pid pid);
Result<ProcessState, ProcessError> process_state(Pid pid);
Result<i32, ProcessError> process_pdbr(Pid pid);
Result<_, ProcessError> reap_process(Pid pid);
```

`reserve_process()` は `Loading` slotを返す。`commit_process()` はmain TCBがpublish可能に
なってから `Alive` にする。途中失敗はLoading Processをrollbackする。

### 6.2 Thread API

main Threadの初期contextはloader内部の値として渡す。

```mln
export struct InitialUserContext {
    i32 entry;
    i32 user_sp;
    i32 arg0;
    i32 arg1;
};
```

```mln
Result<i32, ThreadError> create_main_thread(Pid pid, InitialUserContext init);
Result<i32, ThreadError> spawn_user_thread(Pid pid, ThreadSpawnArgs args);
Result<i32, SchedulerError> spawn_kernel_thread(fn() -> void entry, i32 stack_bytes);

Option<i32> current_tid();
Option<Pid> current_pid();

Result<_, ThreadError> block_current(i32 saved_sp, WaitReason reason);
Result<_, ThreadError> wake_thread(i32 tid, i32 wake_result);
void exit_current_thread(i32 saved_sp, i32 code);
void exit_process_threads(Pid pid, ProcessExitStatus status);
Result<JoinOutcome, ThreadError> join_thread(i32 target_tid);
void finish_deferred_cleanup(i32 retired_thread_slot);
```

`current_pid()` はcurrent TCBの `ThreadOwner::User(pid)` から導出する。
`process.g_current_pid` は廃止する。

### 6.3 Scheduler API

```mln
i32 reschedule(i32 interrupted_sp);
i32 yield_until_tick(i32 interrupted_sp);
i32 block_and_reschedule(i32 interrupted_sp);
void make_runnable(i32 thread_slot);
```

Schedulerが直接受け取る識別子はhot pathではslotとする。外部moduleがTIDからslotへ変換する処理は
`thread.mln` に閉じ込める。

---

## 7. User/kernel syscall ABI

ABI番号は `contracts/myos/syscall.contract.mln` の末尾へ追加し、既存番号を変更しない。

```mln
export enum Syscall {
    EXIT = 1,
    READ,
    WRITE,
    OPEN,
    CLOSE,
    SEEK,
    SBRK,
    YIELD,
    SPAWN,
    OS_CALL,
    WAIT_NOTIFICATION,

    THREAD_SPAWN, // 12
    THREAD_EXIT,  // 13
    THREAD_JOIN,  // 14
    THREAD_SELF,  // 15
    FUTEX_WAIT,   // 16
    FUTEX_WAKE,   // 17
}
```

### 7.1 Shared data contract

新規file `contracts/process/thread.contract.mln` にdata-only contractを置く。

```mln
package process_types;

/** Raw kernel ABI for THREAD_SPAWN. */
export struct ThreadSpawnArgs {
    i32 entry;        // initial user PC
    i32 arg0;         // initial r5
    i32 arg1;         // initial r6
    i32 stack_bytes;  // 0 = default 16 KiB
};

export enum ThreadError {
    NoFreeSlot,
    OutOfMemory,
    InvalidTid(i32),
    JoinSelf,
    AlreadyJoined(i32),
    WouldBlock,
    TimedOut,
    BadAddress(i32),
    ProcessExiting,
    InvalidEntry(i32),
    InvalidStackSize(i32),
    UnexpectedStatus(i32),
}
```

このcontractにはmutable state、scheduler policy、handlerを置かない。
ただしMyLangのorphan ruleに従い、型が所有する意味変換
`From<SyscallFailure> for ThreadError` はこのcontractに置く。

fatal user faultの理由を保持するため、既存の
`contracts/process/control.contract.mln` の `ProcessExitStatus` 末尾には
`IllegalInstruction` をappendする。既存variantはreorderしない。stack guardのpage faultは
既存の `PageFault` を使う。

### 7.2 Register contract

| Syscall | `r5` | `r6` | `r7` | 成功時 `r2` |
|---|---|---|---|---|
| `THREAD_SPAWN` | `ThreadSpawnArgs *` | - | - | new TID |
| `THREAD_EXIT` | exit code | - | - | 戻らない |
| `THREAD_JOIN` | target TID | - | - | target exit code |
| `THREAD_SELF` | - | - | - | current TID |
| `FUTEX_WAIT` | `i32 *addr` | expected | timeout ticks、0=無期限 | 0 |
| `FUTEX_WAKE` | `i32 *addr` | count | - | 起こしたThread数 |

すべての復帰するsyscallで、`r1` は `SyscallStatus`、`r2` は成功値または
エラーpayloadである。`Ok = 0`、失敗statusは正の安定値であり、負数を
エラー表現に使わない。thread/futexで使うstatusは次の通り。

| `r1` status | `r2` payloadから得る `ThreadError` |
|---|---|
| `NoFreeThreadSlot` | `NoFreeSlot` |
| `OutOfMemory` | `OutOfMemory` |
| `InvalidThreadId` | `InvalidTid(payload)` |
| `JoinSelf` | `JoinSelf` |
| `AlreadyJoined` | `AlreadyJoined(payload)` |
| `WouldBlock` | `WouldBlock` |
| `TimedOut` | `TimedOut` |
| `BadAddress` | `BadAddress(payload)` |
| `ProcessExiting` | `ProcessExiting` |
| `InvalidEntry` | `InvalidEntry(payload)` |
| `InvalidStackSize` | `InvalidStackSize(payload)` |

### 7.3 Pointer validation contract

Kernelはuser pointerを直接信頼しない。

- `THREAD_SPAWN` は `ThreadSpawnArgs` 全体をsyscall中にkernel側へcopy-inする。
- `entry` は呼び出しProcessのuser executable mapping内で、実行可能でなければならない。
- `THREAD_JOIN` のexit codeは`r2`で返すため、遅延copy-out用user pointerを保持しない。
- futex addressは4-byte alignedで、呼び出しProcessのread/write可能なuser mappingでなければならない。
- validation失敗はProcessをpanicさせず `BadAddress` / `InvalidEntry` を返す。
- blocking syscallはuser pointerそのものをkernel pointerとして保存しない。`(pid, virtual address)` として保存し、copy-out時にそのProcessのpage tableを使う。

---

## 8. Lifecycle contract

### 8.1 Process spawn

Process生成は次のtransactionとして扱う。

1. Process slotを `Loading` でreserveする。
2. page directoryを作る。
3. executable、data、heap startをmappingする。
4. main user stackとkernel stackを確保する。
5. initial register frameを作る。
6. main TCBの未公開recordを完成させる。
7. 一つのcritical sectionで、Processのthread countとstack-slot bitを初期化し、Processを
   `Alive` にしてmain TCBを `Runnable` としてpublishする。

どこかで失敗した場合は、逆順にTCB、stack mapping、frames、page table、Process slotを回収する。
外部から `Loading` Processや未完成TCBを観測できてはならない。

### 8.2 User thread spawn

`THREAD_SPAWN` は次をatomicなpublish単位として扱う。

1. current Processが `Alive` であることを確認する。
2. argsをcopy-inし、entryとstack sizeを検証する。
3. Processごとのthread上限とglobal TCB slotをreserveする。
4. 未使用user stack slotをreserveする。
5. user pagesとkernel stackを確保する。
6. initial frameを構築する。
7. TIDを割り当てる。
8. 一つのcritical sectionでTCBを `Runnable` としてpublishし、Processの
   `live_threads` と `retained_threads` を増やす。

失敗時はTCBをpublishせず、確保済み資源をすべて逆順に戻す。

### 8.3 Context switch

switch-out:

1. interrupt frame SPをcurrent TCBの `saved_kernel_sp` に保存する。
2. user threadなら `KERNEL_SP` MMIOに退避されたuser SPを `saved_user_sp` に保存する。
3. `Running` なら `Runnable` に戻す。既にBlocked/Exitingなら変更しない。

switch-in:

1. next TCBのownerを確認する。
2. user threadならowner ProcessのPDBRとTCBの `saved_user_sp` をhardwareへ設定する。
3. kernel threadならkernel page directoryとuser SPなしのcontextを使う。
4. next TCBを `Running` にし、`saved_kernel_sp` を返す。

同じPIDのuser thread間でも、最初の実装ではPDBRを書き直してよい。正しさを確認した後に
「PIDが同じならPDBR writeを省略する」最適化を追加する。

### 8.4 Thread exit

`THREAD_EXIT(code)` は呼び出したThreadだけを終了する。

1. current TCBを `Exiting(code)` にする。
2. Processの `live_threads` を減らす。
3. schedulerで別Threadまたはidleへ切り替える。
4. 別stack上で、終了Threadのuser mappingとkernel stackを回収する。
5. TCBを `Zombie(code)` にする。
6. joinerがあればexit codeを書き、joinerをRunnableにする。
7. Processのlive Threadが0なら、§8.6のprocess exitへ進む。

Zombie TCBは小さな終了記録だけを保持し、実行stackは保持しない。
このZombie/join contractはuser threadに適用する。外部からjoinされないkernel threadは、
switch-away後のdeferred cleanupでTCBもfreeしてよい。

### 8.5 Thread join

- joinできるのは同じProcessに属するThreadだけ。
- 自分自身へのjoinは `JoinSelf`。
- 一つのtargetを待てるjoinerは一つだけ。
- targetがliveなら `joiner_tid` を設定し、callerを `Blocked(Join(...))` にする。
- targetが既にZombieなら即座にexit codeをcopy-outしてTCBをreapする。
- join完了時にtarget TCBをfreeし、Processの `retained_threads` を減らす。
- stdlibの `Thread.join()` は成功後にhandle内のTIDを0へする。handleの二重joinはsyscall前に
  `AlreadyJoined` として拒否する。

detachが無いため、joinされないZombie TCBはProcess終了まで残る。ただしstackは残らない。

### 8.6 Process exit

`SYS_EXIT(code)` は呼び出しThreadに関係なくProcess全体を終了する。`main` のreturnもこれを使う。

1. Processを `Exiting(status)` にし、新しいthread spawnとOS operationを拒否する。
2. owner PIDが一致する全TCBをRunnable setとwait queueから外す。
3. notification、join、futex、transport request contextをcancelする。
4. current以外のTCBとstackを回収する。
5. current TCBからidle/kernel contextへ切り替えた後、そのstackも回収する。
6. fd、user mappings、page tablesなどProcess資源を回収する。
7. exit statusだけを残してProcessを `Zombie(status)` にする。

未処理のuser page fault、privilege fault、illegal instructionは一つのThreadだけでなくProcess全体を
終了させる。共有address spaceが壊れている可能性があるためである。

### 8.7 Last-thread rule

`THREAD_EXIT` により最後のlive Threadが終了した場合、そのThreadのcodeをProcess exit codeとして
process exitへ進む。既に `SYS_EXIT` がProcessを `Exiting` にしている場合は、先に設定された
ProcessExitStatusを保持する。

---

## 9. User stack layout

user stack regionは `0x7F00_0000 .. 0x7FFF_FFFF` の16 MiBとし、最大8 Threadに固定slotを割り当てる。

```text
0x8000_0000  ┌──────────────────────┐
             │ slot 0: main thread  │  high = 0x8000_0000
0x7FE0_0000  ├──────────────────────┤
             │ slot 1               │
0x7FC0_0000  ├──────────────────────┤
             │ ...                  │
0x7F00_0000  └──────────────────────┘
```

- slot size: 2 MiB
- default mapped stack: 16 KiB
- initial SP: `slot_high - 0x20`
- mapped stack直下の1 pageはunmapped guard page
- slot内の残りもunmappedのままにする
- `stack_bytes` はpage sizeへ切り上げる
- guardを含めてslotに収まらないsizeは `InvalidStackSize`
- `sys_sbrk` の上限はstack region下端 `0x7F00_0000`

slot 0の初期SPは既存ABIの `0x7FFF_FFE0` と一致する。

kernel stackは各Threadにつき16 KiBを基本値とする。interrupt/syscallがkernel stack上で
filesystemやUI routingまで呼ぶため、user stackとは共有しない。

### 9.1 必須となるMMU cleanup

現在の `mmu.alloc_page()` はalignmentのためheapから8 KiBを確保し、aligned addressだけを返す。
元のallocation addressを失うため、安全にfreeできない。また `unmap_page` も存在しない。

Thread実装より前に、少なくとも次を追加する。

```mln
Result<i32, MmuError> unmap_page(i32 pdbr, i32 vaddr); // mapped frameを返す
Result<_, MmuError> free_frame(i32 frame);
Result<_, MmuError> destroy_user_address_space(i32 pdbr);
```

frame allocatorはaligned frameからallocationを回収できるbookkeepingを持つこと。
`destroy_user_address_space` はProcess固有のuser frameとpage tableだけをfreeし、全Processで共有する
kernel identity-mappingのpage tableはfreeしない。
TCBやProcess slotだけをfreeして物理pageを漏らす実装は、この設計の完了条件を満たさない。

---

## 10. Blocking and wakeup

すべてのblocking operationは同じ順序を使う。

1. syscall中、割り込みによる競合が起きない区間でready conditionを再確認する。
2. conditionが満たされていなければTCBへ `Blocked(reason)` を設定する。
3. wait registrationをpublishする。
4. rescheduleする。
5. producerはregistrationを取り除き、saved `r1 = SyscallStatus` と
   saved `r2 = value/payload` を設定してRunnableにする。

「condition確認」と「Blockedのpublish」の間にproducer通知を失ってはならない。

### 10.1 Notification

既存のsticky notification bitsはTCBへ移す。

- `arm_notification(mask)` はcurrent Threadだけをarmする。
- `WAIT_NOTIFICATION(mask)` はcurrent Threadを `Blocked(Notification(mask))` にする。
- replyの宛先が分かる場合は `notify_tid(tid, mask)` を使う。
- process全体のbroadcastだけが必要なeventに限り `notify_pid(pid, mask)` を使う。

### 10.2 Futex

futex keyは `(pid, user virtual address)` とする。同じvirtual addressでもPIDが異なれば別keyである。

- `FUTEX_WAIT`: kernel内で `*addr == expected` を再確認してからblockする。
- 値が異なれば `WouldBlock` を即座に返す。
- timeout 0は無期限。
- `FUTEX_WAKE`: 同じkeyのwaiterをFIFOで最大count個起こす。
- timeoutとwakeが競合しても、一方だけがregistrationをconsumeする。

### 10.3 Join

joinはtarget TCBの `joiner_tid` がwait registrationになる。target exitとjoin setupは同じ
kernel critical sectionで処理し、終了通知を取りこぼさない。

---

## 11. Atomic instructions and synchronization

user spaceは `di` / `ei` を実行できないため、競合しないlockをsyscallなしで取得するには
atomic read-modify-write命令が必要である。

```text
swp rd, [rs]        tmp = mem[rs]; mem[rs] = rd; rd = tmp
cas rd, rt, [rs]    old = mem[rs]; if old == rd { mem[rs] = rt }; rd = old
```

- 最低限必要なのは `swp`。
- `cas` はencoding可能なら追加する。
- user modeで実行可能。
- alignment、page fault、read/write permissionは通常のload/storeと同じ規則。
- 最初はsingle-coreなので、一命令で完了すればatomicである。
- 将来SMP化する場合、memory orderingとbarrierを別途contract化する。

stdlib API:

```mln
// hosted/thread.mln
export struct Thread { i32 tid; };
export Result<Thread, ThreadError> spawn(i32 entry, i32 arg);
export Result<Thread, ThreadError> spawn_sized(i32 entry, i32 arg, i32 stack_bytes);
export Result<i32, ThreadError> (Thread *self) join();
export i32 self();
export void exit(i32 code);
export void yield();

// sync/atomic.unsafe.mln: T is one word wide (an integer, an enum, a newtype)
export struct Atomic<T> { i32 word; };
export T (borrow Atomic<T> self) load();
export void (borrow Atomic<T> self) store(T value);
export T (borrow Atomic<T> self) swap(T value);
export T (borrow Atomic<T> self) compare_exchange(T expected, T replacement);
export T (borrow Atomic<T> self) fetch_add(i32 delta);
export Result<_, ThreadError> (borrow Atomic<T> self) wait(T expected, i32 timeout_ticks);
export Result<i32, ThreadError> (borrow Atomic<T> self) wake(i32 count);
```

`spawn(entry, arg)` は直接workerをinitial PCにしない。stdlibの `thread_trampoline` をinitial
PCにし、`arg0 = entry`、`arg1 = arg` とする。trampolineは `entry(arg)` の戻り値を
`THREAD_EXIT` へ渡す。これによりworkerがreturnしてもPC 0へ落ちない。

`Thread` handleはTIDを所有するuser-spaceの値であり、TCBそのものではない。初期設計にdetachは
ないため、joinせずhandleを捨ててもkernelのZombie TCBはProcess終了まで残る。

### 11.1 Mutex contract

```mln
export struct Mutex {
    Atomic<MutexState> state;
};
```

`state` の意味:

| Value | Meaning |
|---|---|
| 0 | unlocked |
| 1 | locked、既知のwaiterなし |
| 2 | locked、waiterがいる可能性あり |

- 競合しない `lock()` は `swap` 一回だけで成功し、syscallしない。
- 競合時はstateを2にして `FUTEX_WAIT(&state, 2, 0)` する。
- `unlock()` はstateを0へ戻し、以前の値が2なら一つwakeする。
- wakeはlockの譲渡ではない。起きたThreadは再度atomicに取得を試みる。
- spurious wakeupを許すため、waitは必ずloop内で行う。

### 11.2 Condvar contract

```mln
export struct Condvar {
    Atomic<i32> sequence;
};
```

- waiterはsequenceを読む、Mutexをunlockする、読んだ値でfutex waitする、Mutexをlockし直す。
- notifierはatomic `fetch_add` でsequenceを増やしてからfutex wakeする。
- `notify_one()` は一つ、`notify_all()` はその時点のwaiterすべてを起こす。
- 条件そのものはCondvarに保存しない。利用者は共有状態をMutex下で確認し、必ずloopで待つ。

```mln
export void (borrow Mutex self) init();
export void (borrow Mutex self) lock();
export bool (borrow Mutex self) try_lock();
export void (borrow Mutex self) unlock();

export void (borrow Condvar self) init();
export void (borrow Condvar self) wait(borrow Mutex mutex);
export Result<_, ThreadError> (borrow Condvar self) wait_ticks(borrow Mutex mutex, i32 ticks);
export void (borrow Condvar self) notify_one();
export void (borrow Condvar self) notify_all();
```

---

## 12. Shared-resource safety

Thread APIが存在することと、すべての既存APIがthread-safeであることは同義ではない。

| Subsystem | 初期contract |
|---|---|
| kernel Process/TCB tables | syscall/interrupt critical sectionで直列化 |
| `sys_sbrk` | Process単位で直列化 |
| user allocator | Mutex導入まで複数Threadから同時使用禁止 |
| fd table | kernel側のtable更新を直列化 |
| filesystem global state | worker Threadからの並行利用前にlockが必要 |
| MyAppFramework event queue | consumerは一つのUI Threadに固定 |
| app transport `OS_CALL` | §12.1の制限に従う |

### 12.1 App transportの制限

現在のgatewayはProcessごとに一組の `s0`、`s1`、`out`、`result` staging bufferと
copy-out metadataを持つ。呼び出し側が別々の `result_out` を渡しても、複数Threadから同時に
`OS_CALL` すると途中状態が上書きされる。

したがって初期contractは次のとおり。

- 一つのProcessでapp transportを利用するThreadは一つに固定する。
- event consumerも同じUI Threadに固定する。
- 他Threadはuser-space queue、Mutex、Condvarを介してUI Threadへ依頼する。

将来並行 `OS_CALL` を許す場合は、requestごとのcontextに `(pid, tid, token)`、入力copy、出力、
copy-out先を所有させ、completionは `notify_tid` で要求元だけを起こす。

---

## 13. Failure and cleanup contract

資源獲得の途中失敗を通常の制御経路として扱う。

| Operation | commit point | 失敗時に戻すもの |
|---|---|---|
| Process spawn | ProcessをAliveにする時 | main TCB、両stack、user frames、page tables、fd、PID slot |
| Thread spawn | TCBとProcess countを同時publishする時 | TCB slot、stack slot、user frames、kernel stack |
| Futex wait | Blockedとwait registrationを同時publish | registration、Thread state |
| Join | targetのjoinerを設定しcallerをBlockedにする時 | joiner field、caller state |
| Process exit | Exitingへ遷移する時 | rollbackしない。必ずcleanupを完了してZombieへ進む |

`Drop` を使うcleanup guardは有効だが、ownerを `keep()` した時点を明示する。
current kernel stackだけは通常のscope dropでfreeできないため、switch-away後のdeferred cleanupへ渡す。

---

## 14. Validation

### 14.1 Boundary tests

- Processにuser/kernel SP、kernel stack、task/thread IDが残っていない。
- schedulerにPID、SP、wait reasonのparallel ownershipが残っていない。
- current PID/TIDがcurrent TCBから導出される。
- Process stateにReady/Running/Blockedがない。
- notification待機後もProcess stateとThread stateが矛盾しない。

### 14.2 Lifecycle tests

- Process spawn失敗の各段階で全資源が元のcountへ戻る。
- Thread spawn失敗の各段階でTCB、stack slot、page、heap blockが漏れない。
- 二つのThreadが同じPID/PDBRで交互に実行され、別々のSPを保持する。
- `THREAD_EXIT` はcallerだけを終了する。
- 最後の `THREAD_EXIT` はProcessをZombieにする。
- `SYS_EXIT` はRunnable/Blocked/Zombieを含む全TCBを回収する。
- unhandled user faultはProcess全体を終了させる。
- join前に終了した場合と、終了前にjoinした場合の両方で同じexit codeを得る。
- self join、別ProcessのTID、二重joinを拒否する。
- TCB slot再利用後も古いTIDが新しいThreadを指さない。

### 14.3 Blocking tests

- notificationのcheck-to-block raceでwakeを失わない。
- futex値が異なる場合はblockせず `WouldBlock`。
- futex wake countとFIFO順が正しい。
- timeoutとwakeの競合でThreadを二重にRunnableへ入れない。
- Process exitがjoin/futex/notification waiterを残さない。

### 14.4 Protection tests

- user stack guard pageへのaccessがpage faultになる。
- 他slotのstackへ通常のstack growthでは到達しない。
- invalid entry、kernel address、unaligned futexを拒否する。
- read-only mappingへのatomic instructionがfaultになる。

---

## 15. Implementation order

境界変更と新機能を同じ差分に混ぜない。

| Phase | 内容 | 完了条件 |
|---|---|---|
| 0 | MMUのunmap、frame free、address-space destroy | spawn/exit反復でmemory使用量が増えない |
| 1 | TCB tableを導入し、既存の1 Process = 1 user Threadを移植 | 既存QAがABI変更なしで通る |
| 2 | ProcessからSP/task ID/実行状態/current PIDを除去 | §14.1が通る |
| 3 | exit、deferred stack cleanup、process-wide cleanupを確立 | spawn/exit/faultのleak testが通る |
| 4 | `THREAD_SPAWN` / `EXIT` / `SELF` | 二つのThreadが独立SPで実行できる |
| 5 | unified WaitReason、`THREAD_JOIN` | lifecycle testが通る |
| 6 | `swp`、可能なら`cas`、futex | ISA/futex testが通る |
| 7 | stdlib `Thread` / atomic / Mutex / Condvar | counterとproducer-consumer testが通る |
| 8 | allocatorと対象subsystemのlocking | 許可したAPIを複数Threadから安全に呼べる |
| 9 | request contextを追加する場合のみparallel `OS_CALL` | tid-targeted completion testが通る |

Phase 1では新しいuser-visible thread syscallをまだ追加しない。内部境界のregressionを先に見つける。

---

## 16. Decisions and remaining questions

### Draft 2で採用する方針

1. カーネル内部のscheduler taskとThreadを別オブジェクトにしない。
2. 型名は `Thread` / TCBとし、`Task` は残さない。
3. Processは共有資源、Threadは実行状態を所有する。
4. ProcessにReady/Running/Blockedを置かない。
5. TIDとscheduler slotを分離する。
6. kernel threadとuser threadを同じTCB tableで扱う。
7. main Threadをkernel内で特別なlifecycle objectにしない。
8. fatal user faultはProcess全体を終了する。
9. 初期のapp transportは一Process一利用Threadに制限する。
10. MMU cleanupをuser Thread公開の前提とする。

### 実装前に確認すること

1. `cas` を現行instruction encodingで表現できるか。
2. syscall/interrupt handlerがどの区間でinterruptを再有効化するか。
3. TCB内のpayload enumを現在のMyLang ABIで無理なく格納できるか。
4. frame allocatorをheap alignment bookkeepingで直すか、専用page allocatorへ分離するか。
5. user function pointer型が入るまでstdlib `spawn` のentryを `i32` とするか。
