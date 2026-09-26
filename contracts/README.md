# Shared contracts

Data-only contracts shared by clients and providers. A contract may contain
enums, structs, constants, and declarations, but no transport implementation,
handler, policy, mutable state, or dependency on MyOS, MyAppFramework, or
MyStdLib.

Layout:

- `io/`: platform-neutral semantic contracts such as `FsError`.
- `ui/`: platform-neutral UI semantic contracts such as `UiError`.
- `process/`: process-launch and lifecycle errors shared by hosted clients and MyOS.
- `myos/`: MyOS wire identifiers such as `OsService`.
- `myapp/`: application request/event envelopes and operation tables.

ABI changes are append-only where possible: do not reorder existing enum
variants or struct fields. A removal, reorder, or field-type change is a
breaking change. MyOS and applications currently use a lockstep MyLang ABI,
so shared `Result` / `Option` values may be copied directly when both sides
import the same contract payload type.
