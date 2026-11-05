# MLC-024: 借用検査の穴を塞ぐ

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Done | main | opencode:claude-opus-5.5 | 2026-11-05 |

## Summary

所有権と借用を rc と並べて残すことにした（`docs/design/mylang-memory-model.md`）。そのため、
借用検査を安全の仕組みとして信用できるようにする。2026-10-30 に見つけた穴のうち、借用に
関わるもの（共有借用を通した書き込み、借用中の元の変更、ループの中の move、借用から生
ポインタへの変換、`const` の可変借用）を塞ぐ。

## Background

次のコードは、どれも checked なファイルでエラーにならずに通っていた（2026-11-05 に
`mlc` で確認）。

| コード | 破っている規則 |
| --- | --- |
| `void f(borrow P p) { p.x = 9; }`、`p.x++`、`borrow P r = &a; r.y = 5;` | B4: 共有借用を通した書き換え |
| `borrow P r = &p; p.x = 10; p = P {...};` | B4: 借用中の元の書き換え |
| `borrow mut P m = &mut q; i32 w = q.x; q.y = 3;` | B5: 可変借用中に元を使う |
| `const i32 c = 3; borrow mut i32 cm = &mut c;` | B1: `const` の可変借用 |
| `while (...) { take(q); }`（`q` はループの外の Drop つきの値） | V4: 2周目で move 済みの値を使う。実行時には二重 drop になる |
| `Holder keep(borrow P r) { return Holder { p: r }; }`、`P *p = r;`、`g_p = r;`、`i32 v = r;` | B9: 借用が生ポインタやアドレスになり、追跡が切れる |

調べる中で、もう1つ穴が見つかった。`borrow mut` の引数（またはそれを持つローカル）から
取った借用は、その引数をロックしていなかった。

```c
i32 f(borrow mut Vec<i32> v) {
    Option<borrow mut i32> first = v.at_mut(0);
    v.push(1);      // 通っていた。push の再確保で first がぶら下がる
    ...
}
```

逆に、抜ける分岐の move を合流後も move 済みとして扱っていた（誤検出）:

```c
R w = R { h: 3 };
if (i > 0) { take(w); return 1; }
take(w);    // error: use of moved value 'w'
```

`case` の腕には同じ扱い（`case_arm_diverges`）があったが、`if` にはなかった。

## Design

### Current State（着手前）

- `src/semantic/semantic_walk.c` が、レキシカルな借用と move を1回の走査で検査する。
  - `SemanticBinding` に、move 済み（`moved`）、借りている元（`borrowed_from`）、
    共有借用の数（`shared_borrow_count`）、可変借用中（`mutable_borrow_active`）を持つ。
  - `hold_borrow()` が借用の衝突を、`use_identifier()` が move 済みの使用と借用中の move を
    検出する。
  - `AST_CALL` は、引数の一時的な借用を呼び出しの間だけ数える。
  - `if` と `case` は、分岐ごとに状態を取って合流させる（`merge_if_binding_states()`）。
- 書き込み先（代入の左辺、`++`/`--`、`&mut`）が、共有借用を通っているかを見ていなかった。
- ループの本体は1回だけ走査していて、次の周回への流れを見ていなかった。
- 借用から生ポインタへの変換は、型の互換性の検査で許されていた。
- データだけの struct（`Option<i32>` など）も `impl Copy` がなければ move した。

### 実装したこと

新しい診断は `E06xx`（所有権と借用）に置いた。

| Code | 規則 | 内容 |
| --- | --- | --- |
| `E0601` | B4 | 共有借用を通した書き換え・可変借用 |
| `E0602` | B4、B5 | 借用中の値の書き換え |
| `E0603` | B5 | 可変借用中の値の使用 |
| `E0604` | V4 | ループの中で、ループの外の値を move |
| `E0605` | B1 | `const` の値の可変借用・フィールドの書き換え |

1. **書き込み先の検査**（`check_write_place()`）。代入の左辺、`++`/`--` の対象、`&mut` の
   対象を、フィールド・添字・借用の `*` を通って根の変数までたどる。
   - 共有借用を通る書き込みは E0601。借用の変数そのものへの代入（`r = &other;`）は、
     付け替えなので許す。
   - 根の変数が借用されていれば E0602。
   - 根が `const` なら E0605。
   - 生ポインタの参照外し（`p->x`、`p[i]`）を通る場合は見ない（W0003 の範囲）。
