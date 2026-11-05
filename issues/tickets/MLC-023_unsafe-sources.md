# MLC-023: `.unsafe.mln` と生ポインタの分離

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| In Progress | main | claude-code:opus-5.5 | 2026-10-12 |

## Summary

生ポインタ（`T *`）の参照外し・ポインタ演算・ポインタのキャストを `name.unsafe.mln`
のファイルだけに許し、それ以外のファイルは借用検査の効く `borrow` / `borrow mut` と値で
書く。危険な箇所をファイル単位で閉じ込め、外には安全な API（値・参照・Option）だけを
見せる（Rust の「unsafe は小さな部品に閉じ込める」をファイル単位で強制する形）。

## Background

- 借用検査は `borrow` / `borrow mut` にしか効かない。`R *p = &r; take(r); p->h;` や、drop
  された値へのポインタをスコープの外へ持ち出すコードは通ってしまう。
- コードベースの大半は生ポインタで書かれている（ポインタ receiver 約 70、ポインタの
  フィールド 46、アドレスを i32 で持つ箇所 約 130、借用（当時の `ref`）は約 10）。
- 以前あった `.safe` 修飾子（strict プロファイル）は何も検査しておらず、使われても
  いなかった。

## Design

- `.safe` を廃止し、`.unsafe` を追加。修飾子なしのファイルが検査対象（checked）。
- checked のファイルでは次を W0003 として報告する：
  - 生ポインタの参照外し `*p`、`p->x`、`p[i]`
  - ポインタ演算 `p + n`、`p - n`
  - ポインタとのキャスト `(u8 *)p`、`(i32)p`、`(T *)address`
- `borrow`、配列、`&x`（借用）は対象外。
- 1 ファイルにつき最初の 8 件をその場所で、残りを件数でまとめて報告する（診断表の
  上限 512 件に達するとエラー扱いになるため）。
- unsafe なファイルが公開する API は、`T *` ではなく値・`borrow`・Option で返す。checked
  の側では `T *` を受け取っても参照外しできないので、この境界が自然に守られる。

## Progress

- [x] 段階 1（2026-10-12）：`.unsafe` 修飾子と W0003（警告）。`.safe` を削除。
  計測：対象 118 ファイル中 57 ファイル、約 2000 件。多いのは
  `apps/files.dom.mln` 243、`ui/dom/dom.mln` 221、`dom_widgets.mln` 207、
  `dom_render.mln` 151、`shell/app.mln` 124、`apps/terminal.dom.mln` 108。
- [ ] 段階 2：移行。receiver と API を `borrow` / `borrow mut` に置き換え、残る生ポインタ操作
  （ヒープ、MMIO、ページテーブル、syscall のユーザーメモリ、DOM のノード表など）を
  小さな `.unsafe.mln` に切り出す。trait の receiver（`Self *self`）、std の
  `iter()` が返す `T *` も対象。
  - [x] std の `Vec` / `Slice` / `HashMap`：receiver を `borrow` / `borrow mut` に、
    `at()` / `get()` を `Option<borrow T>` に。書き込み用に `at_mut()` /
    `get_mut()`（`Option<borrow mut T>`）を追加（2026-10-12）。
- [ ] 段階 3：W0003 をエラーにする。
- [x] `unchecked { }` ブロックを削除（2026-10-12）。ファイル単位の `.unsafe.mln` に
  一本化。`&` は常に借用になった（以前はブロック内だけ生のアドレス）。
- [x] キーワード `ref` を `borrow` に改名（2026-10-12）。DOM の `ref={...}` 属性
  （ノード ID の束縛）と同じ単語だったため。`ref` はキーワードでなくなった。
- [x] 借用を置ける場所を、ローカル・引数（receiver を含む）・戻り値に限定
  （2026-10-12）。フィールド、enum の payload、typedef / newtype、グローバル、配列の
  要素、`Option` / `Result` 以外のジェネリック引数に書くとエラー
  （`parser_borrow_positions.c`）。lifetime は入れない。
- [x] 戻り値の借用（2026-10-12）。借用を返す関数は「最初の借用引数」（メソッドなら
  receiver）から借りたものだけ返せる。呼び出し側では、結果がスコープにある間その引数に
  渡した値を借用中として扱う（`Option<borrow T> a = v.at(0); v.push(4);` はエラー）。
  生ポインタ越しに取った借用（`p->rows.at(i)`）は追跡しない。

## 未決事項

- 借用の寿命はレキシカル（スコープの終わりまで）。最後の使用で終わる（NLL）わけでは
  ないので、`at()` の結果を持つ間は同じスコープで `push()` できない。ブロックで囲む。
- 戻り値の借用は最初の借用引数 1 つだけに結び付く。`unwrap_or(&fallback)` の
  `fallback` 側は追跡しない。
- 借用から生ポインタへの変換（`T *p = r;`）は許している。参照外しは W0003。
- アドレスを i32 で持つ箇所を、`core/address.mln` の型に寄せるか。
- import のパスにファイル名が入るため、`.unsafe.mln` への改名は参照側の修正を伴う。
  → import のパスでは `.unsafe` を省くと決めた（`docs/design/mylang-values.md` 規則 U3、
  2026-11-05）。実装は MLC-025。

## Verification

```bash
make -C toolchain/MyLangCompiler test-component   # source-profile と W0003 の fixture
make -C toolchain/MyLangCompiler test-e2e
make build && make qa
```
