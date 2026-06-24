# 汎用構文エンジン化（MyLangSyntaxEngine → MySyntaxEngine）

## 背景・決定

`MyLangSyntaxEngine` は元々**文法ファイルを食う汎用 LR1 エンジン**（テーブル生成＋
shift/reduce）。だがフェーズ2で token role / outline symbol の分類を実装した際、
`src/lr1/syntax_parser.c` に **MyLang の文法シンボル名を直書き**してしまった：

- `role_for_lhs()` … `funcDef`/`structDecl`/`baseType`/`packageDecl`/`postfixExpr`/
  `param` 等の非終端名で token role を決定。
- `symbol_kind_for_lhs()` … 同様に outline symbol の種別を決定。
- scope 判定が終端名 `L_BRACE`/`R_BRACE` 直書き（brace 深さ）。

第2の利用者 **mlnx**（自作ブラウザ記述言語）がこのエンジンを使う予定が確定した。
mlnx の非終端は element/attribute 等で MyLang と全く別物なので、上記の直書きは通用
しない。

**決定**:
1. エンジンは**汎用のまま独立を維持**する（MyLang 専用化しない）。
2. 分類（role / symbol / scope）を**文法ファイルの注釈で宣言**し、エンジンの C コード
   から言語固有を完全に排除する。
3. リポ／ディレクトリを **`MySyntaxEngine`** に改名し、`My*` ファミリに揃えて
   「MyLang の一部ではなく独立エンジン」であることを名前で示す。

## アーキテクチャ上の位置づけ（shared-frontend.md の更新）

`shared-frontend.md` は「エンジンを MyLang 唯一のフロントエンドに育てる
（MyLang 固有に寄せる）」と書いていたが、**この決定で上書きする**。新しい整理：

```
MySyntaxEngine (汎用・多言語)         … 文法駆動の parse 検証 / token role / outline symbol
   ↑ grammar(+注釈)        ↑ grammar(+注釈)
MyLang                   mlnx
   ↑                       ↑
各言語の syntax-check ツール / LSP（role・symbol 文字列を自分の意味へ写すだけ）
```

- エンジンは **tree-sitter 的な「エディタ/LSP 向け汎用パーサ」**の役割。診断・
  ハイライト・アウトラインを文法駆動で提供。
- エンジンは **AST / codegen を持たない**。MyLang の AST と再帰下降パーサは
  `MyLangCompiler` に残る（コンパイル用フロントエンド）。
- よって「2つのパーサ（LR1 と再帰下降）」は**統合せず役割分担で共存**する：
  LR1 エンジン＝エディタ/LSP 向け（多言語）、再帰下降＝コンパイラ用（MyLang）。
  これは多くの処理系（tree-sitter + コンパイラ）と同じ素直な構成。
- 結果、shared-frontend.md の「フェーズ3: コンパイラをクライアント化」「フェーズ4:
  エンジンが直接 LSP を喋る」は**見直し**：LSP は引き続き各言語の syntax-check ツール
  経由でエンジン出力を得る（あるいは将来、汎用エンジンが LSP を喋るなら言語非依存の
  まま）。コンパイラのパーサ削除は行わない。

## 文法注釈の設計（案A）

知識は「どの規則のどのシンボルが何の役割か」＝**文法知識**なので、文法ファイルに
インライン注釈で持たせる。エンジンはそれを汎用に適用するだけ。

### 注釈構文
- `<symbol>@<role>` … そのシンボルの**左端トークン**に role を付与。終端なら自身、
  非終端ならその部分木の左端トークン（例 `declarator@parameter` は declarator の
  先頭 IDENTIFIER に付く）。これで「直接終端」も「declarator 経由」も統一的に扱える。
- `<symbol>@<role>:single` … そのシンボルが**ちょうど1トークン**のときだけ付与。
  呼び出しの callee（`postfixExpr@function:single '('`）のような「素の識別子のみ」
  条件を一般化（現状の単一トークン callee 検出を置換）。
- `<symbol>@decl(<kind>)` … そのシンボルの左端トークンを名前とする**トップレベル宣言
  シンボル**を、scope 深さ 0 で還元されたとき emit。
- ディレクトリ: `%scope <open-terminal> <close-terminal>` … scope を開閉する終端を
  宣言（MyLang は `%scope L_BRACE R_BRACE`、mlnx は別）。

### role / symbol は「文字列」（C enum をやめる）
現状の `SyntaxRole` / `SyntaxSymbolKind` enum は MyLang 前提の固定語彙。汎用化のため
**文法が宣言する任意文字列**にし、エンジンはそれを**そのまま出力に通す**。各言語の
LSP が「`function`→関数トークン型」「mlnx の `element`→…」と写す。エンジンは語彙を
知らない。

