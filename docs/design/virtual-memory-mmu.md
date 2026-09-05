# Design Doc: Virtual Memory & Paging (EMU-003)

## 1. Introduction
To support isolated, true multi-processing, the `MyComputer` architecture needs to evolve from a flat, unprotected physical memory model to a modern protected mode architecture. 

This design document outlines the addition of:
1. **Privilege Rings** (Kernel Mode vs. User Mode)
2. **Virtual Memory Management Unit (MMU)**
3. **Paging System** (Two-level page tables)
4. **Syscalls and Exceptions**

---

## 2. Privilege Modes

We will introduce two execution modes to the CPU, governed by a new bit in the **Status Register (SR)**.

### Status Register (SR) Updates
* **Bit 5 (Mode):** `0` = Kernel Mode (Privileged), `1` = User Mode (Unprivileged)
* *Boot state:* The CPU boots in Kernel Mode (`SR = 0`).

### Mode Restrictions
When `SR[5] == 1` (User Mode):
* The `halt` instruction is trapped (throws a Privilege Violation exception).
* The `iret` instruction is trapped.
* (Optional) The `in` and `out` I/O instructions are trapped.
* Memory access is strictly governed by the `User` bit in the MMU Page Tables.

---

## 3. The Paging System (MMU)

We will adopt a classic 32-bit, two-level paging scheme (similar to x86 non-PAE or RISC-V Sv32) to map 32-bit Virtual Addresses to 32-bit Physical Addresses.

* **Page Size:** 4 KB (4096 bytes)
* **Virtual Address Splitting:**
  * `[31:22]` (10 bits): Page Directory Index
  * `[21:12]` (10 bits): Page Table Index
  * `[11: 0]` (12 bits): Byte Offset

### Page Table Entry (PTE) Format
Each entry in a Page Directory or Page Table is 32 bits (4 bytes):
* `[31:12]` : **Physical Frame Number (PFN)**
* `[11: 6]` : *Reserved / Unused*
* `[5]` : **D (Dirty)** - Set by CPU when the page is written to.
* `[4]` : **A (Accessed)** - Set by CPU when the page is read/written/fetched.
* `[3]` : **U (User)** - If `1`, accessible in User Mode. If `0`, Kernel only.
* `[2]` : **X (Executable)** - If `1`, instruction fetches are allowed.
* `[1]` : **W (Writable)** - If `1`, store instructions are allowed.
* `[0]` : **V (Valid)** - If `1`, the PTE is valid. If `0`, throws a Page Fault.

---

## 4. MMU Control Registers

Rather than adding completely new CPU instructions to manage the MMU, we will leverage `MyComputer`'s heavily memory-mapped nature. We will allocate a new block in the reserved `0x24000100` I/O range.

| Address | Name | Direction | Description |
|---|---|---|---|
| `0x24000100` | `MMU_CTRL` | R/W | Bit 0: Enable Paging (1=Enabled) |
| `0x24000104` | `MMU_PDBR` | R/W | Physical Address of the root Page Directory |
| `0x24000108` | `MMU_FAULT_ADDR` | R | The virtual address that caused the last Page Fault |
| `0x2400010C` | `MMU_FAULT_STATUS` | R | 0=Read, 1=Write, 2=Execute, 3=Privilege Violation |

*Note: Accessing these registers from User Mode memory space will naturally be prevented by the Kernel simply NOT mapping the `0x24000000` I/O block with the `U` bit set.*

---

## 5. Exceptions, Traps, and Syscalls

With processes running in User Mode, they need a safe way to transition back to Kernel Mode for system services (Syscalls) or when a fault occurs (Page Fault).

### New Interrupt Causes
We will extend the existing IRQ Cause register (`0x24000084`) with new bits for synchronous exceptions:
* **Bit 4:** Syscall Trap
* **Bit 5:** Page Fault
* **Bit 6:** Privilege Violation (e.g., executing `halt` in User Mode)

### New Instruction: `syscall`
* **Opcode:** `0x3e` (Pattern: `—`)
* **Behavior:** 
  1. Sets IRQ Cause Bit 4.
  2. Switches `SR[5]` to `0` (Kernel Mode).
  3. Vectors to the standard interrupt handler at `0x24000080`.
  4. The syscall number and arguments can be passed in `r1`, `r2`, etc.

### Context Saving on Traps
Currently, the CPU only pushes the PC and SR implicitly or relies on the Trampoline to save state.
Because a User Mode process might have an invalid Stack Pointer (`sp`), the CPU cannot safely push the `PC` and `SR` onto the User's stack when an interrupt/trap occurs. 

**Solution:** We will add a `KERNEL_SP` MMIO register at `0x24000110`. 
When a trap/interrupt occurs while `SR[5] == 1` (User Mode), the CPU will automatically swap the stack pointer (`sp`) with `KERNEL_SP` before pushing the `PC` and `SR`.

---

## 6. Implementation Steps

### Phase 1: Emulator & CPU Support
1. Implement the `syscall` instruction.
2. Add the User/Kernel mode bit to `SR`.
3. Update the interrupt logic to use `KERNEL_SP` when trapping from User Mode.

### Phase 2: MMU Implementation
1. Add the `MMU_CTRL`, `MMU_PDBR`, and Fault MMIO registers.
2. Modify the CPU's memory read/write/fetch pipeline in `MyEmulator` to pass through a page table walker when `MMU_CTRL[0] == 1`.
3. Implement TLB (Translation Lookaside Buffer) for performance, ensuring it is flushed when `MMU_PDBR` is written.

### Phase 3: MyKernel OS Integration
1. Write a Page Allocator in `MyKernel`.
2. Map the Kernel itself (Identity Mapping) during boot, then flip `MMU_CTRL` to enable paging.
3. Update the executable loader to map `.mbin` files into virtual memory and spawn them in User Mode.
