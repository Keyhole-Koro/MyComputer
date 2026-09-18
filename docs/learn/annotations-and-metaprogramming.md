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
  `(owner, id, arg)` ABI、MyOS フレームワーク（MYOS-016）。本メモの §1 の状態。
- B 案への移行: 未着手。上の §4.5 の順で。
