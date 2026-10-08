# MLC-022: Result エラーの伝播経路トレース

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Done | main | claude-code:opus-5.5 | 2026-10-07 |

## Summary

`Err` を作った場所と、`?` で伝播した各地点をコンパイラが記録する。最上位で
エラーを受け取った側が「どこで発生し、どの経路で上がってきたか」を表示できるようにする
（Zig の error return trace に相当）。デバッグビルドだけで有効にし、`Result` の ABI は変えない。

## Background

- `?` で伝播すると、受け取った側には最後のエラー値しか残らない。発端の場所が分からない。
- MLC-021 で `From` による変換が入ると、`SsdError::DeviceError` が `FsError::IoError` に
  まとめられ、元のエラーの種類も消える。
- 現状の調査手段は、各所に `debug.printf` を手で足すことしかない
  （例: `system/MyKernel/src/kernel/loader.mln`）。

## Design

### Current State

- `?` はパーサで `case` に脱糖している
  （`toolchain/MyLangCompiler/src/frontend/parser/parser_expr_postfix.c:22`）。
  MLC-021 で意味解析専用のノードへ移す予定。
- `Result<T, E>` は普通の payload enum（`toolchain/MyStdLib/core/result.mln`）。

### Proposed Design

- スレッドごとに固定長のリングバッファ（例: 32 エントリ、各 1 ワードのコードアドレス）を持つ。
- コンパイラは、デバッグビルドで次の 2 種類の地点に記録処理を挿入する。
  - `Result` を返す関数で `Err(...)` を作って返す地点：バッファをリセットして発生地点を記録する。
  - `?` の `Err` arm：伝播地点を追記する。`From` で変換する場合も同じ地点で記録する。
- 標準ライブラリに、記録内容の読み出しと表示を行う API を置く
  （例: `@std/debug/error_trace.mln` の `error_trace.print()`）。
- 表示はアドレス列でよい。シンボル名と `file:line` への変換はエミュレータ側か
  ツール側で行う。

```
error FsError::IoError
  ssd.mln:52          wait_for_completion   (Err created)
  ssd.mln:88          write_block
  fs.mln:977          write                 (SsdError -> FsError)
  editor.dom.mln:122  save
```

- リリースビルドでは何も挿入しない（コストゼロ）。

未決事項:

- バッファの置き場所。カーネルのスレッド構造体か、スレッドローカルな領域か。
  カーネルのスレッドとユーザープロセスで分けるか。
- 発生地点のリセット規則。`case` で `Err` を受け取って処理した場合にどう終わらせるか。
- ビルドフラグの名前と、MyOS ビルドでの既定値。
- アドレスからシンボルへの変換手段。リンカの map 出力か、エミュレータの機能か。

### Alternatives Considered

- **作成時にスタックトレースを取る（Java の例外、`anyhow` の backtrace）。**
  記録が重く、エラー値が大きくなる。
- **伝播のたびに文脈文字列を足す（Go の `%w`、`anyhow` の `.context()`）。**
  全て手書きになり、メモリ確保も要る。必要な箇所だけ後から任意で足す機能として残す。
- **作成地点の `file:line` だけをエラー値に持たせる（Rust の `#[track_caller]`）。**
  経路が分からず、`Result` の ABI も変わる。

### Non-Goals

- 文脈文字列の付加（`.context()` 相当）。
- リリースビルドでのトレース。
- 完全なスタックトレースや unwind。

## Progress

- [x] バッファの置き場所と表示 API を決める
  - `@std/debug/error_trace.mln`。イメージごとに 1 本（ユーザープロセスは各自、カーネルの
    タスクは共有）。32 地点、それ以上は件数だけ数える。
  - 地点はアドレスではなく `"fs.mln:667 fs_open"` という静的文字列。シンボル化の手間が
    なく、デバッグビルドだけのコストなので文字列で持つ。
  - `depth()` / `site(i)` / `format(buf, cap)` / `clear()`。
- [x] `Err` 作成地点と `?` の地点への記録処理の挿入（`mlc --error-trace` のときだけ）
  - パーサが `return Err(...)` を起点、`?` の展開した return を伝播として印を付ける。
    From 変換は `(SsdError -> FsError)` を地点に付ける。payload enum の lowering で
    return を作り直すときも印を引き継ぐ。
  - codegen は戻り値を格納したあと、defer の前で `error_trace_note(site, kind)` を呼ぶ。
  - フラグなしでは何も出さない（`tests/check_depfile.py` で確認）。
  - 記録を出したときは depfile に `@std/debug/error_trace.mln` を載せ、import なしでも
    ビルドがリンクする。
- [x] 標準ライブラリの読み出し・表示 API
- [x] アドレスからシンボル・行番号への変換 — 地点を文字列で持つので不要になった。
- [x] fs の I/O エラーで、発生地点から最上位までの経路が表示されることを確認
  - `MYLANG_ERROR_TRACE=1 make build`（`build_toolchain.py --error-trace`）で全体を
    フラグ付きでビルドできる。MyOS の fs syscall 境界が、ユーザーへ返すエラーの
    トレースをゲストログに出す。ターミナルの `cat definitely-missing` で
    `fs.mln:667 fs_open (created)` を確認。多段の伝播と From 変換をまたぐ経路は
    `tests/succeed/trace/errorTrace.mln`（e2e）で確認（4 地点）。
  - ディスク障害を起こせないため、MyOS 上での多段の経路は未確認。

決めたこと:

- 発生地点のリセット: 新しい起点が前のトレースを置き換える。`case` で処理しただけでは
  消さない（Zig と同じ）。
- フラグ名は `--error-trace`。MyOS ビルドの既定は無効。
- テストランナー（MyLangTester）の e2e.cases に、ケースごとのコンパイラフラグの
  4 列目を足した。

## Verification

```bash
make -C toolchain/MyLangCompiler test-component   # check_depfile.py を含む
make -C toolchain/MyLangCompiler test-e2e         # errorTrace（--error-trace 付き）
make qa
MYLANG_ERROR_TRACE=1 make build && python3 system/MyOS/tests/apps_e2e_test.py
```

詳細は `toolchain/MyLangCompiler/docs/error-trace.md`。

## 完了条件

- 多段の `?` で伝播したエラーについて、発生地点と各伝播地点が順に表示される。
- `From` による変換をまたいでも経路が途切れない。
- リリースビルドの生成コードに記録処理が含まれない。

## 関連

- MLC-021 trait と `?` のエラー変換
- MLC-019 `defer` によるスコープ終了処理
