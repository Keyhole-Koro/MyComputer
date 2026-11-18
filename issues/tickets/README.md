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
  ついて本文が古いチケットを残さない。

## 運用ルール

- チケットが完了（実装・検証済み）したら、ファイルを削除し、`../README.md` の索引から
  その行を消す。決まったことはコードと `docs/` に書き、経緯は git の履歴に残る。
- 本文が実装状況とズレてきたら（設計は進んだが記述が古い等）、放置せず書き直す。
  要らなくなったチケットも削除する。

チケット全体の索引とステータス定義は [`../README.md`](../README.md) にある。
