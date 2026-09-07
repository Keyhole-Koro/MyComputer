# MBIN v2 実行可能バイナリヘッダ仕様書 (Executable Binary Header Format)

- **著者**: Google Deepmind Antigravity Agent
- **日付**: 2026-09-07
- **ステータス**: 実装完了 (Implemented)
- **対象**: `toolchain/MyLinker`, `system/MyKernel/src/kernel/loader.mln`, `qa/runners/build_toolchain.py`

---

## 1. 背景と課題

これまで MyComputer におけるバイナリ実行形式は、ヘッダを持たない「フラットバイナリ（Flat Binary）」でした。
フラットバイナリには以下の制約とセキュリティ上の課題がありました：

1. **エントリポイントの固定化**:
   - バイナリの先頭（オフセット 0）がそのまま仮想アドレス `0x40000000` にマップされ、先頭バイトから実行される前提となっていました。`main()` や `__START__` が先頭にない場合、先頭にジャンプ命令を置く必要がありました。
2. **セクション境界の喪失**:
   - コード（`.text`）と読み書き可能データ（`.data`）の境界情報が失われており、ローダー側で区別できませんでした。
3. **W^X（Write XOR Execute / DEP）保護の欠如**:
   - コードとデータが同一ページに混在、あるいは全体が単一領域としてマップされるため、全メモリページを `RWX`（Read/Write/Execute）に設定せざるを得ず、バッファオーバーフロー攻撃やスタック上コード実行攻撃に対して脆弱でした。
4. **BSS領域（未初期化データ）の非効率性**:
   - 初期値ゼロの変数のためにバイナリ内にゼロのパディングを含める必要がありました。

これらを解決するため、軽量かつ確実なセグメント分離・メモリ保護を実現する **MBIN v2 (Executable Header)** を策定・実装しました。
なお、エミュレータがアドレス 0 から直接起動するカーネルROM（`main_linked.mbin`）との互換性を保つため、リンカーはオプション指定時（`--header`）にヘッダを付与し、カーネルローダーはマジック番号による自動判定（ヘッダ付きバイナリ / 従来のフラットバイナリへのフォールバック）をサポートします。

---

## 2. ヘッダ構造仕様 (MBIN Header Specification)

ヘッダはファイルの先頭に配置される **32バイト固定長（8ワード）** の構造です。
すべての数値フィールドは MyComputer のネイティブエンディアンである **Big Endian（ビッグエンディアン）** で記録されます。

```
+-------------------------------------------------------+
| Offset | Field        | Type     | Description        |
+--------+--------------+----------+--------------------+
| 0x00   | magic        | uint32_t | 0x4D42494E ('MBIN')|
| 0x04   | version      | uint32_t | 1                  |
| 0x08   | entry_point  | uint32_t | Initial PC (VAddr) |
| 0x0C   | text_offset  | uint32_t | File offset to Text|
| 0x10   | text_size    | uint32_t | Text size in bytes |
| 0x14   | data_offset  | uint32_t | File offset to Data|
| 0x18   | data_size    | uint32_t | Data size in bytes |
| 0x1C   | bss_size     | uint32_t | BSS size in bytes  |
+-------------------------------------------------------+
```

### C/C++ 構造体定義 (`toolchain/MyLinker/inc/ObjectFormat.h`)

```cpp
const uint32_t MBIN_MAGIC = 0x4D42494E; // 'MBIN'
const uint32_t MBIN_VERSION_1 = 1;

#pragma pack(push, 1)
struct MbinHeader {
    uint32_t magic;         // 0x00: マジックナンバー ('MBIN' = 0x4D42494E)
    uint32_t version;       // 0x04: ヘッダバージョン (現在は 1)
    uint32_t entry_point;   // 0x08: 実行開始仮想アドレス (__START__ のアドレス)
    uint32_t text_offset;   // 0x0C: ファイル先頭から .text までのオフセット (通常 32)
    uint32_t text_size;     // 0x10: .text セクションのバイト数
    uint32_t data_offset;   // 0x14: ファイル先頭から .data までのオフセット (32 + text_size)
    uint32_t data_size;     // 0x18: .data セクションのバイト数
    uint32_t bss_size;      // 0x1C: メモリ上でゼロクリアが必要な .bss のバイト数 (現在 0)
};
#pragma pack(pop)
```

