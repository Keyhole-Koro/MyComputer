# Issues

このディレクトリは、MyComputer の改善案・設計メモを作業チケットとして管理する場所。

## Ticket List

| ID | Ticket | Status | Notes |
| --- | --- | --- | --- |
| MYOS-002 | [割り込み機構（ISA拡張 + タイマー割り込み）](tickets/MYOS-002_interrupts.md) | Proposed | タスク管理、入力駆動、例外処理の前提。 |
| MYOS-003 | [Kernel Heap Improvements](tickets/MYOS-003_kernel-heap.md) | Proposed | DOM 的 OS オブジェクトモデルの前提になる動的メモリ基盤。 |
| MLSP-002 | [MyLang LSP Syntax Diagnostics Follow-ups](tickets/MLSP-002_mylang-lsp-syntax-diagnostics.md) | Proposed | LSP 診断・ハイライト周辺の品質改善。 |
| MLC-006 | [共有フロントエンド化](tickets/MLC-006_shared-frontend.md) | Superseded/Partial | `tickets/MSE-001_syntax-engine-generic.md` の方針で一部上書き。 |
| MSE-001 | [汎用構文エンジン化](tickets/MSE-001_syntax-engine-generic.md) | Proposed | MySyntaxEngine を多言語向け汎用エンジンとして整理。 |
| MYOS-001 | [DOM 的 OS オブジェクトモデル](tickets/MYOS-001_dom-like-os.md) | Proposed | OS 状態、UI、プロセス、デバイスをツリーで扱う長期設計。 |
| MLC-009 | [MyLang Compiler Diagnostics And Type Intelligence](completed/MLC-009_compiler-diagnostics-and-type-intelligence.md) | Done | AST 位置情報、診断、型チェックを強化して compiler を賢くする。 |
| MYOS-006 | [ファイルシステム（SSD デバイス + ブロックドライバ + MyFileSystem(MFS)）](completed/MYOS-006_filesystem.md) | Done | SSD エミュレーション + カーネル FS。永続ストレージの基盤。 |
| MYOS-008 | [MyComputer ネットワーク基盤（仮想 NIC + Ethernet / ARP / IPv4 / ICMP / UDP）](tickets/MYOS-008_network-stack.md) | Proposed | 仮想 NIC から ping、UDP までの最小ネットワークスタック。 |
| MLC-010 | [MyLang Type Mismatch Diagnostics](completed/MLC-010_compiler-type-mismatch-diagnostics.md) | Done | 代入・二項演算・条件式の型不一致を expected / actual 付きで報告する。 |
| MLC-007 | [MyLang Diagnostic Error Codes](completed/MLC-007_compiler-diagnostic-codes.md) | Done | 診断に安定した error code を付け、テスト・docs・LSP 連携を強くする。 |
| MLC-008 | [MyLang Diagnostic Source Ranges](completed/MLC-008_compiler-diagnostic-ranges.md) | Done | 診断を line / col の一点から source range へ拡張する。 |
| MLC-011 | [MyLang Warning Diagnostics](completed/MLC-011_compiler-warning-diagnostics.md) | Done | warning severity、warning fixture、warnings-as-errors の土台を作る。 |
| MLT-002 | [MyLang Test Framework（mytest + test declaration）](tickets/MLT-002_mylang-test-framework.md) | Proposed | `*.test.mln`、Jest 風 test declaration、mytest runner、emulator test options を設計・実装する。 |
| MLT-001 | [MyLang Test Diagnostics Strategy](tickets/MLT-001_mylang-test-diagnostics-strategy.md) | Proposed | `.test.mln` E2E とホスト側テストの役割分担、失敗時の切り分け方針を整理する。 |
| EMU-002 | [エミュレータのデバイス挙動をリアル化（非同期DMA / 実時間タイマー / VBlank同期）](tickets/EMU-002_emulator-realistic-devices.md) | Proposed | DMA を BUSY→DONE→完了割込に、タイマーを実時間ベースに、SWAP を VBlank 同期に。 |
| MLC-014 | [MyLang Function Signature Type Checking](completed/MLC-014_mylang-function-signature-type-checking.md) | Done | 関数 signature に引数型・戻り値型を持たせ、call site の型不一致を semantic で検出する。 |
| MLC-002 | [MyLang Flow-Sensitive Borrow And Move Analysis](tickets/MLC-002_mylang-flow-sensitive-borrow-analysis.md) | In Progress | 分岐、field、関数呼び出し越しの move / borrow 解析を強化する。 |
| MLC-001 | [MyLang Aggregate Initializers And Data Layout](tickets/MLC-001_mylang-aggregate-initializers.md) | Proposed | struct / nested array などの aggregate initializer と data layout を型情報に基づいて扱う。 |
| MLC-003 | [MyLang Package Symbol Resolution](tickets/MLC-003_mylang-package-symbol-resolution.md) | Proposed | package / import / export の symbol table を整備し、import 先の型・signature を semantic に渡す。 |
| MLC-005 | [MyLang Typed Intermediate Representation](tickets/MLC-005_mylang-typed-ir.md) | Proposed | AST 直結 codegen から段階移行できる typed IR の設計と最小実装を進める。 |
| MLSP-001 | [MyLang LSP Semantic Diagnostics Integration](tickets/MLSP-001_mylang-lsp-semantic-diagnostics-integration.md) | Proposed | compiler の semantic diagnostics を JSON / LSP へ接続し、editor でも同じ診断を出す。 |
| MLC-004 | [MyLang Standard Library Foundation](tickets/MLC-004_mylang-standard-library-foundation.md) | Proposed | std / kernel / test library の境界と最小 API を整理する。 |
| MLC-012 | [MyLang Diagnostic Code Registry](completed/MLC-012_mylang-diagnostic-code-registry.md) | Done | diagnostic code のカテゴリ採番規則を明文化し、`E04xx`=package 等の予約帯を記録する。 |
| MYOS-004 | [MyKernel DOM UI Automation（Playwright 風テスト基盤）](tickets/MYOS-004_mykernel-ui-automation.md) | Proposed | MyKernel DOM を locator で操作・検証するヘッドレス UI automation 基盤を作る。 |
| MDT-001 | [MyDOMTranspiler `.mlx` UI DSL Compiler](tickets/MDT-001_mydom-mlx-ui-dsl.md) | In Progress | JSX 風の OS DOM UI 記述を `.mlx` として書き、MyDOMTranspiler で MyLang source へ変換する。 |

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

