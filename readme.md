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

Boot headless and save the desktop as a PNG (`OUT=path` to change the name):

```bash
make screenshot
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

MyLang syntax, token, and semantic-token tests are included in the compiler
test suite. The shared syntax engine builds an LR(1) table from the grammar;
the compiler and the LSP use the same syntax-checking path for diagnostics.

Assembler / linker:

```bash
make as-test
make linker-test
```

MyKernel subsystem tests:

```bash
./toolchain/MyLangTester/build/mytest system/MyKernel/tests/heap
./toolchain/MyLangTester/build/mytest system/MyKernel/tests/scheduler
./toolchain/MyLangTester/build/mytest system/MyOS/tests/fs
```

UI: graphics primitives against the emulator's 2D accelerator, input queues,
DOM hit-dispatch, and the headless end-to-end desktop test through the strict
MyOS automation API:

```bash
make qa-graphics
make qa-dom
make dom-tester-test
make apps-test
make dom-inspect ARGS="--watch"
```

## Desktop UI

`system/MyOS/src/ui/` is a small window system on top of the emulator's 2D
accelerator: anti-aliased proportional text (`font_sans.mln`, generated from a
system TTF by `make font` / `tools/gen_font.py`), rounded windows with a soft
shadow, a title bar (close / minimize / maximize) with drag-to-move and a
resize grip, focus and z-order, right-click window and desktop menus, buttons,
checkboxes, single- and multi-line text fields, lists, a taskbar with an app
launcher and an uptime clock, and Tab focus movement. Apps describe their
windows in `.dom.mln` markup (see `src/apps/`); colours and metrics live in
`theme.mln`. Details: [`system/MyOS/docs/DOM_SPEC.md`](system/MyOS/docs/DOM_SPEC.md),
[`runtime/MyEmulator/readme.md`](runtime/MyEmulator/readme.md).

The source boundaries are intentionally not a linear three-layer stack:
applications use MyAppFramework and MyStdLib hosted APIs, MyOS provides the
services, and both sides consume data-only definitions from the root
`contracts/` directory. MyOS does not import the framework. See
[MyStdLib / MyAppFramework / MyOS boundaries](docs/design/os-app-boundaries.md)
and run `make qa-boundaries` to check the allowed imports.

## User-space programs

The kernel runs isolated user processes (own page tables, W^X, syscalls) — see
[`docs/design/user-space-processes-and-syscalls.md`](docs/design/user-space-processes-and-syscalls.md).
Programs live in `system/MyOS/user/apps/*.mln` (`package app;` exporting
`i32 main()`); `make build` compiles each into an MBIN v2 executable, and
`tools/mkfs.py` places them on the disk image alongside a couple of text
files. Launch them from the desktop's **Terminal** (type `hello`, `echo`,
`count`, or `ls`/`cat`), or browse the disk with **Files** and edit with
**Editor**, all reachable from the taskbar's MyOS menu. A process's stdout is
routed to its terminal window through the kernel's console hooks
(`system/MyOS/src/proc/console.mln`).

## Debugging

`qa/runners/run_kernel.py` creates a session directory under `system/MyKernel/build/sessions/`
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

## MyLang And VS Code

For syntax diagnostics and semantic highlighting in VS Code, install the
extension in [`tools/vscode-mylang`](tools/vscode-mylang/README.md). The
extension launches the repository's MyLang LSP and supports `.mln` and `.mlx`
files. See the design notes for the LR(1) engine and frontend integration:

- [Generic syntax engine](docs/implemented/syntax-engine-generic.md)
- [Shared frontend and LSP](docs/implemented/shared-frontend.md)

## Directory Structure

```text
.
├── architecture/             # Architecture notes and design docs
├── contracts/                # Data-only semantic and wire contracts
├── docs/                     # Project-wide documentation
├── hardware/
│   └── verilator/            # Verilog/Verilator hardware model
├── issues/                   # Proposed / completed work tickets
├── qa/                       # Test scripts, build runners, debug helpers
├── runtime/
│   └── MyEmulator/           # Emulator implementation
├── system/
│   ├── MyFirmware/           # Boot firmware (ROM)
│   ├── MyKernel/             # Core OS kernel
│   ├── MyAppFramework/       # App SDK and process runtime
│   └── MyOS/                 # OS services, file system, UI, and apps
├── toolchain/
│   ├── MyAssembler/          # Assembler
│   ├── MyLangCompiler/       # Compiler (incl. native .dom.mln UI syntax)
│   ├── MySyntaxEngine/       # Generic LR(1) syntax engine
│   ├── MyLinker/             # Linker
│   ├── MyStdLib/             # MyLang standard library
│   ├── MyLangTester/         # MyLang test tooling
│   └── MyLangTestKit/        # MyLang mock/spy test-double runtime
├── tools/                    # Helper tools and editor integration
│   ├── vscode-mylang/        # VS Code syntax/LSP integration
│   └── MyLangServerProtocol/ # MyLang LSP server
├── .devcontainer/            # Dev container settings
└── readme.md                 # This file
```
