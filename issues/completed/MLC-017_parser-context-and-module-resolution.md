# パーサ状態のコンテキスト化と、モジュール解決層

> **[古い / STALE 2026-09-09] tickets/ から completed/ へ移動。本文は最新の実装状況を反映していません。**
> - 実装済み: `parser_state_internal.h` のグローバルは23個→実質1個
>   （`g_default_package`）まで削減済み。`ParserContext` / `ModuleGraph` /
>   `ModuleLoader` / `FrontendSession` が新設され、本文が名指しした4箇所のハック
>   （`parser_toplevel.c`、`parser_dom_sig.c`×2、`codegen_toplevel.c`）は全て
>   `module_loader_load` 経由に置き換え済み。フェーズ1〜3は大部分完了。
> - 未実装（残作業）: 完了条件「import 先の型が解決層から引ける」はプレーンな
>   struct/typedef では未達（[[MLC-016]] と同じ穴）。再着手する前に本文を
>   書き直すこと。

## 背景

MyLang の cross-package な機能 —— 型、定数、enum、generic テンプレート、関数
シグネチャ —— がどれも import 先から取れない。原因は共通で、**パーサが単一翻訳単位を
前提にしたグローバル状態で動いている**こと。

その結果、同じ欠落を回避するハックが**すでに4箇所**にある。いずれも
`lexer_from_file()` で import 先を独立に読み直している。

| 場所 | 何を読んでいるか |
| --- | --- |
| `parser_toplevel.c:40` | import 先の `package` 宣言 |
| `parser_dom_sig.c:96` | DOM タグを裏付ける関数の所在 |
| `parser_dom_sig.c:147` | その関数の引数名 |
| `codegen_toplevel.c:203` | 可変長引数を含む export シグネチャ |

`parser_dom_sig.c:11-22` のコメントが問題を明示している。

> Imported signatures are not known to the parser (imports only register a
> package namespace) ... Cross-package lookup belongs in a shared resolution
> layer that DOM lowering, type checking and imports can all use; until that
> exists this stays DOM-local.

## 問題

このまま generics の cross-package 対応（MLC-016 段2）をやると、**5つ目の、かつ
最大のハック**になる。import 先の generic 宣言を取るには宣言を実際にパースする必要が
あり、それは「解析中に別の翻訳単位を読み込む」操作だからである。

パーサのグローバルは23個ある（`inc/mylang/frontend/parser_state_internal.h:46-68`）。

```
token_head root g_struct_table g_func_table g_type_table
g_generic_template_table g_generic_decl_depth g_current_generic_function_name
g_stop_at_arrow g_unchecked_depth g_default_package g_current_package
g_current_package_heap g_exports g_export_count g_imported_packages
g_imported_pkg_count g_hoisted_funcs g_hoisted_count g_funlit_counter
g_parse_filename g_enum_constants g_enum_constant_count
```

これらを退避・復元しながらネストパースする実装は、再帰の深さ制限と訪問済み集合まで
抱えることになり、既存の4つより壊れやすい。

## 目標

グローバル状態を廃し、モジュール解決層を1つ作る。上記4つのハックを削除する。

## 非目標

- 型システムの拡張。本チケットは「今ある情報を cross-package で引けるようにする」
  ことに閉じる。
- MLC-005（typed IR）との統合。順序としては本チケットが先で構わない。

## 段階

### フェーズ1: パーサを再入可能にする

23個のグローバルを1つのコンテキスト構造体にまとめ、引数で渡す。

- **振る舞いを変えない。** 既存テスト全部がそのまま回帰検出器になる
- ファイル単位・関数単位で刻める。途中で止めても壊れない
- これが済むと「別の翻訳単位を読む」が退避・復元ではなく
  **2つ目のコンテキストを作るだけ**になる

`parser_reset()` はコンテキストの破棄に置き換わる。

### フェーズ2: ドライバを複数ファイル対応にする

現在 `mlc` は1ファイルずつ処理し、間に `parser_reset()` を挟む
（`driver_compile.c:59,77,88,125`）。一方 `driver_walk.c:51` は既にディレクトリを
走査していて、**全ファイルの集合はドライバが持っている**。

「全ファイルをパースしてモジュールグラフを作る → 解決 → lowering / codegen」に
組み替える。フェーズ1 が済んでいれば自然な拡張になる。

### フェーズ3: 解決層

型・定数・enum・generic テンプレート・シグネチャを1か所で解決する。
`lexer_from_file` を使った4つのハックをここで削除する。

### フェーズ4: 下流の解禁

フェーズ3 が済むと、以下が個別の作業ではなくなる。

- MLC-003 Package Symbol Resolution
- MLC-016 cross-package の型・定数（generics の段2 / 段4 を含む）
- MLC-015 phase 3（`str` を package をまたいで使う）

## 検証

各フェーズで既存スイートが緑のままであること。フェーズ1 は振る舞いを変えないので、
特に厳密に見る。

```
toolchain/MyLangCompiler/tests/run_integration_tests.py
toolchain/MyLangCompiler/tests/run_semantic_tests.py
toolchain/MyLangCompiler/tests/run_source_profile_tests.py
toolchain/MyLangCompiler/tests/run_token_tests.py
python3 system/MyKernel/tests/libs/run_std_test.py
python3 qa/runners/run_system.py --no-run
```

## 完了条件

- `parser_state_internal.h` にグローバルが残っていない
- `lexer_from_file` を使った cross-package の読み直しが1箇所も残っていない
- import 先の型・定数・generic テンプレートが解決層から引ける
- MLC-003 / MLC-015 / MLC-016 が本チケットを前提にできる

## 関連

- MLC-003 Package Symbol Resolution（本チケットが前提を作る）
- MLC-015 MyLang Native String
- MLC-016 Cross-Package Types And Constants
- MLC-005 MyLang Typed Intermediate Representation
