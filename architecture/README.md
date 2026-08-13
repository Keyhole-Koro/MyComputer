# 📀 Computer Architecture Specification Document

**Version:** Draft 3.1
**Architecture:** 32-bit

---

## 1. 🧠 Word and Bus Widths

* **Word size:** 32 bits
* **Data bus width:** 32 bits
* **Address bus width:** 32 bits
* **Max addressable memory:** 4 GB (2³²)

---

## 2. 🫲 Register Set

| Name  | Width             | Purpose                                   |
| ----- | ----------------- | ----------------------------------------- |
| R0–R7 | 32-bit            | General-purpose registers                 |
| PC    | 32-bit            | Program Counter                           |
| SP    | 32-bit            | Stack Pointer                             |
| BP    | 32-bit            | Base Pointer (newly introduced)           |
| SR    | 8-bit             | Status Register (flags)                   |
| IR    | 32-bit (optional) | Instruction Register (used for debugging) |

* **Stack direction:** ☑ Down
* **Stack base address:** `0x7FFFFFFF`
* **Calling convention:** Manual (no CALL/RET); caller must manage PC and stack explicitly.

---

## 3. 🧾 Instruction Set Architecture (ISA)

### 3.1 Instruction Format

* **Instruction length:** ☑ Fixed 32-bit
* **Encoding format(s):**

  * `6-bit opcode + 5-bit reg1 + 5-bit reg2 + 16-bit imm/unused` for `reg, reg` operations
  * `6-bit opcode + 5-bit reg + 21-bit imm` for `reg, imm21` and `reg, port`
  * `6-bit opcode + 26-bit imm` for control flow and jumps

### 3.2 Addressing Modes

* ☑ Immediate
* ☑ Direct
* ☑ Indirect (via register)
* ☑ Register

### 3.3 Instruction Categories

| Category      | Examples                         |
| ------------- | -------------------------------- |
| Data Movement | `mov`, `movi`, `load`, `store`   |
| Arithmetic    | `add`, `sub`, `mcp`              |
| Logic         | `and`, `or`, `xor`, `shl`, `shr`, `call`, `ret` |
| Control Flow  | `jmp`, `jz`, `jnz`               |
| Stack         | `push`, `pop`                    |
| I/O           | `in`, `out`                      |
| Special       | `nop`, `halt`, `iret`            |

---

## 📉 Opcode Assignment Table

| Format         | Bits       |
| -------------- | ---------- |
| Opcode         | 6 bits     |
| Reg1 (if used) | 5 bits     |
| Reg2 (if used) | 5 bits     |
| Imm16–26       | 16–26 bits |

### 📅 Data Movement

---

| Mnemonic        | Opcode | Pattern      | Description                      |
| --------------- | ------ | ------------ | -------------------------------- |
| `mov r1, r2`    | `0x01` | `reg, reg`   | Copy r2 into r1                  |
| `movi r1, imm`  | `0x02` | `reg, imm21` | Load **zero-extended** immediate |
| `movis r1, imm` | `0x18` | `reg, imm21` | Load **sign-extended** immediate |
| `load r1, r2`     | `0x03` | `reg, reg`   | r1 ← mem\[r2]                    |
| `store r1, r2`     | `0x04` | `reg, reg`   | mem\[r1] ← r2                    |
| `loadb r1, r2`  | `0x1c` | `reg, reg` | r1 ← byte at mem\[r2] (zero-extend) |
| `storeb r1, r2` | `0x1d` | `reg, reg` | mem\[r1] ← lower byte of r2         |

---

### ➕ **Arithmetic/Logic**

| Mnemonic      | Opcode | Pattern     | Description                    |
| ------------- | ------ | ----------- | ------------------------------ |
| `add r1, r2`  | `0x05` | `reg, reg`  | r1 ← r1 + r2                   |
| `sub r1, r2`  | `0x06` | `reg, reg`  | r1 ← r1 - r2                   |
| `cmp r1, r2`  | `0x07` | `reg, reg`  | Set flags for r1 - r2          |
| `and r1, r2`  | `0x08` | `reg, reg`  | Bitwise AND                    |
| `or r1, r2`   | `0x09` | `reg, reg`  | Bitwise OR                     |
| `xor r1, r2`  | `0x0a` | `reg, reg`  | Bitwise XOR                    |
| `shl r1`      | `0x0b` | `reg`       | Logical shift left             |
| `shr r1`      | `0x0c` | `reg`       | Logical shift right            |
| `addis r1, imm`| `0x19` | `reg, imm`  | r1 ← r1 + sign_extend(imm)     |


---

### ↺ **Control Flow**

| Mnemonic    | Opcode | Pattern | Description                       |
| ----------- | ------ | ------- | --------------------------------- |
| `jmp addr`  | `0x0d` | `imm26` | Unconditional jump                |
| `jz addr`   | `0x0e` | `imm26` | Jump if zero                      |
| `jnz addr`  | `0x0f` | `imm26` | Jump if not zero                  |
| `jg addr`   | `0x10` | `imm26` | Jump if greater (signed)          |
| `jl addr`   | `0x11` | `imm26` | Jump if less (signed)             |
| `ja addr`   | `0x12` | `imm26` | Jump if above (unsigned greater)  |
| `jb addr`   | `0x13` | `imm26` | Jump if below (unsigned less)     |
| `call addr` | `0x1b` | `imm26` | Push return address, jump to addr |

---

### 📦 **Stack**

| Mnemonic  | Opcode | Pattern | Description      |
| --------- | ------ | ------- | ---------------- |
| `push r1` | `0x14` | `reg`   | Push r1 to stack |
| `pop r1`  | `0x15` | `reg`   | Pop from stack   |

