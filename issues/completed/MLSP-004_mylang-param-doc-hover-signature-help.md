# MLSP-004: MyLang Parameter Documentation, Hover, and Signature Help

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Done | main | codex:gpt-5 | 2026-09-18 |

## Summary

MyLang関数の `/** ... */` / `///`、`@param`、`@return` を宣言metadataへ関連付け、解決済みの関数・
methodに対する Hover と Signature Help を提供する。Completionはworkspace index安定後の
後続milestoneに分離する。

## Background

- 現在のLSPには関数signatureやparameter documentationを問い合わせるhandlerがない。
- `tools/MyLangServerProtocol/server.py:478` のsemantic tokensと `:690` のdocument symbolsは
  syntax checker出力を利用するが、doc commentと関数signatureを結ぶmetadataはない。
- MyLangにはfree functionだけでなくreceiver method、generic function、extern declaration、
  rest parameterがあり、関数名とsource regexだけでは正しい宣言を特定できない。
- raw comma countingでは `outer(inner(1, 2), cursor)` のactive parameterを誤る。

## Design

### Current State

- `/** ... */` と `///` は通常のcommentとして扱われ、documentation semanticsを持たない。
- function callから宣言の `SymbolId` を得るeditor向けresolverがない。
- current documentとimport先を統一して引ける `WorkspaceIndex` がない。
- serverは `hoverProvider` と `signatureHelpProvider` をadvertiseしていない。

### Proposed Design

詳細は
[`docs/design/mylang-param-doc-and-lsp.md`](../../docs/design/mylang-param-doc-and-lsp.md)
を正とする。基盤境界は MLSP-003 に依存する。

- frontendが認識したfunction declarationへ、直前の `/** ... */` または連続した `///` blockを添付する。
- `FunctionInfo` をsignatureの正、`FunctionDoc` をdocumentationの正とする。
- call/declarationを先に `SymbolId` へ解決してからdocsを取得する。
- Signature Helpはsyntax tokenのdelimiter depthを追跡し、対象call直下のcommaだけを数える。
- local-document indexから開始し、同じprovider APIのままworkspace/import indexへ広げる。
- method receiverは解決に使うが、通常のcall parameterとしては表示しない。

### Alternatives Considered

- function declarationとcallをregexで解析する案: generics、receiver、ownership modifier、
  nested call、invalid sourceでcompiler grammarと乖離するため採用しない。
- 名前一致した最初の関数のdocを出す案: packageやreceiverが異なる同名関数で誤情報を
  表示するため採用しない。曖昧な場合は結果を返さない。
- Completionも同時実装する案: ranking、replacement range、snippet、workspace探索が
  別設計を要するため後続にする。

### Non-Goals

- struct、enum、field、global variableのdocumentation。
- documentation generator。
- `@param` 不整合をcompiler errorにすること。
- workspace completionの実装。

## Progress

- [x] function declaration metadataへdoc-comment spanを追加する
- [x] `/** ... */` / `///` / `@param` / `@return` extractorを実装する
- [x] doc annotation名を朱色の`docTag` semantic tokenとして表示する
- [x] local-document `SymbolId` resolutionを実装する
- [x] Hoverを実装する
- [x] token-aware Signature Helpを実装する
- [x] method、generic、extern、rest parameterをテストする
- [x] workspace/import resolutionを接続する
- [x] design docと実装の差分を更新する

## Verification

```sh
python3 tools/MyLangServerProtocol/tests/test_doc_comments.py
python3 tools/MyLangServerProtocol/tests/test_hover.py
python3 tools/MyLangServerProtocol/tests/test_signature_help.py
```

上記テストは実装時に追加する。nested call、protected text、multiline/incomplete call、
same-name symbol、UTF-16 position、unsaved document versionをfixtureへ含める。

## 完了条件

- function signatureをregexで再解析せず、frontend metadataへdocsを添付できる。
- definition、resolved call、argument contextでHoverが正しい宣言のdocを返す。
- nested delimiterやstring/comment内のcommaで`activeParameter`がずれない。
- method呼び出しでreceiverをparameter indexへ含めない。
- unresolved/ambiguous callでは誤ったdocを返さない。
- 日本語やemojiより後方のHover/Signature Help positionが正しい。
- Completion capabilityは未実装の間advertiseされない。

## 関連

- [Parameter documentation design](../../docs/design/mylang-param-doc-and-lsp.md)
- [MLSP-003 LSP Architecture Refactor](MLSP-003_mylang-lsp-architecture-refactor.md)
- [MLC-003 Package Symbol Resolution](../tickets/MLC-003_mylang-package-symbol-resolution.md)
