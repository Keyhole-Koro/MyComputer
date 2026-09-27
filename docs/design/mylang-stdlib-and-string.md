# MyLang Standard Library and Native Strings

Where the MyLang standard library is going, what the compiler has to gain
before each step is possible, and what was measured rather than assumed.

Companion to `issues/tickets/MLC-004_mylang-standard-library-foundation.md`.

## 1. What a string is today

Since 2026-09-26, MyLang has a compiler-known borrowed `str` value. Its ABI
layout is two words, `{ char* data; i32 length; }`, and it is `Copy`. Literals
are interned once as NUL-terminated bytes and also have a `{data, length}` view,
so they can be used as `str` without losing compatibility with legacy C-style
APIs. The length is a byte count and may include embedded NUL bytes.

`char*` remains the FFI/MMIO representation: it points to NUL-terminated bytes
and `len(char*)` scans. Use `pointer.as_str()` or `str.from_c(pointer)` to make
a view, and `view.as_c_str()` when calling an API that requires `char*` (a
sliced view is not guaranteed to have a terminator at its logical end).

## 2. Three compiler limits that shape every API

These were each confirmed against the compiler, not inferred.

### 2.1 Struct types cross package boundaries

Imported structs, enums, typedefs, and their transitive field types are now
staged into the importing unit. This is what lets `str`, `Option<str>`, and
the filesystem argument contracts cross module boundaries. Generic imports
also carry concrete plain-type dependencies such as `SeekWhence`.

### 2.2 Exported constants do not survive linking

`export i32 HEADER = 3;` in one package and `ringbuf.HEADER` in another gives
`Undefined symbol 'ringbuf_HEADER'`. Only functions link across packages.
`MyOS/src/ui/dom.mln:27` already records this for enum members.

Consequence: sizes and tags that a caller needs are written as literals and
documented, or exposed as a function.

### 2.3 There is no multiply or divide instruction

The ISA has `add`, `sub`, `and`, `or`, `xor`, `shl`, `shr` and no `mul` or
`div`; codegen expands `*` into a repeated-add loop.

Consequence: index arithmetic uses shifts (`i >> 3`, `i & 7`), ring buffers
wrap with a compare instead of `%`, and a future hash must be djb2
(`(h << 5) + h + c`) rather than FNV, which needs a multiply.

## 3. Phases

### Phase 0 -- done, no compiler change required

`toolchain/MyStdLib/` (moved out of `system/MyKernel/src/lib/` once MyOS and
MyLangCompiler's own tests started reaching into MyKernel for it -- a kernel
repo growing the shared library for its siblings was backwards):

| package | role |
| --- | --- |
| `str` | NUL-terminated string helpers |
| `bytes` | memset / memcpy / memmove / memcmp over byte buffers |
| `bitset` | bit array over a caller-owned buffer |
| `ringbuf` | fixed-capacity i32 FIFO |
| `strbuf` | append-only builder that truncates rather than overruns |

`bytes` rather than `mem` because `package mem` is already the kernel's
word-level absolute-address accessor for RAM and MMIO.

Callers moved onto them: `serial.mln`'s keystroke queue (ringbuf),
`MyOS/src/fs/fs.mln`'s block bitmap (bitset), `MyOS/src/shell/serial.mln`'s
private `str_eq` (str.eq), `MyOS/src/apps/counter.dom.mln`'s hand-written
decimal bytes (strbuf).

### Phase 1 -- `str` as a language type -- done

The compiler now supports aggregate values in locals, globals, fields,
arguments, returns, assignments, and call chains. `str` literals, content
equality (`==`/`!=`), embedded NULs, and cross-package methods are covered by
the compiler and system E2E suites. The standard module provides:
`len`, `is_empty`, `compare`, `starts_with`, `ends_with`, `find`, `slice`,
`byte_at`, `as_c_str`, and the `char*` bridge `as_str`/`from_c`.

The intended shape is three layers:

| layer | representation | ownership |
| --- | --- | --- |
| `char*` | NUL-terminated pointer | none; FFI and MMIO |
| `str` | `{char* data; i32 length;}`, Copy | borrowed |
| `String` | `{u8* ptr; i32 len; i32 cap;}` | owned, heap |

Literals keep their trailing NUL and gain a length, so the same literal is
valid as both `str` and `char*`. A literal may be implicitly passed to legacy
`char*`/`char[]` parameters; an arbitrary `str` requires an explicit
`as_c_str()` conversion. `len` is in bytes and the encoding is UTF-8; a
`chars()` iterator can wait, since `font8x8.mln` is ASCII.

### Phase 2 -- owned types

`String`, `Vec<T>` and friends need a drop hook so the ownership checker's move
tracking can free heap memory at scope end. Generic type/function
monomorphization is already available; the remaining work is ownership-aware
cleanup and allocator integration. The checker already tracks moves, but
nothing runs on the way out of a scope yet.

## 4. Collections worth having, in payoff order

Ranked by what the OS already open-codes.

1. `ringbuf` -- serial RX, mouse and keyboard events. **done**
2. `bitset` -- MFS block allocation, and the page-frame allocator EMU-003
   will need. **done**
3. `strbuf` -- every label and log line. **done**
4. Arena / bump allocator -- per-frame DOM layout, per-syscall scratch;
   avoids fragmenting the first-fit heap. No new language feature needed.
5. `Vec<T>` -- DOM child lists, dirents, the run queue. Needs generics; until
   then a `VecI32` covers most of it, because the DOM is already i32-handle
   based.
6. `HashMap` -- path to inode, id to node, command tables. Needs `str` and
   djb2.
7. Intrusive list -- `heap.mln`'s free list and the scheduler's task list are
   the same structure written twice.
8. `Slice<T>` -- nearly free once `str` exists.
9. `Option<T>` / `Result<T, E>` -- payload enums now distinguish absence from
   typed failure across filesystem and UI boundaries. **done**