---

### 🌐 **I/O**

| Mnemonic       | Opcode | Pattern      | Description    |
| -------------- | ------ | ------------ | -------------- |
| `in r1, port`  | `0x16` | `reg, imm21` | Read from port |
| `out port, r1` | `0x17` | `imm21, reg` | Write to port  |

---

### 🛑 Special

| Mnemonic | Opcode | Pattern | Description    |
| -------- | ------ | ------- | -------------- |
| `halt`   | `0x3f` | —       | Stop execution |

---

## 4. 🗘️ Memory Map

| Address Range           | Size    | Description            |
| ----------------------- | ------- | ---------------------- |
| `0x00000000–0x1FFFFFFF` | 512 MB  | RAM                    |
| `0x20000000–0x23FFFFFF` | 64 MB   | ROM                    |
| `0x24000000–0x240000FF` | 256 B   | I/O Registers (incl. IRQ vector at `0x24000080`) |
| `0x24000100–0x2FFFFFFF` | ~192 MB | Reserved / Future use  |
| `0x30000000–0x30FFFFFF` | 16 MB   | VRAM (Framebuffer)     |
| `0x31000000–FFFFFFFF`   | ∼3.2 GB | Reserved / Future use  |

---

## 5. 🫳 Status Register (Flags)

| Flag | Bit | Meaning               |
| ---- | --- | --------------------- |
| Z    | 0   | Result was zero       |
| N    | 1   | Result was negative   |
| C    | 2   | Carry/borrow occurred |
| V    | 3   | Signed overflow       |
| I    | 4   | Enable interrupts     |

---

## 6. ↺ Control Flow

* **Jump types:** `JMP`, `JZ`, `JNZ`
* **No CALL/RET**: Subroutine support must be implemented via manual stack and PC management.
* **Interrupt return:** `IRET` (restores PC and flags)

---

## 7. 🛯 Interrupt System

* **Interrupt types:**

  * ☑ Maskable (`ei`/`di`, SR bit 0)
* **Interrupt vector:**

  * Single 32-bit handler slot at `0x24000080` (all sources share one vector)
  * `0x24000084` = IRQ Cause register: bit0=timer, bit1=mouse, bit2=serial, bit3=SSD.
    Read to dispatch; write 1s to acknowledge (clear) the handled bits.
* **Dispatch latency:** pending interrupts vector before the next instruction
  fetch (one-instruction latency, like real hardware)
* **Context saved on interrupt:**

  * ☑ PC
  * ☑ SR (flags; interrupts auto-masked until `iret` restores SR)
  * ☐ General registers (saved in software by the trampoline)

---

## 8. 🔌 I/O Interface

* **Method:** ☑ Memory-mapped
* **Address range:** `0x24000000–0x240000FF`
* **Standard Devices:**

| Device        | Address                 | Notes                              |
| ------------- | ----------------------- | ---------------------------------- |
| Serial (UART) | `0x24000000–0x24000005` | TX=`0x00` (W), RX=`0x04` (R, consumes a byte), LSR=`0x05` (bit0=data ready, bit5=TX empty). RX raises IRQ cause bit 2 |
| SSD           | `0x24000010–0x2400001C` | CMD=`0x10` (W: 1=read, 2=write), BLOCK=`0x14`, ADDR=`0x18`, STATUS=`0x1C` (R: 0=idle, 1=busy, 2=done, 0xFF=error). Asynchronous DMA: STATUS reads busy until the transfer completes, then IRQ cause bit 3 |
| 2D DMA        | `0x24000020–0x24000034` | DEST=`0x20`, COLOR=`0x24`, WIDTH=`0x28`, HEIGHT=`0x2C`, STRIDE=`0x30`, CMD=`0x34` (W: 1=fill rect) |
| Display       | `0x24000038`            | SWAP: write 1 to present the back buffer (double buffering) |
| Mouse         | `0x24000040–0x2400005C` | Live state: X=`0x40`, Y=`0x44`, BUTTONS=`0x48` (bit0=left). Event FIFO (64 deep, oldest dropped on overflow): COUNT=`0x4C`, EVT_X=`0x50`, EVT_Y=`0x54`, EVT_BTN=`0x58`, POP=`0x5C` (W). Each change raises IRQ cause bit 1 |
| IRQ control   | `0x24000080–0x24000084` | VECTOR=`0x80` (single shared handler address), CAUSE=`0x84` (R to dispatch, write 1s to acknowledge) |
| Timer         | (internal)              | Wall-clock tick (period from `--timer-interval`, default 1000 µs); raises IRQ cause bit 0. No MMIO registers yet |

Text I/O Notes (Characters)
- Character size is 8 bits (1 byte).
- The serial RX register returns a single byte in the low 8 bits (ASCII 0x00–0x7F recommended); reading it consumes the byte.
- Serial TX consumes one byte per character; higher bits of writes are ignored.
- Use `loadb` and `storeb` for character memory access. `loadb` zero-extends the byte to 32 bits; `storeb` writes only the low 8 bits.
---

## 9. 🕹️ Boot & Reset Behavior

* **Reset vector address:** `0x20000000`
* **Boot sequence:**

  * ☑ Jump to reset vector
  * ☑ Clear registers
  * ☑ Enable interrupts

---

## 10. 🧱 Physical Implementation Notes

* **Technology:** CMOS (custom or discrete 4000 series)
* **Clock frequency:** ∼1–10 MHz (initial target)
* **Clock generation:** Crystal oscillator or RC timer
* **Reset circuit:** Push-button + capacitor + Schmitt trigger inverter