2. **可変借用中の使用。** 借用を持つローカルが可変借用している間に、元の変数を直接使うと
   E0603。呼び出しの引数の一時的な借用は数えない（`mut_borrow_held`）。
3. **借用を通して取った借用。** `borrow` の引数や、借用を持つローカルを通して取った借用は、
   通った引数・ローカルもロックする（`reborrowed_via`）。上の `v.at_mut(0)` → `v.push(1)` が
   止まる。
4. **抜ける分岐。** 文が必ず抜ける（`return`・`break`・`continue` で終わる）かを構文で判定
   する（`stmt_always_exits()`）。`if` の片方が必ず抜けるなら、合流後の状態はもう片方の
   状態にする。
5. **ループの中の move。** ループの本体（`for` の更新式、`while`/`do` の条件を含む）を走査
   した後、ループの外で宣言された変数が、次の周回に流れる状態で move 済みなら E0604。
   次の周回に流れる状態は、本体の終わりの状態と、各 `continue` の時点の状態を合わせたもの。
6. **借用の保存。** checked なファイルで、借用を生ポインタや整数の変数・フィールドに初期化・
   代入する、構造体リテラルに入れる、生ポインタとして返すと W0003。グローバルの借用と、
   生ポインタの先の借用（`&p->x`）は対象外。引数として渡すのは、MLC-023 の移行まで報告
   しない。
7. **データだけの struct の自動コピー**（規則 V2）。`drop()` がなく、フィールドがすべて
   データ（スカラー、enum、newtype、関数値、その固定長配列、同じ条件の struct）の struct は、
   `impl Copy` なしでコピーになる。ループの検査で `Option<i32>` の代入が move と判定され、
   誤検出になったのがきっかけ。生ポインタのフィールドを持つ struct は、持ち物を指している
   かもしれないので（`Vec`）、まだ move のまま。
8. **スタックの使い方。** 分岐の状態のスナップショット（1つで約 60 KB）を、`if` と三項演算子
   でもヒープに置くようにした。`system/MyOS/src/shell/app.mln` の深い入れ子で、8 MB の
   スタックがあふれていた（変更前の版も 4 MB では足りなかった）。

### Alternatives Considered

- **NLL（最後の使用で借用を終える）。** 誤検出は減るが、制御フローグラフが要り、今の
  1回の走査では作れない。レキシカルのまま（規則 B3）。MLC-002 で扱う。
- **ループの本体を2回走査する。** 2周目の「move 済みの使用」がそのまま出るが、ほかの
  診断も2回出る。抑えるための仕組みの方が大きくなるので採らない。
- **借用の保存をエラー（E06xx）にする。** 既存のテストと標準ライブラリに `T *p = &x;` や、
  コンテナを指すイテレータ（`MapEntries { map: map }`）が多く、まとめて通らなくなる。ほかの
  生ポインタの操作と同じく W0003 にして、MLC-023 でまとめてエラーにする。

### Non-Goals

- NLL、フィールド単位の借用（`&mut s.a` と `&mut s.b` の両立）。
- move した元を実行時にゼロにすること（規則 V4 の後半）。codegen の変更なので MLC-025。
- 引数として渡す借用の生ポインタ化（MLC-023 の receiver の移行の後でエラーにする）。

## Progress

- [x] 書き込み先の検査（E0601、E0602、E0605）
- [x] 可変借用中の使用（E0603）
- [x] 借用を通して取った借用のロック
- [x] 抜ける分岐の合流
- [x] ループの中の move（E0604）
- [x] 借用の保存（W0003）
- [x] データだけの struct の自動コピー
- [x] 失敗例・成功例・警告の fixture、`docs/diagnostic-codes.md`、`docs/ownership.md`
- [x] 既存のソースのビルドと QA（既存のソースに新しいエラーはなかった。W0003 は2件増えた）

## Verification

```bash
make -C toolchain/MyLangCompiler test-component
make -C toolchain/MyLangCompiler test-e2e
make build && make qa
```

## 完了条件

- Background の表のコードが、それぞれの E06xx または W0003 で止まる。
- 抜ける分岐の例がエラーにならない。
- 既存のソースがすべてビルドでき、QA が通る。

## 関連

- `docs/design/mylang-memory-model.md`（規則 B1、B4、B5、B9、V2、V4）
- MLC-002 Flow-Sensitive Borrow And Move Analysis
- MLC-023 `.unsafe.mln` と生ポインタの分離
