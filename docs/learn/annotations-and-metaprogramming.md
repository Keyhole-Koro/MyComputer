# アノテーションとメタプログラミング — `@app` をどこに置くか

MyLang の `@app` / `@timer` / `@key` は 2026-09-18 時点で **コンパイラの C ソース**
（`toolchain/MyLangCompiler/src/frontend/parser/parser_lower_app.c`）に名前と意味が
埋め込まれている。これは「動くが置き場所が間違っている」状態で、本来は

1. アノテーションの**定義**（名前・引数・付けられる対象）が言語機能として `.mln` に書け、
2. アノテーションの**実装**（`@app` を見て何を生成するか）も `.mln` にある

べきだ、という結論になった。このメモは、そこへ至る比較と、選んだ方式（B: コンパイル時
テンプレート）の設計メモ。実装状況は末尾。

---

## 1. 今の実装が何をしているか

```
@app struct Counter { i32 clicks = 0; i32 label; };
i32 (Counter *c) view() { ... }
@timer(100) void (Counter *c) poll() { ... }
```

`parser_lower_app.c` は上を見て、MyLang の**ソース文字列**を組み立て、それを通常の
トップレベルパーサに食わせている（`parse_generated_toplevels()`）：

```
void __app_Counter_init(i32 self) { Counter *p = (Counter*)self; p->clicks = 0; }
i32  __app_Counter_view(i32 self) { Counter *p = (Counter*)self; return p->view(); }
void Counter__poll__tramp(i32 owner, i32 id, i32 arg) { Counter *p = (Counter*)owner; p->poll(); }
export i32* __app_Counter_desc() { ... i32 の表 ... }
```

つまり実態は **テキストテンプレート**で、コンパイラが知っている「意味」は

- `app` / `timer` / `key` / `open` / `on_close` / `task` という名前と引数の形
- 記述子テーブルのレイアウト（`[0] name … [10..] timers, keys`）
- `"Ctrl+S"` → `(mods=2, code='s')` の変換
- ハンドラ ABI `(owner, id, arg)` へのトランポリン

のうち、最後の 1 つ以外は全部 **MyOS のフレームワークの都合**であって、コンパイラの
知識であるべきではない。`system/MyOS/src/app/app.mln` が `D_TIMER_COUNT = 8` の
ように同じレイアウトをもう一度書いているのが、二重定義の証拠。

---

## 2. Python のデコレータと何が違うか

```python
@app
class Counter: ...        # == Counter = app(Counter)
```

Python でこれが「ただの関数」で済むのは、3 つの前提があるから：

| 前提 | Python | MyLang |
| --- | --- | --- |
| **実行時に走る** | import 時にモジュールが上から実行され、その場で `app()` が呼ばれる | モジュール初期化コードが無い（`main` から呼ばれたものだけ動く） |
| **型が値** | `cls.__name__`、`cls.__dict__`、`getattr` で中身を見られる（リフレクション） | struct は型であって値ではない。実行時に名前もフィールドも分からない |
| **クロージャ** | `wrapper` が `func` を掴んだまま返せる | ラムダはトップレベル関数に hoist されるだけでキャプチャ不可 |

MyOS の `@app` はラッパ関数を「作って」いない（既存メソッドを表に並べているだけ）ので、
クロージャは要らない。前 2 つを足せば Python 式が成立する — それが §3 の「D 案」。

---

## 3. 比較した 4 案

