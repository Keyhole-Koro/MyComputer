# Issues

このディレクトリは、MyComputer の改善案・設計メモを作業チケットとして管理する場所。

## Ticket List

| ID | Ticket | Status | Notes |
| --- | --- | --- | --- |
| ISSUE-001 | [割り込み機構（ISA拡張 + タイマー割り込み）](tickets/interrupts.md) | Proposed | タスク管理、入力駆動、例外処理の前提。 |
| ISSUE-002 | [Kernel Heap Improvements](tickets/kernel-heap.md) | Proposed | DOM 的 OS オブジェクトモデルの前提になる動的メモリ基盤。 |
| ISSUE-003 | [MyLang LSP Syntax Diagnostics Follow-ups](tickets/mylang-lsp-syntax-diagnostics.md) | Proposed | LSP 診断・ハイライト周辺の品質改善。 |
| ISSUE-004 | [共有フロントエンド化](tickets/shared-frontend.md) | Superseded/Partial | `tickets/syntax-engine-generic.md` の方針で一部上書き。 |
| ISSUE-005 | [汎用構文エンジン化](tickets/syntax-engine-generic.md) | Proposed | MySyntaxEngine を多言語向け汎用エンジンとして整理。 |
| ISSUE-006 | [DOM 的 OS オブジェクトモデル](tickets/dom-like-os.md) | Proposed | OS 状態、UI、プロセス、デバイスをツリーで扱う長期設計。 |
| ISSUE-007 | [MyLang Compiler Diagnostics And Type Intelligence](tickets/compiler-diagnostics-and-type-intelligence.md) | Proposed | AST 位置情報、診断、型チェックを強化して compiler を賢くする。 |

## Status

- `Proposed`: 設計メモ段階。実装前。
- `In Progress`: 実装中。
- `Blocked`: 依存作業待ち。
- `Done`: 実装・検証済み。
- `Superseded/Partial`: 後続チケットで一部方針が上書き済み。

## Suggested Order

1. ISSUE-002: Kernel heap を安定させる。
2. ISSUE-001: 割り込みとタイマーの土台を作る。
3. ISSUE-006: Kernel Object Tree の最小実装を始める。
4. ISSUE-007: compiler の診断と型チェックを強化する。
5. ISSUE-005 / ISSUE-003: mylang UI リテラルや LSP 体験に必要な構文基盤を整える。
