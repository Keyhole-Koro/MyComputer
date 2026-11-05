# MLC-025: 参照数つきオブジェクトと rc / owned モード

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Proposed | - | - | 2026-11-05 |

## Summary

`docs/design/mylang-memory-model.md` の §4（オブジェクト）、§6（モード）、§9（スレッドと
割り込み）を実装する。`new` と共有ポインタ `T^`、`weak`、`share()`、ファイルごとの
rc / owned モード、ポインタの先の借用の保持（規則 B7）が中心。

## Background

- 今のヒープは `heap.alloc` / `heap.free` を直接呼ぶ。返るのは整数のアドレスで、解放忘れと
  二重解放を防ぐものがない。`system/` 以下で43箇所。
- 所有権と借用（move、`Drop`、`borrow`）は実装済みで、残す。穴は MLC-024 で塞いだ。
- 2026-10-30 の議論で、rc を実装し、所有権と借用もモードとして選べるようにすると決めた。

## Design

### Current State

- `src/backend/codegen/codegen_drop.c`: Drop つきの値の実行時の持ち主フラグと、スコープの
  終わりの drop。参照数の −1 の土台になる。
- `toolchain/MyStdLib/memory/allocator.mln`: 標準のアロケータの境界（`configure()` で
  確保と解放の関数を差し込む）。カーネルは `heap.alloc`、アプリは MyAppFramework の
  first-fit を使う。
- 安全性のプロファイルは、ファイル名の `.unsafe.mln` で決まる（`source_spec.c`）。
  ジェネリックの本体は、テンプレートを書いたファイルのプロファイルで検査する
  （`fundef.origin_path` / `origin_unsafe`）。モードも同じ仕組みに載せられる。
- カーネルの末尾は `0x1FB3CC`（2026-10-30）。21 ビット即値の上限 `0x200000` まで約 19 KB
  しかない。増減のコードでカーネルが大きくなるので、先に MLC-027 の命令の追加か、
  カーネルの配置の見直しが要る。

### Proposed Design

1. **ランタイム。** オブジェクトの前に参照数（と weak の数）のヘッダを置く。確保は
   サイズ別のページから。解放は、中身の drop → メモリを返す。デバッグ用の漏れ検査。
2. **コンパイラ。**
   - 型 `T^`、`weak T^`、式 `new T { ... }`、`try_new T { ... }`、`x.share()`。
   - 共有できる値のコピーで +1、上書きとスコープの終わりで −1（codegen_drop.c を広げる）。
   - 型ごとの drop の処理（中の共有ポインタの −1、`drop` の呼び出し）。
   - 値の種類の自動判定（規則 V2）。データだけの struct の自動コピーは MLC-024 で入れた。
     残りは、共有できる値の区別と、生ポインタのフィールドを持つ struct の扱い。
   - move した元をゼロにする（規則 V4）。持ち主フラグは要らなくなる。
   - ポインタの先の借用の保持（規則 B7）、payload の取り出し（規則 B8）。
   - null の検査（規則 C2）と確保の失敗（規則 C3）の trap。
3. **モード。** `mode owned;` / `mode unsafe;` の宣言（規則 M1、U2）。owned では共有できる
   値を move-only として検査し、rc ではコピーを共有にする。`.unsafe.mln` のファイル名は
   廃止する。
4. **カーネルとスレッド。** 参照数の増減を atomic に（当面は `cas`）。割り込みの中で0に
   なったものは後で解放する。
5. **`str`** を借用と同じ置き場所の規則にする（規則 B2）。

### Alternatives Considered

- 共有ポインタを今の `T*` にする: 今のコードの `T*`（生ポインタ）の意味が一度に変わって
  しまい、少しずつ移せない。`T^` で始め、移行が終わった後に寄せるかを決める。
- 共有ポインタを標準ライブラリの `Rc<T>` にする: 文法は変えずに済むが、`p.x` で中に
  触れるための仕組みがどのみち要り、書く量も増える。

### Non-Goals

- 既存コードの移行（MLC-026）。
- 循環の回収（漏れ検査で見つけるところまで）。

## Progress

- [ ] rc を入れる前の基準の計測（MLC-027）
- [ ] ランタイム（ヘッダ、確保、解放、漏れ検査）
- [ ] `T^`、`new`、`try_new`、参照数の増減、型ごとの drop
- [ ] `weak`
- [ ] 共有できる値の区別（規則 V2 の残り）、move した元のゼロ化
- [ ] `mode` 宣言（owned / unsafe）と `share()`
- [ ] ポインタの先の借用の保持、payload の取り出し
- [ ] null と確保の失敗の trap
- [ ] atomic な増減、割り込みの中の解放の先送り
- [ ] `str` の置き場所

## Verification

```bash
make -C toolchain/MyLangCompiler test-component
make -C toolchain/MyLangCompiler test-e2e
make build && make qa
```

## 完了条件

- 規則 O1〜O7、B7、B8、M1〜M5、C2、C3、T1〜T3、U2 に、成功例と失敗例のテストがある。
- 同じソースを rc と owned で動かした e2e が、同じ結果を返す（規則 M3）。

## 関連

- `docs/design/mylang-memory-model.md`
- MLC-024 借用検査の穴を塞ぐ
- MLC-026 既存コードの移行
- MLC-027 メモリモデルの性能
