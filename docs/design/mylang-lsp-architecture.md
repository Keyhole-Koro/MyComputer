# MyLang LSP Architecture

Status: Implemented (MLSP-003)

This document defines the architecture of the MyLang language server and its
VS Code integration. Feature specifications such as parameter documentation,
Hover, Signature Help, Completion, diagnostics, and navigation build on this
foundation.

The first consumer of this design is
[`mylang-param-doc-and-lsp.md`](mylang-param-doc-and-lsp.md).

The implementation lives in `tools/MyLangServerProtocol/lsp_analysis.py`,
`tools/MyLangServerProtocol/server.py`, and `tools/vscode-mylang/extension.js`.

---

## 1. Motivation

The current implementation is intentionally small:

- `tools/vscode-mylang/extension.js` implements its own JSON-RPC connection and
  registers VS Code providers directly.
- `tools/MyLangServerProtocol/server.py` owns protocol framing, document state,
  compiler subprocess management, diagnostics, semantic tokens, and document
  symbols in one class.
- Some editor-facing information comes from the syntax engine while other
  information is reconstructed by scanning source text.

This was enough for the initial diagnostics and highlighting features. Adding
Hover, Signature Help, Completion, navigation, and workspace-wide symbol
resolution directly to the same structure would duplicate standard LSP client
behavior and make parsing, caching, cancellation, and symbol identity harder to
maintain.

## 2. Goals

1. Use the standard LSP boundary between VS Code and the language server.
2. Keep protocol transport separate from MyLang analysis.
3. Reuse compiler or syntax-engine facts instead of re-parsing declarations
   independently for each feature.
4. Give every analysis result an owning document version.
5. Support local-document features first and workspace/import resolution
   without changing provider APIs later.
6. Define one position-conversion boundary for UTF-8 compiler offsets and LSP
   UTF-16 positions.
7. Keep the server usable by editors other than VS Code.

## 3. Non-Goals

- Building a fully incremental compiler in the first iteration.
- Moving semantic analysis into the VS Code extension.
- Replacing `mylang-syntax-check` before the compiler frontend exposes an
  equivalent editor-oriented API.
- Implementing every future LSP method as part of the architecture refactor.

---

## 4. Target Architecture

```text
+------------------------------+
| VS Code Extension            |
| vscode-languageclient        |
+---------------+--------------+
                | LSP over stdio
+---------------v--------------+
| Protocol Layer               |
| initialize / dispatch / I/O  |
+---------------+--------------+
                |
+---------------v--------------+
| Analysis Service             |
| Hover / Signature / symbols  |
+-------+--------------+-------+
        |              |
+-------v-------+ +----v----------------+
| DocumentStore | | WorkspaceIndex      |
| snapshots     | | imports / SymbolId  |
+-------+-------+ +----+----------------+
        |              |
+-------v--------------v-------+
| FrontendBackend              |
| syntax checker / compiler    |
+------------------------------+
```

### 4.1 VS Code Extension

The extension should use `vscode-languageclient` instead of maintaining a
custom request table and LSP-to-VS-Code adapter.

Responsibilities:

- Start and stop the Python language server.
- Provide the document selector and extension configuration.
- Apply lightweight TextMate highlighting immediately while semantic analysis
  is still pending.
- Let the language client manage document synchronization, cancellation,
  capability negotiation, provider registration, and protocol type conversion.
- Keep VS Code-only presentation settings out of the language server.

The extension must not contain MyLang declaration parsing or symbol-resolution
logic.

### 4.2 Protocol Layer

The protocol layer owns only LSP concerns:

- JSON-RPC framing and request dispatch.
- `initialize`, `shutdown`, and `exit` lifecycle.
- Capability declaration.
- Conversion between LSP UTF-16 positions and internal source spans.
- Cancellation and error conversion.

It delegates feature requests to `AnalysisService`. The initial implementation
may retain the existing dependency-free Python framing, but the framing and
dispatcher must be separated from analysis state so they can be replaced by an
LSP framework later without rewriting feature logic.

