# MyLang Parameter Documentation, Hover, and Signature Help

Status: Implemented (MLSP-004)

This document defines MyLang function documentation and the editor behavior
built from it. It depends on the document, position, frontend, and symbol-index
boundaries defined in [`mylang-lsp-architecture.md`](mylang-lsp-architecture.md).

Completion is intentionally deferred until workspace symbol indexing is stable.

---

## 1. Goals

1. Define deterministic `/** ... */` and `///` documentation formats for functions.
2. Display a resolved function signature and documentation in Hover.
3. Display the active parameter and its documentation in Signature Help.
4. Work with free functions, methods, generic functions, extern declarations,
   and rest parameters without maintaining a second MyLang declaration parser.
5. Support the current document first and imported workspace declarations in a
   later milestone through the same symbol-resolution interface.

## 2. Non-Goals

- Documentation attached to structs, enums, fields, or global variables.
- Documentation-site generation.
- Documentation validation as a compiler error.
- Completion in the first provider milestone.
- Guessing a declaration by name when symbol resolution is ambiguous.

---

## 3. Documentation Syntax

### 3.1 Example

```mylang
/**
 * Adds two 32-bit integers.
 *
 * Both operands are interpreted as signed values.
 * @param a The first operand.
 * @param b The second operand.
 * @return The sum of `a` and `b`.
 */
export i32 add(i32 a, i32 b) {
    return a + b;
}
```

### 3.2 Supported content

The first milestone supports:

| Content | Syntax | Meaning |
| --- | --- | --- |
| Summary/body | Plain doc-comment text | Prose before the first tag. |
| Parameter | `@param <name> <text>` | Documentation for a declared parameter. |
| Return value | `@return <text>` | Documentation for the returned value. |

`@returns` is accepted as an alias for `@return`.

The first non-empty prose line is the summary. Remaining prose before the first
tag is the body. Blank doc-comment lines preserve paragraph breaks. In a block
comment, leading whitespace, `*`, and one optional following space are stripped.

Tags are single-line in the first milestone. Multiline tag continuation,
`@brief`, `@note`, and `@warning` are reserved extensions and must not be
partially interpreted.

Unknown tags are retained as unrendered text in the extracted comment so a
future server version can support them, but they do not affect Hover or
Signature Help.

All `@name` annotations inside `/** ... */` and `///` documentation comments are
emitted as the `docTag` semantic token. The VS Code extension colors `docTag`
vermilion (`#D3381C`); surrounding documentation remains comment-colored.

### 3.3 Attachment

A `/** ... */` block or contiguous `///` block attaches only to the immediately
following function or extern function declaration. A blank line or another
token breaks attachment.

```mylang
/** This does not attach to `foo`. */

export void foo() {}
```

Leading indentation and one optional space after `///` are stripped. Ordinary
`/* ... */` and `//` comments do not form documentation blocks; block docs must
start with `/**`.

Documentation is associated with a frontend-provided declaration span. The
extractor does not use a regular expression to decide whether the following
source text is a function.

### 3.4 Parameter matching

`@param` names match source-level parameter names exactly and case-sensitively.
Parameter order always comes from `FunctionInfo`, never from tag order.

- A missing tag produces an undocumented parameter.
- An unknown parameter name is ignored by providers.
- For duplicate tags, the first tag wins.
- `@return` on a `void` function is retained but not rendered in the first
  milestone.
- A rest parameter uses its declared source name.

Documentation warnings for unknown or duplicate tags may be added later without
changing extraction behavior.

---

## 4. Data Model

Documentation augments the declaration metadata from the LSP architecture:

```python
@dataclass(frozen=True)
class ParamDoc:
    name: str
    text: str


@dataclass(frozen=True)
class FunctionDoc:
    summary: str
    body: str
    param_docs: dict[str, ParamDoc]
    return_doc: str | None
    comment_span: SourceSpan
```

`FunctionInfo` remains authoritative for symbol identity, signature, generic
parameters, receiver, parameter order and types, return type, and declaration
span. `FunctionDoc` contains documentation only.

Parsed docs are cached with the owning `(URI, document version)` analysis. They
must not outlive the declaration metadata to which they were attached.

---

## 5. Symbol Resolution

Hover and Signature Help first resolve a call or declaration to `SymbolId`, then
load its `FunctionInfo` and `FunctionDoc`.

Resolution rules include:

- A local free-function call resolves in the current package scope.
- A package-qualified call resolves through the import table.
- A method call resolves using the receiver type and method name.
- A generic instantiation points back to its template declaration for docs.
- An ambiguous or unresolved call returns no documentation result.

The local-document milestone uses an index containing only declarations from the
current snapshot. Workspace/import support later populates the same
`WorkspaceIndex`; provider behavior does not change.

For methods, the receiver participates in resolution but is not displayed as an
ordinary call argument. A future `@receiver` tag can document it separately.

---

## 6. Hover

`textDocument/hover` is available at:

- a function name in its declaration;
- the callee portion of a resolved call;
- an argument expression whose containing call and parameter can be resolved.

Hover over a declaration or callee renders the full signature and docs:

````markdown
```mylang
add(i32 a, i32 b) -> i32
```

Adds two 32-bit integers.

