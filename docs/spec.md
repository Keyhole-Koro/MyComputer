# Architecture and Project Specification

This document summarizes the current architecture specification and how it maps to the project
modules. It is based on `MyEmulator/architecture/README.md`.

## Architecture summary
- Word size: 16 bits
- Data bus width: 16 bits
- Address bus width: 16 bits
- Max addressable memory: 64 KB (2^16)

## Register set
- General purpose: R0-R7 (16-bit)
- PC (Program Counter, 16-bit)
- SP (Stack Pointer, 16-bit)
- SR (Status Register, 8 or 16-bit)
- IR (Instruction Register, 16-bit, optional)

Notes:
- Stack direction: down
- Stack base address: TBD
- Calling convention: TBD

## Instruction set architecture (ISA)
- Instruction length: fixed 16-bit
- Encoding format(s): TBD

### Addressing modes (TBD)
- Immediate
- Direct
- Indirect
- Register
- Base + offset / indexed

### Instruction categories (examples)
- Data movement: MOV, LOAD, STORE
- Arithmetic: ADD, SUB, INC, DEC
- Logic: AND, OR, XOR, NOT
- Control flow: JMP, CALL, RET, JZ, JNZ
- Stack: PUSH, POP
- I/O: IN, OUT
- Special: NOP, HALT, IRET

## Memory map
- 0x0000-0x7FFF: 32 KB RAM
- 0x8000-0xBFFF: 16 KB ROM
- 0xC000-0xC0FF: 256 B I/O registers
- 0xC100-0xC1FF: 256 B interrupt vector table
- 0xC200-0xFFFF: 14 KB reserved / future use

## Status register flags
- Z (Zero): bit 0
- N (Negative): bit 1
- C (Carry): bit 2
- V (Overflow): bit 3
- I (Interrupt Enable): bit 4

## Control flow
- Jump types: JMP, JZ, JNZ, JC, JNC, etc.
- Call behavior: push return address to stack
- Return behavior: pop return address from stack
- Interrupt return: IRET (restores PC and flags)

## Interrupt system (TBD)
- Maskable vs non-maskable: TBD
- Vector table: 0xC100-0xC1FF
- Vector format: 16-bit addresses per interrupt
- Trigger type: edge vs level TBD
- Context saved on interrupt: TBD

## I/O interface
- Method: memory-mapped or port-mapped (TBD)
- Address range: 0xC000-0xC0FF
- Standard device map (proposed):
  - 0xC000: keyboard
  - 0xC010: SSD
  - 0xC020: display (optional)
  - 0xC030: serial (optional)

## Boot and reset
- Reset vector address: 0x8000
- Boot sequence: TBD (jump to reset vector, clear registers, enable interrupts)

## Implementation notes
- Technology: CMOS (4000 series or custom logic)
- Clock frequency: ~1 MHz (initial)
- Clock generation: crystal oscillator or timer circuit
- Reset circuit: push-button + capacitor + Schmitt trigger

## Project modules
- `MyEmulator`: CPU, bus, RAM, and runtime implementation (C++)
- `MyAssembler`: assembler for the ISA (C)
- `MyLangCompiler`: compiler front-end to assembler (C)
- `MyTester`: test runners (Python)

## Sources
- `MyEmulator/architecture/README.md`