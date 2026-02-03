# MyKernel

Minimal sample kernel built from mixed sources (high-level `.ml` + a small hand-written `.masm` stub). The stub jumps into `f_kernel_main`, which is produced by the compiler from `src/kernel_main.ml`.

## Layout
- `src/kernel_main.ml` — high-level entry (`int kernel_main()`) that seeds a simple bump-allocator skeleton and returns the remaining heap bytes.
- `asm/stub.masm` — RAM entrypoint (`__START__`) that calls `f_kernel_main`, mirrors the return value to `R0/R1` and `mem[0x100]`, then halts.
- `build/` — generated `.masm`, `.mbin`, `.mobj`, and linker outputs.

## Quick build + run (manually)
```bash
# From repo root
MyLangCompiler/mlc MyKernel/src/kernel_main.ml MyKernel/build/kernel_main.masm
MyAssembler/build/myas MyKernel/build/kernel_main.masm MyKernel/build/kernel_main.mbin --obj MyKernel/build/kernel_main.mobj
MyAssembler/build/myas MyKernel/asm/stub.masm          MyKernel/build/kernel_stub.mbin --obj MyKernel/build/kernel_stub.mobj
MyLinker/mllinker MyKernel/build/kernel_linked.mbin \
  MyKernel/build/kernel_stub.mobj MyKernel/build/kernel_main.mobj

# Ensure ROM exists (generate once if needed)
MyAssembler/build/myas MyEmulator/examples/boot_rom.masm MyEmulator/build/os/boot_rom.mbin

# Run
MyEmulator/build/myemu --rom MyEmulator/build/os/boot_rom.mbin --ram MyKernel/build/kernel_linked.mbin
```

See `MyTester/run_kernel.py` for an automated version.
