# Project Progress Overview

## Achievement Levels
- **Emulator**: 25%
- **Assembler**: 80%
- **Compiler**: 80%

## Emulator CLI (ROM-aware)
- `--rom <file>` loads an image at 0x20000000 and defaults the entry point there
- `--ram <file>` (or `-i/--in`) loads an image into RAM; override start with `--ram-base <addr>`
- `--entry <addr>` overrides the start PC; `--reg R0` prints a single register after run
- Dump of the first 64KB of RAM is saved to `memory_dump.txt` each run

## Compiler Test
- Run the compiler test script: `python3 mlc-test.py`

## Layout
- Example ROM/kernel sources: `MyEmulator/examples/boot_rom.masm`, `MyEmulator/examples/kernel.masm`
- Prebuilt demo images and hexdumps: `MyEmulator/build/os/*.bin` / `*.txt`