1. MYOS-003: Kernel heap を安定させる。
2. MYOS-002: 割り込みとタイマーの土台を作る。
3. MYOS-001: Kernel Object Tree の最小実装を始める。
4. MLC-009: compiler の診断と型チェックを強化する。
5. MSE-001 / MLSP-002: mylang UI リテラルや LSP 体験に必要な構文基盤を整える。
6. MYOS-006: ファイルシステムを実装する（SSD + ブロックドライバ + MyFileSystem(MFS)）。
7. MLT-002: Python runner を置き換える MyLang test framework を整備する。
8. MLT-001: `mytest` の診断性と、`.test.mln` 化する範囲を整理する。
9. MLC-012: diagnostic code の採番規則を明文化する（MLC-014 / MLC-003 が新 code を足す前の土台）。
10. MLC-002: move / borrow 解析を分岐・field・関数呼び出しへ広げる（MLC-014 の signature 拡張に依存）。
11. MLC-001 / MLC-003: aggregate data layout と package symbol 解決を固める。
12. MLC-005: typed IR の導入可否を設計し、段階移行を始める。
13. MLSP-001 / MLC-004: LSP 診断と標準 library の開発体験を整える。
14. MYOS-004: DOM-like UI と headless emulator をつなぎ、Playwright 風 E2E テストを可能にする。
15. MDT-001: MyDOMTranspiler で `.mlx` UI DSL を MyLang source へ変換し、OS DOM UI を宣言的に書けるようにする。
16. MYOS-008: 仮想 NIC と Ethernet / ARP / IPv4 / ICMP / UDP を追加し、headless で通信可能にする。
