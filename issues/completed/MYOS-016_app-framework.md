# MYOS-016: アプリケーションフレームワーク（@app 属性・ui API・イベントキュー）

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Done | main | claude-code:opus-5 | 2026-09-18 |

## Summary

MyOS のデスクトップアプリを「`@app` を付けた struct + メソッド」で書けるようにし、
登録・起動・インスタンス管理・イベント配送・終了時の回収を framework
（`system/MyOS/src/app/`）に集めた。既存 5 アプリを移植し、`main.mln` から
アプリ固有のコードを無くした。

## Background

移植前のアプリは (1) ハンドラが `i32 id` しか受け取れずインスタンス状態が
グローバル配列 + `slot_of(id)` 表になる（`notes.dom.mln`, `terminal.dom.mln`）、
(2) ノード id を `first_child`/`next_sibling` の走査で取り直す、(3) close の
検出が `forget_if_closed()` のポーリング、(4) 登録が `main.mln` の import 列と
`open_app(index)` の if 列、という形だった。ラムダはキャプチャできないので
(1) に言語側の逃げ道が無かった。

## Design

詳細は `system/MyOS/docs/APP_FRAMEWORK.md`（アプリの書き方と裏側）、文法は
`toolchain/MyLangCompiler/docs/grammar.md` "Attributes and applications"。

### 決めたこと

- **属性文法** `@name(args)` を追加（キーワード `app` ではなく）。namespace と
  衝突せず、`@timer` / `@key` / `@open` / `@on_close` / `@task` も同じ仕組み。
- **ハンドラ ABI を `(owner, id, arg)` に統一**。コンパイラがメソッド・ローカル
  関数からトランポリンを生成するので、アプリ側は `(i32 id)` などの自然な形で書く。
- **`ref={lvalue}`** と **デフォルト引数** (`i32 x = 0`) を文法に追加。markup から
  `x={0} y={0}` と走査コードが消える。
- **Node に `owner` / `on_close`**。ハンドラ実行中は `g_current_owner` が
  インスタンスを指し、生成ノードに刻まれる → `remove_owned` で一括回収。
- **イベントキュー**（Phase A: コンポジタタスク上で drain）。別タスク化は
  DOM ロックと共に次段。
- **manifest 生成**（`qa/runners/gen_app_manifest.py` → `build/apps_manifest.mln`）。
  import 追跡コンパイル + セクション無しリンカでは宣言だけで表に載せられないため。
- **`ui.mln` はスカラのみ**（i32 / char\*）。将来 syscall 面に写すため。
- レシーバはポインタ必須。`ref mut` struct 引数が呼び出し側へ書き戻されない
  （既存のコード生成の穴）ため、コンパイラで拒否する。

### Alternatives Considered

- `app Counter {}` キーワード: 一発芸で汎用性が無く、`import app` と衝突 → 属性に。
- アプリが `app.register()` を呼ぶ方式: 宣言と登録の二重化 → manifest 生成に。
- React 式の再実行 + diff: VDOM の確保と diff が RAM 事情に合わない → retained + `ref`。

### Non-Goals

- UI server のプロセス化、Surface ノード（自前描画）、DOM ロック（Phase B）。
- `@task` の framework 実装（`spawn_task` がタスク引数を取らない）。

## 実装中に見つけて直したもの

- **コンパイラ: `({ break; })` を case アームに書くと break が無視される**
  （`gen_stmt()` がループラベルを持たない）。`fs.dir_next` の `Result<Option>`
  リファクタ以降 `ls` が無限・重複表示になっていた原因の半分。修正 + 回帰テスト。
- **コンパイラ: struct 値の case アーム (`Ok(v) -> v` を `Option` 変数へ) が
  コピーされない**（未修正・既存制限）。呼び出し側を文レベル 2 段 case にした。
- `dom_click_test.py` は Notes が Terminal に隠れていて失敗していた → 前面化を追加。

## Progress

- [x] コンパイラ: 属性文法、`@app` lowering、トランポリン、`ref=`、デフォルト引数、LSP 文法
- [x] DOM: owner / on_close / イベントキュー / key filter / 要素のデフォルト・testId
- [x] `app.mln` / `ui.mln` / manifest 生成 / `main.mln` 縮小
- [x] counter / notes / editor / files / terminal 移植
- [x] `app_framework_test.py`、`make qa` 21/21、E2E 3 本 green
- [x] ドキュメント（APP_FRAMEWORK.md、grammar.md、source-modifiers.md）

## Verification

```
make qa
make framework-test
make dom-tester-test
make apps-test
```

## 関連

- MYOS-014 / MYOS-015（DOM・WM・アプリの土台）
- `docs/design/user-space-processes-and-syscalls.md`（ui.mln をスカラに縛った理由）