The server advertises only implemented capabilities. In addition to the
existing semantic-token and document-symbol capabilities, the first interactive
feature milestone adds:

```json
{
  "textDocumentSync": 1,
  "hoverProvider": true,
  "definitionProvider": true,
  "signatureHelpProvider": {
    "triggerCharacters": ["(", ","]
  }
}
```

`completionProvider` is advertised only when Completion is implemented.

### 4.3 DocumentStore

`DocumentStore` owns immutable snapshots:

```text
DocumentSnapshot
  uri
  version
  text
  line_map
```

- `didOpen` and `didChange` create a new snapshot.
- A request captures one snapshot and never mixes results from different
  versions.
- Unsaved editor contents take precedence over disk contents.
- Closing a document releases the open snapshot, but cached workspace metadata
  may remain if the file belongs to the workspace.

Analysis caches are keyed by at least `(URI, version)`. A result computed for an
older version must not be published as the result for a newer version.

### 4.4 Source Positions

The compiler and syntax checker may report UTF-8 byte-oriented locations while
LSP uses UTF-16 code units by default. Python string indices are neither of
those for non-BMP characters.

Each snapshot therefore owns a `LineMap` that converts between:

- internal UTF-8 byte offsets;
- zero-based line and UTF-8 byte column locations from native tools;
- LSP zero-based line and UTF-16 character positions.

All conversion happens at backend and protocol boundaries. Feature code uses
internal `SourceSpan` values and must not calculate LSP character positions
directly.

### 4.5 FrontendBackend

`FrontendBackend` is the only component that calls `mylang-syntax-check` or a
future compiler frontend service. It returns editor-oriented metadata rather
than raw protocol responses:

```text
AnalysisUnit
  diagnostics
  tokens
  declarations
  references
  imports

FunctionInfo
  symbol_id
  name
  package
  receiver_type?
  type_parameters
  parameters
  return_type
  declaration_span
  doc_comment_span?
```

The syntax-engine output should be extended to expose function signatures and
declaration spans. Source scanning may attach comment trivia to a known
declaration, but it must not be the authoritative parser for MyLang function
syntax.

If the document is temporarily invalid, the backend may return partial metadata
whose confidence and source version are known. Providers must prefer no result
over a result resolved to the wrong declaration.

### 4.6 Symbol Identity and WorkspaceIndex

A plain function name is not a stable identity. `SymbolId` must distinguish at
least:

```text
package
receiver type, when present
symbol name
declaration URI
declaration span
```

Generic instantiations refer back to the template declaration for documentation.
Method resolution includes the receiver type. Package-qualified calls resolve
through imports before documentation is selected.

`WorkspaceIndex` stores exported declaration metadata and import relationships.
The local-document milestone can use the same interface with an index containing
only the current document. Later workspace support therefore changes index
population, not Hover or Signature Help APIs.

Opening or changing a document indexes that document only. Interactive
features first attempt local resolution; if it fails, the server maps the
pointer's callee or argument context to one source import, loads only that
file, and retries. It does not index unrelated direct or transitive imports on
the request path. Diagnostics, feature analysis, and semantic
tokens share a bounded content-addressed cache of raw frontend results so the
same snapshot is not sent through the native parser repeatedly.

Index entries are invalidated when:

- an open document version changes;
- a watched workspace file changes on disk;
- its package or exported declarations change;
- an import edge changes.

### 4.7 AnalysisService

The service exposes editor operations independent of JSON-RPC:

```text
hover(snapshot, position) -> HoverResult?
definition(snapshot, position) -> Location?
signature_help(snapshot, position) -> SignatureHelpResult?
document_symbols(snapshot) -> list[Symbol]
completion(snapshot, position) -> list[CompletionCandidate]
```

Requests resolve symbols through `WorkspaceIndex` and use declaration metadata
from `FrontendBackend`. Protocol-specific objects such as `MarkupContent` are
created only in the protocol layer.

