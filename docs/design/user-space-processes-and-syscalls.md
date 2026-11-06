# Design Document: User-Space Processes & Syscall Subsystem

> **Boundary note (2026-10-08):** この文書のPCBとprocess stateは、初期の
> 「1 process = 1 schedulable context」を説明している。複数Thread導入後の
> Process / Thread / Scheduler境界、TCB、状態遷移、stack所有権については
> `docs/design/threads.md` を優先する。

## 1. Overview & Objectives

With the Virtual Memory Management Unit (MMU), 2-level paging, and CPU privilege rings (`SR_USER`) in place, `MyComputer` is ready to transition from single-privilege flat execution to **protected user-space multiprocessing**.

This document specifies the design for:
1. **Isolated Virtual Address Space Layout** per process.
2. **Process Control Block (PCB)** and state lifecycle.
3. **Executable Loading (`.mbin`)** from the MyFileSystem (MFS) disk into user memory.
4. **Syscall ABI & Dispatch Table** for safe kernel-user transitions.
5. **Context Switching & User Mode Entry (`iret`)**.

```mermaid
graph TD
    subgraph "User Space (SR[5] = 1, PTE_USER = 1)"
        UA["User Application (.mbin)"] --> |"syscall (r1=sys_nr)"| TRAP["CPU Syscall Trap (Opcode 0x3E)"]
        USTACK["User Stack (0x7FFF_FFFF)"]
        UHEAP["User Heap (0x4100_0000)"]
        UCODE["User Code & Data (0x4000_0000)"]
    end

    subgraph "Kernel Space (SR[5] = 0, Privileged)"
        TRAP --> |"Stack Swap (KERNEL_SP) & Vector"| DISP["Syscall Dispatcher"]
        DISP --> SYS_FS["File Syscalls (read/write/open/close)"]
        DISP --> SYS_MEM["Memory Syscalls (sbrk/mmap)"]
        DISP --> SYS_PROC["Process Syscalls (spawn/exit/yield)"]
        DISP --> |"iret (Restores SR_USER & User SP)"| UA
        
        PCB["Process Control Block (PCB Table)"]
        SCHED["Scheduler"]
        MMU_MGR["Kernel MMU Page Manager"]
    end
```

---

## 2. Virtual Address Space Layout (Per Process)

Each user process is assigned its own **Page Directory (PDBR)**. All user processes share an identical identity mapping for the kernel in lower memory, but maintain isolated, non-overlapping user code, heap, and stack pages.

| Virtual Address Range | Size | Region | Page Attributes | Description |
|---|---|---|---|---|
| `0x0000_0000 .. 0x00FF_FFFF` | 16 MB | **Kernel Image & Heap** | `V \| W \| X` (`U=0`) | Identity-mapped kernel code, heap, data. Inaccessible to User Mode. |
| `0x1F00_0000 .. 0x1FFF_FFFF` | 16 MB | **Kernel Stack** | `V \| W` (`U=0`) | Kernel interrupt/trap stack space. Inaccessible to User Mode. |
| `0x2400_0000 .. 0x2400_1FFF` | 8 KB | **Hardware MMIO** | `V \| W` (`U=0`) | UART, SSD, MMU, DMA2D registers. Trapped if accessed in User Mode. |
| `0x3000_0000 .. 0x302F_FFFF` | 3 MB | **VRAM Framebuffer** | `V \| W` (`U=0`) | Display buffer (User draws via Syscall or shared mapping). |
| `0x4000_0000 .. 0x40FF_FFFF` | 16 MB | **User Code & Static Data** | text `V \| X \| U`, data `V \| W \| U` | Loaded from `.mbin` executable on MFS (in practice linked at `0x20000`: MyLang materializes addresses with a 21-bit immediate, so an image must sit below 2 MB; its pages replace the kernel identity mapping of that range in the process's own directory). Text is read-only; globals, strings and constant pools are in the data segment (the compiler's `.data`). |
| `0x4100_0000 .. 0x4FFF_FFFF` | 240 MB | **User Dynamic Heap** | `V \| W \| U` | User dynamic memory, grown upward via `sys_sbrk()`. |
| `0x7F00_0000 .. 0x7FFF_FFFF` | 16 MB | **User Stack** | `V \| W \| U` | Process stack: 4 pages (`0x7FFF_C000..`), starting at `0x7FFF_FFE0` and growing downward. |

---

## 3. Process Control Block (PCB)

The kernel manages up to **16 concurrent processes** via a static table `g_proc_table[16]`.

```c
typedef struct {
    i32 pid;              // Process ID (1..16, 0 = Unused / Kernel idle)
    i32 state;            // PROC_UNUSED, PROC_READY, PROC_RUNNING, PROC_BLOCKED, PROC_ZOMBIE
    i32 page_directory;   // Physical address of the root Page Directory (PDBR)
    i32 kernel_stack_top; // Physical top of this process's dedicated kernel stack (for KERNEL_SP)
    i32 user_entry;       // Virtual entry point, from the MBIN header
    i32 user_sp;          // Saved User Stack Pointer
    i32 heap_break;       // Current User Heap break pointer (starts at 0x41000000)
    i32 exit_code;        // Return code when state == PROC_ZOMBIE
    i32 fd_table[8];      // Per-process virtual FD table mapping to MFS descriptors
    char name[16];        // Process name (e.g. "shell.mbin", "editor.mbin")
} Process;
```

