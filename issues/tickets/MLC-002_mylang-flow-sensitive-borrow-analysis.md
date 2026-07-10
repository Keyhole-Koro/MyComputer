# MyLang Flow-Sensitive Borrow And Move Analysis

## 背景

MyLangCompiler には semantic stage があり、use-after-move、borrow 中の move、
shared borrow と mutable borrow の競合、local reference return などの基本的な安全性検査が
入っている。

一方で、現状の coverage document では以下が薄いと明記されている。

- branch-sensitive move state merge
- field-sensitive move tracking
- borrow conflicts through function calls
- raw-pointer restrictions inside and outside `unchecked`

所有権と borrow のルールは、OS / driver / UI object tree のような長寿命データ構造を扱う時に
言語の安全性と書き味を直接決める。今のままだと、単純な直線コードは守れても、分岐・関数境界・
struct field をまたぐケースで false positive / false negative が出やすい。

## 問題

### 分岐後の move 状態

```mylang
i32 main() {
    Buffer b = make_buffer();
    if (cond()) {
        consume(b);
    }
    use(b);
    return 0;
}
```

片方の branch だけで move された値を、分岐後にどう扱うかを定義する必要がある。

### field 単位の move

```mylang
Pair p = make_pair();
consume(p.left);
use(p.right);
```

struct 全体を moved と見るか、field 単位で tracking するかを決める必要がある。

### 関数呼び出し越しの borrow

```mylang
ref i32 r = &x;
mutate(&mut x);
```

関数引数に `ref` / `ref mut` を渡した時、呼び出し前後の borrow 状態をどう扱うかが未整理。

## 目標

- 分岐後の move / borrow 状態 merge ルールを定義する。
- field-sensitive tracking の最小仕様を決める。
- 関数呼び出し時の borrow effect を検査する。
- `unchecked` と raw pointer 操作の境界を明確にする。
- semantic failure fixture で false negative を防ぐ。

## 非目標

- Rust と同等の borrow checker を一気に作ることは目指さない。
- lifetime parameter や generic lifetime は扱わない。
- 高度な alias analysis は扱わない。

## 設計方針

### 1. まずは保守的な merge ルールにする

分岐後の状態は安全側に倒す。

- どちらかの branch で moved なら、merge 後は maybe moved とする。
- maybe moved の値を read / move しようとしたら semantic error にする。
- 両 branch で確実に初期化された local は initialized とする。

将来、definite assignment と合わせて状態 lattice を整理する。

### 2. Field-sensitive tracking は浅く始める

最初は `base.field` の 1 階層だけを tracking する。

- `p.left` を move しても `p.right` は使える。
- `p` 全体を move したら全 field が使えない。
- `p.left.sub` のような深い path は、最初は `p.left` として扱う。

### 3. Function call effects を signature から読む

関数 parameter が `ref` か `ref mut` かを見て、call site で borrow conflict を検査する。

- `ref` 引数: shared borrow として扱う。
- `ref mut` 引数: mutable borrow として扱う。
- by-value non-copy 引数: move として扱う。

parameter が `ref` / `ref mut` / by-value のどれかは
`mylang-function-signature-type-checking.md` が `SemanticFunctionSig` に追加する
`param_borrow_kinds` から読む。本チケットは signature 側の拡張を前提とし、
借用種別の保持自体は ISSUE-016 の責務とする（フェーズ4 は ISSUE-016 完了に依存する）。

### 4. `unchecked` の仕様を分ける

`unchecked` は raw pointer 操作を許すための escape hatch とする。
ただし、通常の reference safety を完全に無効化するか、raw pointer 操作だけを許すかは明文化する。

初期方針:

- raw pointer dereference は `unchecked` 内だけ許可する。
- `ref` / `ref mut` の基本 conflict は `unchecked` 内でも可能な範囲で維持する。

`mylang-standard-library-foundation.md` は MMIO / device アクセスを標準 library の
`unchecked` 境界で隠す方針を持つ。その場合でも、library 関数の signature に現れる
`ref` / `ref mut` に対する borrow conflict 検査は呼び出し側で維持される。
`unchecked` が無効化するのは raw pointer dereference の制限のみであり、
reference safety（`ref` / `ref mut` conflict）は無効化しない、という境界を両チケットで共有する。

## 段階移行

### フェーズ1: 状態 model の文書化

- move / borrow / maybe moved / initialized の状態を docs にまとめる。
- 既存 behavior と異なるケースを fixture 化する。

### フェーズ2: Branch merge

- `if` / `case` / loop 後の状態 merge を実装する。
- branch-sensitive fail fixture を追加する。

### フェーズ3: Field-sensitive tracking

- binding key を `name` だけでなく `name.field` まで扱えるようにする。
- struct field move fixture を追加する。

### フェーズ4: Function call effects

- function signature の parameter type から borrow / move effect を適用する。
- call 越しの borrow conflict fixture を追加する。

### フェーズ5: Raw pointer restrictions

- unchecked 外の raw pointer dereference を semantic error にする。
- unchecked 内の許可範囲を fixture 化する。

## 検証

1. `python3 toolchain/MyLangCompiler/tests/run_semantic_tests.py`
2. `python3 qa/mlc-test.py`
3. `make -C toolchain/MyLangCompiler clean all`

## 変更ファイル（想定）

- `toolchain/MyLangCompiler/src/semantic/semantic_walk.c`
- `toolchain/MyLangCompiler/inc/mylang/semantic/semantic_internal.h`
- `toolchain/MyLangCompiler/tests/semantic_coverage.md`
- `toolchain/MyLangCompiler/tests/fail/semantic/*`
- `toolchain/MyLangCompiler/tests/succeed/semantic/*`

## 完了条件

- 分岐後の maybe moved が検出される。
- struct field の独立した move が最小限扱える。
- `ref` / `ref mut` 引数を持つ関数呼び出しで borrow conflict が検出される。
- raw pointer 操作の unchecked 境界がテストで固定される。
