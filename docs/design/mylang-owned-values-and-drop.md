# MyLang Owned Values, Automatic Drop, and `String`

Status: implemented, with the limitations listed in section 7.

This document is the normative project-level specification for deterministic
cleanup, the standard allocator boundary, and the heap-owned `String` type.
The compiler-oriented ownership overview remains in
`toolchain/MyLangCompiler/docs/ownership.md`.

## 1. Terminology

- An **owner** is a binding responsible for eventually releasing a value.
- A **move** transfers that responsibility without duplicating it.
- A **borrow** provides temporary access and does not transfer responsibility.
- A **droppable type** is a non-pointer, non-reference, non-array struct that
  defines a valid `drop()` method, or contains a droppable field.
- An **active owner** is a binding that currently contains an initialized,
  not-yet-moved droppable value.

Pointers, references, primitive values, enums, and borrowed `str` values do
not participate in automatic drop. Their ordinary Copy/borrow rules still
apply.

## 2. Declaring deterministic cleanup

A struct opts into deterministic cleanup with a method named `drop`:

```mln
struct Resource {
    i32 handle;
};

void (Resource *self) drop() {
    release(self->handle);
    self->handle = 0;
}
```

The compiler recognizes the method only when all of the following are true:

- its lowered name belongs to the receiver type (`Resource__drop` above);
- it has exactly one receiver parameter;
- the receiver is a pointer or reference, not a value receiver;
- its return type is `void`.

The method must release only resources directly managed by its containing
type. It must not manually drop droppable fields: after the containing
type's method returns, the compiler drops those fields automatically.

`drop()` has no error channel. It must complete normally and must accept the
zero/empty state used by its type.

## 3. Ownership state and moves

The compiler reserves one runtime ownership flag for every droppable local and
by-value parameter.

- A by-value parameter starts active because the caller transferred ownership.
- A local declared without an initializer starts inactive.
- Successful whole-value initialization or assignment activates the owner.
- A whole-value move clears the source flag.
- Moving a value into a by-value call parameter makes the callee its owner.
- Returning a droppable aggregate moves it into the caller's result storage.
- Self-assignment does not drop or deactivate the value.

The runtime flag is separate from semantic move checking. The semantic phase
still rejects source-level use after move; the flag ensures generated cleanup
is correct when initialization depends on a runtime branch.

```mln
String text;
if (needs_text) {
    text = string.from_str("hello");
}
// text is dropped only on the path where the assignment ran.
```

Struct assignment is a bytewise aggregate transfer at the ABI level, but a
non-Copy/droppable value is an ownership move at the language level. Rawly
duplicating the three words of a `String` would create two owners and is not a
supported operation.

## 4. When cleanup runs

An active owner is dropped exactly once on every implemented exit path:

- normal lexical scope exit;
- `return`, through the function's shared cleanup epilogue;
- `break`, for values owned inside the exited loop;
- `continue`, for values owned by the completed iteration;
- whole-binding overwrite, before the replacement is written.

Bindings are cleaned up in reverse declaration order. For a struct value, the
order is:

1. call the struct's own `drop()` method, if present;
2. drop droppable fields in reverse declaration order;
3. recursively apply the same rule to those fields.

Moving the entire containing struct transfers all of its fields together.
Moving an ordinary standalone owner into a struct literal is also supported:

```mln
Resource resource = acquire();
Holder holder = Holder { resource: resource };
// resource is inactive; holder now owns it.
```

Application code should not call `drop()` manually. A manual call does not
clear the compiler's ownership flag and can therefore release the same
resource twice at scope exit.

## 5. Standard allocator contract

`toolchain/MyStdLib/memory/allocator.mln` is the allocator boundary for owned
standard-library values. An executable installs it once during startup:

```mln
allocator.configure(runtime_alloc, runtime_free);
```

The callbacks use the current freestanding ABI:

- allocation: `(i32 size) -> i32 address`; zero means failure;
- deallocation: `(i32 address) -> void`; freeing zero is a no-op;
- requested sizes are positive byte counts;
- returned storage must be suitably aligned for ordinary MyLang values;
- a successful allocation remains valid until passed to the matching free
  callback.

