# Issues

このディレクトリは、MyComputer の改善案・設計メモを作業チケットとして管理する場所。

## Ticket List

| ID | Ticket | Status | Notes |
| --- | --- | --- | --- |
| MYOS-002 | [割り込み機構（ISA拡張 + タイマー割り込み）](completed/MYOS-002_interrupts.md) | Done | 最小仕様どころか複数割込み原因対応の本格 IRQ ディスパッチャまで実装済み。 |
| MYOS-003 | [Kernel Heap Improvements](completed/MYOS-003_kernel-heap.md) | Stale/Partial | 隣接ブロック統合・アドレス順 free list・exhaustion panic は実装済み。統計・整合性チェックのみ未実装。要再検証。 |
| MLSP-002 | [MyLang LSP Syntax Diagnostics Follow-ups](tickets/MLSP-002_mylang-lsp-syntax-diagnostics.md) | Proposed | LSP 診断・ハイライト周辺の品質改善。 |
| MLC-006 | [共有フロントエンド化](completed/MLC-006_shared-frontend.md) | Superseded | 上書き元の MSE-001 が完了し、独自の残存スコープはゼロ。 |
| MSE-001 | [汎用構文エンジン化](completed/MSE-001_syntax-engine-generic.md) | Done | MySyntaxEngine への改名・文法注釈方式への置換が完了。 |
| MYOS-001 | [DOM 的 OS オブジェクトモデル](completed/MYOS-001_dom-like-os.md) | Stale/Partial | Phase1・2・4は設計通り実装済み。Phase3は click のみ、Phase5未着手。要再検証。 |
| MLC-009 | [MyLang Compiler Diagnostics And Type Intelligence](completed/MLC-009_compiler-diagnostics-and-type-intelligence.md) | Done | AST 位置情報、診断、型チェックを強化して compiler を賢くする。 |
| MYOS-006 | [ファイルシステム（SSD デバイス + ブロックドライバ + MyFileSystem(MFS)）](completed/MYOS-006_filesystem.md) | Done | SSD エミュレーション + カーネル FS。永続ストレージの基盤。 |
| MYOS-008 | [MyComputer ネットワーク基盤（仮想 NIC + Ethernet / ARP / IPv4 / ICMP / UDP）](tickets/MYOS-008_network-stack.md) | Proposed | 仮想 NIC から ping、UDP までの最小ネットワークスタック。 |
| MLC-010 | [MyLang Type Mismatch Diagnostics](completed/MLC-010_compiler-type-mismatch-diagnostics.md) | Done | 代入・二項演算・条件式の型不一致を expected / actual 付きで報告する。 |
| MLC-007 | [MyLang Diagnostic Error Codes](completed/MLC-007_compiler-diagnostic-codes.md) | Done | 診断に安定した error code を付け、テスト・docs・LSP 連携を強くする。 |
| MLC-008 | [MyLang Diagnostic Source Ranges](completed/MLC-008_compiler-diagnostic-ranges.md) | Done | 診断を line / col の一点から source range へ拡張する。 |
| MLC-011 | [MyLang Warning Diagnostics](completed/MLC-011_compiler-warning-diagnostics.md) | Done | warning severity、warning fixture、warnings-as-errors の土台を作る。 |
| MLT-002 | [MyLang Test Framework（mytest + test declaration）](tickets/MLT-002_mylang-test-framework.md) | Proposed | `*.test.mln`、Jest 風 test declaration、mytest runner、emulator test options を設計・実装する。 |
| MLT-001 | [MyLang Test Diagnostics Strategy](completed/MLT-001_mylang-test-diagnostics-strategy.md) | Done | 完了条件3点（移行方針・build/emulator失敗の切り分け・test-all.pyでのE2E区別）を充足。 |
| MLT-003 | [MyLang Function Mocking Framework](tickets/MLT-003_mylang-di-and-mocking.md) | Proposed | MyLangTestKitを基盤に、production DIを要求しない型付きMock/Spyとtest-build dispatchを設計する。 |
| EMU-001 | [エミュレータへのディスプレイ（minifb）追加](completed/EMU-001_emulator-display-minifb.md) | Done | VRAM 定義・描画ループ・`--headless` すべて実装済み。 |
| EMU-002 | [エミュレータのデバイス挙動をリアル化（非同期DMA / 実時間タイマー / VBlank同期）](completed/EMU-002_emulator-realistic-devices.md) | Stale/Partial | タイマー実時間化・SSD DMA非同期化は実装済み。DMA2D fillのみ未対応。要再検証。 |
| EMU-003 | [Virtual Memory & Paging](completed/EMU-003_virtual-memory-mmu.md) | Done | MMU・2段ページング・TLB・syscall命令・カーネル側ページディレクトリまで実装済み。 |
| MLC-014 | [MyLang Function Signature Type Checking](completed/MLC-014_mylang-function-signature-type-checking.md) | Done | 関数 signature に引数型・戻り値型を持たせ、call site の型不一致を semantic で検出する。 |
| MLC-002 | [MyLang Flow-Sensitive Borrow And Move Analysis](tickets/MLC-002_mylang-flow-sensitive-borrow-analysis.md) | In Progress | 分岐、field、関数呼び出し越しの move / borrow 解析を強化する。 |
| MLC-001 | [MyLang Aggregate Initializers And Data Layout](tickets/MLC-001_mylang-aggregate-initializers.md) | Proposed | struct / nested array などの aggregate initializer と data layout を型情報に基づいて扱う。 |
| MLC-003 | [MyLang Package Symbol Resolution](tickets/MLC-003_mylang-package-symbol-resolution.md) | Proposed | package / import / export の symbol table を整備し、import 先の型・signature を semantic に渡す。 |
| MLC-005 | [MyLang Typed Intermediate Representation](tickets/MLC-005_mylang-typed-ir.md) | Proposed | AST 直結 codegen から段階移行できる typed IR の設計と最小実装を進める。 |
| MLSP-001 | [MyLang LSP Semantic Diagnostics Integration](tickets/MLSP-001_mylang-lsp-semantic-diagnostics-integration.md) | Proposed | compiler の semantic diagnostics を JSON / LSP へ接続し、editor でも同じ診断を出す。 |
| MLC-004 | [MyLang Standard Library Foundation](tickets/MLC-004_mylang-standard-library-foundation.md) | In Progress | フェーズ1〜3 完了（str / bytes / bitset / ringbuf / strbuf）。serial / test の命名は未決。 |
| MLC-015 | [MyLang Native String (`str` / `String`)](completed/MLC-015_mylang-native-string.md) | Stale/Partial | フェーズ1（struct値渡し・値返し）は実装済み。フェーズ2以降未着手。要再検証。 |
| MLC-016 | [Cross-Package Types And Constants](completed/MLC-016_cross-package-types-and-constants.md) | Stale/Partial | 定数の越境利用は解決済み。型（struct/typedef）の越境は未解決。要再検証。 |
| MLC-017 | [パーサ状態のコンテキスト化とモジュール解決層](completed/MLC-017_parser-context-and-module-resolution.md) | Stale/Partial | グローバル23→実質1個、4つのハックは置換済み。型の解決層越境のみ未達。要再検証。 |
| MYOS-010 | [MyKernel / MyOS 相互依存の解消](completed/MYOS-010_submodule-dependency-cycle.md) | Done | テストと起動処理を MyOS へ移し、MyKernel から MyOS への参照をゼロにした。 |
| MYOS-011 | [`dom_click_test.py` control-stdio タイムアウト](completed/MYOS-011_dom-click-test-control-stdio-timeout.md) | Stale/Partial | バグ自体は現存。記載の原因（文字インターリーブ）は再現せず、別症状（起動直後ハング）に変化。要再調査。 |
| MLC-012 | [MyLang Diagnostic Code Registry](completed/MLC-012_mylang-diagnostic-code-registry.md) | Done | diagnostic code のカテゴリ採番規則を明文化し、`E04xx`=package 等の予約帯を記録する。 |
| MYOS-004 | [MyKernel DOM UI Automation（Playwright 風テスト基盤）](completed/MYOS-004_mykernel-ui-automation.md) | Done | MyKernel DOM を locator で操作・検証するヘッドレス UI automation 基盤（`system/MyOS/tests/dom_click_test.py` 等）を実装済み。 |
| MDT-001 | [MyDOMTranspiler `.mlx` UI DSL Compiler](completed/MDT-001_mydom-mlx-ui-dsl.md) | Done | JSX 風の OS DOM UI 記述。native `.dom.mln` へ統合し、MyDOMTranspiler は撤去（2026-08-13）。 |
| MYOS-009 | [Kernel UI Separation](completed/MYOS-009_kernel-ui-separation.md) | Done | compositor とデモアプリを分離済み。残っていた `main.mln` 自体の移動は MYOS-010 で完了。 |

