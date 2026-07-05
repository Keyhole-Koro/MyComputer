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
| ISSUE-008 | [ファイルシステム（SSD デバイス + ブロックドライバ + MyFileSystem(MFS)）](tickets/filesystem.md) | Proposed | SSD エミュレーション + カーネル FS。永続ストレージの基盤。 |
| ISSUE-009 | [MyLang Type Mismatch Diagnostics](completed/compiler-type-mismatch-diagnostics.md) | Done | 代入・二項演算・条件式の型不一致を expected / actual 付きで報告する。 |
| ISSUE-010 | [MyLang Diagnostic Error Codes](completed/compiler-diagnostic-codes.md) | Done | 診断に安定した error code を付け、テスト・docs・LSP 連携を強くする。 |
| ISSUE-011 | [MyLang Diagnostic Source Ranges](completed/compiler-diagnostic-ranges.md) | Done | 診断を line / col の一点から source range へ拡張する。 |
| ISSUE-012 | [MyLang Warning Diagnostics](completed/compiler-warning-diagnostics.md) | Done | warning severity、warning fixture、warnings-as-errors の土台を作る。 |
| ISSUE-013 | [MyLang Test Framework（mytest + test declaration）](tickets/mylang-test-framework.md) | Proposed | `*.test.mln`、Jest 風 test declaration、mytest runner、emulator test options を設計・実装する。 |
| ISSUE-014 | [MyLang Test Diagnostics Strategy](tickets/mylang-test-diagnostics-strategy.md) | Proposed | `.test.mln` E2E とホスト側テストの役割分担、失敗時の切り分け方針を整理する。 |
| ISSUE-015 | [エミュレータのデバイス挙動をリアル化（非同期DMA / 実時間タイマー / VBlank同期）](tickets/emulator-realistic-devices.md) | Proposed | DMA を BUSY→DONE→完了割込に、タイマーを実時間ベースに、SWAP を VBlank 同期に。 |
| ISSUE-016 | [MyLang Function Signature Type Checking](tickets/mylang-function-signature-type-checking.md) | Proposed | 関数 signature に引数型・戻り値型を持たせ、call site の型不一致を semantic で検出する。 |
| ISSUE-017 | [MyLang Flow-Sensitive Borrow And Move Analysis](tickets/mylang-flow-sensitive-borrow-analysis.md) | Proposed | 分岐、field、関数呼び出し越しの move / borrow 解析を強化する。 |
| ISSUE-018 | [MyLang Aggregate Initializers And Data Layout](tickets/mylang-aggregate-initializers.md) | Proposed | struct / nested array などの aggregate initializer と data layout を型情報に基づいて扱う。 |
| ISSUE-019 | [MyLang Package Symbol Resolution](tickets/mylang-package-symbol-resolution.md) | Proposed | package / import / export の symbol table を整備し、import 先の型・signature を semantic に渡す。 |
| ISSUE-020 | [MyLang Typed Intermediate Representation](tickets/mylang-typed-ir.md) | Proposed | AST 直結 codegen から段階移行できる typed IR の設計と最小実装を進める。 |
| ISSUE-021 | [MyLang LSP Semantic Diagnostics Integration](tickets/mylang-lsp-semantic-diagnostics-integration.md) | Proposed | compiler の semantic diagnostics を JSON / LSP へ接続し、editor でも同じ診断を出す。 |
| ISSUE-022 | [MyLang Standard Library Foundation](tickets/mylang-standard-library-foundation.md) | Proposed | std / kernel / test library の境界と最小 API を整理する。 |
| ISSUE-023 | [MyLang Diagnostic Code Registry](completed/mylang-diagnostic-code-registry.md) | Done | diagnostic code のカテゴリ採番規則を明文化し、`E04xx`=package 等の予約帯を記録する。 |

## Status

- `Proposed`: 設計メモ段階。実装前。
- `In Progress`: 実装中。
- `Blocked`: 依存作業待ち。
- `Done`: 実装・検証済み。
- `Superseded/Partial`: 後続チケットで一部方針が上書き済み。

`Done` になったチケットのファイルは [`tickets/`](tickets/) から [`completed/`](completed/) へ
`git mv` で移動し、上の索引リンクも `completed/...` に更新する。運用詳細は
[`tickets/README.md`](tickets/README.md) を参照。

## Suggested Order

1. ISSUE-002: Kernel heap を安定させる。
2. ISSUE-001: 割り込みとタイマーの土台を作る。
3. ISSUE-006: Kernel Object Tree の最小実装を始める。
4. ISSUE-007: compiler の診断と型チェックを強化する。
5. ISSUE-005 / ISSUE-003: mylang UI リテラルや LSP 体験に必要な構文基盤を整える。
6. ISSUE-008: ファイルシステムを実装する（SSD + ブロックドライバ + MyFileSystem(MFS)）。
7. ISSUE-013: Python runner を置き換える MyLang test framework を整備する。
8. ISSUE-014: `mytest` の診断性と、`.test.mln` 化する範囲を整理する。
9. ISSUE-023: diagnostic code の採番規則を明文化する（ISSUE-016 / ISSUE-019 が新 code を足す前の土台）。
10. ISSUE-016: 関数 signature の型情報を semantic に持たせ、API 呼び出しの型不一致を早く落とす。
11. ISSUE-017: move / borrow 解析を分岐・field・関数呼び出しへ広げる（ISSUE-016 の signature 拡張に依存）。
12. ISSUE-018 / ISSUE-019: aggregate data layout と package symbol 解決を固める。
13. ISSUE-020: typed IR の導入可否を設計し、段階移行を始める。
14. ISSUE-021 / ISSUE-022: LSP 診断と標準 library の開発体験を整える。
