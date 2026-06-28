# ファイルシステム（SSD デバイス + ブロックドライバ + SimpleFS）

現状の MyComputer にはストレージが一切無い。アーキテクチャ仕様には SSD デバイスが
`0x24000010` に定義されているが、エミュレータ・カーネルともに未実装。ファイルの永続化、
設定の保存、将来のシェルや `init` ファイルの読み込みなどの前提インフラになる。

ゴール: **エミュレータ側の SSD ブロックデバイス**を作り、カーネルに**ブロックドライバ**と
**SimpleFS**を実装する。カーネル起動時にマウントし、ファイルの作成・読み書き・削除・
一覧表示ができることを確認する。

## 設計判断

- **ブロックサイズ**: 256 bytes。この小さなアーキテクチャに合わせたサイズ。
- **ディスク容量**: 64 KB（256 ブロック）。`--disk disk.img` CLI引数でホストファイルを
  ディスクイメージとして使用。
- **I/O方式**: メモリマップド I/O。CMD レジスタ書き込みで即座に DMA 的ブロック転送。
- **FS 種類**: SimpleFS。FAT 的なブロックチェインによるシンプルな独自FS。
  ディレクトリ階層無し（フラット）、最大32ファイル。
- **自動フォーマット**: `init()` 時にスーパーブロックのマジックナンバーが無ければ
  自動的に `format()` する。

## 調査で判明している事実

- アーキテクチャ仕様の I/O マップ: SSD は `0x24000010`（`architecture/README.md`）。
- エミュレータの I/O 範囲: `IO_BASE(0x24000000)` – `IO_END_INCLUSIVE(0x240000FF)`。
  シリアル (`0x24000000–0x05`) と IRQ ベクタ (`0x24000080`) のみ使用中。
  `0x24000010–0x2400001F` は空き。
- エミュレータの RAM: `HashMap<u32, u8>` でスパース管理。バス経由の読み書き関数あり。
- カーネルのメモリアクセス: `mem.write_word(addr, val)` / `mem.read_word(addr)` で
  メモリマップド I/O を操作（`libs/serial.mln` と同じパターン）。
- ヒープ: `heap.alloc(size)` / `heap.free(ptr)` で動的バッファ確保可能。
- DOM: `dom.create_node(kind, name)` / `dom.append_child(parent, child)` でカーネル
  オブジェクトツリーに登録可能。`NODE_DIRECTORY` (4) / `NODE_FILE` (5) が定義済み。

## 実装の概要

### Layer 1: MyEmulator — SSD デバイスエミュレーション（Rust）

#### I/O レジスタマップ

| アドレス | 名前 | R/W | 説明 |
|----------|------|-----|------|
| `0x24000010` | `SSD_CMD` | W | コマンド (1=READ, 2=WRITE) |
| `0x24000014` | `SSD_BLOCK` | W | ブロック番号 (0-indexed) |
| `0x24000018` | `SSD_ADDR` | W | RAM 上のバッファアドレス |
| `0x2400001C` | `SSD_STATUS` | R | ステータス (0=idle, 2=done, 0xFF=error) |

#### 動作仕様

- CMD 書き込みで即座にブロック転送を実行（同期 DMA）。
- READ (CMD=1): `disk[block*256 .. +256]` → `RAM[addr .. +256]`
- WRITE (CMD=2): `RAM[addr .. +256]` → `disk[block*256 .. +256]`、ホストファイルに flush。
- 成功時 STATUS=2、エラー時 STATUS=0xFF。
- `--disk` 未指定時は SSD 無効（STATUS 常に 0xFF）。
- ディスクイメージファイルが存在しなければ 64KB ゼロ埋めで新規作成。

#### 変更ファイル

- `constants.rs`: SSD アドレス定数追加。
- `machine/ssd.rs`（新規）: `SsdDevice` 構造体。ディスクイメージの読み書きロジック。
- `machine/mod.rs`: `mod ssd;`、`ssd` フィールド追加、`load_disk()` メソッド。
- `machine/memory_bus.rs`: SSD レジスタへの読み書きルーティング追加。
- `cli.rs`: `--disk <file>` 引数追加。
- `app.rs`: ディスクイメージのロード処理。

### Layer 2: MyKernel — ブロックドライバ（`libs/ssd.mln`）

```
package ssd;
export i32 BLOCK_SIZE = 256;
export i32 read_block(i32 block_num, i32 buf_addr)   — 1ブロック読み出し（0=成功, -1=エラー）
export i32 write_block(i32 block_num, i32 buf_addr)   — 1ブロック書き込み（0=成功, -1=エラー）
```

I/O レジスタに BLOCK, ADDR, CMD を順に書き込み、STATUS を読んで結果を返す。
`libs/serial.mln` と同じメモリマップド I/O パターン。

### Layer 3: MyKernel — SimpleFS（`libs/fs.mln`）

#### ディスクレイアウト

