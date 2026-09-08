# Errors and Exceptions across System Layers

This document provides a comprehensive reference for how errors, faults, and exceptions are detected, propagated, and handled across all layers of `MyComputer`: Hardware & Emulator, Firmware (Bootloader), and Kernel & OS Subsystems.

---

## 1. Architectural Overview

```
+-------------------------------------------------------------------------+
| Layer 3: Kernel & OS Subsystems (MyKernel / MyOS)                       |
|   - Heap OOM Panics (heap.panic -> halt_cpu)                            |
|   - Task Slot & Stack Exhaustion (spawn_task returns -1)                |
|   - Filesystem Errors (disk missing, table full, block alloc failure)   |
|   - Driver Buffer Status (Serial RX empty, Mouse FIFO drain)            |
+-------------------------------------------------------------------------+
                                    ▲
                                    │ Memory / Registers / IRQs
                                    ▼
+-------------------------------------------------------------------------+
| Layer 2: Firmware / Bootloader (MyFirmware)                             |
|   - SSD Read & Status Error Handling                                    |
|   - Kernel Payload Loading & Verification                               |
+-------------------------------------------------------------------------+
                                    ▲
                                    │ MMIO / Memory Bus / CPU State
                                    ▼
+-------------------------------------------------------------------------+
| Layer 1: Hardware & Emulator (MyEmulator / Verilog CPU)                 |
|   - CPU Status Register (SR) Flags (Z, N, C, V, IE)                     |
|   - Stack Overflow / Underflow Checks                                   |
|   - Instruction Decode & Opcode Faults                                  |
|   - MMIO Device Status Registers & IRQ Causes (Timer, Mouse, RX, SSD)   |
|   - Starvation & Unmapped Memory Handling                               |
+-------------------------------------------------------------------------+
                                    ▲
                                    │ (Planned - EMU-003)
                                    ▼
+-------------------------------------------------------------------------+
| Layer 1.5 (Future): MMU & Protected Mode Traps                          |
|   - Synchronous Exceptions: Page Fault, Privilege Violation, Syscall   |
+-------------------------------------------------------------------------+
```

---

## 2. Layer 1: Hardware & Emulator Layer

Located in `runtime/MyEmulator/src/machine/` and `hardware/verilator/`.

### 2.1 CPU Flags & ALU Conditions
The CPU does not trigger hardware traps on arithmetic anomalies (such as overflow or carry); instead, it records the condition in the 8-bit **Status Register (SR)**:

