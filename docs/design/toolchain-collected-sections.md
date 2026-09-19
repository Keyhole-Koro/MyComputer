# Toolchain: データ内シンボル参照（`.word`）と束ねセクション（`.section`）

MyAssembler / MyLinker / MyLangCompiler にまたがる仕様。2026-09-19 に、アノテーションの
メタデータ表を「誰も列挙しなくてもリンク時に全部集まる」形にするために追加した。
C/ELF で言えば `.word sym`（データ内リロケーション）と `__start_SECTION` /
`__stop_SECTION`（`KEEP(*(SECTION))`）に相当する。

関連: `toolchain/MyLinker/DESIGN.md`、`toolchain/MyLinker/inc/ObjectFormat.h`、
`toolchain/MyLangCompiler/docs/grammar.md` "Attributes and annotations"、
`docs/learn/annotations-and-metaprogramming.md`。

---

## 1. 背景 — 無かったもの

| 事実 | 帰結 |
| --- | --- |
| リロケーションは `movi rX, label`（21bit 即値）と `call/jmp label`（26bit 相対）の 2 種だけ。**データにアドレスを埋める手段が無い** | グローバル `char *s = "x";` が null になる。関数ポインタ表を静的に書けない。表は「起動時に埋める関数」として生成するしかない |
| セクションは TEXT / DATA の 2 種。実際には `.byte` も TEXT に置かれ、DATA は常に 0 バイト | 「全オブジェクトから同種のものを集める」場所が無い |
| 未参照オブジェクトはリンクから落とされる（needed-symbol による活性化） | 誰からも呼ばれない登録用データを持つオブジェクトは消える |

このため、アプリの一覧は Python 生成の manifest か、`main.mln` の特別な `extern` 宣言を
コンパイラが定義に置き換えるという目印に頼っていた。

## 2. `.word` — データ内の 32bit 値とシンボル参照

```asm
table:
  .word seven, 100, greeting     ; 関数ラベル, 定数, データラベル
greeting:
  .byte 0x48, 0x69, 0x00
```

- 1 オペランド = 4 バイト、ビッグエンディアン（メモリ上の 32bit 読みは BE。`memory_bus.rs` の
  `u32::from_be_bytes`）。ラベルブロック内で `.byte` の後に置かれ、`.byte` は 4 バイト境界に
  パディングされる
- **シンボルオペランド**はプレースホルダ 0 で出力し、`RelocEntry{type=2 (RELOC_WORD32)}` を
  積む。リンカはシンボルの最終アドレスを **32bit 全体**に書く（`RELOC_ABSOLUTE` は
  `movi` の下位 21bit だけを patch するので別種にした）
- 未定義かつ `import` されていないシンボルはアセンブル時エラー（`movi` と同じ規則）
- ローカルラベル（非 export）は `name-[module:n]` に一意化されるので、`.word s_3` のような
  文字列ラベル参照もモジュールを跨いで衝突しない

### mlc が使う場所

- **グローバル初期化子**（`codegen_data.c`）：`char *s = "hi";` → `s: .word s_N`、
  `i32 f = handler;` → `.word handler`、`char *names[] = {"a","b"}` → `.word` の列。
  4 バイト幅の要素は全部 `.word` で出す。これで「グローバル `char*` を文字列で初期化すると
  null」のバグは消えた（`menu_items()` を関数にする回避は不要になった）
- **アノテーション行**（下記 §4）

## 3. `.section NAME` — 束ねセクション

```asm
.section annotations
__annotations_rows:
  .word s_31, Terminal__view, s_1, 12, 2, 0, s_0, 0
  .word s_34, Terminal__poll, s_1, 12, 1, 100, 0, 0
```

- `.section NAME` は**次のラベルブロック 1 つ**に効く。そのブロックは命令を持てず、
  `.byte` / `.word` だけ（違反はアセンブルエラー）
- ブロックのバイト列は今まで通り TEXT に置かれる（**物理的には動かさない**）。
  オブジェクトには `CollectEntry{ name[64], offset(TEXT 内), size }` を 1 つ記録する
- オブジェクト形式は **LNK2**（マジック `0x4C4E4B32`）：`FileHeader` に `collect_count`、
  リロケーション表の後に `CollectEntry` 配列

### リンカが合成する索引

全（活性）オブジェクトの同名チャンクをリンク順に集め、DATA の末尾に**索引**を置く：

```
__NAME_start:   .word chunk0_addr, chunk0_size
                .word chunk1_addr, chunk1_size
                ...
__NAME_end:
_end:                      ; 以前どおり、イメージの末尾
```