| ブロック # | 用途 |
|------------|------|
| 0 | Superblock (マジック `0x53464653` = 'SFFS', version=1, max_files=32) |
| 1–4 | File Entry Table (32 エントリ × 32 bytes = 1024 bytes = 4 ブロック) |
| 5 | Block Allocation Bitmap (256 ビット = 32 bytes) |
| 6–255 | Data blocks |

#### File Entry（32 bytes）

| Offset | Size | Field |
|--------|------|-------|
| 0 | 16 | filename (null-terminated) |
| 16 | 4 | first_block (0 = free entry) |
| 20 | 4 | file_size (bytes) |
| 24 | 4 | flags (reserved) |
| 28 | 4 | reserved |

#### データブロックチェイン

各データブロック:
- `bytes[0..4]` = next_block ポインタ (0 = チェイン終端)
- `bytes[4..256]` = データペイロード (252 bytes/block)

#### API

```
export void init()                         — FS 初期化/マウント（マジック不一致なら自動 format）
export void format()                       — ディスクフォーマット
export i32 create(ref char filename)       — ファイル作成、fd を返す
export i32 open(ref char filename)         — ファイルを開く、fd を返す (-1 = not found)
export i32 read(i32 fd, i32 buf, i32 size) — 読み出し、読んだバイト数を返す
export i32 write(i32 fd, i32 buf, i32 size)— 書き込み（append）、書いたバイト数を返す
export void close(i32 fd)                  — ファイルを閉じる
export void list()                         — ファイル一覧をシリアル出力
export i32 remove(ref char filename)       — ファイル削除 (0=成功, -1=失敗)
```

#### 内部ヘルパー

- `str_match(ref char a, i32 b_addr, i32 max_len)` — 文字列比較
- `alloc_block()` — 空きブロック確保、ビットマップ更新
- `free_block(block_num)` — ブロック解放、ビットマップ更新
- `find_free_fd()` — 空き fd スロット検索
- `find_entry_by_name(ref char filename)` — ファイルエントリ検索

#### オープンファイルテーブル（インメモリ）

```
i32 FD_MAX = 8;
i32 fd_entry_idx[8];     // file entry index (-1 = unused)
i32 fd_offset[8];        // current read/write offset
i32 fd_first_block[8];   // first block of file
i32 fd_file_size[8];     // file size in bytes
```

### Layer 4: カーネル統合

- `kernel_main.mln`: `import fs` 追加、`kernel_init()` 内で `fs.init()` 呼び出し。
- `libs/dom.mln`: `init()` に `NODE_DIRECTORY` の `"fs"` ノードを device 配下に追加。

## 実装時に詰める点

- write 操作のセマンティクス: 純粋な append か、offset ベースのランダムライトか。
  最小版は append のみで十分。
- ファイルサイズ上限: ブロックチェインなので理論上は全データブロック分 (250 blocks ×
  252 bytes ≈ 63KB)。実用上は問題ない。
- 同名ファイルの create 時の挙動: エラーを返すか上書きか。最小版はエラーを返す。
- ディスクイメージの永続化タイミング: WRITE コマンド実行時に即座にホストファイルへ flush。

## 検証

1. **エミュレータ単体**: SSD レジスタへの読み書きが正しく動作すること。`--disk` 未指定時に
   STATUS=0xFF が返ること。ブロック read/write でディスクイメージが正しく更新されること。
2. **ブロックドライバ**: カーネルから `ssd.read_block()` / `ssd.write_block()` を呼び、
   RAM バッファとディスク間でデータが正しく転送されること。
3. **ファイルシステム**:
   - `fs.init()` → 初回は自動フォーマット → `"kernel: fs ready"` が出力される。
   - `fs.create("hello")` → `fs.write(fd, buf, len)` → `fs.close(fd)` → データが永続化。
   - エミュレータ再起動後 `fs.open("hello")` → `fs.read(fd, buf, len)` → 同じデータが読める。
   - `fs.list()` → ファイル名とサイズが表示される。
   - `fs.remove("hello")` → ファイルが削除され、ブロックが解放される。
4. **回帰**: ディスク未指定時に既存のカーネル出力が不変であること。

## 依存関係

- **前提（実装済み）**: 割り込み機構 (ISSUE-001)、ヒープ (ISSUE-002)、DOM (ISSUE-006)。
- **後続（このチケットが前提）**: シェル、init ファイル読み込み、ユーザーアプリのファイル保存。

## 変更ファイル

- 新規: `runtime/MyEmulator/src/machine/ssd.rs`、
  `system/MyKernel/src/libs/ssd.mln`、`system/MyKernel/src/libs/fs.mln`。
- 変更: `runtime/MyEmulator/src/{constants.rs,machine/mod.rs,machine/memory_bus.rs,cli.rs,app.rs}`、
  `system/MyKernel/src/kernel_main.mln`、`system/MyKernel/src/libs/dom.mln`。
- 不変: MyAssembler、MyLangCompiler、MyLinker（新命令不要、全て既存の仕組みで実装可能）。
