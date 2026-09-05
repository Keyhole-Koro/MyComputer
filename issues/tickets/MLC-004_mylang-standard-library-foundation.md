# MyLang Standard Library Foundation

## 背景

MyLang は kernel、emulator、test framework と一緒に育っているため、言語機能だけでなく
標準的な library surface が重要になっている。

現状は kernel tests や runtime support の中に必要な helper が増えているが、文字列、メモリ、
配列、I/O、assertion、device access のような基本 API をどこに置き、どう versioning するかは
まだ薄い。

DOM 的 OS object model、filesystem、UI、test framework を伸ばす前に、MyLang 側の標準 library の
最小構成を決めておきたい。

## 問題

library の置き場所や API 方針が曖昧だと、以下が起きる。

- test-only helper と production kernel helper が混ざる。
- 同じ処理が複数 package に重複する。
- compiler / linker / package import の fixture が現実の使い方とずれる。
- OS API の呼び出し規約が場当たり的になる。
- LSP / docs / examples が追従しづらい。

## 目標

- MyLang standard library の最小 package 構成を決める。
- kernel-only / userland-like / test-only の境界を決める。
- 文字列、メモリ、配列、serial、assertion の最小 API を定義する。
- package import / export の実例として compiler tests に使う。
- docs と examples を整備する。

## 非目標

- 大規模な libc 互換 library は作らない。
- dynamic allocation 前提の高機能 collection は、heap 方針が固まるまで後回しにする。
- user process model がない段階で POSIX 風 API を作り込まない。

## 設計方針

### 1. Package を用途で分ける

候補:

```text
std.core      基本型 helper、panic、halt
std.mem       memset / memcpy / memcmp
std.str       string length / compare / copy
std.serial    serial read / write
std.test      assertion / test reporting
kernel.*      kernel 内部 API
device.*      MMIO / device register wrapper
```

`std.test` は test-only として扱い、production image に混ざらないようにする。

### 2. Compiler tests と実利用を揃える

package import/export の compiler fixture は、人工的な `pkg_math` だけでなく標準 library の
小さい実例も使う。

### 3. 低レベル API は明示的に unsafe / unchecked と接続する

MMIO や raw pointer 操作は `unchecked` と関連する。
標準 library 側で unsafe 境界を隠す場合、どこで安全性を保証しているか docs に書く。

### 4. Test framework と連携する

`system/MyKernel/tests/libs/test.mln` にある assertion API を、将来的に `std.test` へ寄せるか、
`kernel.test` として残すかを本チケットで決定する（両論併記のまま次工程へ進めない）。
この決定は `mylang-test-framework.md`（ISSUE-013）と `mylang-test-diagnostics-strategy.md`
（ISSUE-014）が assertion library の package 名に依存するため、下流の命名確定の前提になる。

## 段階移行

### フェーズ1: Library inventory

- 既存 `.mln` helper を一覧化する。
- test-only / kernel-only / reusable を分類する。

### フェーズ2: Package layout 決定

- directory layout
- package names
- import style
- build_toolchain の source discovery 方針

### フェーズ3: Minimal core APIs

**実装済み**（`system/MyKernel/src/lib/`）:

| package | 内容 |
| --- | --- |
| `str` | len / cmp / eq / ncmp / starts_with / copy / ncopy / cat / chr / find / itoa / xtoa / atoi |
| `bytes` | set / zero / copy / move / cmp / eq / find |
| `bitset` | get / set / clear / put / toggle / find_clear / find_set / count |
| `ringbuf` | init / push / pop / peek / has / full / count / capacity |
| `strbuf` | reset / push / append / append_n / append_i32 / append_hex / truncate |

`std.mem` は `bytes` という名前になった。`package mem`（`src/mm/mem.mln`）が
すでにカーネルの word 単位の絶対アドレスアクセサとして存在するため。

呼び出し側の回収も済んでいる: `serial.mln` の入力キュー（ringbuf）、
`MyOS/src/fs/fs.mln` のブロックビットマップ（bitset）、
`MyOS/src/apps/shell.mln` の私的な `str_eq`（str.eq）、
`MyOS/src/apps/counter.dom.mln` の手書き10進バイト列（strbuf）。

**保留**:

- `std.serial` — 既存の `serial` package をそのまま使っている。分離の必要性が
  出てから。
- `std.test` / `kernel.test` の命名決定 — 未決。下流の ISSUE-013 / ISSUE-014 が
  依存するため、別途決める必要がある。

API 設計は compiler の3つの制約に強く縛られている（struct が package 境界を
越えない、export した定数がリンクされない、乗除算命令がない）。詳細と実測の
根拠は `docs/design/mylang-stdlib-and-string.md`。制約自体の解消は
`MLC-016_cross-package-types-and-constants.md`。

### フェーズ4: Compiler fixtures

- standard library package を import する succeed fixture を追加する。
- non-exported helper import など fail fixture も追加する。

### フェーズ5: Docs

- package usage examples
- test library usage
- unsafe boundary

## 検証

1. `python3 qa/mlc-test.py`
2. `python3 qa/runners/run_mylang.py <std library example> --headless`
3. `toolchain/MyLangTester/build/mytest system/MyKernel/tests`

## 変更ファイル（想定）

- `toolchain/MyLangCompiler/docs/*`
- `toolchain/MyLangCompiler/tests/succeed/package/*`
- `system/MyKernel/src/lib/*`
- `system/MyKernel/tests/libs/*`
- `qa/runners/build_toolchain.py`

## 完了条件

- 標準 library の package layout が文書化されている。
- 最小 API が MyLang source として存在する。
- compiler package tests が標準 library の実例を使う。
- test-only library と production library の境界が明確になっている。
- assertion library を `std.test` / `kernel.test` のどちらにするかが決定・文書化され、
  ISSUE-013 / ISSUE-014 がその名前を前提にできる。