- 1 チャンク = `(アドレス, バイト数)` の 8 バイト。読む側は `(__NAME_end - __NAME_start) / 8`
  個のペアを歩き、各チャンクをその場で読む
- `__NAME_start` / `__NAME_end` はリンカ合成シンボル。参照側は `extern i32 __NAME_start[];`
  （MyLang）または `import __NAME_start`（asm）で受ける。mlc は `extern` グローバルを
  定義ではなく import として出す（以前は `extern` を無視して定義していた）
- 複数のセクション名があれば最初に現れた順に並ぶ
- **活性化規則**：`CollectEntry` を持つオブジェクトはそれだけで live になる（誰も参照しなくても
  落とされない）。「表に載せる」は登録行為なので、参照の有無で消えては困る

### MBIN ヘッダ（未実装・TODO）

アプリを MFS 上の `.mbin` にしたとき、ローダがその実行形式の索引を読めるように、
`MbinHeader` に索引のオフセットとサイズ（またはセクション名ごとの表）を載せる。
今は `__annotations_start` シンボル経由なので、カーネルにリンクされた表しか読めない。

## 4. アノテーションでの使い方

mlc は `@a(args)` を検査したうえで、モジュールごとに `annotations` セクションへ
**8 ワード × 行**を出す（`codegen_annotations.c`）：

| ワード | 内容 |
| --- | --- |
| 0 | アノテーション名（`char*`） |
| 1 | 付けられた関数 |
| 2 | レシーバ型名（`char*`、プレーン関数は `""`） |
| 3 | その型の `sizeof`（プレーン関数は 0） |
| 4 | 引数の数 |
| 5–7 | 引数（数値／bool は 0・1／文字列は `char*`） |

読む側（`system/MyAppFramework/src/meta.mln`）は `__annotations_start..end` のペアを歩き、
チャンクサイズ / 32 を行数として平坦なインデックスを提供する。**コンパイラは行を書くだけ、
リンカは集めるだけ、意味は読み手**という分担。manifest 生成も、`main.mln` の
`extern i32* __annotations_table(i32 m);` という目印も不要になった。

## 5. 重複定義の検出

DESIGN.md には「Detect Duplicate Definitions (Error)」とあったが、実装は needed-symbol
に入ったものだけを見ていて、同名を 2 オブジェクトが定義しても黙って先勝ちだった。
今は活性オブジェクト全体で `DEFINED` シンボルの重複をエラーにする。除外：

- `__mlg_` 接頭辞（generics の実体化。同名 = 同一物、先勝ちで正しい）
- `-[` を含むローカルラベル（アセンブラの一意化タグ。タグはファイルの**ステム**だけなので
  `runtime/verdict.mln` と `platform/mycomputer/verdict.mln` のように同名ファイルで重複する。
  オブジェクトを跨いで参照されないので害はないが、タグにパスを含めるのが本来の直し）

## 6. 変更したファイル

| 場所 | 変更 |
| --- | --- |
| `MyLinker/inc/ObjectFormat.h` | `LINKER_MAGIC` = LNK2、`FileHeader.collect_count`、`RELOC_WORD32`、`CollectEntry` |
| `MyAssembler/src/parser.c` | `.word`、`.section`（ブロック境界としても扱う） |
| `MyAssembler/src/codeGen.c` | `.word` の出力とリロケーション、チャンク記録 |
| `MyAssembler/src/assembler.c` | `CollectEntry` の書き出し |
| `MyLinker/src/Linker.cpp` | LNK2 読み込み、WORD32 patch、索引合成、活性化規則、重複検出 |
| `MyLinker/tools/obj_gen.py`, `obj_dump.py`, `qa/tools/obj-viewer.py` | LNK2 対応 |
| `MyLangCompiler/src/backend/codegen/codegen_annotations.c` | 行の出力 |
| `MyLangCompiler/src/backend/codegen/codegen_data.c` | `.word` によるポインタ初期化 |
| `MyLangCompiler/src/backend/codegen/codegen_toplevel.c` | `extern` グローバルを import に |
| `MyAppFramework/src/meta.mln` | 索引の読み手 |

## 7. 検証

```
make -C toolchain/MyAssembler test-component test-e2e
make -C toolchain/MyLinker test-component        # test_collect: 2 オブジェクトのチャンクが索引に
make -C toolchain/MyLangCompiler test-e2e        # annotationTable, globalPointerInit
make qa && make framework-test
```
