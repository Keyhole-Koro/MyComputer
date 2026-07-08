# MyComputer

## Build And Run

Build the full system (MyFirmware + MyKernel/MyOS) and run it in the emulator:

```bash
make run
```

Build the system without opening a display window:

```bash
make run ARGS="--headless --step 300000"
```

Build the system images without running them:

```bash
make build
```

(Note: `make kernel` can still be used for testing the kernel directly in ROM)

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
make qa
```

Compiler integration tests:

```bash
make mlc-test
```

Assembler / linker:

```bash
make as-test
make linker-test
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
make kernel ARGS="--trace --step 10000"
make kernel ARGS="--headless --profile profile.json --step 300000"
make kernel ARGS="--mem 0x00000000 0x100"
```

Profile report:

```bash
make profile ARGS="system/MyKernel/build/sessions/<session>/profile.json"
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