| 案 | 中身 | 1 定義 | 2 実装 | コスト |
| --- | --- | --- | --- | --- |
| **A. 宣言のみ** | `annotation app(bool single = false, char *name = "") on struct;` を `.mln` に書き、コンパイラは未知の名前・引数の形・対象を宣言で検査。展開は C のまま | ○ | × | 小 |
| **B. コンパイル時テンプレート** | `annotation` の本体を MyLang の**テンプレート**で書く。`@T`、`@each(f in @fields(T))`、`@methods(T, timer)`、`@tramp(m)` のような少数の反射ディレクティブをコンパイラが埋め、結果を今と同じ経路で再パース | ○ | ○ | 中 |
| **C. comptime** | `annotation` の本体を通常の MyLang 関数 `void app(Decl d, Emit e)` として書き、コンパイラ内の **MyLang インタプリタ**で実行。`Decl` は AST の反射 API | ○ | ○ | 大（インタプリタ + 反射 API + 生成コードの衛生） |
| **D. RTTI + 起動時デコレータ（Python 式）** | コンパイラは struct ごとに `TypeInfo`（名前・サイズ・フィールド・メソッド・**属性をデータとして**）と統一 ABI サンクを生成。`@app(single) struct Counter` は起動時の `app(&TypeInfo_Counter, true)` 呼び出しに変換され、`app` は**ただの `.mln` 関数** | ○（宣言不要） | ○ | 中 |

他言語との対応：Java のアノテーション = A + 外部プロセッサ、Rust の derive/proc-macro = C、
Zig の comptime = C、Svelte/Vue のコンパイラ = B 寄り、Python/Ruby のデコレータ = D。

### D 案のトレードオフ（B と迷った点）

D はデコレータが本当に「ただの関数」になり、新しいテンプレート言語を覚える必要が無い。
将来ユーザー空間アプリになっても同じ記述子を syscall で渡せる。反面：

- **エラーが起動時になる** — `view` が無い、`@timer` の引数が文字列、は `debug.panic` で
  ブートが止まる形。コンパイルエラーより遅い段階。
- **コードを作れない** — 「宣言を見て何かに登録する」型のデコレータは全部書けるが、
  関数を合成する型（Python の `wrapper`）は無理。
- **記述子データがバイナリに乗る**（`@` 付きの型だけ出せば実害なし）。
- 起動時に呼ぶ一覧は結局どこかで作る（manifest 生成は残る）。

### 選んだのは B

理由：検査がコンパイル時に残る、生成もできる、そして**今の C 実装が既にテキスト
テンプレートなので、`.mln` へ移すだけで済む**。B で足りなくなったら C に上げても、
テンプレートは「文字列を返す関数」として C の中で生き残る。

---

## 4. B の設計メモ

### 4.1 宣言

```mylang
// system/MyOS/src/app/annotations.mln
annotation app(bool single = false, char *name = @name(T))
    on struct T
    requires method view()
{ ...テンプレート本体 (4.2)... }

annotation timer(i32 ms)     on method of app;   // 展開は app 側が @methods(T, timer) で拾う
annotation key(char *combo)  on method of app;
annotation open              on method of app;
annotation on_close          on method of app;
```

- `on struct T` / `on method of X`：付けられる対象。`of app` は「`@app` 型のメソッド限定」。
- 引数はデフォルト付きで、既存のデフォルト引数と同じ規則（literal のみ）。
- `requires` は展開前に検査され、失敗はその場でコンパイルエラー（今の `@app struct 'Thing'
  needs a view method` と同じ位置・同じ文言で出せる）。
- 本体を持たない宣言（`timer` 等）はマーカー。属性としての検査（引数の形・対象）だけ
  コンパイラがやる。

### 4.2 テンプレート本体とディレクティブ

本体は MyLang のトップレベル宣言の列で、`@...` がディレクティブ。それ以外は文字として
そのまま出る。ディレクティブは**反射の読み取り**と**繰り返し**だけで、計算はしない
（計算が要る = C 案の領域）。

