# <ID>: <タイトル>

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Proposed | - | - | YYYY-MM-DD |

<!--
運用ルール（このコメントブロックは実チケットでは削除する）:

- Status: Proposed / In Progress / Blocked / Done / Superseded / Stale-Partial
  （定義は ../README.md の Status セクション参照）。
- Branch: 実際に作業しているブランチ名。作業前は "-"。
  複数ブランチにまたがった場合は最後に main へ入ったものに更新する。
- Agent: 今その ticket を担当している人 / AI agent。
  例: "human:keyhole-koro", "claude-code:sonnet-5", "claude-code:opus-5 (subagent)"。
  担当が変わったら上書きする（履歴はこの表ではなく git log / commit で追う）。
- Updated: このファイルを最後に実質更新した日付（YYYY-MM-DD、相対表現禁止）。
- 着手する agent は、着手時に Branch / Agent / Updated / Status(In Progress) を
  必ず更新すること。放置された "In Progress" は次に見た人が信用できなくなる。
- Done になったら tickets/README.md の運用ルールに従い completed/ へ git mv。
-->

## Summary

<1〜2文。このチケットが「何を」「なぜ」やるのかを、後から拾い読みしても分かるように。>

## Background

<現状の問題・きっかけとなった観測事実。憶測ではなく再現コード/ログ/該当ファイルを示す。
コードの引用は file:line 形式（例: `src/foo.c:123`）で。>

## Design

### Current State

<関連する既存実装の事実を列挙する。ここは「調査結果」であって「提案」ではない。
- 該当ファイル / 関数 / 型
- 今のデータフローや契約
- 既知の制約・ハック・TODO>

### Proposed Design

<やろうとしていること。図・擬似コード・データ構造の案を歓迎。
大きい設計は `docs/design/<name>.md` を新設して詳細をそちらへ逃がし、ここからリンクしてよい
（目安: 複数 ticket にまたがる/複数サブモジュールにまたがる規模なら分離）。>

### Alternatives Considered

<却下した案と、却下した理由。「なぜこの設計にしたか」を後で追えるようにする。
無ければ "検討中" と書いてよいが、Proposed → In Progress に進める前には埋めること。>

### Non-Goals

<明示的にやらないこと。スコープが際限なく広がるのを防ぐ。>

## Progress

<フェーズ/タスク単位のチェックリスト。実装が進むごとにここを更新する。
Status を In Progress にしたら、このチェックリストは常に実態と一致させること
（チェックだけついて説明文が古いままのチケットが一番始末に負えない）。>

- [ ] <タスク1>
- [ ] <タスク2>

## Verification

<完了判定に使うコマンド/テスト。再現手順があるならそのまま貼れる形で。>

```
<command>
```

## 完了条件

<Done と判定するための、具体的で検証可能な条件を箇条書きで。
「実装した」ではなく「〜が〜を返す」「〜のテストが緑になる」レベルまで具体化する。>

## 関連

<依存する/されるチケット、参照した design doc へのリンク。>

---

## Few-shot examples

以下は記入例（架空の題材）。粒度・トーンの参考にする。実チケットでは上の
テンプレート本体だけを使い、このセクションごと削除する。

### 例1: 小さめのバグ修正チケット

```markdown
# EXA-101: heap free() が末尾ブロックを未初期化のまま返す

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| In Progress | fix/exa-101-heap-tail-block | claude-code:sonnet-5 | 2026-09-09 |

## Summary

`heap.mln` の `free()` が、ヒープ末尾に隣接するブロックを free list に繋ぐ際、
サイズフィールドを更新せずに繋いでいるため、直後の `alloc()` が壊れたサイズを読む。

## Background

`system/MyKernel/src/libs/heap.mln:142` の `free()` で、
`block.next = tail; tail = block;` のみ行い `block.size` を再計算していない。
再現: `run_std_test.py --case heap_tail_free` が
`expected size=64, got size=0` で落ちる。

## Design

### Current State

- `free_list` は単方向リンクリスト、各ノードは `{ size: i32, next: ptr }`。
- 末尾ブロックの `size` はブート時のゼロ初期化のまま使われている
  （`heap_init()` がその1ブロックだけ `size` を設定し損ねている）。

### Proposed Design

`heap_init()` で末尾ブロック生成時に `size = heap_end - heap_start - HEADER_SIZE`
を明示的に設定する。あわせて `free()` 側にも防御的な assert を足す。

### Alternatives Considered

- `free()` 側だけで毎回サイズを計算し直す案 → 根本原因（初期化漏れ）を隠すので却下。

### Non-Goals

- coalescing のアルゴリズム自体の変更（別チケット MYOS-003 の範囲）。

## Progress

- [x] 再現テストを書く（`heap_tail_free`）
- [x] `heap_init()` の初期化漏れを修正
- [ ] `run_std_test.py` 全体で回帰確認

## Verification

\`\`\`
python3 system/MyKernel/tests/libs/run_std_test.py --case heap_tail_free
\`\`\`

## 完了条件

- `heap_tail_free` テストが緑になる
- `run_std_test.py` の既存ケースが壊れない

## 関連

- MYOS-003 Kernel Heap Improvements
```

### 例2: 大きめの設計チケット（docs/design へ分離するケース）

```markdown
# EXA-202: MyLang generics のモノモーフィ化キャッシュ

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Proposed | - | - | 2026-09-09 |

## Summary

generic 関数の実体化 (`Vec<T>.push` 等) が呼び出しごとに再生成されており、
同一 `<T>` の重複コードがバイナリサイズを押し上げている。実体化をキャッシュする。

## Background

`codegen_generic.c` の `instantiate_template()` は呼び出しサイトごとに
無条件で新しい specialization を生成する（重複排除は MyLinker 側の
`__mlg_` 接頭辞デデュープ任せで、コード生成自体は毎回走る）。

## Design

### Current State

（要点のみ。詳細な型パラメータ表現・シンボル命名規則は下記 design doc 参照）

### Proposed Design

設計の詳細は [`docs/design/generic-monomorphization-cache.md`](../../docs/design/generic-monomorphization-cache.md) に分離。
要点: `(template_name, [arg_types])` をキーにした翻訳単位内キャッシュを
`codegen_generic.c` に持たせる。

### Alternatives Considered

- リンク時デデュープのみに頼り続ける → codegen 自体のコストと一時ファイルサイズが
  そのままなので、規模が大きくなると効かなくなる。

### Non-Goals

- クロス翻訳単位でのキャッシュ共有（MLC-017 のモジュール解決層が前提になるため別チケット）。

## Progress

- [ ] design doc のレビュー
- [ ] キャッシュキーの実装
- [ ] 既存 generics テストでの回帰確認

## Verification

\`\`\`
toolchain/MyLangCompiler/tests/run_integration_tests.py
\`\`\`

## 完了条件

- 同一 `<T>` の呼び出しが2回以上ある fixture で、生成コードが重複しない
- 既存の generics テストが緑のまま

## 関連

- MLC-017 パーサ状態のコンテキスト化とモジュール解決層
- `docs/design/generic-monomorphization-cache.md`
```
