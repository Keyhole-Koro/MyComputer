# MLC-021: trait と `?` のエラー変換

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Done | main | claude-code:opus-5.5 | 2026-10-08 |

## Summary

型をまたいだ共通の振る舞いを表す静的な `trait` を導入し、`?` が
`From` trait を介して異なるエラー型へ伝播できるようにする。あわせて、名前規約で
認識している `drop()` を `Drop` trait へ移す。

## Background

- `system/MyOS/src/fs/fs.mln` には `SsdError` を `FsError::IoError` へ落とす
  手書きの `case` が 19 箇所ある（例: `fs.mln:284`）。

  ```mylang
  case ssd.write_block(block, g_buf) of {
      Ok(_) -> _;
      Err(_) -> ({ return Err(FsError::IoError); });
  };
  ```

  `?` はエラー型が一致しないと使えない。
- `?` はパーサで `case` に脱糖しているだけで、型を見ていない
  （`toolchain/MyLangCompiler/src/frontend/parser/parser_expr_postfix.c:22`）。
  型不一致は `tests/fail/semantic/resultTryErrorMismatch_fail.mln` で
  「`?` never guesses an error conversion」として意図的に拒否している。
- 変換を局所 helper（`write_block_or_io()`）に閉じ込める案は試して撤回した。
  呼び出し側が helper を知る必要があり、`SsdError → FsError` の関係を
  型として表せないため。
- コンパイラは既に名前規約で振る舞いを認識している。`drop()` という名前の
  メソッドを持つ struct を自動 drop する
  （`docs/design/mylang-owned-values-and-drop.md`、`src/backend/codegen/codegen_drop.c`）。
  `?` の変換を同じやり方で足すと、名前規約による特例が増え続ける。

## Design

### Current State

- `FsError` は公開契約の `contracts/io/fs.contract.mln:6` にある。
  `SsdError` は MyOS 内部ドライバの `system/MyOS/src/fs/ssd.mln:31` にある。
  契約からドライバを参照してはならない。
- ジェネリクスは翻訳単位ごとの monomorphization で、制約・推論・オーバーロードは
  ない（`toolchain/MyLangCompiler/docs/generics.md`）。
- receiver メソッドは struct と enum の両方に書ける
  （`i32 (ref Shape s) area()` が enum `Shape` でコンパイルできることを確認済み）。
- 自動 drop の実利用は `toolchain/MyStdLib/text/string.mln:53` の
  `void (String *self) drop()` のみ。
- 手書き `Err(_) -> return Err(...)` は全体で 21 箇所。型をまたぐ変換が必要なのは
  fs の `SsdError → FsError` だけ。`system/MyKernel/src/mm/mmu.mln` の
  `Err(e) -> return Err(e)` は同じ型の伝播なので、現行の `?` で置換できる。
  `system/MyKernel/src/kernel/loader.mln` は後始末を伴うので MLC-019 の範囲。

### Proposed Design

構文は仮。class は導入せず、enum／struct（データ）＋receiver メソッド（その型だけの
振る舞い）＋trait（型をまたいだ振る舞い）で役割を分担する。

```mylang
// @std/core/convert.mln
export trait From<S> {
    Self from(S source);                     // receiver なし = 関連関数
}

// @std/core/drop.mln
export trait Drop {
    void (Self *self) drop();                // receiver あり = メソッド
}

// system/MyOS/src/fs/fs.mln
impl From<SsdError> for FsError {
    FsError from(SsdError e) {
        return case e of { SsdError::DeviceError -> FsError::IoError; };
    }
}

// 値を見ずに一つの variant へ落とすだけなら、この短縮形でもよい
impl From<SsdError> for FsError = FsError::IoError;

// 境界つきジェネリクス（型引数は今と同じく明示）
T convert<T: From<S>, S>(S value) { return T::from(value); }
```

規則:

1. **Nominal。** 型が trait を満たすのは `impl` を書いたときだけ。メソッド名が
   一致するだけでは満たさない。`impl` は trait の全項目をシグネチャ一致で実装する。