### フィールド詳細

1. **`magic` (0x00, 4 bytes)**:
   - ASCII文字列 `"MBIN"`（`0x4D, 0x42, 0x49, 0x4E`）。
   - ローダーは先頭4バイトを読み取り、この値に一致する場合のみヘッダ付きバイナリとして解釈します。
2. **`version` (0x04, 4 bytes)**:
   - ヘッダフォーマットのバージョン番号。現在は `1`。
3. **`entry_point` (0x08, 4 bytes)**:
   - プロセスの初期プログラムカウンタ（PC）。リンカーで解決されたエントリシンボル（通常 `__START__`）の仮想アドレス（例: `0x40000000`）。
4. **`text_offset` (0x0C, 4 bytes)**:
   - ファイル先頭からの機械語コード領域（`.text`）の開始バイト位置。通常はヘッダの直後である `32`（`0x00000020`）。
5. **`text_size` (0x10, 4 bytes)**:
   - 機械語コードの有効バイト数。
6. **`data_offset` (0x14, 4 bytes)**:
   - ファイル先頭からの初期化済みデータ領域（`.data`）の開始バイト位置。ファイル内ではパディングなしで `text_offset + text_size` に連続配置されます。
7. **`data_size` (0x18, 4 bytes)**:
   - 初期化済みデータのバイト数。
8. **`bss_size` (0x1C, 4 bytes)**:
   - 未初期化データ（`.bss`）のバイト数。ファイル上にはデータを保持せず、ローダーがメモリ確保時にゼロクリアします。

---

## 3. メモリ保護アーキテクチャ (W^X / DEP)

MyComputer の MMU（2-Level Paging）は、ページテーブルエントリ（PTE）ごとに以下のパーミッションビットを備えています：
- `PTE_VALID (0x01)`: ページが存在するか
- `PTE_WRITABLE (0x02)`: 書き込み可能か (1 = RW, 0 = Read Only)
- `PTE_EXEC (0x04)`: 実行可能か (1 = Executable, 0 = No Exec)
- `PTE_USER (0x08)`: ユーザーモードアクセス可能か (1 = User, 0 = Kernel Only)

MBIN v2 では、各セグメントをページ（4096バイト = 4 KiB）境界で分離し、厳格な **W^X (Write XOR Execute)** 保護を適用します：

```
Virtual Address Space:
+------------------------+ 0x7FFFFFE0 (USER_STACK_TOP)
| User Stack (4KB)       | PTE: 0x0B (VALID | WRITABLE | USER) [RW, No-Exec]
+------------------------+ 0x7FFFF000 (USER_STACK_BASE)
|                        |
|        ...             |
|                        |
+------------------------+ 0x41000000 (USER_HEAP_BASE)
| User Heap (brk)        | PTE: 0x0B (VALID | WRITABLE | USER) [RW, No-Exec]
+------------------------+
|                        |
+------------------------+ data_vaddr + align_4k(data_size)
| Data / BSS Segment     | PTE: 0x0B (VALID | WRITABLE | USER) [RW, No-Exec]
+------------------------+ data_vaddr = 0x40000000 + align_4k(text_size)
| Text (Code) Segment    | PTE: 0x0D (VALID | EXEC | USER)     [RX, No-Write]
+------------------------+ 0x40000000 (USER_CODE_BASE)
```

### パーミッション設計のセキュリティ効果

1. **Textセクションの保護 (`0x0D` = Valid | Exec | User)**:
   - 実行可能だが**書き込み不可**。
   - プログラムが自身のコードを改ざんする（セルフモディファイングコードや不正なポインタによるコード破壊）ことや、攻撃者によるシェルコード注入をハードウェアレベルで完全に阻止します。
2. **Data / BSSセクションの保護 (`0x0B` = Valid | Writable | User)**:
   - 読み書き可能だが**実行不可**。
   - グローバル変数やデータ領域に配置されたコードの実行を試みた場合、即座に MMU Page Fault（原因: 実行不可違反）が発生し、カーネルによってプロセスが終了されます。
