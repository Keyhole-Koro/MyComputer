# MYOS-017: アノテーションを言語機能に、`@app` の実装を MyAppFramework へ

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Done | main | claude-code:opus-5 | 2026-09-19 |

## Summary

MYOS-016 でコンパイラの C ソースに埋めていた `@app` / `@timer` / `@key` の名前と意味を
取り出し、`annotation` 宣言 + コンパイル時テンプレートという言語機能に置き換えた。
`@app` の定義・展開・記述子の読み手は新リポジトリ
[MyAppFramework](https://github.com/Keyhole-Koro/MyAppFramework)（`system/MyAppFramework`）
に移り、アプリはそれを `import { app, timer } from ".../annotations.mln"` で使う。

## Background

`parser_lower_app.c` は `strcmp(a->name, "timer")` で属性名を判定し、記述子テーブルの
レイアウトと `"Ctrl+S"` の解釈まで持っていた。同じレイアウトを `app.mln` の `D_*` が
二重に定義していた。比較検討は `docs/learn/annotations-and-metaprogramming.md`。

## Design

- **コンパイラ**（MyLangCompiler `86e0b83`）: `annotation` キーワード、`TEMPLATE_BODY`
  トークン、`AST_ANNOTATION`、`SYMBOL_ANNOTATION`（import で解決）、
  `parser_lower_annot.c`（宣言との検査・テンプレート展開・`@tramp`）。
  `parser_lower_app.c` / `parser_app_internal.h` は削除。
- **LSP 文法**（MySyntaxEngine `81b1d69`）: `annotationDecl`。
- **MyAppFramework**: `src/annotations.mln`（`@app` テンプレート、マーカー 5 つ）、
  `src/app.mln`（MyOS から移動 + `key_spec_matches`、`install()` がデスクトップメニューも配線）、
  `src/ui.mln`、`docs/APP_FRAMEWORK.md`。
- **MyOS**: `src/app/` 削除、アプリ 5 本と `boot/main.mln` が framework を import。
- **manifest 生成**: framework の import 先を変更。

### Non-Goals

- comptime（C 案）、RTTI + 起動時デコレータ（D 案）。テンプレートで足りなくなったら。
- MyOS/src/apps ↔ MyAppFramework ↔ MyOS/src/ui の循環解消（UI server 切り出し）。

## Verification

```
make qa                      # 21/21
make framework-test          # PASS
make dom-tester-test         # PASS
make apps-test               # PASS
```

## 関連

- MYOS-016、`docs/learn/annotations-and-metaprogramming.md`
