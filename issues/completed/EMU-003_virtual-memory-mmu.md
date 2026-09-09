# Virtual Memory & Paging (EMU-003)

> **[DONE 2026-09-09] 実装済みのため tickets/ から completed/ へ移動。**
> `mmu.rs` に2段ページテーブル・TLB（64エントリ）・特権チェックを実装済み、
> `Opcode::Syscall` 実装済み、`MyKernel/src/mm/mmu.mln` に
> `create_page_directory` / `enable_paging`、`loader.mln` がページフォールト
> 駆動のユーザープロセスロードまで実装済み。完了条件を commit `464eddc
> "feat(mm): add the MMU and 2-level paging layer (EMU-003)"` が明示的に満たす。

## 背景・目的
MyComputer は現在フラットな物理メモリモデルで動作しており、特権モードやメモリ保護の概念がありません。
将来的に隔離されたマルチプロセス（ユーザー空間アプリケーション）をサポートするため、仮想メモリ管理ユニット（MMU）とページング機構、およびユーザー/カーネルモードの特権リングを実装します。

## 詳細設計
設計の詳細については、以下のドキュメントを参照してください：
[`docs/design/virtual-memory-mmu.md`](../../docs/design/virtual-memory-mmu.md)

## 完了条件
- `MyEmulator` 側に MMU、2段ページテーブル、TLB のエミュレーションが実装されていること。
- `SR` レジスタに特権モードが追加され、ユーザーモードからの特権命令や I/O アクセスがブロックされること。
- 新しい `syscall` 命令で安全にカーネルモードへ遷移できること。
- `MyKernel` 側でページディレクトリアロケータが実装され、ページングを有効化してブートできること。