3. **スタック領域の保護 (`0x0B` = Valid | Writable | User)**:
   - 読み書き可能だが**実行不可**。
   - スタックバッファオーバーフローによりスタック上にリターンアドレスと悪意あるシェルコードを注入されても、シェルコードへ制御が移った瞬間に Page Fault となり、攻撃を無効化します。

---

## 4. ツールチェーンの対応 (`toolchain/MyLinker`)

### ページアライメントとシンボル解決
リンカーに `--header` オプションが指定された場合、リンカーは以下の処理を行います：

1. **Textセクション仮想アドレス**:
   - `text_base_addr = base_addr` (通常 `0x40000000`)
2. **Dataセクション仮想アドレス**:
   - Textセクションの終端を 4096 バイト境界に切り上げます：
     $$\text{data\_base\_addr} = (\text{text\_base\_addr} + \text{total\_text\_size} + 4095) \ \& \ \sim 4095$$
   - これにより、データシンボル（グローバル変数や文字列定数など）のアドレス解決が、ページ分離後の仮想アドレスと完全に一致します。
3. **ヘッダ出力**:
   - ファイルの先頭 32 バイトに `MbinHeader`（Big Endian）を出力します。
   - 続いて `text_section` の全バイトを出力し、その直後にパディングなしで `data_section` の全バイトを出力します。ファイルサイズは不要に肥大化しません。

### コマンドライン仕様
```bash
mllinker [--map <map_file>] [--base <hex_addr>] [--header] <output.bin> <input1.obj> ...
```
- `--header`: MBIN v2 ヘッダをファイル先頭に付与し、Data セクションのベースアドレスを 4KB ページ境界にアラインします。
- 省略時: 従来のフラットバイナリを出力します（カーネルROMビルド用）。

---

## 5. カーネルローダーの実装 (`system/MyKernel/src/kernel/loader.mln`)

### ロード手順

1. **ヘッダ検証**:
   - バイナリの先頭 4 バイトを読み取り、`0x4D42494E` と比較します。
   - 一致しない場合：従来のフラットバイナリとして `USER_CODE_BASE` (0x40000000) に `PTE_USER_RWX` でロード（後方互換性維持）。
   - 一致する場合：
     - バージョン確認（`version == 1`）。
     - 各セクションのサイズ・オフセットが入力バッファの範囲内か境界検査。
2. **ページテーブル設定**:
   - ユーザープロセスの Page Directory を作成し、カーネル空間（RAM, MMIO, VRAM）をアイデンティティマップ。
3. **Textセクションのマッピング (RX)**:
   - 仮想アドレス `USER_CODE_BASE` (0x40000000) から `text_size` バイト分の物理フレームを確保。
   - ファイルの `text_offset` からデータをコピー。
   - PTE フラグに `PTE_USER_RX` (`0x0D`) を設定。
4. **Dataセクションのマッピング (RW)**:
   - `data_size > 0` の場合、仮想アドレス `USER_CODE_BASE + align_4k(text_size)` から `data_size` バイト分の物理フレームを確保。
   - ファイルの `data_offset` からデータをコピー。
   - PTE フラグに `PTE_USER_RW` (`0x0B`) を設定。
5. **BSSセクションのゼロクリア**:
   - `bss_size > 0` の場合、ゼロクリアされたページを Data の終端に `PTE_USER_RW` でマッピング。
6. **スタック・ヒープ初期化**:
   - スタックページ（`0x7FFFF000`）を `PTE_USER_RW` でマッピング。
   - `heap_break` に初期ヒープベース（`0x41000000`）を設定。
7. **プロセスの初期化とエントリポイント設定**:
   - ヘッダの `entry_point` を `user_entry` および初期トラップフレームの PC に設定。
   - スケジューラーにタスクを登録し、Ready 状態に遷移。

### エラーハンドリング (`Result<_, LoaderError>`)

C言語スタイルのマジックナンバー（`-1` や `0/NULL` 戻り値）や大域的なエラー整数定数を排し、MyLang の型システム・標準ライブラリ（`MyStdLib`）が提供する代数的データ型 `Result<T, E>` を採用しています。

初期実装ではファイルシステム層のエラー型 `FsError` を借用していましたが、レイヤーの独立性（カーネル・メモリ管理層がファイルシステム層に依存する逆依存の排除）と関心事の分離のため、各コンポーネントで固有のエラー型を定義・利用するようにリファクタリングされました：

