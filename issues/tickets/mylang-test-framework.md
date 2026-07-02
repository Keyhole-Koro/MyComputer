# MyLang Test Framework（mytest + test declaration）

## 背景

MyKernel の `run_serial_rx_test.py` などは、Python がビルド・エミュレータ起動・入力注入・
出力判定を外側から行っている。これを `*.test.mln` へ寄せ、テスト本体を MyLang で書ける
ようにする。

ただし、`stdin` や `step` はエミュレータ起動前に必要な設定であり、通常の MyLang
実行時関数として `test.stdin(...)` を呼んでも間に合わない。したがって、テスト宣言は
`mytest` が静的に読むトップレベル宣言として扱う。

## 目標

- `*.test.mln` を `mytest` で発見・ビルド・実行・判定できるようにする。
- テストケースは Jest に近い書き味にする。
- テスト実行前に必要な runner 設定と、エミュレータ内で実行される MyLang テスト本体を
  明確に分ける。
- 既存 Python runner を段階的に置き換える。

## 仕様案

`test(...)` は通常の MyLang 関数呼び出しではなく、`mytest` 専用のトップレベル
test declaration とする。

```mylang
test("serial_rx", {
    stdin: "PINGq";
    expect: "TEST_PASS";
    step: 10000000;
}, () => {
    test.expect_serial_byte(80, 1000000, "serial_rx:P");
    test.expect_serial_byte(73, 1000000, "serial_rx:I");
    test.expect_serial_byte(78, 1000000, "serial_rx:N");
    test.expect_serial_byte(71, 1000000, "serial_rx:G");
    test.expect_serial_byte(113, 1000000, "serial_rx:q");
    test.pass();
});
```

### 役割

- `test("name", options, body)`:
  - `mytest` が静的に読むトップレベル宣言。
  - compiler にそのまま渡す通常コードではない。
- `options`:
  - runner / emulator 起動前に必要な設定。
  - 初期キー: `stdin`, `expect`, `step`, `timer_interval`。
- `body`:
  - エミュレータ内で実行される MyLang コード。
  - `mytest` が `kernel_main()` などへ lowering してから compiler に渡す。
- `test.expect_*`, `test.pass()`, `test.fail()`:
  - MyLang 側の assertion library。
  - `system/MyKernel/tests/libs/test.mln` のような test-only library として提供する。

## 設計判断

### `test(...)` を runtime 関数にしない

Jest は JavaScript の実行環境上で `test()` を実際に呼んでテスト登録できる。一方、
MyLang の kernel/emulator テストでは `stdin` や `step` を emulator 起動前に知る必要が
ある。したがって `test(...)` は runtime 関数ではなく、`mytest` がソースから読む
宣言として扱う。

### MyCompiler へ入れる範囲

まず MyCompiler には通常の言語機能として lambda syntax を追加する。

```mylang
() => {
    ...
}

(i32 x) => {
    return x + 1;
}
```

既存の `(i32 x) { ... }` function literal lowering を流用できるため、比較的小さい変更で
済む。`test(...)` declaration 自体は当面 MyCompiler に入れず、`mytest` が前処理する。

### MyLangTester へ入れる範囲

- `*.test.mln` discovery。
- `test(...)` declaration parser。
- `options` の読み取り。
- `body` を `kernel_main()` へ lowering した一時 `.mln` 生成。
- `qa/build_toolchain.py` または後続のネイティブ build API 経由で build。
- `myemu` 起動、stdin 注入、serial output 判定。

### MyEmulator へ入れる範囲

初期段階では既存の stdin pipe と `--headless --step` で足りる。後続でテストランナーから
扱いやすくするため、以下を追加する。

- `--stdin <file>`: pipe なしで入力を注入する。
- `--serial-out <file>`: serial output を安定して保存する。
- step limit 到達時の exit code を非ゼロにする。
- halt / step-limit / emulator error の終了理由を区別する。

## 段階移行

> 現状（暫定実装）: lambda を使わない暫定形式が既に入っている。
> `test("name", {...}, () => {})` ではなく `test { name; stdin; expect; step; }` ブロック +
> 通常の `i32 kernel_main()` で記述する（`system/MyKernel/tests/serial_rx.test.mln`）。
> `mytest`（`toolchain/MyLangTester`）はこの `test { }` を読んでビルド → `myemu` 実行 →
> `expect` の serial 出力照合まで動作し、assertion library
> `system/MyKernel/tests/libs/test.mln` も存在する。
> したがってフェーズ1・3は暫定形式で概ね実装済みで、本チケットの主眼は
> **フェーズ2（lambda 構文）** と、暫定 `test { }` 形式から
> 決定済みの `test(...)` + lambda 形式への移行である。options のキー名は暫定実装に合わせ
> `expect` を正とする（旧案の `output` は使わない）。

### フェーズ1: 仕様固定と最小 mytest（暫定 `test { }` 形式で実装済み）

- `toolchain/MyLangTester` を submodule として導入する。
- コマンド名は `mytest`。
- `--list` で `*.test.mln` を発見する。
- 暫定 `test { }` metadata block を読めるようにする。
- `serial_rx.test.mln` を最初の縦通しケースにする。

### フェーズ2: MyLang lambda syntax

- lexer に `=>` token を追加する。
- parser で `(params) => block` と `() => block` を function literal として扱う。
- MySyntaxEngine の grammar と syntax-check も更新する。
- 既存 `(params) block` は互換のため残す。

### フェーズ3: assertion library（暫定形式で実装済み・lambda 移行時に再確認）

- `tests/libs/test.mln` を用意する。
- `pass`, `fail`, `assert_eq_i32`, `wait_serial_rx`, `expect_serial_byte` などを提供する。
- 失敗時は `TEST_FAIL:<reason>`、成功時は `TEST_PASS` を serial 出力して halt する。

### フェーズ3.5: `test(...)` declaration への移行

- `mytest` で `test("name", options, () => { ... })` を静的に読めるようにする。
- `body` を `kernel_main()` へ lowering する。
- 暫定 `test { }` + 手書き `kernel_main()` のテストを新形式へ移す。
- 移行完了後に暫定 `test { }` support を削除する。

### フェーズ4: Python runner の置き換え

- `run_serial_rx_test.py` を `serial_rx.test.mln` + `mytest` に置き換える。
- heap / scheduler / filesystem も `*.test.mln` 化する。
- `qa/test-all.py` から MyKernel の Python runner を段階的に外す。

### フェーズ5: emulator test options 強化

- `--stdin <file>`、`--serial-out <file>` を追加する。
- 終了理由と exit code を整理する。
- `mytest` 側の shell pipe 依存をなくす。

## 検証

1. `make -C toolchain/MyLangTester`
2. `toolchain/MyLangTester/build/mytest --list system/MyKernel/tests`
3. `toolchain/MyLangTester/build/mytest system/MyKernel/tests/serial_rx.test.mln`
4. `make -C toolchain/MyLangCompiler all`
5. `python3 toolchain/MyLangCompiler/tests/run_syntax_check_tests.py`
6. `python3 toolchain/MyLangCompiler/tests/run_integration_tests.py arrowFunctionLiteral`

## 関連

- `system/MyKernel/tests/run_serial_rx_test.py`
- `toolchain/MyLangTester`
- `toolchain/MyLangCompiler` function literal lowering
- `runtime/MyEmulator` stdin / serial / step handling
