# Toolchain: データ内シンボル参照（`.word`）と束ねセクション（`.section`）

MyAssembler / MyLinker / MyLangCompiler にまたがる仕様。2026-09-19 に、アノテーションの
メタデータ表を「誰も列挙しなくてもリンク時に全部集まる」形にするために追加した。
C/ELF で言えば `.word sym`（データ内リロケーション）と `__start_SECTION` /
`__stop_SECTION`（`KEEP(*(SECTION))`）に相当する。2026-09-20 に、索引方式（LNK2）から
物理連結 + 名前ディレクトリ（LNK3）に変え、読み手を MyStdLib の API にした。

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
- ブロックのバイト列は TEXT ではなく、オブジェクトの**束ねセクション blob**（DATA の後ろ）に
  置かれる。オブジェクトには `CollectEntry{ name[64], offset(blob 内), size }` を 1 つ記録し、
  ブロック内のシンボル／リロケーションは `section = 2 (SECTION_COLLECT)` + blob オフセットで表す
  （blob 内のリロケーションは `RELOC_WORD32` のみ）
- オブジェクト形式は **LNK3**（マジック `0x4C4E4B33`）：`FileHeader` に `collect_count` /
  `collect_size`、`RelocEntry` に `section`、リロケーション表の後に `CollectEntry` 配列

### リンカのレイアウト — 物理連結 + ディレクトリ

全（活性）オブジェクトの同名チャンクを**リンク順に隙間なく並べる**。読む側は 1 本の配列として
読めばよく、チャンク境界を意識しない：

```
                         ; ... 各オブジェクトの DATA ...
__section_annotations:   ; チャンク A、チャンク B、... を連結
__section_notes:         ; 別名のセクションは出現順に続く
__sections:              ; ディレクトリ：1 行 3 ワード [name(char*), start, size]
  .word n0, __section_annotations, 96      ; __section_annotations_size はこの行の size ワード
  .word n1, __section_notes, 16
  .word 0, 0, 0                            ; 終端行
n0: "annotations\0"  n1: "notes\0"        ; 4 バイト境界にパディング
_end:                    ; 以前どおり、イメージの末尾
```

- リンカ合成シンボル：`__section_<name>`（先頭アドレス）、`__section_<name>_size`
  （バイト数を持つワードのアドレス）、`__sections`（ディレクトリ。束ねセクションが 1 つも
  無くても終端行だけのものを必ず定義する）
- 参照側は `extern i32 __sections[];`（MyLang）または `import __sections`（asm）で受ける。mlc は
  `extern` グローバルを定義ではなく import として出す
- **活性化規則**：`CollectEntry` を持つオブジェクトはそれだけで live になる（誰も参照しなくても
  落とされない）。「表に載せる」は登録行為なので、参照の有無で消えては困る
- 名前で探せるので、読み手側に「セクション名ごとの extern 宣言」は要らない（MyLang にはトークン
  連結が無いので、静的な名前解決だけだと `as_slice<T>("annotations")` のような API が作れない）

### MBIN ヘッダ（済、MYOS-021）

`--header` でリンクした実行形式は、ヘッダ（version 2、36 バイト）に `sections_offset` ——
このディレクトリのファイル内オフセット —— を持つ（`docs/design/mbin-executable-header.md`）。
MyStdLib `format/mbin.mln` がそれを読み（`section_offset(image, name)`、`va_to_ptr`）、
`meta/annotations.mln` の `in_image(image)` がファイル上のアノテーション表を同じイテレータで
返す。MyOS のシェルは起動時にディスク上の MBIN ファイルのヘッダを読んで `@app` 行を
ランチャーに載せる（ロードはしない）。

## 4. 読み手 — MyStdLib の API

「コンパイラは行を書くだけ、リンカは集めるだけ、意味は読み手」という分担。読み手の共通部分は
MyStdLib に置いた：

### `memory/section.mln` — セクションを名前で

```mylang
import section from ".../MyStdLib/memory/section.mln";
import { as_slice } from ".../MyStdLib/memory/section.mln";

section.exists("annotations");             // bool
section.start("annotations");              // 先頭アドレス（無ければ 0）
section.size("annotations");               // バイト数（無ければ 0）
Slice<Row> rows = as_slice<Row>("annotations");   // size / sizeof(Row) 要素の Slice
```

`__sections` を歩いて名前を `str.eq` で照合する。`as_slice<T>` は generic なので import 側の
TU で実体化される — そのため本体は同パッケージの **export 関数**（`start`/`size`）だけを呼ぶ
（§6 のコンパイラ変更「テンプレート内の export 名の書き換え」）。