Both operands are interpreted as signed values.

**Parameters**

- `a` — The first operand.
- `b` — The second operand.

**Returns**

The sum of `a` and `b`.
````

Hover over an argument expression renders the matched parameter only:

````markdown
```mylang
i32 b
```

The second operand.
````

The returned LSP `Hover.range` covers the callee identifier or the argument
expression selected by the frontend metadata. Markdown is treated as untrusted;
command links and raw HTML are not enabled.

Documentation indexing is lazy. If the current document or the selected import
has not been indexed yet, the first Hover response contains `Loading...`; the
server then indexes only that target and sends
`mylang/hoverReady`. The VS Code extension re-requests Hover automatically when
the request position is also the cursor position. Mouse-only Hover keeps the
loading message until VS Code requests the position again.

---

## 7. Signature Help

`textDocument/signatureHelp` is triggered by `(` and `,` and may also be invoked
manually.

For `add(10, |)` the server returns:

- `activeSignature = 0`
- `activeParameter = 1`
- signature label: `add(i32 a, i32 b) -> i32`
- parameter labels: `i32 a` and `i32 b`
- parameter documentation from the corresponding `@param` tags

Parameter labels use `[start, end]` offsets into the signature label rather than
duplicated label strings when possible.

### 7.1 Active-call discovery

The call-site analyzer operates on syntax tokens, not raw comma counting.
Starting at the cursor, it finds the nearest enclosing call whose opening
parenthesis is not closed before the cursor. It ignores tokens inside strings
and comments and tracks nested:

- parentheses;
- brackets;
- braces;
- recognized generic argument lists.

Only commas at the selected call's argument depth advance `activeParameter`.
For example, the cursor below selects parameter 1 of `outer`, not parameter 2:

```mylang
outer(inner(1, 2), |)
```

For a rest parameter, indices at or beyond the fixed parameter count select the
rest parameter. Otherwise, an argument index beyond the declared parameter list
returns the index required by LSP while omitting parameter documentation.

Incomplete code is expected. If the enclosing call can be identified but its
callee cannot be resolved confidently, the server returns no Signature Help.

---

## 8. Protocol Integration

The server advertises:

```json
{
  "hoverProvider": true,
  "signatureHelpProvider": {
    "triggerCharacters": ["(", ","]
  }
}
```

Positions and ranges are converted through the snapshot's `LineMap`. Provider
logic never consumes an LSP UTF-16 position directly.

The standard VS Code language client registers the features from server
capabilities. The extension does not manually translate LSP Hover,
SignatureHelp, MarkupContent, Range, or enum values into VS Code API objects.

---

## 9. Implementation Plan

### Milestone 1: Documentation extraction

- Add declaration metadata required by `FunctionInfo` to the frontend backend.
- Attach `/** ... */` or contiguous `///` trivia to known function declaration spans.
- Parse prose, `@param`, and `@return` into `FunctionDoc`.
- Cover free, extern, generic, method, and rest-parameter declarations.

### Milestone 2: Local Hover and Signature Help

- Build a current-document symbol index.
- Implement callee and argument-context resolution.
- Implement token-aware active parameter selection.
- Add protocol handlers and advertise capabilities.

### Milestone 3: Workspace/import resolution

- Populate exported `FunctionInfo` and docs from workspace files.
- Resolve package imports and package-qualified calls.
- Invalidate affected index entries on file and import changes.

### Milestone 4: Completion

Completion is a separate feature over the stable workspace index. Its design
must specify candidate ranking, filtering, replacement ranges, snippet insertion,
and LSP-to-editor behavior before `completionProvider` is advertised.

---

## 10. Verification

### Documentation extraction

- Summary and multi-paragraph body.
- Single and multiple `@param` tags.
- Missing, unknown, and duplicate parameter tags.
- `@return`, `@returns`, and `void` behavior.
- Blank-line attachment break.
- Ordinary `//` and reserved tags are not partially parsed.
- Documentation annotation names use `docTag`; ordinary comments do not.
- Declarations with `export`, `extern`, generics, receivers, arrays, ownership
  modifiers, and rest parameters.

### Hover

- Definition and resolved call sites.
- Argument-to-parameter mapping.
- Same-named functions in different packages and receiver types.
- Unresolved and ambiguous calls return no result.
- Markdown content and Hover ranges.

### Signature Help

- Empty, first, middle, and final arguments.
- Nested calls such as `outer(inner(1, 2), cursor)`.
- Commas in strings, comments, initializers, and generic arguments.
- Multiline and incomplete calls.
- Rest parameters and too many arguments.
- Method calls exclude the receiver from `activeParameter`.

### Positions and document state

- Japanese text and emoji before a hovered symbol or call.
- Unsaved edits use the current document version.
- Results from superseded versions are discarded.

## 11. Completion Criteria

- Function documentation is attached to frontend-provided declarations without
  regex-parsing MyLang signatures.
- Hover and Signature Help resolve through `SymbolId`.
- Nested calls and protected text do not corrupt `activeParameter`.
- Position conversion is correct for UTF-16 clients.
- Local-document tests pass before workspace indexing is enabled.
- Completion remains unadvertised until its separate milestone is implemented.
