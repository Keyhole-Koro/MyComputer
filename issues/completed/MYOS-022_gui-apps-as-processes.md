# MYOS-022: GUI アプリを .mbin に

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Done | main | claude-code:opus-5 | 2026-09-21 |

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

### Alternatives Considered

- ブロッキング syscall（要求を送ったプロセスをカーネルが寝かせ、返事で起こす）→ scheduler に
  wait queue が要る。`UI_REQUEST` → `UI_REPLY` を `sys_yield`（次の tick まで sleep）で待つ
  ポーリングにした。1 kHz なので 1 要求 2〜3 ms
- カーネルに UI / FS / PROC の syscall を個別に足す → MyKernel が MyOS の事情を知ることになる。
  `OS_CALL(service, args)` 1 本と登録ハンドラ（`set_os_handler`）にし、サービス番号は SDK の
  `os_services.mln` が持つ
- ユーザプロセスのテキストを RWX にする（グローバルがテキストにあった）→ W^X を壊すので、
  mlc がグローバル・文字列・定数プールを `.data` に出すようにし、アセンブラに `.data` / `.text`
  を足した（MyLinker は DATA 内の WORD32 リロケーションを patch）

### Non-Goals

- 複数インスタンス / プロセス（`@app(single)` 以外は 2 回目の起動で新プロセス）は動くが、
  1 プロセスに複数インスタンスは無い

## Progress

- [x] カーネル：`OS_CALL` syscall + `set_os_handler`、`YIELD` = 次の tick まで sleep（`reschedule` と `tick` を分離）、ユーザスタック 16 KiB、カーネルスタック 16 KiB、ヒープ 8 MiB と割り込み禁止ロック、`irq.save_disable/restore`（IE のソフト複製）、カーネルページテーブルの共有、ローダの word コピー
- [x] SDK：`uiproto.mln`（syscall 版の運び手）、`os_services.mln` / `os_call.masm`、`fs.mln` / `console.mln`、`app_main.mln`、`runtime.run()` / `log()`、`text_of` → `text_copy`、`set_text_fmt` をアプリ側で整形
- [x] OS：`proc/os_calls.mln`（per-pid チャネル、ユーザメモリのコピー）、`ui_events.bind`、サーバが文字列を自分のコピーで持つ（`dom.set_text_copy`、`TEXT_OWNED`）、シェルはプロセス起動・`window_ready`・EXIT・reap、`dom.note_app_starting`（automation の `starting`）
- [x] ビルド：`build_user_apps.py` が `src/apps/*.dom.mln` を `.mbin` に、`main.mln` の import と `host.mln` を削除
- [x] toolchain：mlc がデータを `.data` に、アセンブラ `.data`/`.text`、リンカ DATA リロケーション、`~` の codegen 修正（21 bit 即値）、`fs.read` の word コピー
- [x] テスト：3 つの E2E、`make qa` 21 suites 緑。`app_framework_test` 段 8 は「ランチャー = ディスクの @app」、apps_e2e は exit code を待つ、heap の OOM テストは `HEAP_SIZE` を参照
- [x] emulator：`os.ready` はシェルが「起動中のアプリ 0」と報告するまでゲストを回す

## Verification

```
make qa
python3 system/MyOS/tests/app_framework_test.py
python3 system/MyOS/tests/dom_click_test.py
python3 system/MyOS/tests/apps_e2e_test.py
```

## 完了条件

- `boot/main.mln` がアプリを import しない — 済
- 全 GUI アプリがディスクの .mbin から起動し、既存 E2E が緑 — 済

## 関連

- MYOS-020、MYOS-021
