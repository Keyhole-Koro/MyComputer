# 共有フロントエンド化（SyntaxEngine をツールチェーン唯一のフロントエンドに）

> **更新（一部上書き）**: 第2の利用者 mlnx の登場により、エンジンは MyLang 専用に
> 寄せず**汎用のまま独立**を維持する方針に変更した。「エンジン＝MyLang 唯一の
> フロントエンド」「コンパイラのパーサ削除」「エンジンが直接 LSP を喋る」は
> `syntax-engine-generic.md` の整理で上書きされる。フェーズ1-2 で実装
> 済みの lexer/token/role/symbol 出力はそのまま有効。

現状、字句・構文の知識がツールチェーン内で**3箇所に分散**している：

- `tools/MyLangServerProtocol/server.py` … semantic tokens 用に **正規表現でレキシング
  ＋型/関数/プロパティの分類を当て推量**でやっている（`semantic_tokens()`）。
- `toolchain/MyLangCompiler/src/frontend/lexer/lexer.c` … 本物のレキサ。`Token{kind,
  value, line, col, next}` を生成。診断（`tools/syntax_check.c`）とコンパイルで使用。
- `toolchain/MyLangCompiler/src/frontend/parser/*` … 再帰下降パーサ。AST を構築
  （`new_fundef`/`new_param`/`new_member_access` 等）。
- `toolchain/MySyntaxEngine` … LR1 テーブル。**トークンid列を受理判定するだけ**
  （`syntax_parse_token_ids`）。レキサ・AST・名前・位置を持たない。診断のために
  `mylang-syntax-check`（MyLangCompiler 側）経由で使われている。

結果として **レキサが2つ（C と Python正規表現）**、**パーサが2つ（LR1エンジン と
再帰下降）** ある。LSP のハイライト分類は「役割を知っている AST」と「位置を知っている
レキサ」が別レイヤに分かれているため、Python が位置から役割を逆算する推量コードに
なっている。

ゴール: **SyntaxEngine をツールチェーン唯一のフロントエンドに育てる**。
`source → lexer → tokens(位置) → parser → AST` を一本化し、
`{ diagnostics, tokens[位置+役割], AST, symbols }` を公開する。MyLangCompiler は
AST を消費する側（lowering/codegen 専念）、LSP は全機能をエンジンに問い合わせる
（診断・ハイライト・将来 hover/定義ジャンプ/シンボル）。server.py から言語知識を
ゼロにする。

**最終形の通信構成（決定: A = clangd 型）**: エンジン（C）が**直接 LSP/JSON-RPC を
喋る**言語サーバになる。`server.py`（Python の LSP）と、その下の
`mylang-syntax-check` への subprocess＋自前 `content N\n` プロトコルは**両方とも
過渡的**で、最終的に**廃止**する。エディタ ↔ エンジン の 1 プロセス・stdio・
JSON-RPC 直結（clangd/ccls と同じモデル）。

```
最終形:  VSCode ──stdio(LSP/JSON-RPC)──> mylang language server (C, = SyntaxEngine)
過渡:    VSCode ──stdio(LSP)──> server.py(Python) ──subprocess/content N──> mylang-syntax-check(C)
```

server.py は完全な LSP 実装の**移植元（仕様書）**として使う（JSON-RPC フレーミング・
lifecycle・capabilities・semantic tokens 符号化が実装済み）。C への移植であって
設計の発明ではない。

## 確定した設計判断（合意済み）

- **方向性**: (ii) 再帰下降を同居させるだけ、ではなく **(i) パーサを1つに統一**する。
  中途半端な同居だと「2パーサ」の臭みが残り統合の意味が薄い。
- **唯一の本質的決断＝パーサの統一先**: LR1 を本物のパーサに昇格（reduce に意味
  アクションを足して AST 構築）→ 再帰下降を削除。重複を完全に消す。
- **段階移行**: 一気にやらない。**第一歩はレキサをエンジンへ移すこと**（土台・低リスク・
  即効）。位置つきトークンが出た時点で LSP の字句ハイライトは正規表現ゼロで成立する。
- **通信は A（C が直接 LSP）**: B（C をライブラリリンクして Python LSP を残す）は
  subprocess を FFI 境界に置き換えるだけの過渡形で、共有フロント完成時に Python が
  お飾りになり作業の大半が捨てになる。よって B は採らず A を終点とする。