- **MMU層 (`system/MyKernel/src/mm/mmu.mln`)**:
  - エラー型:
    ```mln
    export enum MmuError {
        AllocFailed,            // 物理フレーム / Page Table 確保失敗（OOM）
        InvalidDirectory,       // pd_addr == 0 などの不正なページディレクトリ
        UnalignedAddress(i32),  // アドレスが 4KB 境界に揃っていない (不正アドレスをペイロードに保持)
    }
    ```
  - `mmu.alloc_page()`: `Result<i32, MmuError>`
  - `mmu.create_page_directory()`: `Result<i32, MmuError>`
  - `mmu.map_page()`: `Result<_, MmuError>` (戻り値なし/Unit)
  - `mmu.map_range()`: `Result<_, MmuError>` (戻り値なし/Unit)
  - `mmu.setup_identity_kernel_mapping()`: `Result<_, MmuError>` (戻り値なし/Unit)
- **プロセス管理層 (`system/MyKernel/src/kernel/process.mln`)**:
  - エラー型:
    ```mln
    export enum ProcessError {
        NoFreeSlot,
        InvalidPid(i32),
    }
    ```
  - `process.alloc_proc()`: `Result<i32, ProcessError>`
- **ローダー層 (`system/MyKernel/src/kernel/loader.mln`)**:
  - エラー型:
    ```mln
    export enum LoaderError {
        ProcSlotFull,        // プロセススロット枯渇
        OutOfMemory,         // メモリ不足 (ページディレクトリ / フレーム / スタック確保失敗)
        MmuInvalidDir,       // MMU内部エラー: 不正なページディレクトリ (pd == 0)
        MmuUnaligned(i32),   // MMU内部エラー: アドレスのアライメント不正 (不正アドレス)
        InvalidHeader(i32),  // MBINヘッダ無効または未サポートバージョン (不正なバージョン番号)
        InvalidBounds(i32),  // セクション境界がバッファサイズを超過 (バッファサイズ)
        SpawnTaskFailed,     // スケジューラタスク生成失敗
    }
    ```
  - `loader.map_segment()`: `Result<_, LoaderError>` (戻り値なし/Unit)
  - `loader.spawn_from_buffer()`: `Result<i32, LoaderError>`
    - 成功時: `Ok(pid)`
    - 失敗時: `Err(LoaderError)`

MyLang コンパイラの機能強化により、ネストしたバリアントのパターンマッチ構文 `case result of { Ok(v) -> ...; Err(AllocFailed) -> ...; Err(InvalidHeader(v)) -> ...; }` がサポートされ、以前のような `case e of { ... }` というネストが不要になりました。

さらに、以下の言語機能が整備されました：
1. **ユニット型 `Result<_, E>` と `return Ok(_);`**:
   成功時に意味のある値を返さない関数（Rust の `Result<(), E>` 相当）において、型引数にワイルドカード型 `_` を指定した `Result<_, E>` と `return Ok(_);` が利用可能になりました。パターンマッチでも `Ok(_) -> ...` として受け取れ、ダミー値（`0` など）を排除した自然で安全な記述が可能です。
2. **スコープ修飾バリアント (`Enum::Variant`)**:
   `MmuError::AllocFailed` や `LoaderError::OutOfMemory` のように列挙型名で修飾した記法に対応しました。これにより、異なる enum 間で同名のバリアントが存在しても衝突せず、関数内で直接 `return Err(LoaderError::OutOfMemory);` のように返却できます。

---

## 6. まとめと今後の展望

MBIN v2 ヘッダの導入により、MyComputer は以下を達成しました：
- **安全なメモリ保護 (W^X / DEP)**: コード領域の書き換え防止、データ・スタック領域でのコード実行防止
- **完全な後方互換性**: カーネルROMおよび既存フラットバイナリの継続動作
- **決定論的なエントリポイント設定**: `__START__` シンボルの自動バインド

将来の拡張としては、動的リンク用のシンボルテーブルセクションの追加や、スレッドローカルストレージ（TLS）、ELF コンバーター（`elf2mbin`）のサポートが考えられます。