### Process States
* **`PROC_UNUSED` (0):** Free slot in `g_proc_table`.
* **`PROC_READY` (1):** Ready to be scheduled.
* **`PROC_RUNNING` (2):** Currently executing on the CPU.
* **`PROC_BLOCKED` (3):** Waiting on I/O, sleep timer, or child process.
* **`PROC_ZOMBIE` (4):** Terminated, waiting for parent to read `exit_code` and clean up.

---

## 4. Syscall ABI & Calling Convention

Syscalls leverage the standard MyLang register convention.

### Register Assignments
* **`r1` : Syscall Number** (Input) / **`SyscallStatus`** (Output)
* **`r2` : Success Value or Error Payload** (Output)
* **`r5` : Argument 1**
* **`r6` : Argument 2**
* **`r7` : Argument 3**
* `SyscallStatus::Ok` is zero. Failures are positive stable enum values, so a
  valid negative application value cannot be mistaken for an error. On success
  `r2` contains the byte count, PID, TID, address, exit code, or other scalar
  result. On failure it contains status-specific context such as the rejected
  TID or address.
* MyLang assembly stubs copy `r2` through an explicit final out parameter and
  return the `r1` status. Higher-level stdlib adapters turn the pair into
  `Result<T, E>`; for example thread adapters use
  `From<SyscallFailure> for ThreadError`.
* `SYS_OS_CALL` uses the same register envelope only for routing. Typed service
  results such as `Result<T, FsError>` remain copied through the service's
  caller-provided result address.

### Syscall Table Definition

| Number (`r1`) | Name | Signature | Description |
|---|---|---|---|
| `1` | `SYS_EXIT` | `void sys_exit(i32 code)` | Terminates current process with return code. |
| `2` | `SYS_READ` | `SyscallStatus sys_read(i32 fd, char *buf, i32 count, i32 *value_out)` | Reads bytes; writes the byte count to `value_out`. |
| `3` | `SYS_WRITE` | `SyscallStatus sys_write(i32 fd, char *buf, i32 count, i32 *value_out)` | Writes bytes; writes the byte count to `value_out`. |
| `4` | `SYS_OPEN` | `i32 sys_open(char *path, i32 flags)` | Opens a file from MFS and returns process `fd`. |
| `5` | `SYS_CLOSE` | `i32 sys_close(i32 fd)` | Closes an open process descriptor. |
| `6` | `SYS_SEEK` | `i32 sys_seek(i32 fd, i32 offset, i32 whence)` | Moves file cursor position. |
| `7` | `SYS_SBRK` | `SyscallStatus sys_sbrk(i32 increment, i32 *value_out)` | Extends the heap and writes the previous break to `value_out`. |
| `8` | `SYS_YIELD` | `void sys_yield()` | Voluntarily yields remaining time slice to scheduler. |
| `9` | `SYS_SPAWN` | `SyscallStatus sys_spawn(char *path, i32 *value_out)` | Loads a `.mbin` binary and writes its PID to `value_out`. |
| `10` | `SYS_OS_CALL` | `SyscallStatus os_call(i32 service, i32 args, i32 *value_out)` | Routes a MyOS service and writes its scalar routing value to `value_out`; domain results normally use the service args record. |
| `11` | `SYS_WAIT_NOTIFICATION` | `SyscallStatus sys_wait_notification(i32 mask, i32 *value_out)` | Consumes or waits for notification bits and writes the delivered mask to `value_out`. |
| `12..17` | thread/futex calls | See `docs/design/threads.md` | Thread lifecycle and process-local futex operations use the same status/value envelope. |

`SYS_SPAWN(path)` / the `PROC_SPAWN` service resolve a bare name through the
search path `/bin`, then `/apps` (`console.open_executable`); a path with a
`/` is taken as is.

`SYS_YIELD` puts the calling task to sleep until the next timer tick
(`scheduler.yield_until_tick`) rather than merely rescheduling it. The
application transport uses `SYS_WAIT_NOTIFICATION` for request, reply, and
event readiness instead of polling with `SYS_YIELD`. `SYS_OPEN` / `SYS_CLOSE` /
`SYS_SEEK` are numbers only; files are reached through `SYS_OS_CALL` (`FS_*`
services).

### Typed OS_CALL records

An `OS_CALL` argument record names its own service. The contract declares the
record and, directly below it, the service it travels under:

```mylang
export struct FsOpenArgs { char *path; i32 path_length; Result<i32, FsError> *result_out; };
export impl OsCall for FsOpenArgs = OsService::FS_OPEN;
```