| ディレクティブ | 意味 |
| --- | --- |
| `@T` / `@name(T)` | 対象型の識別子 / 文字列リテラル |
| `@arg(single)` | アノテーション引数（literal として埋まる） |
| `@each(f in @fields(T) where f.init) { ... }` | フィールドの繰り返し。`@f`、`@f.init`、`@f.type` |
| `@each(m in @methods(T, timer)) { ... }` | `@timer` 付きメソッドの繰り返し。`@m`、`@m.args[0]`（その属性の引数） |
| `@count(@methods(T, key))` | 個数（表のサイズ計算用） |
| `@i` | `@each` の 0 起点カウンタ |
| `@tramp(m)` | メソッド `m` を `(owner, id, arg)` に包んだ関数の名前（生成は組み込み） |
| `@sizeof(T)` | 今は `T probe; sizeof(probe)` で回避しているもの |

`@tramp` だけが「コンパイラの組み込み」として残る。呼び出し規約（引数レジスタ、
`ref mut` が書き戻されない、等）はコンパイラの領分なので、これは正しい境界。

`@key("Ctrl+S")` の文字列→`(mods, code)` 変換は、テンプレート側では**文字列のまま表に
入れ**、`app.mln` が起動時にパースする（`parse_key_spec` を `.mln` に移す）。コンパイル時に
数値にしたければ C 案が要る — これは D 案と同じ判断。

### 4.3 コンパイラに残るもの

- `@` トークン、`attribute*` の構文（済）
- `annotation` 宣言の構文と、それに対する属性の検査（名前・引数の形・対象・`requires`）
- ディレクティブの評価（フィールド・メソッド・属性引数の列挙）と文字列展開
- 展開結果の再パース（`parse_generated_toplevels`、済）
- `@tramp` の生成（`ensure_method_trampoline`、済）
- DOM markup の `onClick={c->click}` → トランポリン置換（済。これは DOM 文法側の機能）

消えるもの：`parser_lower_app.c` の `collect_methods` / `lower_one_app` / `read_app_attr` /
`parse_key_spec`、つまり **名前と意味の全部**。

### 4.4 `app.mln` 側

`__app_T_desc()` が返す表のレイアウトは `annotations.mln` のテンプレートと `app.mln` の
`D_*` の**同じファイル群**で決まる（両方 MyOS 側）。コンパイラの docs から表の説明が
消え、`system/MyOS/docs/APP_FRAMEWORK.md` だけが正になる。

### 4.5 移行手順

1. `annotation` 宣言の構文 + 属性検査（A 案相当）。C の意味は残したまま、宣言と C の
   突き合わせで動くことを確認
2. ディレクティブ評価器（`@T`, `@each`, `@fields`, `@methods`, `@arg`, `@tramp`, `@i`,
   `@count`, `@sizeof`）
3. `annotations.mln` を書き、生成結果が今の C 実装と**同一テキスト**になることを比較
4. `parser_lower_app.c` から意味を削除、`grammar.md` の表を「機構」の説明に書き換え
5. `parse_key_spec` を `app.mln` へ

---

## 5. 実装状況

- 2026-09-18: `@`属性構文、C 実装の `@app` lowering、`ref=`、デフォルト引数、
  `(owner, id, arg)` ABI、MyOS フレームワーク（MYOS-016）。§1 の状態。
- 2026-09-19: B 案（テンプレート）→ E 案（デコレータ関数 + `__annotations_init`）と試し、
  最終的に **F 案：Java 式メタデータ** に落ち着いた。

### F 案（採用）— アノテーション = 宣言付きメタデータ、ライフサイクルは framework

```mylang
// annotations.mln — Java の @interface 相当。呼ばれない
export void timer(i32 fn, char *type, i32 size, i32 ms);

@timer(100)
void (Terminal *t) poll() { ... }
// → コンパイラが terminal___annotations() の表に 1 行:
//    ["timer", Terminal__poll, "Terminal", sizeof(Terminal), 1, 100, 0, 0]
```

- **mlc**：`@a(x)` を宣言（同ファイル / symbol-list import）と照合し、モジュールの
  `annotations` 束ねセクションに 8 ワード × 行の**静的データ**を出す。関数は呼ばない、
  名前の意味も知らない
