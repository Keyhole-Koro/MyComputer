# MLSP-003: MyLang LSP Architecture Refactor

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Done | main | codex:gpt-5 | 2026-09-18 |

## Summary

VS Code 拡張の独自 JSON-RPC client と、単一クラスに集約された Python LSP server を
標準 Language Client・versioned document snapshot・frontend adapter・symbol index の境界へ
分割する。Hover 等の対話機能を追加する前に、位置変換と解析結果の寿命を安定させる。

## Background

- `tools/vscode-mylang/extension.js:7` の `JsonRpcConnection` が request table、timeout、
  framing、process lifecycle を独自実装している。
- `tools/vscode-mylang/extension.js:247` と `:257` で、server capability を受けた provider を
  VS Code API へ個別登録している。
- `tools/MyLangServerProtocol/server.py:115` の `LspServer` が protocol、document state、
  syntax-check subprocess、diagnostics、semantic tokens、document symbols をすべて所有する。
- `tools/MyLangServerProtocol/server.py:206` の同期 dispatch 中に、`:362` の
  `query_syntax_checker()` が native subprocess を待つため、今後解析が重くなると request
  受付や cancellation も停止する。
- LSP の UTF-16 position、Python の文字 index、native tool の column の変換境界がない。

## Design

### Current State

- extension は `vscode-languageclient` を利用していない。
- server は full-text sync の内容を `Dict[str, Document]` に保存するが、解析cacheを
  document versionへ関連付けていない。
- syntax checker は token と symbol を返すが、関数signature・receiver・importを含む
  共通 declaration metadata はまだ返さない。
- import先を含む editor symbol index は存在しない。

### Proposed Design

詳細は
[`docs/design/mylang-lsp-architecture.md`](../../docs/design/mylang-lsp-architecture.md)
を正とする。

要点:

- VS Code側を `vscode-languageclient` に移行する。
- Python側を protocol layer、`DocumentStore`、`LineMap`、`AnalysisService`、
  `FrontendBackend`、`WorkspaceIndex` に分ける。
- snapshot と解析結果を `(URI, version)` で関連付ける。
- native tool の UTF-8 byte location と LSP UTF-16 position を `LineMap` で変換する。
- declarationを `SymbolId` と `FunctionInfo` で表現し、名前だけのlookupを避ける。
- stdio受付を長時間のfrontend処理から分離し、stale resultとcancellationを扱う。

### Alternatives Considered

- 現在の `extension.js` と `server.py` に provider を直接追加する案: protocol型変換、
  cancellation、snapshot管理、symbol解決が機能ごとに増殖するため採用しない。
- 最初から Python LSP framework へ全面移行する案: client移行とserver内部分割を同時に
  大きくし過ぎるため必須にしない。protocol層を分離し、後から交換可能にする。
- compilerを先にdaemon化する案: 初期目的には過大なので、既存syntax-check subprocessを
  `FrontendBackend` 越しに利用する。

### Non-Goals

- このチケット内で Hover、Signature Help、Completion を完成させること。
- fully incremental compiler の実装。
- `mylang-syntax-check` の即時廃止。
- package symbol resolution 自体のcompiler側再設計。

## Progress

- [x] standard Language Clientへ移行し、既存機能を維持する
- [x] protocol dispatchをanalysis stateから分離する
- [x] `DocumentStore` と versioned snapshotを追加する
- [x] UTF-8/UTF-16 `LineMap` を追加する
- [x] `FrontendBackend` と解析cacheを追加する
- [x] `SymbolId` / `FunctionInfo` / local-document indexを追加する
- [x] stale result、cancellation、backend failureをテストする
- [x] architecture docと実装の差分を更新する

## Verification

```sh
for test_file in tools/MyLangServerProtocol/tests/test_*.py; do python3 "$test_file" || exit 1; done
npm --prefix tools/vscode-mylang test
```

加えて、Language Client経由の initialize、open/change/close、semantic tokens、document
symbols、shutdown、cancellation と、`LineMap` の日本語・emoji fixtureを自動テストする。

## 完了条件

- extensionが独自 `JsonRpcConnection` を持たず、standard Language Clientでserverへ接続する。
- 既存のsyntax diagnostics、semantic tokens、document symbolsが回帰しない。
- protocol、document state、frontend access、feature logicが別componentになっている。
- 解析結果がURI/versionへ関連付けられ、古いversionの結果を返さない。
- UTF-8 byte locationとLSP UTF-16 positionの相互変換テストが通る。
- `FunctionInfo` をregexによる関数宣言再解析なしで取得できる。

## 関連

- [LSP architecture design](../../docs/design/mylang-lsp-architecture.md)
- [MLSP-004 Parameter Documentation, Hover, and Signature Help](MLSP-004_mylang-param-doc-hover-signature-help.md)
- [MLSP-001 Semantic Diagnostics Integration](../tickets/MLSP-001_mylang-lsp-semantic-diagnostics-integration.md)
- [MLSP-002 Syntax Diagnostics Follow-ups](../tickets/MLSP-002_mylang-lsp-syntax-diagnostics.md)
