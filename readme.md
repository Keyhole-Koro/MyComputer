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
- Run the compiler test script: `python3 qa/MyTester/mlc-test.py`

## Layout
- Example ROM/kernel sources: `runtime/MyEmulator/examples/boot_rom.masm`, `runtime/MyEmulator/examples/kernel.masm`
- Prebuilt demo images and hexdumps: `runtime/MyEmulator/build/os/*.bin` / `*.txt`

## Directory Structure
```text
.
├── architecture/             # Architecture notes and design docs
├── docs/                     # Project-wide documentation
├── qa/
│   └── MyTester/             # Test scripts, test inputs, and expected outputs
├── runtime/
│   └── MyEmulator/           # Emulator implementation
├── system/
│   └── MyKernel/             # Kernel sources
├── toolchain/
│   ├── MyAssembler/          # Assembler
│   ├── MyLangCompiler/       # Compiler
│   └── MyLinker/             # Linker
├── tools/                    # Helper tools and editor integration
├── .devcontainer/            # Dev container settings
├── .github/workflows/        # CI configuration
└── readme.md                 # This file
```
