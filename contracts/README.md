# Shared contracts

Data-oriented contracts shared by clients and providers. A contract may contain
enums, structs, constants, declarations, and semantic conversion/description
trait implementations owned by a contract type. It must not contain transport
implementation, handlers, policy, mutable state, or dependencies on MyOS or
MyAppFramework. Imports from MyStdLib are limited to foundational traits such
as `From` and `Describe` and the core `Result` / `Option` types.

An `OS_CALL` argument record is followed by `impl OsCall for Record =
OsService::X;`, which binds it to the one service that accepts it. Its reply
type is the concrete type of its `result_out` field.

Layout:

- `io/`: platform-neutral semantic contracts such as `FsError`.
- `ui/`: platform-neutral UI semantic contracts such as `UiError`.
- `process/`: the `Pid` type, and process-launch and lifecycle errors shared by hosted
  clients and MyOS.
- `sync/`: shared raw synchronization-word meanings such as `MutexState`.
- `myos/`: MyOS wire identifiers such as `OsService`.
- `myapp/`: application request/event envelopes and operation tables.

ABI changes are append-only where possible: do not reorder existing enum
variants or struct fields. A removal, reorder, or field-type change is a
breaking change. MyOS and applications currently use a lockstep MyLang ABI,
so shared `Result` / `Option` values may be copied directly when both sides
import the same contract payload type.
