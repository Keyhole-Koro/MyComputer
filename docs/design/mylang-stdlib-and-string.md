# MyLang Standard Library and Native Strings

Where the MyLang standard library is going, what the compiler has to gain
before each step is possible, and what was measured rather than assumed.

Companion to `issues/tickets/MLC-004_mylang-standard-library-foundation.md`.

## 1. What a string is today

Since 2026-09-26, MyLang has a compiler-known borrowed `str` value. Its ABI
layout is two words, `{ char* data; i32 length; }`, and it is `Copy`. The
length is a byte count and may include embedded NUL bytes. `str` never owns or
provides writable storage.

`char*` remains the low-level FFI/MMIO representation. New bounded text uses
`InlineString<N>`; code that must expose a NUL-terminated pointer uses the
separate `InlineCString<N>` boundary type. This keeps the terminator slot and
embedded-NUL restriction out of normal MyLang strings.

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
| `str` | borrowed length-aware string algorithms and legacy boundary helpers |
| `bytes` | memset / memcpy / memmove / memcmp over byte buffers |
| `bitset` | bit array over a caller-owned buffer |
| `ringbuf` | fixed-capacity i32 FIFO |
| `InlineString<N>` | inline owned string; atomic mutation, no NUL slot |
| `InlineCString<N>` | inline NUL-terminated storage for system boundaries |

`bytes` rather than `mem` because `package mem` is already the kernel's
word-level absolute-address accessor for RAM and MMIO.

Callers moved onto them: `serial.mln`'s keystroke queue (ringbuf),
`MyOS/src/fs/fs.mln`'s block bitmap (bitset), and MyOS application/syscall
scratch strings (`InlineString` / `InlineCString`). The old truncating
`strbuf` and borrowed-storage `StringBuilder` APIs were removed.

### Phase 1 -- `str` as a language type -- done

The compiler now supports aggregate values in locals, globals, fields,
arguments, returns, assignments, and call chains. `str` literals, content
equality (`==`/`!=`), embedded NULs, and cross-package methods are covered by
the compiler and system E2E suites. The standard module provides:
`len`, `is_empty`, `compare`, `starts_with`, `ends_with`, `find`, `slice`,
`byte_at`, `as_c_str`, and the `char*` bridge `as_str`/`from_c`.

The intended shape is four explicit layers:

| layer | representation | ownership |
| --- | --- | --- |
| `str` | `{char* data; i32 length;}`, Copy | borrowed view |
| `InlineString<N>` | `{u8 data[N]; i32 length;}` | owned, inline |
| `InlineCString<N>` | `{char data[N]; i32 length;}` | owned inline FFI boundary |
| `String` | `{u8* data; i32 length; i32 capacity;}` | owned, growable heap |

Const generics use explicit declarations such as `struct InlineString<const
N>` and uses such as `InlineString<128>`. An `i32.to_string()` returns an
owned `InlineString<12>`; formatting no longer borrows a caller-provided
temporary array. `len` is in bytes and the encoding is UTF-8; a `chars()`
iterator can wait, since `font8x8.mln` is ASCII.

### Phase 2 -- owned types -- in progress

The normative behavior and current limitations are specified in
[MyLang Owned Values, Automatic Drop, and `String`](mylang-owned-values-and-drop.md).

The compiler now recognizes `void (T *self) drop()` as deterministic cleanup,
tracks ownership at runtime across branch-dependent initialization and moves,
and recursively drops owned fields. Cleanup covers normal scope exit,
`break`, `continue`, and function return. `memory/allocator.mln` separates the
container API from its runtime allocator; MyOS uses the kernel heap and
MyAppFramework supplies a process-local first-fit heap over `sbrk`.

`text/string.mln` is the first heap-owned container. It provides atomic
`reserve`, `append`, and `push`, returns allocation failure as `false`, and is
freed automatically. `Vec<T>` still needs element-aware construction and move
semantics before it should migrate to the same mechanism.

## 4. Collections worth having, in payoff order

Ranked by what the OS already open-codes.

1. `ringbuf` -- serial RX, mouse and keyboard events. **done**
2. `bitset` -- MFS block allocation, and the page-frame allocator EMU-003
   will need. **done**
3. `InlineString<N>` / `InlineCString<N>` -- labels, log lines, and explicit
   C-style system boundaries. **done**
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
