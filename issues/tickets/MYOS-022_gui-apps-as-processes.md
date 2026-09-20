# MYOS-022: GUI アプリを .mbin に

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Proposed | - | - | 2026-09-20 |

## Summary

デスクトップアプリを個別にビルドして `/apps` に置き、プロセスとして起動する。
`boot/main.mln` の明示 import と Phase A（image にリンク）経路を消す。
`docs/design/os-app-boundaries.md` の段 5。MYOS-020 と MYOS-021 の後。

## Design

### Proposed Design

- アプリ 1 本 = SDK（annotations / ui / elements / handlers）+ アプリのソース → `.mbin`
- 起動：シェルが `/apps/<name>.mbin` のヘッダから `@app` を読み、`launch` で
  `loader.spawn` → アプリの `main`（SDK が生成）が `view()` を呼び、`run()` でイベントを待つ
- `@timer` / `@key` / `@open` / `@on_close` はシェルがアプリのチャネルへイベントとして送る
- 移行期間は「組み込み」と「インストール済み」をレジストリが束ね、終わったら前者を消す

### Non-Goals

- 検討中

## Progress

- [ ] SDK が `main` を生成（`@app` の view を呼ぶ）
- [ ] アプリごとのビルドと `/apps` への配置
- [ ] シェルの launch をプロセス起動に
- [ ] `main.mln` の import 削除、Phase A 経路の削除

## Verification

```
make qa
python3 system/MyOS/tests/app_framework_test.py
python3 system/MyOS/tests/dom_click_test.py
python3 system/MyOS/tests/apps_e2e_test.py
```

## 完了条件

- `boot/main.mln` がアプリを import しない
- 全 GUI アプリが `/apps` の .mbin から起動し、既存 E2E が緑

## 関連

- MYOS-020、MYOS-021