| Bit | Flag | Name | Set Condition |
| :--- | :--- | :--- | :--- |
| Bit 0 | `SR_IE` | Interrupt Enable | Set by `ei` (Opcode `0x1E`), cleared by `di` (`0x1F`) or IRQ vectoring |
| Bit 1 | `SR_CARRY` | Carry / Borrow | Set when unsigned `lhs < rhs` during `sub` or arithmetic carry |
| Bit 2 | `SR_ZERO` | Zero | Set when ALU result or loaded value equals zero |
| Bit 3 | `SR_SIGN` | Negative / Sign | Set when the MSB of the result is 1 (`result < 0` in two's complement) |
| Bit 4 | `SR_OVERFLOW` | Overflow | Set when signed arithmetic overflows (`(lhs < 0 != rhs < 0) && (lhs < 0 != res < 0)`) |

Software checks these conditions using conditional branches (`jz`, `jnz`, `jg`, `jl`, `ja`, `jb`).

### 2.2 Stack Bounds & Faults
The CPU stack grows downward starting from `0x7FFFFFFF` (RAM upper limit):
* **Stack Overflow:** Occurs if `SP == RAM_START (0x00000000)` on `push`. In `MyEmulator`, this returns `Err("Stack overflow")` and halts the emulator.
* **Stack Underflow:** Occurs if `SP > RAM_END_EXCLUSIVE (0x20000000)` on `pop`. In `MyEmulator`, this returns `Err("Stack underflow at address...")` and halts execution.

### 2.3 Instruction Decode & Register Faults
* **Unknown Opcode:** If the 6-bit opcode field is unmapped (e.g. outside `0x01..=0x20` and `0x3F`), `execute_instruction()` returns `Err("Unknown opcode: 0xXX")`.
* **Invalid Register Index:** Register indices $> 12$ (valid: R0–R7, PC=8, SP=9, BP=10, SR=11, LR=12) return `Err("Invalid register index")`.

### 2.4 Unmapped Memory & Bus Access
* **Read from Unmapped Space:** Reads outside RAM (`0x00000000-0x1FFFFFFF`), ROM (`0x20000000-0x23FFFFFF`), VRAM (`0x30000000-0x30FFFFFF`), or I/O (`0x24000000-0x240000FF`) return `0xFFFF_FFFF` for words and `0xFF` for bytes.
* **Write to Read-Only / Unmapped Space:** Writes outside valid ranges or to read-only spaces are silently ignored or recorded in fallback debug structures.

### 2.5 Hardware Devices & MMIO Status
Each MMIO peripheral signals status and errors through dedicated registers:

| Device | Register | Error / State Representation | Handling Mechanism |
| :--- | :--- | :--- | :--- |
| **SSD Block Device** | `SSD_STATUS_ADDR` (`0x2400001C`) | `0` = Idle, `1` = Busy, `2` = Done, `0xFF` = Error | Controller sets `SSD_STATUS_ERROR` on bad block, invalid command, or host disk I/O failure. Raises `IRQ_CAUSE_SSD` on completion. |
| **Serial UART** | `SERIAL_LSR_ADDR` (`0x24000005`) | Bit 0 (`DR`) = Data Ready, Bit 5 (`THRE`) = Transmit Ready | Reading `SERIAL_RX_ADDR` when empty returns `0`. |
| **Mouse Controller** | `MOUSE_EVT_STATUS` (`0x2400004C`) | Event FIFO Depth (0–64) | When FIFO exceeds 64 events, oldest events are dropped (`dropped` flag set) so fresh state is preserved. |
| **Interrupt Controller** | `IRQ_VECTOR_ADDR` (`0x24000080`) | Handler Vector Address | If vector is not a valid RAM address, interrupt dispatch is suppressed to prevent branching into unmapped memory. |
| **Timer / IRQ Monitor** | Emulator internal | Starvation Warning | If the timer IRQ handler execution duration exceeds the tick interval for 16 consecutive times, a starvation warning is logged. |

---

## 3. Layer 2: Firmware / Bootloader Layer

Located in `system/MyFirmware/src/`.

### 3.1 SSD Read Errors during Kernel Loading
In `fw_main()` (`system/MyFirmware/src/fw/main.mln`):
1. The firmware issues block read commands to copy 10 blocks (640 KB) from SSD block `16000` to RAM address `0x00100000`.
2. It busy-polls `SSD_STATUS_ADDR` while the device is `SSD_STATUS_BUSY (1)`.
3. If `*p_status != SSD_STATUS_DONE (2)` (e.g. `SSD_STATUS_ERROR`), the firmware emits:
   ```
   firmware: SSD read error!
   ```
   and returns from `fw_main()`, which reaches `stub.masm`'s `halt` instruction.

### 3.2 Boot Size Boundaries
The firmware currently assumes the kernel fits within 10 blocks (640 KB). If the kernel grows beyond this size without updating firmware parameters, truncated binary loading occurs.

---

## 4. Layer 3: Kernel & OS Subsystems Layer

Located in `system/MyKernel/src/` and `system/MyOS/src/`.

### 4.1 Memory Management & Heap Allocator (`heap.mln`)
* **Out of Memory Panic:** If `heap.alloc(size)` cannot find a free block large enough (first-fit search fails), it invokes the shared debug utility:
  ```c
  debug.panic("out of memory");
  ```
  This immediately halts the CPU after emitting the diagnostic message over the serial console.
* **Invalid Allocation Size:** If `size <= 0`, `heap.alloc()` returns `0` (NULL).
* **Null Pointer Deallocation:** Calling `heap.free(0)` safely returns without corrupting the free list.

### 4.2 Task Scheduler (`scheduler.mln`)
* **Task Slot Exhaustion:** The scheduler supports up to `MAX_TASKS = 256`. If all slots are occupied, `spawn_task(func_ptr)` returns `-1` and logs:
  ```
  Error: Task slots exhausted! (MAX_TASKS reached)
  ```
* **Stack Memory Exhaustion:** If `heap.alloc(1024)` fails when creating a task stack, `spawn_task` logs:
  ```
  Error: Out of memory for task stack!
  ```
  and returns `-1`.
* **Fatal Idle Stack Failure:** If `heap.alloc(512)` fails during `scheduler.init()`, the kernel logs `"scheduler: FATAL: no memory for the idle stack"`.
* **Idle Execution & Starvation Avoidance:** When no tasks are runnable (`TASK_RUNNABLE`), the scheduler switches to a dedicated idle context running `wfi_cpu()` to prevent CPU starvation and burning host cycles.

### 4.3 MyFileSystem / MFS (`fs.mln`)
* **Missing or Unformatted SSD:** `fs.init()` verifies the superblock magic `0x4D465331 ('MFS1')`. If the SSD read fails or disk is absent, it logs:
  ```
  fs: no disk (SSD disabled)
  ```
  and sets `g_enabled = 0`, preventing further file system operations.
* **File Creation Failures (`fs.create`):** Returns `-1` under any of these error conditions:
  - File already exists (`find_entry_by_name != -1`).
  - Directory table full (`MAX_FILES = 2048` reached).
  - Disk full (`alloc_block()` returns `0` when bitmap has no free data blocks).
* **File Descriptor Faults:** Operations on invalid file descriptors (`fd < 0`, `fd >= FD_MAX (8)`, or `g_fd_table[fd].entry_idx == -1`) return `0` for read/write or `-1` for open/create.
* **Partial Writes on Disk Exhaustion:** If the disk becomes full while writing a file, `fs.write()` links up to the last allocated block, updates `file_size` with the actual bytes written, and returns the written count.

---

## 5. Planned Layer: MMU, Traps & Syscalls (EMU-003)

Documented in `docs/design/virtual-memory-mmu.md` and tracked in `issues/tickets/EMU-003_virtual-memory-mmu.md`.

| Planned Mechanism | Exception Type | IRQ Cause Bit | Trigger Condition | Handling Procedure |
| :--- | :--- | :--- | :--- | :--- |
| **Page Fault** | Synchronous Exception | Bit 5 | Accessing page with `V=0` (not present) or permission violation (`W=0`, `X=0`, or `U=0` from User Mode) | Hardware logs virtual address to `MMU_FAULT_ADDR` (`0x24000108`) and fault reason to `MMU_FAULT_STATUS` (`0x2400010C`). CPU transitions to Kernel Mode (`SR[5] = 0`), swaps stack to `KERNEL_SP`, and vectors to IRQ handler. |
| **Privilege Violation** | Synchronous Exception | Bit 6 | Executing privileged instructions (`halt`, `iret`) or accessing `0x24000000` I/O range while `SR[5] == 1` (User Mode) | CPU traps to Kernel Mode, switches SP to `KERNEL_SP`, and enters Kernel trap dispatcher. |
| **System Call (`syscall`)** | Software Trap | Bit 4 | Executing `syscall` instruction (Opcode `0x3E`) in User Mode | CPU switches to Kernel Mode (`SR[5] = 0`), swaps `SP` to `KERNEL_SP`, pushes `PC`/`SR`, and jumps to the kernel vector `0x24000080`. Kernel inspects arguments in `R1`, `R2`, etc. |

---

## 6. Error & Exception Handling Summary Matrix

| Layer | Component | Fault / Error Condition | Severity | Propagation / Recovery |
| :--- | :--- | :--- | :--- | :--- |
| **Hardware** | ALU / CPU | Zero, Sign, Carry, Overflow | Info | Updated in Status Register (`SR`) flags |
| **Hardware** | CPU Stack | Stack Overflow / Underflow | Fatal | Emulator returns `Err` and aborts |
| **Hardware** | Decoder | Unknown Opcode / Invalid Reg | Fatal | Emulator returns `Err` and aborts |
| **Hardware** | Peripherals | SSD error, Mouse FIFO drop | Warning | Latched in status registers / IRQ cause bits |
| **Firmware** | Bootloader | SSD read failure | Fatal | Logs error message and executes CPU `halt` |
| **Kernel** | Memory | Heap allocation failure (OOM) | Fatal | `heap.panic("out of memory")` -> `halt_cpu()` |
| **Kernel** | Scheduler | Task slot or stack exhaustion | Recoverable | Returns `-1` to caller with debug error log |
| **Kernel / OS** | Filesystem | Disk full, duplicate file, bad FD | Recoverable | Returns `-1` or `0` bytes transferred |
| **Future** | MMU / Ring 3 | Page fault, Privilege violation | Trapped | Dispatched via IRQ handler to OS kernel |