2. **置き場所（orphan rule）。** `impl` を書けるのは、trait か、対象の型・型引数の
   どれかが自パッケージのものである場合に限る。`impl From<SsdError> for FsError` は
   `SsdError` を持つ MyOS に置け、契約ファイルは変更しない。
3. **一意性。** 同じ trait と型の組み合わせの `impl` は、パッケージ単位で一つまで。
4. **静的ディスパッチ。** `<T: Trait>` の呼び出しは実体化の時点で `impl` を解決する。
   vtable は作らない。境界は `T: A + B` で複数書ける。
5. **関連関数の呼び出し。** `Type::name(...)` で呼ぶ。同じ名前の enum variant と
   衝突する場合はエラー。
6. **`?` の統合。** パーサは `?` を意味解析専用のノード（`AST_TRY` など）として残す。
   意味解析では、外側の関数の戻り値のエラー型を `Dst`、式のエラー型を `Src` とする。
   - `Src == Dst` のときは今と同じ展開になる。
   - そうでなければ `impl From<Src> for Dst` を探し、`Err(Dst::from(e))` へ展開する。
   - 見つからなければ、「`impl From<Src> for Dst` を追加せよ」という note 付きのエラーにする。
   - 変換は一段だけで、連鎖はしない。`?` 以外で暗黙の型変換はしない。
7. **`Drop` への移行。** 自動 drop の判定を「`drop` という名前のメソッドがあること」から
   「`impl Drop` があること」へ切り替える。移行期間は `impl` のない `drop()` に警告を
   出し、その後エラーにする。

診断例:

```
fs.mln:284:38: error: `?` cannot convert SsdError into FsError
  note: add `impl From<SsdError> for FsError`
fs.mln:40:1: error: conflicting impl From<SsdError> for FsError
fs.mln:40:1: error: impl Drop for FsError is not allowed here
  note: neither Drop nor FsError belongs to this package
app.mln:9:12: error: User does not implement Eq (required by contains<T: Eq>)
```

確定した仕様は `toolchain/MyLangCompiler/docs/traits.md` にある（言語仕様なので
コンパイラの docs に置いた）。以下の未決事項は、そこに書いた形で決着した。

- impl の可視性：定義モジュールでは常に見える。`export impl` は、その型が import 側で
  見えている場合に、定義モジュールの importer へ伝わる。
- receiver：trait では `Self *self` と書き、impl では `Self` か具体型で同じ形に書く。
  型の綴りが一致しなければシグネチャ不一致のエラー。
- キーワード：`trait` / `impl Trait for Type`。
- その場で変換先を指定する `?` の構文は入れていない（必要になったら別チケット）。
- orphan rule の「自パッケージ」：リポジトリ全体で `mylang.toml` が 1 つなので、
  「`@alias/...` を経由せずに見えている宣言」を自ソースツリーとした。

未決事項:

- `impl` が見える範囲。定義したモジュールとそれを import したモジュールにするか、
  `export impl` で明示させるか。
- trait の receiver の `Self *self` と、impl 側の `ref` / pointer 表記を一致させる規則。
- キーワード。`impl Trait for Type` か `Type implements Trait` か。
- その場で変換先を指定する `?` の構文（Rust の `map_err` に相当）を別途用意するか。
  三項演算子と曖昧にならない綴りが必要（`? else FsError::IoError` など）。

### Alternatives Considered

- **局所 helper（`write_block_or_io()`）。** 撤回した。変換が型の関係として現れず、
  `?` も helper を使わないため。
- **`?` 専用の変換宣言（trait なし）。** `drop` と同じく名前規約の特例が増える。
  イテレータや比較など、今後の同種の要求にも再利用できない。
- **Java／Go 風の interface。** 型の外から実装を後付けできず（`FsError` は契約側にある）、
  `from` のような値を受け取らない関数も表しにくい。
- **class／オブジェクト、あるいは enum の各 variant を型にする方式
  （Kotlin の sealed class など）。** サブタイプ関係、レイアウト、暗黙のヒープ確保や
  vtable が必要になり、OS／カーネルのコードに合わない。
