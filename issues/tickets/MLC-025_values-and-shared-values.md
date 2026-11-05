# MLC-025: 値だけのメモリモデル（共有値、Box、プール）

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Blocked | - | - | 2026-11-05 |

> メモリモデルの候補が2つある（`docs/design/mylang-values.md` と
> `docs/design/mylang-objects.md`）。このチケットは前者に沿って書いてある。後者を採る場合は
> 書き直す。決まるまで着手しない。

## Summary

`docs/design/mylang-values.md` の §4（書き換え）、§6（ヒープの値）、§7（識別とつながり）、
§13（コンパイラと実行時）を実装する。共有値のカウントと「書く前にコピー」、`new` と
`Box<T>`、`Pool`・`Table`・`Handle`、グローバルの借用の保持、import での `.unsafe` の省略が
中心。

## Background

- 2026-10-30 に rc を採り、所有権と借用もモードで切り替える案（`mylang-memory-model.md`）を
  書いたが、`^`・`own`・`weak`・モードと、人が決めることが多かった。木と世代の案
  （`mylang-tree-generation-memory.md`）は代償が大きかった。
- 2026-11-05 に「値だけ」のモデルに決めた。安全なコードからポインタをなくし、代入をコピーの
  意味にし、つながりはプールとハンドルで表す。解放はコンパイラがする。
- 所有権と借用（move、`Drop`、`borrow`）は実装済みで、そのまま規則 V4〜V6、B1〜B6 になる。
  穴は MLC-024 で塞いだ。

## Design

### Current State

- `src/backend/codegen/codegen_drop.c`: 所有値の持ち主フラグと、スコープの終わりの drop。
  共有値のカウントの −1 の土台になる。
- `toolchain/MyStdLib/memory/allocator.mln`: 標準のアロケータの境界（`configure()` で確保と
  解放の関数を差し込む）。カーネルは `heap.alloc`、アプリは MyAppFramework の first-fit。
- `toolchain/MyStdLib/text/string.mln`、`collections/vec.mln`、`collections/hashmap.mln`:
  今は所有値（`Drop` を持ち、move）。中身を共有値にする。
- 安全性のプロファイルは、ファイル名の `.unsafe.mln` で決まる（`source_spec.c`）。
  ジェネリックの本体は、テンプレートを書いたファイルのプロファイルで検査する。
- カーネルの末尾は `0x1FB3CC`（2026-10-30）。21 ビット即値の上限 `0x200000` まで約 19 KB
  しかない。カーネルは共有値を使わない（規則 H6）ので、カウントのコードは増えないはず
  だが、確かめる。

### Proposed Design

1. **共有値の中身。** カウントつきのヘッダを持つバッファ。コピーで +1、上書き・スコープの
   終わり・コンテナからの削除で −1、0 で解放（`codegen_drop.c` を広げる）。型ごとの解放
   （中の共有値の −1、`drop` の呼び出し）。
2. **書く前にコピー（規則 W2）。** 共有値の中身への書き込みの前に、カウントが 1 かを確かめ、
   違えばコピーして持ち主を自分だけにする。書き込みの経路（`a.b.c = x`、`v.push()`、
   `&mut a.b`）ごとに1回。
3. **`new` と `Box<T>`。** `new T { ... }`、`try_new`、`b.x` / `b.f()` / `*b`。再帰する型の
   検査（`Box` を通さない再帰はエラー）。`Box<T>` にゼロ値がないことの検査（初期化の強制）。
4. **省略。** `borrow` の引数は数えない。最後の使用は move にする。増やして減らす組を消す。
5. **グローバルの借用の保持（規則 B7）。** グローバルの共有値を借りている間、中身を保持する。
6. **`Pool<T, N>`・`Table<T>`・`Handle<T>`・`Map<K, V>`。** 標準ライブラリ。世代つきの
   ハンドル、`get` / `get_mut` / `insert` / `remove` / イテレータ。
7. **move した元をゼロにする（規則 V4）。** 持ち主フラグを置き換える。
8. **import での `.unsafe` の省略（規則 U3）。** モジュールの解決（`module_loader.c` /
   `resolver.c`）と LSP。
9. **`impl Copy` の削除。** 規則 V2 の自動判定に置き換える（データだけの struct は MLC-024 で
   済み）。

### Alternatives Considered

- rc と所有権のモード切り替え（`mylang-memory-model.md`）: 人が決めることが多い。
- 木と世代（`mylang-tree-generation-memory.md`）: CPU の変更と触るたびの照合が要る。
- オブジェクト（識別と共有の書き換え）を言語に持つ: 輪と解放の問題が戻ってくる。識別は
  プールで足りる。

### Non-Goals

- 既存コードの移行（MLC-026）。
- 性能の最適化と CPU の命令（MLC-027）。

## Progress

- [ ] rc を入れる前の基準の計測（MLC-027）
- [ ] 共有値の中身（ヘッダ、カウント、解放、型ごとの解放）
- [ ] 書く前にコピー
- [ ] `new`、`Box<T>`、`try_new`、再帰の検査、初期化の強制
- [ ] 省略（`borrow` の引数、最後の使用、組の削除）
- [ ] グローバルの借用の保持
- [ ] `Pool`・`Table`・`Handle`・`Map`
- [ ] move した元のゼロ化
- [ ] import での `.unsafe` の省略
- [ ] `impl Copy` の削除

## Verification

```bash
make -C toolchain/MyLangCompiler test-component
make -C toolchain/MyLangCompiler test-e2e
make build && make qa
```

## 完了条件

- 規則 W1〜W3、H1〜H6、I1〜I4、B7、B8、C3、U3 に、成功例と失敗例のテストがある。
- `b = a; b.x = 1;` の後で `a.x` が変わらない e2e が、データ・共有値・`Box`・コンテナの
  それぞれにある。
- カーネルのサイズが上限を超えない。

## 関連

- `docs/design/mylang-values.md`
- MLC-024 借用検査の穴を塞ぐ（完了）
- MLC-026 既存コードの移行
- MLC-027 メモリモデルの性能
