# MLC-018: 型付き関数値とコールバック

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Proposed | - | codex:gpt-6 | 2026-10-02 |

## Summary

現在 `i32` として保存・呼び出している関数アドレスに、引数型と戻り値型を持つ
`fn(...) -> ...` 型を追加する。DOM、アプリイベント、注釈のコールバックをこの型へ直接移行する。

## Background

- `toolchain/MyLangCompiler/src/backend/codegen/codegen_call.c` は、値からの呼び出しを
  「関数ポインタを格納した i32」として生成している。
- `system/MyOS/src/ui/dom/dom.mln` の `on_click`、`on_key`、`on_change`、`on_tick` と、
  `system/MyAppFramework/src/runtime/runtime.mln` の `Handler.fn` はすべて `i32` である。
- 間接呼び出しでは、引数個数・引数型・戻り値型を意味解析で検証できない。

## Design

### Proposed Design

型構文を次の形にする。

```mylang
fn(i32 owner, i32 id, i32 arg) -> void
fn(i32 owner, i32 code, i32 mods) -> bool
```

関数値の実行時表現は現行ABIと同じ1ワードのコードアドレスとする。型情報には戻り値、
固定引数、可変長の有無を保持し、直接関数、ローカル変数、struct field、importされた関数値の
代入と間接呼び出しで同じ互換性判定を使う。`0` は関数値へ代入せず、未登録状態には
`Option<fn(...) -> ...>` を使う。

DOMの用途ごとに別の型を使い、イベントハンドラとキー判定関数を混同できないようにする。
古い `i32` コールバックAPIは残さず、呼び出し側を一括移行する。

### Alternatives Considered

- `typedef i32 Handler` は表記だけが変わり、誤ったシグネチャを検出できないため採用しない。
- 引数をすべて1種類の巨大なイベントstructに統一する案は、同期キー判定の戻り値など用途差を
  隠すため採用しない。

### Non-Goals

- クロージャ環境を持つ値。最初の段階ではコードアドレスだけを扱う。
- 呼び出し規約の追加。

## Progress

- [ ] lexer・parser・ASTへ関数型を追加
- [ ] TypeInfoとmodule metadataへ関数シグネチャを追加
- [ ] 代入・引数・戻り値・間接呼び出しの型検査を追加
- [ ] codegenで1ワード関数値を扱う
- [ ] DOM、AppFramework、annotationsの `i32` コールバックを移行
- [ ] LSPのhoverとsignature helpへ関数型を表示

## Verification

```bash
make -C toolchain/MyLangCompiler test-component
make -C toolchain/MyLangCompiler test-e2e
make qa
```

## 完了条件

- シグネチャが一致する関数値を保存して間接呼び出しできる。
- 引数個数、引数型、戻り値型の不一致がsemantic errorになる。
- UIとアプリ実行系にコールバック用途の `i32` fieldが残らない。

## 関連

- MLC-014 MyLang Function Signature Type Checking
- MLC-003 MyLang Package Symbol Resolution

