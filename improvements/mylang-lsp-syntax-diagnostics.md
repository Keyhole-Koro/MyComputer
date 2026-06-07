# MyLang LSP Syntax Diagnostics Follow-ups

The LR(1)-based VSCode syntax diagnostics pipeline is now usable. Remaining work is mostly quality and integration hardening.

## High Priority

- Report multiple syntax errors per document instead of stopping at the first parse error.
- Add CI coverage for `make test-syntax-check` in `toolchain/MyLangCompiler`.
- Improve diagnostic ranges for incomplete syntax at end-of-file and missing delimiters.

## Grammar And Parser Quality

- Decide how to handle the remaining `IDENTIFIER ASTARISK` ambiguity:
  - Keep the single known conflict for LSP mode, or
  - introduce a type-aware token such as `TYPE_IDENTIFIER`, or
  - accept reduced support for user-defined type pointer declarations in the LSP grammar.
- Add more invalid syntax fixtures for expression, declaration, block, and control-flow errors.
- Periodically check conflict count with:
  ```sh
  cd toolchain/MyLangSyntaxEngine
  ./build/bin/output --conflicts tests/fixtures/grammars/mylang_lsp.grammar
  ```

## VSCode Experience

- Add extension settings for diagnostics debounce duration and syntax diagnostics enable/disable.
- Surface syntax-check startup/build failures in VSCode instead of silently returning no diagnostics.
- Consider clearing stale diagnostics if the syntax checker process crashes.

## LSP Features

- Improve semantic token accuracy using compiler lexer/parser context instead of regex-only classification.
- Improve document symbols for structs, enums, functions, globals, and local declarations.
- Add workspace-level handling for multiple open MyLang files.

## Performance And Maintenance

- Keep LR table cache invalidation covered by tests.
- Consider placing the syntax table cache under a dedicated build/cache directory.
- Add a short developer doc for the source -> compiler lexer -> syntax-check -> LSP diagnostics flow.