---

## 5. Request and Update Flow

### Document update

1. The language client sends full-text `didOpen` or `didChange`.
2. `DocumentStore` creates a snapshot and its `LineMap`.
3. The previous analysis result for that URI is superseded.
4. When semantic highlighting is enabled, diagnostics are marked pending
   instead of starting analysis in the update notification.
5. The semantic-token request runs the frontend and flushes its response first.
6. Pending diagnostics reuse that raw frontend result and are published after
   the highlighting response, only if the analyzed version is still current.
7. Documentation and declaration indexing remain lazy until Hover or Signature
   Help needs them; direct dependencies are loaded only if local resolution
   fails.

### Interactive request

1. The protocol layer converts the LSP position using the captured snapshot.
2. `AnalysisService` requests cached analysis for the same snapshot version.
3. The service resolves the relevant declaration and constructs a feature
   result.
4. The protocol layer converts spans and documentation to LSP objects.
5. Cancellation or a superseding document version discards stale work.

The stdio reader must not wait synchronously for a long compiler operation. A
first implementation may use one serialized analysis worker, provided the
protocol loop can still receive cancellation and lifecycle messages.
Within one document generation, interactive requests and semantic highlighting
run ahead of background document-symbol work. Document updates define ordering
barriers so prioritization never analyzes a request against a later snapshot.

---

## 6. Failure Behavior

- A crashed syntax-checker process is restarted for a later request and logged
  to the client.
- Backend timeout or malformed output produces no speculative feature result.
- Diagnostics from a failed analysis do not clear valid diagnostics unless the
  server can identify the failure as an empty successful result.
- One malformed document must not terminate the LSP process.
- Unknown requests return the standard method-not-found error.

---

## 7. Migration Plan

### Phase A: Standardize the client boundary

- Replace the custom VS Code JSON-RPC connection with
  `vscode-languageclient`.
- Preserve diagnostics, semantic tokens, and document symbols.
- Add lifecycle and capability tests.

### Phase B: Split server responsibilities

- Extract protocol dispatch, `DocumentStore`, `LineMap`, and
  `FrontendBackend` from `server.py`.
- Key analysis results by URI and document version.
- Add UTF-16 conversion tests, including Japanese text and emoji.

### Phase C: Add declaration metadata

- Extend syntax-engine output with function signatures, parameters, receivers,
  generic parameters, imports, and declaration spans.
- Introduce `SymbolId`, `FunctionInfo`, and the local-document index.
- Keep regex parsing only as an explicitly limited fallback.

### Phase D: Add interactive features

- Implement Hover and Signature Help using the parameter-documentation design.
- Add workspace/import index population.
- Implement Completion after workspace symbol resolution is stable.

---

## 8. Verification

### Protocol and extension

- Initialize capability snapshot.
- Open/change/close synchronization through the standard language client.
- Server shutdown, crash, and restart behavior.
- Request cancellation and method-not-found responses.

### Document and position model

- Stale analysis is not returned for a newer document version.
- Unsaved contents override disk contents.
- UTF-8/UTF-16 conversion works before and after Japanese text and emoji.

### Frontend and indexing

- Free functions, methods, generic functions, extern declarations, and rest
  parameters produce stable metadata.
- Same-named functions in different packages or receiver types have different
  `SymbolId` values.
- Import and export changes invalidate the affected index entries.

## 9. Completion Criteria

- The VS Code extension no longer maintains a custom JSON-RPC request client.
- Protocol transport, document state, frontend access, and feature logic are
  separate components.
- Analysis results are versioned and position conversion is tested.
- Existing diagnostics, semantic tokens, and document symbols continue to work.
- Hover and Signature Help can consume stable `FunctionInfo` without parsing
  function declarations themselves.
- Go to Definition resolves local and directly imported functions, structs,
  enums, type aliases, and enum members from frontend declaration spans.