The record's `result_out` field is the reply type, written out concretely
rather than through a type parameter. A client sends a record with
`send<FsOpenArgs>(&args)`, which takes the service number from the record's
type. A provider reads it with `accept<FsOpenArgs>(service, args, &request)`,
which copies the record only when `service` is the one bound to it, and
writes the result with `reply<Result<i32, FsError>>(request.result_out, &r)`.
Sending a record under another service number, or replying with another
result type, is a compile error on either side.

Type arguments stay explicit at every call, so a reader sees the record and
reply types without following the trait. The helpers are module-local
because exported generic functions cannot yet be package-qualified. The
filesystem services use this binding; process, IPC, and log services still
pass their records as raw addresses.

---

## 5. Process Lifecycle & Execution Flow

### 1. Spawning a Process (`sys_spawn(path)`)
1. **Find File:** Kernel calls `fs.open(path)` to verify the executable exists on SSD.
2. **Allocate PCB:** Finds a free slot in `g_proc_table`.
3. **Create Page Directory:** 
   * `pd = mmu.create_page_directory();`
   * `mmu.setup_identity_kernel_mapping(pd);` (kernel is protected with `U=0`).
4. **Load Code Pages:**
   * Reads file size and refuses a file without an MBIN header (`docs/design/mbin-executable-header.md`).
   * Allocates physical frames `mmu.alloc_page()` for every 4 KB of code/data.
   * Reads executable contents into allocated physical frames.
   * Maps text at the page of the header's `entry_point` with `PTE_VALID | PTE_EXEC | PTE_USER`, and data and BSS after it with `PTE_VALID | PTE_WRITABLE | PTE_USER`.
5. **Allocate Stack Pages (`0x7FFF0000 .. 0x7FFFFFFF`):**
   * Allocates physical stack frame.
   * Maps virtual address `0x7FFF0000` with `PTE_VALID | PTE_WRITABLE | PTE_USER`.
6. **Initialize Process State:**
   * `proc.user_sp = 0x7FFFFFE0;`
   * `proc.user_entry = entry_point;`
   * `proc.heap_break = 0x41000000;`
   * `proc.state = PROC_READY;`

### 2. Entering User Mode (`proc_start / proc_switch`)
To jump into user space safely:
1. Switch `MMU_PDBR` register to `proc.page_directory`.
2. Set `KERNEL_SP` MMIO register to `proc.kernel_stack_top`.
3. Set CPU registers:
   * Set user stack pointer `sp = proc.user_sp`.
   * Push fake return `PC` (the entry point) and `SR` (`SR_USER | SR_IE = 0x21`) onto the kernel stack.
4. Execute `iret`.
5. The CPU automatically transitions to User Mode (`SR[5] = 1`), loads the entry point into `PC`, and executes the user binary.

### 3. Trapping on Syscall & Returning
1. User code executes `syscall`.
2. Hardware swaps `sp` with `KERNEL_SP`, pushes user `PC` and `SR`, clears `SR[5]` (Kernel mode), and vectors to interrupt handler.
3. Handler saves user registers (`r1..r7`).
4. `syscall_dispatcher()` inspects `r1`, executes the service, then writes status to the saved `r1` slot and value/payload to saved `r2`.
5. Handler restores user registers (`r1..r7`).
6. `iret` restores user stack and user mode `PC`.

---

## 6. Implementation Plan & Milestones

| Phase | Milestone | Deliverables |
|---|---|---|
| **Phase 1** | **Syscall Dispatcher & Kernel Stubs** | Implement `syscall.mln` with dispatch table (`sys_read`, `sys_write`, `sys_exit`, `sys_yield`), argument decoding, and return handling. |
| **Phase 2** | **Executable Loader (`.mbin`)** | Implement `loader.mln` to load `.mbin` files from MFS into dedicated user page tables. |
| **Phase 3** | **User Process Spawner & `iret` Trampoline** | Implement assembly stub `user_enter.masm` to set `KERNEL_SP`, configure `SR_USER`, and jump to user space. |
| **Phase 4** | **User Space Standard Library (`libmy.mln`)** | Provide lightweight user-space wrapper functions (`print`, `println`, `open`, `read`, `write`, `exit`). |
| **Phase 5** | **Integration Test Suite** | Test spawning an isolated user application that issues syscalls, prints to stdout, reads file data, and exits cleanly. |

---

## 7. Security & Isolation Invariants

1. **Kernel Memory Inaccessibility:**
   * All lower 16 MB kernel RAM, stack, and MMIO pages must have `PTE_USER == 0`. Any read/write/fetch from User Mode triggers immediate `IRQ_CAUSE_PRIVILEGE_VIOLATION`.
2. **Hardware Direct Access Blocked:**
   * User mode code cannot access MMIO (`0x24000000`) or SSD registers directly; all device I/O must go through verified syscalls.
3. **Privileged Instructions Trapped:**
   * User mode execution of `halt`, `iret`, `in`, `out`, `ei`, `di`, `wfi` immediately traps to the kernel.
4. **Pointer Validation:**
   * The kernel syscall handlers must validate all user buffer pointers (`buf < 0x40000000` is rejected) to prevent user programs from tricking the kernel into overwriting kernel memory.