### `meta/annotations.mln` — アノテーション行のイテレータ

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

```mylang
import annotations from ".../MyStdLib/meta/annotations.mln";
import { Annotations } from ".../MyStdLib/meta/annotations.mln";

Annotations it = annotations.named("app");         // all() / named(n) / of_type(t) / where(n, t)
while (it.next()) {
    register_app(it.type(), it.size(), it.fn(), it.arg(0), it.text(1));
}
annotations.count();                               // 全行数
```

- `AnnotationRow`（8 ワードそのまま）と `Annotations`（カーソル + フィルタ）は export struct
- メソッド：`next()`、`reset()`、`row()`、`name()`、`fn()`、`type()`、`size()`、`argc()`、
  `arg(k)`、`text(k)`（`char*` として）、`flag(k)`
- 知らない名前の行は `named()` で頼まれなければ見えない。他のフレームワークが自分の
  アノテーションを同じ表に混ぜても互いに干渉しない
- MyAppFramework の `app.install()` はこれで `"app"` / `"timer"` / `"key"` / `"open"` /
  `"on_close"` を型名キーのレジストリに振り分ける。`meta.mln` は無くなった

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
| `MyLinker/inc/ObjectFormat.h` | `LINKER_MAGIC` = LNK3、`collect_count`/`collect_size`、`RELOC_WORD32`、`SECTION_COLLECT`、`RelocEntry.section`、`CollectEntry` |
| `MyAssembler/src/parser.c` | `.word`、`.section`（ブロック境界としても扱う） |
| `MyAssembler/src/codeGen.c` | `.word` の出力とリロケーション、blob へのチャンク記録 |
| `MyAssembler/src/assembler.c` | blob と `CollectEntry` の書き出し |
| `MyLinker/src/Linker.cpp` | LNK3 読み込み、WORD32 patch、物理連結、`__section_*` / `__sections` 合成、活性化規則、重複検出 |
| `MyLinker/tools/obj_gen.py`, `obj_dump.py`, `qa/tools/obj-viewer.py` | LNK3 対応 |
| `MyLangCompiler/src/backend/codegen/codegen_annotations.c` | 行の出力 |
| `MyLangCompiler/src/backend/codegen/codegen_data.c` | `.word` によるポインタ初期化 |
| `MyLangCompiler/src/backend/codegen/codegen_toplevel.c` | `extern` グローバルを import に。import した型のメソッドのシグネチャ登録 |
| `MyLangCompiler/src/frontend/parser/parser_import_generics.c` | **クロスパッケージのメソッド呼び出し**：`import { T }` で T の export メソッドのプロトタイプを登録（`import_type_methods`）。T のフィールド型（同モジュールの struct、実体化済み `__mlg_s_` struct）も依存順に取り込む（`import_member_types`） |
| `MyLangCompiler/src/frontend/parser/parser_instantiate.c` | 取り込んだ `__mlg_s_` 実体（`is_imported_instance`）を自 TU の実体化で再利用 |
| `MyLangCompiler/src/frontend/parser/parser_method_resolve.c` | 連鎖レシーバ `pkg.f().m()` の型を import 先の宣言から解決 |
| `MyLangCompiler/src/frontend/module/module_loader.c` | generic テンプレート本体の export 名を link 名に書き換えてから importer に渡す |
| `MyLangCompiler/src/frontend/parser/parser_expr_unary.c`, `codegen_expr.c` | `sizeof(型)`（generic の `T` を含む） |
| `MyStdLib/memory/section.mln`, `meta/annotations.mln` | 読み手の API（§4） |
| `MyOS/src/shell/app.mln`（当時 `MyAppFramework/src/app.mln`） | `install()` をイテレータで。`meta.mln` 削除 |
| `MyLangTester/src/CompilerTestRunner.java` | e2e ケースが `../../MyStdLib/...` をリンクできるように |

## 7. 検証

```
make -C toolchain/MyAssembler test-component test-e2e
make -C toolchain/MyLinker test-component        # test_collect: 2 オブジェクトのチャンクが連結、test_collect_dir: ディレクトリ
make -C toolchain/MyLangCompiler test-e2e        # annotationTable（イテレータ API）, importedMethods, sizeofType, globalPointerInit
make qa && make framework-test
python3 system/MyOS/tests/dom_click_test.py; python3 system/MyOS/tests/apps_e2e_test.py
```
