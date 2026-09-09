# tickets/

このディレクトリには **未完了**（`Proposed` / `In Progress` / `Blocked`）のチケットだけを置く。

## 新規チケットの作り方

[`_TEMPLATE.md`](_TEMPLATE.md) を `git cp` 感覚でコピーして書き始める（few-shot 記入例つき）。

```
cp issues/tickets/_TEMPLATE.md issues/tickets/<ID>_<slug>.md
```

- 冒頭の `Status / Branch / Agent / Updated` 表は必須。着手する human / AI agent は
  着手時に **その場で** 更新する（放置された古い担当表示は次に見た人を混乱させる）。
- `Design` セクション（Current State / Proposed Design / Alternatives Considered /
  Non-Goals）は Design Doc 相当。`Proposed` → `In Progress` に進める前に埋めること。
  複数 ticket・複数サブモジュールにまたがる大きい設計は `docs/design/*.md` に詳細を
  逃がし、ticket からリンクしてよい。
- `Progress` のチェックリストは実装が進むたびに実態と同期させる。チェックだけ
  ついて本文が古いチケットを残さない（`../README.md` の `Stale/Partial` 参照）。

## 運用ルール

- チケットが完了（実装・検証済み、status `Done`）したら、ファイルを
  `../completed/` へ **`git mv`** で移動する（履歴を保つため `mv` ではなく `git mv`）。
- 移動したら `../README.md` の索引リンクを `tickets/...` から `completed/...` に更新する。
- ここに `Done` のチケットが残っていたら、それは移動し忘れ。`completed/` に移すこと。
- 本文が実装状況とズレてきたら（設計は進んだが記述が古い等）、放置せず
  `Status: Stale/Partial` にして本文冒頭に古い旨の注記を足す。移動が必要かは
  `../README.md` の `Stale/Partial` の定義を参照。

完了済みチケットの一覧・過去の設計判断は [`../completed/`](../completed/) を参照。
チケット全体の索引とステータス定義は [`../README.md`](../README.md) にある。
