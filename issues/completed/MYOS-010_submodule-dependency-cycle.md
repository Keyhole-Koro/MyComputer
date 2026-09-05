# MyKernel / MyOS 相互依存の解消

## 背景

`system/MyKernel` と `system/MyOS` は独立した git submodule だが、互いに import
しあっていた。そのため **どちらも単体では build もテストもできなかった**。

```
MyKernel → MyOS   src/kernel/main.mln (dom, fs, shell, compositor, counter)
                  tests/fs/*, tests/dom/dom_hit_dispatch.test.mln
MyOS → MyKernel   src/fs/{fs,ssd}.mln, src/ui/{dom,compositor}.mln,
                  src/apps/{shell,counter.dom}.mln
```

## 原因

どちらも「MyOS の仕事を MyKernel のファイルでやっていた」という同じ形だった。

**テスト**: MyOS の `fs.mln` / `dom.mln` に対するテストが MyKernel のリポジトリに
置かれ、`../../../MyOS/src/...` で越境していた。テストが被テスト対象と別の git repo
にあった。

**起動処理**: `MyKernel/src/kernel/main.mln` の `kernel_init()` を仕事で分けると、
大半が OS 側のものだった。

| カーネルの仕事 | OS の仕事 |
| --- | --- |
| `heap.init()` | `dom.init()` |
| `scheduler.init()` | `counter.mount()` / `dom.dump()` |
| `irq.set_handler()` | `fs.init()` |
| `irq.enable()` | `scheduler.spawn_task(shell.run)` |
| | `compositor.run()` |

カーネルがデモアプリ（counter）まで import している状態だった。

## 対応

置き場所を直しただけで、仕掛けは何も足していない。

**テスト → MyOS へ**

```
MyOS/tests/fs/{test_fs_smoke,test_minode_fd}.mln + stub + runner
MyOS/tests/dom/dom_hit_dispatch.test.mln
```

`MyKernel/tests/dom/dom_lowering.dom.test.mln` は残した。compiler の `.dom.mln`
lowering 契約を検証するもので、MyOS に依存していない。

**起動処理 → MyOS へ**

```
MyOS/src/boot/main.mln     システム起動。MyKernel を import する（許される向き）
MyOS/src/boot/stub.masm    __START__ から kernel_main を呼ぶ
```

`stub.masm` は4行のファイルで、しかもテスト側はすでにこの形だった —— 各テストが
自分の stub と自分の `kernel_main` を持ち、「イメージの入口は誰か」はビルドする側が
決めていた。`main.mln` だけがその原則から外れていた。

当初は「カーネルが OS エントリを1つ呼び、そのシンボルを `extern` でリンク時に
解決する」という案を書いたが、これは `main.mln` が MyKernel にあることを前提に
した余計な仕掛けだった。前提を疑えば移動するだけで済む。

`qa/runners/run_kernel.py` と `run_system.py` のデフォルト `--source` / `--stub`
を MyOS 側に変更した。

## 結果

```
$ grep -rn "MyOS/" --include=*.mln --include=*.masm system/MyKernel
(空)
```

MyKernel から MyOS への参照はゼロになった。依存は MyOS → MyKernel の一方向。

検証:

```
qa/runners/run_system.py --no-run          build complete
qa/runners/run_kernel.py --headless        boot → dom ready → shell task → MyOS>
MyKernel tests/libs/run_std_test.py        164 checks PASS
MyKernel tests/heap/run_heap_tests.py      7 passed, 0 failed
MyOS     tests/fs/run_fs_smoke_test.py     PASS
MyOS     tests/fs/run_minode_fd_test.py    PASS
```

## 残っていること

MyKernel 単体 CI（MyOS のチェックアウトなしで `tests/` が通ること）はまだ設定して
いない。参照はゼロになったので、あとは CI 定義だけ。

## 関連

- MYOS-009 Kernel UI Separation —— 「カーネル main から compositor とデモアプリを
  分離する」という同じ主題。本件で `main.mln` ごと MyOS に移したため、MYOS-009 の
  主要部分も満たされている。
