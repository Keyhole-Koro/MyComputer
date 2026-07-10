# MyLang Test Diagnostics Strategy

## 背景

`*.test.mln` + `mytest` によって、kernel/emulator E2E テストを MyLang 側に寄せられるように
なった。一方で、MyLang を実行するには compiler、assembler、linker、emulator、kernel
library がすべて必要になる。

そのため、Python runner をすべて `.test.mln` に置き換えると、テスト本文は読みやすくなるが、
失敗時の原因切り分けが難しくなる可能性がある。

## 問題

`.test.mln` の失敗原因は広い。

- MyLang compiler の regression
- assembler / linker の regression
- emulator の regression
- kernel library の regression
- `mytest` の test declaration lowering の regression
- テスト対象機能そのものの regression

E2E としては有用だが、低レベル機能の単体テストまで全部 `mytest` に寄せると、どの層が
壊れたか分かりにくい。

## 方針案

- `.test.mln` は「縦通しが動くこと」を確認する E2E DSL として使う。
- compiler / syntax / semantic / assembler / linker のホスト側テストは残す。
- `qa/run_kernel.py` や `qa/run_mylang.py` のような手動実行・デバッグ用ツールは残す。
- Python runner を置き換えるかどうかは、診断性が悪化しないケースから判断する。
- 置き換える場合も、失敗時に build log、generated source、emulator output、linked binary の
  パスを明確に出す。

## 置き換え候補

### 向いている

- `serial_rx.test.mln`
  - 既に `mytest` へ移行済み。
  - IRQ 経由の serial RX、echo、halt、`kernel: heap ready` を E2E で確認する。
- scheduler E2E
  - もともと emulator + timer interrupt 前提。
  - `timer_interval` option と serial marker 判定で `.test.mln` 化しやすい。

### 慎重に判断する

- heap tests
  - 現在は R1 や panic serial output を Python が直接判定している。
  - `.test.mln` 化は可能だが、低レベル allocator regression の切り分けは悪化する可能性がある。
- filesystem smoke
  - `.test.mln` 化には `mytest` の `disk` option が必要。
  - persistent disk / temporary disk の扱いを決める必要がある。

## 将来やるかもしれないこと

- `mytest` に failure diagnostics を追加する。
  - generated source path
  - build directory
  - build command
  - emulator command
  - emulator output tail
  - expected string mismatch の前後文脈
- `mytest --keep-artifacts` を追加する。
- `mytest --verbose` を追加する。
- `options` に `disk`, `reg`, `timeout` などを追加するか検討する。
- `qa/test-all.py` 上で、E2E と host-level tests を明確に分類表示する。

## 完了条件

- どの Python runner を `.test.mln` に移行し、どれを残すかの判断基準が文書化されている。
- `mytest` 失敗時に、少なくとも build と emulator のどちらで落ちたかすぐ分かる。
- `qa/test-all.py` の suite 表示で、E2E 失敗と host-level 失敗が区別できる。
