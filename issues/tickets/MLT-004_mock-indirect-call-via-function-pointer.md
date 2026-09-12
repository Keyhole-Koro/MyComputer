# MLT-004: mock.spy / mock.of の function pointer 経由 indirect call 対応

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Proposed | - | - | 2026-09-12 |

## Summary

`mock.spy(target)` / `mock.of(target)` は `target` という名前へのソース上の直接呼び出し
（direct-call relocation）しか横取りできない。`target` の値を関数ポインタとして変数へ渡し、
その変数経由で呼ぶ（indirect call）と、mockのrecord/dispatchを一切通らず素通りする。
これはMLT-003で意図的な`Initial exclusions`として明記済みだが、実際にテストを書く過程で
「素朴なグローバルカウンタに戻す」以外の代替が無く不便だったため、対応方針を検討する。

## Background

`system/MyKernel/tests/dom/dom_lowering.dom.test.mln` のDOM lowering end-to-endテストで、
`<Button onClick={on_click} .../>` のように関数を値としてpropに渡し、`Button`内部では
`onClick(99);` という形で間接的に呼び出す（`onClick`はただの`i32`パラメータで、たまたま
`on_click`のアドレスが入っている）。

このケースで `mock.spy(on_click)` を仕込んでも、`mock.calls(on_click)` は `0` のまま、
`mock.never(on_click)` が通ってしまう（実際には`on_click`は1回呼ばれ、独自のグローバル
カウンタでは検出できる）ことを実測で確認した。つまり:

- `Button(...)`, `Window(...)` のような**ソースに名前で直接書かれた呼び出し**は
  `mock.spy`/`mock.of`のrecordが効く。
- `onClick(99)`のような、**変数経由の間接呼び出し**は横取りされず、original実装へ
  何の記録もされずに直接飛ぶ。

`toolchain/MyLangTestKit/tests/../README.md`（Mock core節）および
`issues/tickets/MLT-003_mylang-di-and-mocking.md`の `Interception contract` /
`Initial exclusions` に「function pointerを経由したindirect call」は当初から対象外と
明記されている。今回はその制約に実運用（コールバックpropを持つDOM要素のテスト）で
直接ぶつかった、という具体的な再現ケース。

回避策として、`dom_lowering.dom.test.mln` では次の2案のいずれかで対応する:

1. コールバック自身の中で、名前を直接書いた薄いラッパー関数を経由させ、そのラッパーを
   spyする（`on_click`本体から`record_click(id)`のような直接呼び出しを1つ挟む）。
2. 何もせず、素朴なグローバルカウンタで検証する（現状のコミット済み実装はこちら）。

## Design

### Current State

- `toolchain/MyLangTestKit/runtime/facade.mln` の `spy(i32 fn)` / `target(i32 target)` は
  `mock_targets[]`にtarget（関数の生アドレス値）を登録するだけで、redirectの実体は
  MyLangTester/Linkerが**呼び出し命令（call relocation）**を書き換えることで実現している
  （`record()`はentry経由で呼ばれた時だけ実行される。間接call命令はそもそもentryを通らない）。
- MLT-003 `Interception contract`:
  > 既存function内のdirect callをMock / Spyで観測するには、そのcallがTestKitのentryを
  > 通る必要がある。
- MLT-003 `Initial exclusions` に明記:
  > function pointerを経由したindirect call。
- 現状、関数を値として保持・伝搬するAPI（コールバックprop、イベントハンドラ、関数テーブル
  等)は、mock/spyの対象外になる。これはDOM要素のイベントハンドラに限らず、関数ポインタを
  引数に取るコールバック全般に及ぶ既知の制約。

### Proposed Design

（検討中。方向性の候補のみ）

- **候補A: symbol-level redirect** — `--redirect <original>=<entry>` を、call relocation
  だけでなく`<original>`の**アドレスを値として参照する**relocation（`i32 x = on_click;`
  のような代入）にも適用する。`<entry>`は既存の設計通り「未一致ならoriginalへfallback」
  するため、間接呼び出し側は`<entry>`のアドレスを保持することになり、実行時にそこを
  経由すれば従来の`enter/dispatch/leave/record`がそのまま機能する。
  - 懸念: 関数値の同一性比較（`if (fn == on_click)`のような比較）がある場合、
    アドレスがentryにすり替わることで結果が変わりうる。
  - 懸念: aggregate return等、entryが完全に同一ABIを持たない構成が将来的に増えると
    「値として持ち出しても安全なentry」という前提が崩れる。
- **候補B: 呼び出し側での明示的な計装ヘルパー** — 今回の回避策1のように、「間接的に
  呼ばれるがゆえにspyできない関数」を書く側に、直接呼び出しを1つ挟む薄いラッパーを
  書く規約を定め、それをドキュメント化する。TestKit自体への変更は不要。
  - 既存の`Initial exclusions`と矛盾しない、最小コストの対応。
  - ただし「関数ポインタを他モジュールから渡された場合」（呼び出し元がラッパーを
    知らない/挟めない場合）には使えない。

### Alternatives Considered

- 何もしない（素朴なグローバルカウンタを使い続ける）: DOM loweringテストのように
  対象が少数なら実用上問題ないが、testkitの他のassertion（`mock.called_with`等）と
  検証スタイルが分裂し、テストの読みやすさが下がる。

### Non-Goals

- aggregate/array引数・aggregate戻り値・variadic関数のmock対応（MLT-003の別exclusion、
  本チケットのスコープ外）。
- cross-target global call order の記録（同上）。

## Progress

- [ ] 候補A/Bどちらで進めるか方針決定
- [ ] （候補Aの場合）MyLinker側でaddress-of relocationのredirect対応を設計
- [ ] （候補Bの場合）ラッパー規約をREADME/MLT-003に明文化
- [ ] `dom_lowering.dom.test.mln`のonClick検証を、決定した方式に合わせて書き換え

## Verification

```
./toolchain/MyLangTester/build/mytest system/MyKernel/tests/dom/dom_lowering.dom.test.mln
```

対応後は、上記テストの`on_click`検証を素朴なグローバルカウンタ（`g_clicks`/`g_click_id`）
ではなく、他のプロパティ検証と同じ`mock.called_with(on_click, 99)` / `mock.once(on_click)`
形式に置き換えられることを確認する。

## 完了条件

- 関数ポインタ経由で呼ばれるコールバックが、`mock.spy`/`mock.of`で観測可能になる
  （候補A採用の場合）、または「観測不可能な理由と回避策」がMLT-003 / TestKit README に
  明文化される（候補B採用の場合）。
- `dom_lowering.dom.test.mln`のonClick検証が、決定した方式に沿った形に更新されている。

## 関連

- [MLT-003](MLT-003_mylang-di-and-mocking.md) — `Interception contract` / `Initial exclusions`
  で本制約を既に明記している親チケット。
- `system/MyKernel/tests/dom/dom_lowering.dom.test.mln` — 本制約に実際にぶつかった
  再現ケース。
- `toolchain/MyLangTestKit/README.md` — Mock coreのredirect実装に関する説明。
