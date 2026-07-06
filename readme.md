# MyComputer

## Build And Run

Build the full system (MyFirmware + MyKernel/MyOS) and run it in the emulator:

```bash
python3 qa/run_system.py
```

Build the system without opening a display window:

```bash
python3 qa/run_system.py --headless --step 300000
```

Build the system images without running them:

```bash
python3 qa/run_system.py --no-run
```

(Note: `python3 qa/run_kernel.py` can still be used for testing the kernel directly in ROM)

Build the emulator:

```bash
make -C runtime/MyEmulator
```

Run the emulator directly:

```bash
runtime/MyEmulator/target/release/myemu -i system/MyKernel/build/main_linked.mbin
```

## Tests

Full QA runner:

```bash
python3 qa/test-all.py
```

Compiler integration tests:

```bash
python3 qa/mlc-test.py
```

Assembler / linker:

```bash
python3 qa/as-test.py
python3 qa/linker-test.py
```

MyKernel subsystem tests:

```bash
python3 system/MyKernel/tests/heap/run_heap_tests.py
python3 system/MyKernel/tests/scheduler/run_scheduler_test.py
python3 system/MyKernel/tests/fs/run_fs_smoke_test.py
```

## Debugging

`qa/run_kernel.py` creates a session directory under `system/MyKernel/build/sessions/`
by default. It stores build logs, emulator logs, serial output, register dumps, memory
dumps, and related debug artifacts there.

Common options:

```bash
python3 qa/run_kernel.py --trace --step 10000
python3 qa/run_kernel.py --headless --profile profile.json --step 300000
python3 qa/run_kernel.py --mem 0x00000000 0x100
```

Profile report:

```bash
python3 qa/profile_report.py system/MyKernel/build/sessions/<session>/profile.json
```

## Tickets

- [Issue index](issues/README.md)
- [DOM-like OS object model](issues/tickets/dom-like-os.md)
- [MyKernel DOM UI Automation](issues/tickets/mykernel-ui-automation.md)

## Directory Structure

```text
.
├── architecture/             # Architecture notes and design docs
├── docs/                     # Project-wide documentation
├── issues/                   # Proposed / completed work tickets
├── qa/                       # Test scripts, build runners, debug helpers
├── runtime/
│   └── MyEmulator/           # Emulator implementation
├── system/
│   ├── MyFirmware/           # Boot firmware (ROM)
│   ├── MyKernel/             # Core OS kernel
│   └── MyOS/                 # OS services, file system, UI, and apps
├── toolchain/
│   ├── MyAssembler/          # Assembler
│   ├── MyLangCompiler/       # Compiler
│   ├── MyLinker/             # Linker
│   └── MyLangTester/         # MyLang test tooling
├── tools/                    # Helper tools and editor integration
├── .devcontainer/            # Dev container settings
└── readme.md                 # This file
```
