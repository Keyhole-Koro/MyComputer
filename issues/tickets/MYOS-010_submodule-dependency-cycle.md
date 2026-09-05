# MyKernel / MyOS 相互依存の解消

## 背景

`system/MyKernel` と `system/MyOS` は独立した git submodule だが、互いに import
しあっている。そのため **どちらも単体では build もテストもできない**。

```
MyKernel → MyOS   src/kernel/main.mln (dom, fs, shell, compositor, counter)
MyOS → MyKernel   src/fs/{fs,ssd}.mln, src/ui/{dom,compositor}.mln,
                  src/apps/{shell,counter.dom}.mln
```

MLC-004 phase 0 の作業中に、この循環の中でも特に筋の悪い形が見つかった。
**MyOS の `fs.mln` / `dom.mln` に対するテストが MyKernel のリポジトリに置かれ、
`../../../MyOS/src/...` で越境していた** —— テストが被テスト対象と別の git repo に
あった。これは対応済みで、テストは MyOS へ移した（MyOS `tests/fs/`, `tests/dom/`）。

残っているのは本体側の循環。

## 問題

- submodule を単体で CI にかけられない。片方の変更が他方の pointer 更新と
  同時でないと検証できない
- 依存の向きが定義されていないため、どちらに置くべきコードかの判断基準がない
- `MyKernel/src/kernel/main.mln` がデモアプリ（counter）まで import しており、
  カーネルがアプリを知っている

## 目標

依存を **MyOS → MyKernel の一方向**にする。MyKernel は OS 層を知らない。

## 設計方針

MYOS-009（Kernel UI Separation, In Progress）がすでに
「カーネル main から compositor とデモアプリを分離する」を掲げており、本チケットは
その完了条件を「MyKernel から MyOS への import がゼロになること」まで広げるもの。

想定される手段:

- カーネルは起動後に「OS エントリポイント」を1つ呼ぶだけにし、そのシンボルを
  リンク時に MyOS 側が供給する（`extern` 宣言 + リンカ解決）
- `main.mln` を MyKernel 側の最小起動シーケンスと、MyOS 側の
  `os_main()` に分ける

## 検証

- `grep -rn "MyOS/" --include=*.mln --include=*.masm system/MyKernel` が空になる
- MyKernel 単体で `tests/` が全て通る

## 完了条件

- MyKernel から MyOS への import が存在しない
- MyKernel の CI が MyOS のチェックアウトなしに通る
- 依存の向きが docs に明記される

## 関連

- MYOS-009 Kernel UI Separation
