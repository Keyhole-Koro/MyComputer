# MyLang Standard Library and Native Strings

Where the MyLang standard library is going, what the compiler has to gain
before each step is possible, and what was measured rather than assumed.

Companion to `issues/tickets/MLC-004_mylang-standard-library-foundation.md`.

## 1. What a string is today

A string is a `char*` pointing at NUL-terminated bytes. A literal is interned
into the data section by the compiler (`codegen_strings.c`, one `.byte`
sequence per distinct literal) and its address loaded with `movi`.

There is no length word, so `len` is an O(n) walk, a substring cannot be taken
without copying, and a string cannot contain a NUL. Reads have to be masked
with `0xFF` because `char` sign-extends into `i32`, which makes any byte
>= 0x80 compare as negative.

## 2. Three compiler limits that shape every API

These were each confirmed against the compiler, not inferred.

### 2.1 Struct types do not cross a package boundary

The importing file never learns an imported typedef. Both of these fail to
parse:

```mylang
import sb from "sb.mln";
sb.SB b;                    // error: expected ';' after expression

import { SB } from "sb.mln";
SB b;                       // error: expected ';' after expression
```

`parser_dom_sig.c` says the same thing from the other side: "imports only
register a package namespace".

Consequence: no public std API takes or returns a struct. State that has to
persist lives in a caller-owned array handed over as an `i32*` or `char*`
handle, with named offsets inside the package -- the shape `heap.mln` already
uses for its block headers.

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
`MyOS/src/fs/fs.mln`'s block bitmap (bitset), `MyOS/src/apps/shell.mln`'s
private `str_eq` (str.eq), `MyOS/src/apps/counter.dom.mln`'s hand-written
decimal bytes (strbuf).

### Phase 1 -- `str` as a language type

Requires compiler work, in dependency order:

1. **Struct values passed and returned.** Structs are pointer-only today;
   nothing can return a two-word `{ptr, len}`. This is the gating item.
2. **Aggregate initializers** (MLC-001), to construct one.
3. **Cross-package types** (MLC-003), or `str` is unusable outside the package
   that declares it -- see 2.1.
4. **Literals typed as `str`**, with `==` lowered to a byte compare.

The intended shape is three layers:

| layer | representation | ownership |
| --- | --- | --- |
| `char*` | NUL-terminated pointer | none; FFI and MMIO |
| `str` | `{u8* ptr; i32 len;}`, Copy | borrowed |
| `String` | `{u8* ptr; i32 len; i32 cap;}` | owned, heap |

Literals should keep their trailing NUL *and* gain a length, so the same
literal is valid as both `str` and `char*` and no existing kernel call site
has to change. The cost is one byte per literal.

`len` is in bytes and the encoding is UTF-8; a `chars()` iterator can wait,
since `font8x8.mln` is ASCII.

### Phase 2 -- owned types

`String`, `Vec<T>` and friends need two more things: monomorphization
(generics parse today but instantiation is rejected outright, in
`parser_type.c` and `parser_expr_primary.c`), and a drop hook so the
ownership checker's move tracking can free heap memory at scope end. The
checker already tracks moves; nothing runs on the way out.

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
9. `Option<T>` / `Result<T, E>` -- would unify the `-1` / panic / status-flag
   mix `docs/learn/errors-and-exceptions.md` describes. Needs generics and
   payload-carrying enums, so it is last.
