# MLC-019: `defer` によるスコープ終了処理

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Proposed | - | codex:gpt-6 | 2026-10-02 |

## Summary

早期 `return`、Resultの `?`、`break`、`continue` があっても必ず実行される
`defer` を追加し、割り込み復元、所有者コンテキスト復元、途中生成物の破棄を簡潔に書けるようにする。

## Background

- `system/MyKernel/src/mm/heap.mln` は割り込み状態を保存して最後に復元する。
- `system/MyOS/src/ui/protocol.mln` はDOM ownerを保存して要求処理後に復元する。
- UIノード生成は後続処理が失敗した場合に `remove_node(id)` を各分岐で手書きしている。
- compilerには所有値の自動dropがあるが、任意の処理をスコープ終了へ登録する構文はない。

## Design

### Proposed Design

単文とblockを登録できる構文にする。

```mylang
i32 was = irq.save_disable();
defer irq.restore(was);

i32 id = dom.create_node(NodeKind::WINDOW, title)?;
bool mounted = false;
defer { if (!mounted) { dom.remove_node(id); } }
```

deferは登録された時点から、そのlexical scopeを抜ける全経路でLIFO順に実行する。
通常の末尾、`return`、`?`による早期return、`break`、`continue`を対象にする。
既存の自動dropと同じcleanup計画へ統合し、defer本体を先に、同じ地点までに登録済みの
所有値dropを後に実行する。

変数は参照ではなく同一stack slotを読むため、実行時点の値が見える。defer本体から
`return`、`break`、`continue`、別の`defer`は使用不可とする。

### Alternatives Considered

- ScopeGuard structだけで表現する案は、型付き関数値やクロージャが先に必要になるため採用しない。
- 関数末尾だけに展開する案は早期returnと`?`で漏れるため採用しない。

### Non-Goals

- 例外unwind。MyLangのエラー経路はResultを使う。
- 非同期キャンセル。

## Progress

- [ ] token・AST・parserへdefer文を追加
- [ ] semanticで禁止されたcontrol flowと寿命を検査
- [ ] 既存drop cleanupと共通のスコープ終了計画を作る
- [ ] 全退出経路のcodegenへLIFO cleanupを挿入
- [ ] heap、UI protocol、DOM生成をdeferへ移行
- [ ] grammar、ownership docs、LSPを更新

## Verification

```bash
make -C toolchain/MyLangCompiler test-component
make -C toolchain/MyLangCompiler test-e2e
make qa
```

## 完了条件

- 全退出経路で各deferがちょうど1回、逆順に実行される。
- deferと自動dropの順序が仕様書と一致する。
- 割り込み状態、DOM owner、途中作成ノードの手動cleanup分岐を置換できる。

## 関連

- `docs/design/mylang-owned-values-and-drop.md`
- MLC-002 MyLang Flow-Sensitive Borrow And Move Analysis

