# tickets/

このディレクトリには **未完了**（`Proposed` / `In Progress` / `Blocked`）のチケットだけを置く。

## 運用ルール

- チケットが完了（実装・検証済み、status `Done`）したら、ファイルを
  `../completed/` へ **`git mv`** で移動する（履歴を保つため `mv` ではなく `git mv`）。
- 移動したら `../README.md` の索引リンクを `tickets/...` から `completed/...` に更新する。
- ここに `Done` のチケットが残っていたら、それは移動し忘れ。`completed/` に移すこと。

完了済みチケットの一覧・過去の設計判断は [`../completed/`](../completed/) を参照。
チケット全体の索引とステータス定義は [`../README.md`](../README.md) にある。
