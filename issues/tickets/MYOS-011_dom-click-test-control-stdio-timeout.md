# `dom_click_test.py` が control-stdio でタイムアウトする

## 背景

MYOS-004 で入れたヘッドレス UI automation（MyDOMTester）の実テストである
`system/MyOS/tests/dom_click_test.py` が失敗する。

```
$ python3 qa/runners/run_system.py --no-run
$ python3 system/MyOS/tests/dom_click_test.py
kernel: spawning shell task
ui: Startinclick thg OS shee buttonll...
My (windowOS>  must have focus)
Error: control-stdio: timed out waiting for the kernel to boot
```

## 問題

カーネルは正常に起動しており、シリアル TX にも出力が出ている。しかし
control-stdio クライアントが待っている boot マーカーを認識できずタイムアウトする。

出力を見ると **shell タスクと UI タスクの print が1文字単位で混ざっている**。

```
ui: Startinclick thg OS shee buttonll...
```

は `ui: click the button (window must have focus)` と
`Starting OS shell...` がインターリーブしたもの。`debug.print` は
`serial.putc` を1バイトずつ呼ぶだけで、タスク間の排他がない。マーカー行が
分断されるため、クライアント側のマッチが成立しないと考えられる。

## 切り分け済みの事実

- MLC-004 phase 0（std library 導入、`serial.mln` の ringbuf 化、`counter` の
  `strbuf` 化）を **全て戻したベースラインでも同じエラーで失敗する**。
  phase 0 による回帰ではない
- テストは MYOS-004 のコミット以降、通っていた形跡がない

## 目標

`dom_click_test.py` が通るようにする。これが通らないと counter アプリの
ラベル生成（`clicks: N`）を自動で検証する手段がない。

## 想定される方向

- `debug.print` / `println` を行単位でアトミックにする（タスク切り替えを
  抑止するか、行バッファを持つ）
- または control-stdio のマーカー検出を行分断に耐える形にする

前者の方が根本的。シリアルは今後もログの主経路なので、行が混ざる状態は
UI automation 以外でも問題になる。

## 検証

```
python3 qa/runners/run_system.py --no-run
python3 system/MyOS/tests/dom_click_test.py
```

## 完了条件

- `dom_click_test.py` が `PASS: clicks: 0 -> 1 -> 3` を出す
- シリアル出力が行単位で混ざらない

## 関連

- MYOS-004 MyKernel DOM UI Automation