### MyLang 文法での宣言例（現直書きの置換）
```
%scope L_BRACE R_BRACE

funcDef     : type 'IDENTIFIER'@function@decl(function) '(' paramList ')' block
funcProto   : type 'IDENTIFIER'@function@decl(function) '(' paramList ')' ';'
param       : type declarator@parameter
varDecl     : type declarator@decl(variable) ';'
structDecl  : 'STRUCT' 'IDENTIFIER'@struct@decl(struct) '{' fieldList '}' ';'
enumDecl    : 'ENUM' 'IDENTIFIER'@struct@decl(enum) '{' enumItems '}' ';'
typedefStmt : 'TYPEDEF' type 'IDENTIFIER'@type@decl(type) ';'
baseType    : 'IDENTIFIER'@type
packageDecl : 'PACKAGE' 'IDENTIFIER'@namespace
importDecl  : 'IMPORT' 'IDENTIFIER'@namespace ';'
postfixExpr : postfixExpr '.' 'IDENTIFIER'@property
            | postfixExpr@function:single '(' argList ')'
```

## エンジン側の実装変更

- **grammar loader**（`syntax_grammar.c`）: `@role` / `@role:single` / `@decl(kind)` /
  `%scope` をパースし、**production ごとのメタデータ**（rhs index → role 文字列 /
  single フラグ / decl 種別）と scope 終端集合に落とす。role/symbol 文字列は intern。
- **parser**（`syntax_parser.c`）: 直書きの `role_for_lhs`/`symbol_kind_for_lhs`/
  `L_BRACE` 比較を**削除**。REDUCE 時に「その production のメタデータ」を pos_stack で
  適用するだけ（既存の pos_stack 機構を流用）。scope 深さは宣言された scope 終端の
  shift で増減。
- **出力**（`SyntaxResult` 拡張 or 既存 roles/symbols バッファ）: role/symbol を
  **文字列（または intern id）**で返す。`SyntaxRole`/`SyntaxSymbolKind` enum は撤去。
- `syntax_check.c`（MyLangCompiler 側）: enum→文字列マップ（`role_name`/
  `symbol_kind_name`）が不要になり、エンジンが返す文字列をそのまま JSON に載せる。

## 改名チェックリスト（MyLangSyntaxEngine → MySyntaxEngine）

submodule なので機械的だが範囲が広い：
- GitHub リポ名 `Keyhole-Koro/MyLangSyntaxEngine` → `MySyntaxEngine`。
- 親リポ `.gitmodules` の path/url、ディレクトリ `toolchain/MyLangSyntaxEngine` →
  `toolchain/MySyntaxEngine`。
- **CI**: `MyLangCompiler/.github/workflows/ci.yml` の「Checkout MyLangSyntaxEngine」
  ステップ（repository 名・path）。
- include パス `-I../MyLangSyntaxEngine/include`、include ディレクトリ
  `include/mylang_syntax_engine/` → `include/my_syntax_engine/`（または `syntax_engine/`）、
  `#include "mylang_syntax_engine/syntax_engine.h"`。
- `syntax_check.c` の `default_grammar_path` 文字列
  （`../MyLangSyntaxEngine/tests/fixtures/grammars/mylang_lsp.grammar`）。
- シンボル接頭辞は既に `syntax_*`/`SYNTAX_*` で中立 → 改名不要（幸い）。

**重要**: 改名だけ先行して直書きを残すと「汎用名なのに中身は MyLang 専用」という
最悪の不一致になる。**注釈化（直書き排除）と改名はセットで1パス**にする。

## 移行手順

1. 文法注釈の構文を確定（本メモの案A）。
2. grammar loader に注釈パースを実装、production メタデータ＋scope 終端を保持。
3. parser の直書き分類を削除し、メタデータ駆動に置換。role/symbol を文字列出力へ。
4. MyLang 文法ファイルに注釈を付与。既存テスト（run_token_tests.py /
   test_semantic_tokens.py）が緑のままであることを確認（出力契約は不変）。
5. リポ/ディレクトリ/CI/include/grammar path を `MySyntaxEngine` へ改名。
6. mlnx 用は別 grammar（自分の注釈付き）を後で追加するだけ。

## 検証

- 注釈化の前後で MyLang の token role / symbol 出力が**完全一致**すること
  （既存ゴールデンが回帰ガード）。
- `%scope` 駆動の深さ判定が brace 直書きと同一挙動（globals のみ symbol 化、
  field/local/call 除外）。
- 不均衡 scope（`}}}}` / `{{{{`）で ASan/UBSan クリーン（既存と同じ）。

## 関連
- `shared-frontend.md`（この決定で「エンジン＝MyLang 専用フロントエンド」
  の方針を上書き。フェーズ1-2 の lexer/token/role/symbol 実装はそのまま有効）。
- `mylang-lsp-syntax-diagnostics.md`。