- **`thiserror` 風に enum 定義側で `#[from]` 指定する方式。** 変換元の型を契約の
  enum が参照することになるので、今回の層構造では使えない。
- **`anyhow` 風にエラー型を消す方式。** 呼び出し側がエラーを型で区別できなくなる。

### Non-Goals

- 動的ディスパッチ（`dyn Trait`）。ただし構文の余地は残す。
- trait のデフォルト実装、関連型、blanket impl、特殊化。
- 型引数の推論。
- 発端の追跡（MLC-022 で扱う）。

## Progress

- [x] 構文と規則を `toolchain/MyLangCompiler/docs/traits.md` に確定する
- [x] token・AST・parser に `trait` / `impl ... for` / 型パラメータの境界を追加
- [x] trait と impl の登録、orphan rule と一意性の検査
- [x] 境界つきジェネリクスの実体化と、メソッド・関連関数（`Type::name`、`T::name`）の解決
- [x] `?` に `From` による変換を実装（意味解析専用ノードは作らず、型が確定する
      payload enum lowering の `check_try_error_type` で変換を挟む）
- [x] `impl From<...> for ... = Variant;` の短縮形
- [x] `@std/core/convert.mln`（`From`）、`cmp.mln`（`Eq`）、`iter.mln`（`Iterator`）、`drop.mln`（`Drop`）
- [x] `==` / `!=` を `Eq` に、`for (T x in it)` を `Iterator` に接続
- [x] `String` を `impl Drop` に移行（`drop` という名前のメソッドだけの型も互換のため引き続き認識）
- [x] `impl Drop` のない `drop()` に警告 W0002（`tests/warn/semantic/dropWithoutImpl_warn.mln`。
      MyLangTester が `tests/warn` を実行していなかったので、警告が出ることを確かめる段を追加）
- [x] `fs.mln` の `SsdError` 変換 19 箇所を `?` に置換
- [x] grammar、generics、ownership の docs、LSP 文法（MySyntaxEngine）と LSP のキーワードを更新
- [x] LSP のアウトライン：trait を interface として、trait／impl 本体のメソッドを method として表示
      （エンジンは波括弧の外の宣言しか記録しないため、`tools/syntax_check.c` で補う）
- [x] LSP のナビゲーション：impl の項目を呼び出し先として解決（`Self` の receiver、
      `Type::from(...)`、短縮形 impl はヘッダ）、trait のホバー（項目・doc・既知の impl）、
      impl 項目のホバーに impl と trait 側の doc、`textDocument/implementation`
- [x] LSP が `@alias/...` の import を `mylang.toml` で解決するように（10/5 のエイリアス化以降、
      標準ライブラリなどへのジャンプ・ホバーが届いていなかった）
- [x] `make build` / `make qa` での OS 全体の確認（22/22）
- [x] MyKernel `mm/mmu.mln` の伝播 7 箇所を `?` に、MyOS の DOM の子要素ループ 13 箇所を
      `dom.children(id)`（`impl Iterator<i32> for Children`）の for-in に移行

- [x] MyKernel／MyOS での trait の利用を拡大（2026-10-07）
  - `@kernel/mm/heap.mln` に `HeapBlock`（`impl Drop`、`keep()`）、MyOS `fs.mln` に
    `FileHandle`（`impl Drop`）
  - 契約に `impl From<MmuError> for LoaderError`、`impl From<LoaderError> for SpawnError`
  - loader `spawn_from_buffer`：プロセス枠を `ProcessSlot`（`impl Drop`）が持ち、
    手書きの `release_proc` 14 箇所を削除。MMU エラーは `?` と From で変換。
    失敗時に漏れていたカーネルスタックも `HeapBlock` で解放するようにした
  - console `spawn_file`：`FileHandle`／`HeapBlock` と `?` で `fs.close`／`heap.free` の
    手書き 10 箇所を削除
  - UI protocol `create`：ノード名を `HeapBlock` が持ち、作成の 14 箇所を `?` に。
    名前を使わない 5 種類で名前の複製が漏れていたのも解消