- **最大の障壁＝LSP向けエラー回復**: LSP は編集中の壊れたコードを常に食う。共有
  フロントエンドは**部分入力で graceful に落ちる**必要がある。今のコンパイラ parser は
  エラーで止まる作りの可能性が高く、これが新要件かつ一番の地雷。
- **incremental sync**: 最終形は `textDocumentSync: Incremental`（変更範囲だけ受信）を
  目指す。現状 server.py は `textDocumentSync: 1`（Full=全文送信）。

## 調査で判明している事実

- **エンジンは純粋な LR1 アクセプタ**。公開APIは grammar ロード／テーブル構築／
  `syntax_parse_token_names`・`syntax_parse_token_ids`（受理判定＋expected集合を返す
  だけ）。AST も意味アクションも無い（`toolchain/MySyntaxEngine/include/
  mylang_syntax_engine/syntax_engine.h`）。
- **stdio プロトコルは既に存在**: `mylang-syntax-check --stdio <grammar> [cache]` が
  `content <N>\n<bytes>\n` を受け、`{"status":..,"diagnostics":[..]}` を返す
  （`MyLangCompiler/tools/syntax_check.c` の `run_stdio`/`check_source`）。server.py の
  `query_syntax_checker` がこの JSON を既にパースしている。**tokens を同じ応答に
  相乗りさせるのが拡張の自然な入口**。
- **レキサは位置を持つ**: `Token{kind, value, line, col}`、line/col は 1始まり
  （診断側が `line-1`/`col-1` で LSP 化済み＝整合実証済み）。`tokenkind2str()` で
  種別名を文字列化できる（`parser_token.c` 等で実用済み）。
- **AST は役割を全て持つが位置を捨てている**: `new_fundef(ret_type,name,..)` /
  `new_param(type,name)` / `new_var_decl(type,name)` / `new_member_access(lhs,
  member_name)` / `new_typedef`/`new_struct`/`new_enum` / `new_import_stmt(path,
  symbols)` / `new_identifier(name)` 等、**名前は `char*` で受け取り line/col を保持
  しない**（`MyLangCompiler/inc/mylang/frontend/parser_ast_internal.h`）。これが
  「役割つき位置トークン」を直接出せない唯一の壁。
- **TokenKind にコメントが無い**。レキサはコメントを完全に破棄する
  （`MyLangCompiler/inc/mylang/frontend/lexer.h`）。ハイライトでコメントを塗るには
  trivia トークン化が別途必要。
- **enum に `i8/i16/u8/u16` が無い**（`I32/U32` のみ）。これらは現状 `IDENTIFIER` に
  なる。
- **`&mut` は1トークンではない**（`ADDRESS` + `MUT` の2トークン）。

## 段階移行の概要

### フェーズ1: レキサをエンジンへ移す（土台）
- `lexer.c`/`lexer.h` を MySyntaxEngine 側へ移設、または共有できる形で公開。
  MyLangCompiler と syntax-check は移設先のレキサを使う。
- syntax-check の stdio 応答に `tokens` を追加: 既存の Token リストを舐めて
  `[line-1, col-1, len, tokenkind2str(kind)]` を JSON 出力（C 側にマッピングは
  書かず raw 種別名を吐く）。
- server.py: `semantic_tokens()` の**字句系正規表現を削除**し、応答の `tokens` を
  描画。種別名→semantic type のマップは Python 側に置く（表示の都合は LSP の責務）。
  → この時点で二重レキサ解消。分類（型/関数/プロパティ）の overlay 正規表現だけ残る。

### フェーズ2: パーサ統一とAST公開（本丸）
- (i) LR1 の reduce に意味アクションを足して AST を構築できるようにする。
  あるいは再帰下降をエンジンへ移し LR1 をバリデータに降格（非推奨＝(ii)）。
- **AST/トークンに位置を通す**: name を受ける各コンストラクタに line/col（または
  Token）を持たせる。診断の範囲表示も同時に改善される（今はパースエラー1点のみ）。
- エンジンが `{ diagnostics, tokens[位置+役割], symbols }` を公開。役割は AST から
  確定情報として与える（推量を排除）。
- server.py: **overlay 正規表現を全削除**し描画専用に。FUNCTION_DEF/CALL・
  TYPE_USAGE・PARAM・PROPERTY・STRUCT/TYPEDEF・PACKAGE(namespace) が消える。