If no allocator is configured, `allocator.alloc()` returns zero and
`allocator.free()` is a no-op. Owned constructors therefore report allocation
failure instead of dereferencing an absent runtime service.

Runtime installation currently works as follows:

- MyOS configures the standard allocator with `heap.alloc` / `heap.free`
  immediately after `heap.init()`.
- MyAppFramework installs a per-process first-fit allocator before creating
  the application instance.
- Compiler E2E tests install an explicit test allocator.

The MyAppFramework allocator aligns allocations to four bytes, stores an
eight-byte header, reuses an address-ordered free list, and coalesces adjacent
free blocks. It does not split oversized free blocks, return pages to the OS,
or provide synchronization. Invalid pointers and double-free remain undefined
behavior.

## 6. Heap-owned `String`

The standard type is defined in `toolchain/MyStdLib/text/string.mln`:

```mln
struct String {
    u8 *data;
    i32 length;
    i32 capacity;
};
```

`String` owns `data`; `length` and `capacity` are byte counts. Its contents may
contain embedded NUL bytes, and no trailing NUL slot is reserved. Use
`InlineCString<N>` when a `char *` boundary requires NUL termination.

Construction uses package functions because MyLang does not yet provide
associated-function syntax:

```mln
import string from "text/string.mln";
import { String } from "text/string.mln";

String line = string.with_capacity(128);
line.append("pid=");
InlineString<12> pid = 42.to_string();
line.append(pid.as_str());
```

### 6.1 Operations

| operation | contract |
| --- | --- |
| `string.with_capacity(n)` | Creates an empty owner. Negative capacity acts as zero; allocation failure produces a zero-capacity empty value. |
| `string.from_str(value)` | Copies all bytes. Allocation failure produces a zero-capacity empty value. |
| `len()` | Returns initialized byte length. |
| `capacity_bytes()` | Returns allocated byte capacity. |
| `is_empty()` | Tests `length == 0`. |
| `as_str()` | Returns a borrowed view of the initialized bytes. |
| `clear()` | Sets length to zero and retains the allocation. |
| `reserve(additional)` | Ensures space for `length + additional`; returns false on invalid size, overflow, or allocation failure. |
| `append(value)` | Appends all bytes and returns false without changing the text if growth fails. |
| `push(value)` | Appends one byte and has the same failure guarantee. |
| `drop()` | Frees the allocation and resets the representation to its empty state. |

Growth starts at four bytes and doubles until the required capacity is met.
Allocation and copying finish before the old allocation is freed, so a failed
growth leaves the original value unchanged.

`append()` supports a source view wholly contained in the same String, even
when growth reallocates it:

```mln
str original = line.as_str();
line.append(original);
```

Other borrowed views passed to `append()` must remain valid for the duration
of the call. Any operation that may grow or drop a String must be treated as
invalidating previously borrowed views.

## 7. Current limitations

These are unsupported rather than part of the stable ownership model:

1. **Droppable local arrays.** One flag cannot describe which array elements
   were initialized or moved. Use a container with its own `drop()` method.
2. **Partial field/dereference moves and replacement.** Moving or replacing a
   droppable field independently requires per-field flags. The compiler emits
   an error for the cases it detects; move or replace the containing owner.
3. **Droppable globals.** Automatic cleanup is function-local; global owners
   have no shutdown drop pass.
4. **Ownerless temporaries.** A discarded owning call result has no tracked
   binding. Bind owned results to a local or immediately move them into another
   owner.
5. **Manual destruction.** Calling `drop()` directly does not update the
   ownership flag and is unsupported in ordinary application code.
6. **Thread safety.** The standard allocator selector and the current
   application heap are not synchronized.

Future element/field-level initialization flags should land before `Vec<T>` or
arrays of `String` are treated as automatically managed values.

## 8. Required regression coverage

Changes to this specification must preserve tests for:

- move initialization, whole-binding assignment, by-value calls, and return;
- recursive field cleanup and reverse ordering;
- branch-dependent initialization;
- `break` and `continue` cleanup;
- overwrite-before-replacement;
- allocator failure atomicity;
- String reallocation and self-append;
- exactly one final free for the surviving owner.
