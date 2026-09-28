# MyComputer agent guidance

This file contains repository workflow guidance for coding agents. Language,
ABI, and subsystem behavior belong in `docs/` or the owning submodule's
technical documentation, not here.

## Repository shape

The root repository owns the system integration and the submodule pointers.
The following directories are independent repositories:

- `system/MyKernel`, `system/MyOS`, and `system/MyAppFramework`
- `toolchain/MyLangCompiler`, `toolchain/MyStdLib`, `toolchain/MyAssembler`,
  `toolchain/MyLinker`, `toolchain/MySyntaxEngine`, `toolchain/MyLangTester`,
  and `toolchain/MyLangTestKit`
- `runtime/MyEmulator` and `hardware/verilator`

Commit source changes in the repository that owns them. After a submodule
commit, update and commit its pointer in the root repository.

## Safe workflow

- Inspect `git status --short` before editing and preserve existing user work.
- Do not use destructive reset, checkout, or recursive deletion commands to
  discard changes.
- Use `apply_patch` for source and documentation edits.
- Keep changes scoped to the requested subsystem. Ask before a broad redesign,
  deletion of referenced documentation, or an external coordination change.
- Verify with the smallest relevant test first, then run the broader suite in
  proportion to the risk.

## Common validation

From the root:

```bash
make build
make qa
```

For compiler changes:

```bash
make -C toolchain/MyLangCompiler test-component
make -C toolchain/MyLangCompiler test-e2e
```

For standard-library and system changes, use the relevant root QA suites and
finish with `git diff --check` plus a recursive status check.

## Documentation placement

- `AGENTS.md`: instructions for coding agents and repository workflow.
- `docs/design/`: normative project design, ABI, and boundary decisions.
- `docs/implemented/`: implemented feature records and migration history.
- `docs/learn/`: explanatory material and tutorials.
- `issues/`: proposals, tickets, and completed work history.
- A submodule's `docs/` contains technical details specific to that repository.

When a document mixes agent instructions with technical design, split the
instructions into the nearest `AGENTS.md` and keep the design independently
readable. Check current source and tests before treating an old design note as
authoritative.