### フェーズ3: コンパイラをクライアント化
- MyLangCompiler はエンジンの AST を消費して lowering/codegen に専念。
- 負けたパーサ（再帰下降 or LR1 のどちらか）を削除。重複を完全に解消。

### フェーズ4: エンジンが直接 LSP を喋る（通信 A・終点）
- エンジンに LSP/JSON-RPC 層を実装（`server.py` を仕様書として移植）: Content-Length
  フレーミング・initialize/shutdown/exit・semanticTokens(full→将来delta)・
  publishDiagnostics・documentSymbol、`textDocumentSync: Incremental`。
- VSCode 拡張の起動コマンドを `server.py` から **エンジンのバイナリ直結**に切替。
- `server.py` と `mylang-syntax-check` の自前 `content N\n` プロトコルを**廃止**。

## 実装時に詰める点

- **エラー回復方針**: 部分/不正入力でも字句層は常に動く（フェーズ1で担保）。AST 層は
  通った範囲だけ役割を付け、残りは `variable`/未分類にフォールバック。LR1 のエラー
  回復（同期トークンでの recovery）をどこまで実装するか。
- **コメントの扱い**: trivia トークンとして emit（パース経路では無視、ハイライト経路で
  使用）。`TokenKind` に COMMENT を追加するか、別の trivia リストで返すか。
- **文字列リテラルの幅**: lexer がエスケープ変換後の `value` を持つ場合、`strlen` が
  ソース上の幅とズレる可能性。元の幅（または開始〜終了 col）を保持しているか要確認。
- **桁は UTF-16 オフセット**（LSP 仕様）。C は byte offset。今 ASCII なら一致、非ASCII
  で将来ずれる点を仕様にメモ。
- **i8/i16/u8/u16** をレキサ/型に足すか、当面 `IDENTIFIER` のままにするか。
- **パフォーマンス**: lex+parse コストは診断で既に毎回払っている。共有化＝同じ解析の
  結果に tokens を相乗りさせるだけで、フェーズ1はむしろ速くなる（Python正規表現パス
  削除＋1往復統合）。常駐プロセス・LR1テーブルのディスクキャッシュ（`.table`）は既に
  ある。効く対策は **debounce（didChange を 100〜200ms まとめる）** と **診断+tokens を
  1往復で返す** の2つ。インクリメンタルパース（変更領域だけ再解析）は重火器でこの規模
  では時期尚早。tree-sitter 的なエディタ内ハイライトは将来の選択肢として記憶に留める
  （ハイライト=tree-sitter / 意味=LSP の二層が世の中の定番）。

## 検証

1. **フェーズ1**: `mylang-syntax-check --stdio` に手で `content N` を流し tokens JSON を
   目視確認。`MyLangCompiler/tests` にゴールデン追加。server の新旧トークン列を差分比較
   し、字句層が一致してから正規表現を削除。
2. **フェーズ2**: 代表的なソース（関数定義・struct・typedef・import・member access・
   パラメータ）で役割が AST 由来で正しく付くこと。壊れた入力（編集途中）で字句層が
   生き、AST 層が通った範囲だけ精錬されること。
3. **回帰**: コンパイラのテストが緑のまま（AST 位置追加が codegen を壊さないこと）。
   診断の既存出力が不変、または範囲がより正確になること。
4. **server**: 最終的に server.py から正規表現・言語知識が消え、描画専用になっている
   こと。

## 変更ファイル（想定）

- 移設/拡張: `toolchain/MySyntaxEngine/*`（lexer 受け入れ、意味アクション/AST、
  tokens+symbols 公開、最終的に **LSP/JSON-RPC 層**を実装＝終点 A）。
- 変更: `toolchain/MyLangCompiler/tools/syntax_check.c`（過渡: tokens 出力。最終的に
  役割を終え廃止候補）、`src/frontend/lexer/*`・`src/frontend/parser/*`・
  `inc/mylang/frontend/parser_ast_internal.h`（位置の付与、パーサ統一）、driver
  （エンジン AST 消費）。
- 廃止予定: `tools/MyLangServerProtocol/server.py`（フェーズ1-3 では正規表現削除→
  描画専用化、フェーズ4で **LSP 実装をエンジンへ移植後に廃止**）。VSCode 拡張の起動
  コマンドをエンジン直結へ。
- 関連メモ: `mylang-lsp-syntax-diagnostics.md`。
