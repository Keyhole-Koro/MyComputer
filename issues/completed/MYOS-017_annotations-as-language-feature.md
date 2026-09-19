# MYOS-017: アノテーションを言語機能に、`@app` の実装を MyAppFramework へ

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Done | main | claude-code:opus-5 | 2026-09-19 |

## Summary

MYOS-016 でコンパイラの C ソースに埋めていた `@app` / `@timer` / `@key` の名前と意味を
取り出し、「アノテーション = プロトタイプで宣言するメタデータ。コンパイラは宣言と照合して
モジュールの表に記録するだけ、意味とライフサイクルは読み手（framework）」という
Java 式の言語機能に置き換えた（途中で試したテンプレート方式・デコレータ関数方式は差し戻し）。
`@app` の宣言と読み手は新リポジトリ
[MyAppFramework](https://github.com/Keyhole-Koro/MyAppFramework)（`system/MyAppFramework`）
に移り、アプリはそれを `import { app, timer } from ".../annotations.mln"` で使う。

## Background

`parser_lower_app.c` は `strcmp(a->name, "timer")` で属性名を判定し、記述子テーブルの
レイアウトと `"Ctrl+S"` の解釈まで持っていた。同じレイアウトを `app.mln` の `D_*` が
二重に定義していた。比較検討は `docs/learn/annotations-and-metaprogramming.md`。

## Design

- **コンパイラ**: `parser_lower_annot.c` — `@a(...)` を `a` の宣言（同ファイル / symbol-list
  import）に解決し、先頭 3 引数 `(i32 fn, char *type, i32 size)` と残りの引数を検査して
  モジュールの表 `__annotations()` に 1 行記録。`extern i32* __annotations_table(i32 m);` を
  宣言した TU に全モジュール分の集約を生成。メソッドはポインタ／参照レシーバ必須。
  `onClick={c.click}` はメソッドの実体を渡す（呼び出し規約が余分な引数を無視することを実測）。
  `parser_lower_app.c` は削除。**`ref mut` の書き戻しバグを修正**（`codegen_lvalue.c`）。
- **MyAppFramework**: `src/annotations.mln`（宣言 5 つ）、`src/meta.mln`（表の読み手）、
  `src/app.mln`（型名キーのレジストリ、`key_spec_matches`、`install()` が表を走査）、
  `src/ui.mln`、`docs/APP_FRAMEWORK.md`。
- **MyOS**: `@app` は struct ではなく view メソッドに。フィールド初期化子は view() へ。
  `boot/main.mln` がアプリを明示 import + 集約の extern 宣言（TODO: fs 上の .mbin へ）。
- **削除**: `qa/runners/gen_app_manifest.py`、`build/apps_manifest.mln`。
- **MyOS**: `src/app/` 削除、アプリ 5 本と `boot/main.mln` が framework を import。
- **manifest 生成**: framework の import 先を変更。

### Non-Goals

- comptime（C 案）、テンプレート（B 案）、デコレータ関数（E 案）— 経緯は
  `docs/learn/annotations-and-metaprogramming.md`。
- アプリの fs 化（ローダがメタデータ表を読む）— `main.mln` の TODO。
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
