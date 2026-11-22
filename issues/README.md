# Issues

このディレクトリは、MyComputer の改善案・設計メモを作業チケットとして管理する場所。

## Ticket List

| ID | Ticket | Status | Notes |
| --- | --- | --- | --- |
| MLC-004 | [MyLang Standard Library Foundation](tickets/MLC-004_mylang-standard-library-foundation.md) | In Progress | フェーズ1〜3 完了（str / bytes / bitset / ringbuf / strbuf）。serial / test の命名は未決。 |
| MLC-018 | [型付き関数値とコールバック](tickets/MLC-018_typed-function-values.md) | Proposed | `i32`関数アドレスをシグネチャ付きの1ワード関数値へ置き換える。 |
| MLC-020 | [ABI透過な不透明newtype](tickets/MLC-020_opaque-newtypes.md) | Proposed | Pid、Fd、NodeId等を基底scalarと同じABIのnominal typeにする。 |
| MLC-025 | [値だけのメモリモデル（共有値、Box、プール）](tickets/MLC-025_values-and-shared-values.md) | Proposed | 段階2。採用した値だけのモデル（`docs/design/mylang-values.md`）の共有値、Box、プール。 |
| MLC-026 | [既存コードを値だけのモデルへ移す](tickets/MLC-026_memory-model-migration.md) | In Progress | アプリ、AppSDK、DOM を移した。OS とカーネルの unsafe はファイル単位のまま。 |
| MLC-027 | [メモリモデルの性能（計測と最適化）](tickets/MLC-027_memory-model-performance.md) | In Progress | rc の前の基準は済み。参照数の最適化、レジスタ割り当て、命令の追加。段階4。 |
| MLC-028 | [構文の整理](tickets/MLC-028_syntax-cleanup.md) | Proposed | `case` の腕のブロック、使われていない予約語、DOM のハンドラ。段階5。 |
| MLT-002 | [MyLang Test Framework（mytest + test declaration）](tickets/MLT-002_mylang-test-framework.md) | Proposed | `*.test.mln`、Jest 風 test declaration、mytest runner、emulator test options を設計・実装する。 |
| MLT-003 | [MyLang Function Mocking Framework](tickets/MLT-003_mylang-di-and-mocking.md) | Proposed | MyLangTestKitを基盤に、production DIを要求しない型付きMock/Spyとtest-build dispatchを設計する。 |
| MLT-004 | [mock.spy / mock.of の function pointer 経由 indirect call 対応](tickets/MLT-004_mock-indirect-call-via-function-pointer.md) | Proposed | 関数ポインタ経由の間接呼び出しがmock/spyのrecordを素通りする既知の制約に、DOM loweringテストで実際にぶつかった件。 |
| MYOS-008 | [MyComputer ネットワーク基盤（仮想 NIC + Ethernet / ARP / IPv4 / ICMP / UDP）](tickets/MYOS-008_network-stack.md) | Proposed | 仮想 NIC から ping、UDP までの最小ネットワークスタック。 |
| MYOS-014 | [デスクトップ UI 刷新（描画プリミティブ・WM・キーボード・スクリーンショット）](tickets/MYOS-014_desktop-visual-overhaul.md) | In Progress | 2D アクセラレータ、キーボード、フォント、テーマ、ウィンドウクロームなど、綺麗な画面の土台。 |

## Status

- `Proposed`: 設計メモ段階。実装前。
- `In Progress`: 実装中。
- `Blocked`: 依存作業待ち。

完了したチケットは削除する（内容はコードと `docs/` に移り、経緯は git の履歴に残る）。
運用の詳細は [`tickets/README.md`](tickets/README.md) を参照。