- **リンカ**：全オブジェクトの `annotations` チャンクを 1 本のセクションに物理連結し、
  `__sections` ディレクトリに名前で載せる（`docs/design/toolchain-collected-sections.md`）。
  チャンクを持つオブジェクトは参照されなくても落とさない。当初は `main.mln` の
  `extern i32* __annotations_table(i32 m);` という目印をコンパイラが定義に置き換える方式で
  動かしたが、`.word` と `.section` を toolchain に足してリンカに移した。索引（アドレス・サイズの
  ペア列）を歩く方式も一度作ったが、読み手が「チャンク」を意識するのは分担として筋が悪いので、
  連結して名前で探せる形にした
- **MyStdLib**：`memory/section.mln`（セクションを名前で `as_slice<T>`）、`meta/annotations.mln`
  （`annotations.named("app")` → `it.next()` / `it.fn()` … のイテレータ）。読み手の共通部分は
  framework ではなく stdlib に置く。これを書くのに mlc へ**クロスパッケージのメソッド呼び出し**
  （import した型の export メソッド）と `sizeof(型)` を足した
- **MyAppFramework**：`annotations.mln`（宣言）、`app.mln`（`install()` がイテレータで registry
  へ。いつ・順序・検証はここ）
- **発見**：`main.mln` がアプリを明示 import（暫定）。最終形はアプリを MFS 上の .mbin にし、
  同じ表を MBIN ヘッダに載せてローダが読む（main.mln の TODO）

Python の manifest 生成、`__annotations_init`、テンプレート、`annotation` キーワード、
`@tramp` は全部無い。呼び出し規約が余分な引数を無視する（実測）ので、`onClick={c.click}` も
`@timer` のメソッドも実体をそのまま表に載せられる。

### 途中で捨てた案

- **B（テンプレート）**：記法（`@each`, `@{T}`）を確認せずに決めて実装したので差し戻し。
  記法を増やすほど角が増える（識別子内 splice、コメント内の `@` の誤爆）。
- **E（デコレータ関数）**：`a(fn, "T", sizeof(T), x)` を `__annotations_init()` に生成。動いたが、
  「いつ走るか」をコンパイラが決めること、Python 的な直感と裏腹に何も wrap しないこと、
  ライフサイクルが framework に無いことから、F に。E との差はコンパイラが出すものが
  「呼び出し」か「データ」かだけで、F は複数の読み手・遅延処理・検証の場所を framework 側に持てる。

### 実装して分かったこと・直したこと

- **toolchain に足したもの**（`docs/design/toolchain-collected-sections.md`）：`.word symbol`
  （`RELOC_WORD32`）、`.section NAME` + `CollectEntry`（LNK3）、リンカの物理連結と `__sections`
  ディレクトリ、活性化規則、重複定義の検出、`extern` グローバルの import 化、グローバル
  ポインタの静的初期化（`char *s = "x";` が null になるバグの解消）。

- **mlc に足したもの**：`import { T }` で T の export メソッドが呼べる（フィールド型・実体化済み
  generic も一緒に取り込む）、連鎖レシーバ `pkg.f().m()` の型解決、`sizeof(型)`、generic
  テンプレート本体の export 名の link 名への書き換え（importer の TU で実体化しても同パッケージの
  export 関数を呼べる）。

- **`ref mut` の書き戻しバグを修正**（`codegen_lvalue.c`）：参照型の変数への `s.v` が、参照を
  deref せずに「ポインタが入っているスロット」をフィールドとして読み書きしていた。修正後は
  `ref` / `ref mut` レシーバも handler に使える（Counter が `ref mut Counter c` で書かれている）。
- グローバルの `char *g[16]`（ポインタ配列）が誤コンパイルされる（未修正）。`i32` 配列で回避。
- リンカは同名シンボルの重複を検出しない（黙って片方を選ぶ）。
- `Ok(Some(idx))` を値の case で受ける struct コピー未対応（MYOS-016 で判明）は残っている。