- [x] trait の残りの機能（2026-10-08）
  - デフォルト実装：trait の項目に本体を書ける。本体はトークンとして保持し、省略した
    impl ごとに `Self` を置き換えて再パースする（モジュールをまたいでも同じ）
  - ジェネリックな struct／enum への境界：`struct Pair<T: Eq>`。インスタンス化時に検査
  - ジェネリック impl と、インスタンスへの impl：`impl<T: Eq> Eq for Box<T>`、
    `impl Make for Box<i32>`。テンプレートとして保持し、型のインスタンスが作られる
    たびに、一致して境界を満たすものだけ具体化する。`Box<i32>::make(...)` の呼び出し、
    import した型のフィールドとして届いたインスタンス、エクスポートしたテンプレートも対応
  - `dyn Trait`（2026-10-12 に削除）：データへのポインタとメソッドごとの関数ポインタを
    持つ構造体（`__dyn_5_Shape { u8 *data; fn(u8 *) -> i32 __m_area; }`）に変換し、
    `s.area()` は生成したディスパッチメソッド、`T *` は dyn 値が期待される場所
    （初期化・代入・引数・戻り値・構造体リテラル）で生成した変換関数を通す設計だった。
    dyn 値の配列やモジュール間の受け渡しまで動いたが、使い道が `say_error` と
    `ui.set_error` の 2 箇所だけで、どちらも `e.describe()` の文字列を渡せば済んだ。
    コンパイラ約 500 行と、所有しない参照という利用者側の注意点に見合わないため外した。
    違う型を一つの表に入れて呼ぶ必要（ドライバ表、カーネルと OS の境界など）が
    関数ポインタで辛くなったときに入れ直す（実装はコミット 8574365 以降の
    `parser_trait_dyn.c`）
  - 診断でインスタンス名を `Box<Opaque>` と表示（デマングル）
  - LSP：`impl<T>`、デフォルト実装（impl が省いた項目は trait の本体へ）。文法と
    構文チェッカも対応
- [x] MLC-022（`?` の伝播経路トレース）を実装

#### 実装中に直した既存の不具合

- ジェネリクスの実体化が 1 つもないファイルでは、import した数値 enum を関数の引数・
  戻り値に使うと `unknown type` になっていた（import した型を program の末尾に足して
  いたため）。先頭に入れるよう修正。
- `items[i].method()`（`*(items + i)`）の receiver の型を推論できなかった。
- `?` の展開がダミーの `yield 0` を置いていたため、`?` ごとに位置 0:0 の
  unreachable 警告が出ていた。

- `import X from "f.mln";` で X が package 名でも宣言済みの名前でもないとき、何も import
  せずに通っていた（`X.f()` が後で解決できなくなる）。エラーにし、package 名での書き方を示す。
  これに頼っていた MyStdLib `bitset.mln` と MyKernel／MyOS のテスト 11 ファイルを
  package 名での import に直した（`make qa` 22/22）。

- `case` が構造体（または payload を持つ enum の変数）を値として返すと、1 ワードしか
  コピーされなかった。`?` で構造体を返す Result を受けるときも同じ。結果の型が
  aggregate なら常に destination passing にした。
- 意味解析が `case` のアームを順に検査していたため、別のアームでの移動を誤って
  「移動済みの値の使用」としていた。アームごとに状態を分けて合流させるようにした。
- 構造体を返す直接呼び出しの引数に、構造体を返す呼び出しを入れると誤った値になっていた
  （codegen の sret 経路だけ一時領域のずれを考慮していなかった）。
- 構造体リテラルのフィールドや呼び出し引数の途中で `?` が return すると、スタックが
  ずれたまま関数を抜けていた。エピローグで `mov sp, bp` するようにし、構造体リテラル内
  の一時変数もローカルとして集めるようにした。