## Status

- `Proposed`: 設計メモ段階。実装前。
- `In Progress`: 実装中。
- `Blocked`: 依存作業待ち。
- `Done`: 実装・検証済み。
- `Superseded/Partial`: 後続チケットで一部方針が上書き済み。
- `Stale/Partial`: 一部実装済みだが本文が古く、実際の進捗・残作業を反映していない。`completed/` にあるが未完了。着手前に内容を再検証・書き直すこと。

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
9. MLT-003: MyLangTestKitを追加し、production DIを要求しない型付きfunction Mock / Spyをtest buildへ追加する。
10. MLC-012: diagnostic code の採番規則を明文化する（MLC-014 / MLC-003 が新 code を足す前の土台）。
11. MLC-002: move / borrow 解析を分岐・field・関数呼び出しへ広げる（MLC-014 の signature 拡張に依存）。
12. MLC-001 / MLC-003: aggregate data layout と package symbol 解決を固める。
13. MLC-005: typed IR の導入可否を設計し、段階移行を始める。
14. MLSP-001 / MLC-004: LSP 診断と標準 library の開発体験を整える。
15. MYOS-004: DOM-like UI と headless emulator をつなぎ、Playwright 風 E2E テストを可能にする。
16. MDT-001: OS DOM UI を宣言的に書けるようにする。MyLangCompiler の native `.dom.mln` 構文で実現し、MyDOMTranspiler は撤去済み。
17. MYOS-008: 仮想 NIC と Ethernet / ARP / IPv4 / ICMP / UDP を追加し、headless で通信可能にする。
