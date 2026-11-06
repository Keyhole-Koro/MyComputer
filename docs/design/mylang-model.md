# MyLang モデル拡張：entity と関係

**Status:** 実装済み（2026-11-06）。DOM のノード表、コンソール、シェルのインスタンスがこれで書かれている。

**Scope:** `.model.mln` の宣言、生成するコード、`delete` の連鎖、索引、`Blob`、制約

関連文書:

- `docs/design/mylang-values.md`: 言語の核。この文書は核に規則を足さない。
- `toolchain/MyLangCompiler/docs/source-modifiers.md`: ファイル名の修飾子。
- `toolchain/MyLangCompiler/src/frontend/model/model_expand.c`: 実装。

---

## 0. 一言で

- 核は値、借用、unsafe のまま。つながりの手入れだけを言語の外に出す。
- `.model.mln` に entity と関係を宣言すると、普通の MyLang の型とメソッドに展開される。
  字句解析の前のテキスト展開で、意味解析より後ろはモデルを知らない。
- 使う側に特別な構文はない。普通のメソッド呼び出しで読み書きする。
- 展開されたコードは安全なファイルとして検査される。生成器のバグは論理の誤りにはなるが、
  範囲検査と世代比較の内側に収まる。

## 1. 宣言

```text
entity Node   max 512 { i32 kind; Text<64> text; i32 owner; }
entity Window max 16  { Text<64> title; }

Node   has   many Node as children / parent, ordered;
Window knows one  Node as focus;

index Node.owner;
```

| 語 | 意味 |
| --- | --- |
| `entity T max N` | 最大 N 行の表。N は 4095 まで |
| `A has one/many B` | 所有。A が消えれば B も消える |
| `A knows one B` | 関連。B が消えれば関連が外れる |
| `A knows many B` | 関連の鎖。A が消えても B は残り、鎖から外れる |
| `as 名前 / 逆の名前` | 両側のメソッド名。逆の名前は省ける |
| `ordered` | 順序を保つ。どの鎖も追加の順を保つので、意図を書くための語 |
| `index T.列`、`unique T.列` | `i32` の列で引くハッシュ表 |

宣言ではない行は、そのまま展開先に残る。`package` と `import` はここに書く。

## 2. 生成するもの

| 宣言 | 生成するもの |
| --- | --- |
| `entity T` | `struct T { i32 id; }`、`TRow`、`new_t()`、`is_live()`、`row()`、`raw()`、`t_from_raw()`、`delete()`、`t_all()` |
| `has`、`knows many` | `name()` の反復子、`name_add()`、`name_detach()`、`name_first()`、`name_last()`、`name_next()`、`name_prev()`、`name_count()`、逆の名前 |
| `knows one` | `name()`、`set_name()`、`clear_name()` |
| `index`、`unique` | 列の読み書き、`t_by_列()` |

列は `row()` が返す `borrow TRow` から読み書きする。索引のある列だけは `row()` に出ず、
専用の読み書きを通す。索引を壊さないため。

ID を語のまま持つコード向けに、`t_live_id()`、`t_row_id()`、`t_name_first_id()`、
`t_name_next_id()`、`t_逆の名前_id()` もある。構造体を作らず、呼び出しが一段で済む。

## 3. ID と世代

ID は `世代 << 12 | 番号 + 1` の1語で、0 は「無し」。行を消すと世代が進むので、番号が再利用
されても古い ID は生きている行に届かない。`row()` は古い ID を表の範囲外の添字に変えるので、
範囲検査が trap する（`0x1BAD01`）。

## 4. 容量と失敗

`max` が表の大きさを決める。表は静的な配列で、確保器を使わないのでカーネルでも使える。
`new_t()` は一杯なら None を返す。

## 5. 制約

- **モデルは一ファイルで閉じる。** `delete` は、その entity に触る関係を全部知る必要がある。
- **モデルをまたぐ参照は値。** `i32` の列に持ち、連鎖しない。
- **多対多は未実装。** 対を entity にして書く。宣言するとエラーになる。
- **`delete` は再帰する。** 深い木はスタックを使う。

## 6. 可変長の列：`Blob`

`@std/memory/blob.mln` の `Blob` は、確保した可変長のバイト列を指す世代つきの番号。列の型に
使える。読み書きは範囲検査つきのメソッドだけで、偽の番号は何にも届かない。

`free()` は番号をすぐ無効にするが、バイト列は `collect()` まで残す。`str` は保存できないので、
`str` が生きていない地点で `collect()` を呼べば、解放済みのメモリを読む `str` は残らない。
DOM では、コンポジタの1周の終わり、DOM のロックの中で呼ぶ。

## 7. 未決事項

- 共有値（`mylang-values.md` §6）を実装した時、`Blob` をどう扱うか。
- 多対多の関係。