- 別々のブロック（兄弟の `if` や内側のブロック）で同じ名前のローカルを別の型で宣言すると、
  codegen が名前だけでスロットを引くため、後の宣言が最初の宣言の型・サイズ・オフセットで
  扱われていた（未知のメンバーはエラーにならず `; unknown member` のコメントになるだけ）。
  MyOS の `proc/syscall.mln` では PROC_EXITED の `request.result_out` を `ProcSpawnArgs`
  のオフセットで読み、ターミナルのユーザースタックの保存 bp／lr を壊していた。codegen の
  前に、同じ関数内で再宣言された名前をスコープに沿って一意な綴り（`name__s2`）に変える
  ようにした（`codegen_scope_names.c`、`succeed/scope/siblingShadowTypes.mln`）。

#### apps_e2e の調査で直した不具合（trait 以外）

- 別モジュールの payload enum を import した側で、payload の型が import されず
  enum のレイアウトが変わっていた（`SpawnError` 経由で shell の `slot` が壊れた）。
  `import_member_types` が enum の payload 型も import するようにした。
- MyOS: shell／automation のタスクスタック 1 KiB が溢れていた（16 KiB に）。
  idle スタック 512 B も割り込み処理で溢れていた（8 KiB に）。
- MyOS: gateway の結果バッファ `RESULT_CAP` 32 B が 44〜48 B の UI Result より小さく、
  隣のヒープブロック（ウィンドウ名）を壊していた（64 B と起動時のサイズ検査）。
- MyOS: test id がステージングバッファを指したままだった（`set_test_id_copy` で複製）。
- MyKernel: 共有カーネルページテーブルを最初のプロセスのディレクトリで作っていたため、
  そのプロセスのユーザースタック用テーブルまで全プロセスで共有され、プロセスを
  ロードするたびに他のプロセスのスタックが付け替わっていた。専用のテンプレート
  ディレクトリで作るようにした。
- MyOS: `list_row_at` が `LIST` 以外を拒否するようになっていて（157f7a6）、ランチャー
  メニューのクリックが何も起動しなかった。`MENU` も受け付ける。

#### 既知の制限・未解決

- （解消済み）`case` が構造体を値として返す場合の不具合。for-in の展開は
  `Some` の payload フィールドから要素を読む形のまま。
- （解消済み）`system/MyOS/tests/apps_e2e_test.py` のページフォルト。上の一覧を参照。
- （解消済み）`set_test_id_copy` のリーク。ノードが `TEST_ID_OWNED` で所有を記録し、
  付け直しと削除で解放する。
- （解消済み）codegen は未知のメンバーをエラーにする。
- （解消済み）入れ子の構造体リテラルは、1 ワード以下のフィールドでは失敗していた。
- associated type、ジェネリック型への `impl ... = 値;`、impl テンプレート同士の重なりの
  検出は未対応（`docs/traits.md` の Not supported yet）。
- （解消済み）`make build` が MyStdLib `collections/bitset.mln` の別名 import で止まっていた。

## Verification

```bash
make -C toolchain/MyLangCompiler test-component   # 345 passed（trait の succeed/fail/syntax_check を含む）
make -C toolchain/MyLangCompiler test-e2e         # 122 passed（trait 6 件を含む）
make -C toolchain/MySyntaxEngine test
python3 -m tests.run                              # tools/MyLangServerProtocol
make qa                                           # 22/22
python3 system/MyOS/tests/apps_e2e_test.py        # PASS
```

## 完了条件

- `fs.mln` の `ssd.read_block` / `ssd.write_block` の伝播が全て `...?;` で書け、
  手書きの `Err(_) -> ({ return Err(FsError::IoError); })` が残っていない。
- `impl From` がない型同士の `?` は、上記の note 付きでコンパイルエラーになる
  （`resultTryErrorMismatch_fail.mln` が引き続き緑）。
- 重複 impl と orphan rule 違反を検出する fail テストがある。
- 境界を満たさない型引数で実体化するとエラーになる。
- `String` の自動 drop が `impl Drop for String` で従来通り動き、
  `automaticDrop.mln` が緑。

## 関連

- MLC-019 `defer` によるスコープ終了処理（`?` の早期 return と cleanup 順序）
- MLC-022 Result エラーの伝播経路トレース
- `docs/design/mylang-owned-values-and-drop.md`
- `toolchain/MyLangCompiler/docs/generics.md`
