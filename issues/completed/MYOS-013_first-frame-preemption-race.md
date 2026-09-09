# MYOS-013: 初回フレームがタイマー割り込みでプリエンプトされ box/button/text が遅延描画される

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Done | - | claude-code:sonnet-5 | 2026-09-09 |

## Summary

`compositor.run()`冒頭の初回 `dom.render_all()` が、`scheduler.init()`/`irq.enable()`
呼び出し後（プリエンプション有効化後）に実行されていたため、最初のタイマー割り込みが
render_all()のツリー走査の途中でtask 0を横取りしてしまい、box/button/textが「その場では
描かれず、後続の scheduler スライスが十分溜まってから遅れて出現する」状態になっていた。
ユーザー視点では「クリックした瞬間に関係ない四角（box）が描画される」ように見えたが、
クリックは無関係で、実際は起動シーケンスのプリエンプション競合だった。

## Background

ユーザー報告: 「clickしたときに、関係ないところに四角が描画されてしまう」
（MYOS-012 の DOM inspector CLI 作業中に見つかった）。

`system/MyOS/tests/dom/click_artifact_repro.domscript` でクリック前後のスクリーンショット
＋DOM snapshotを取得し、差分をピクセル単位で解析:

- クリック前後の差分は box (x=220,y=240,w=1160,h=720) の領域とほぼ一致 → 「新しい図形」
  ではなく「まだ描かれていなかった box が初めて描かれた」ことが判明。
- **クリックせずに `frame_wait()` だけを重ねても同じ現象が再現**（tick 16〜32 の間で
  box/button が同時に正しい色になる）。クリックは無関係と確定。

## Design

### Current State（修正前）

`system/MyOS/src/boot/main.mln`（修正前）:

```c
counter.mount();       // box/column/button/text を含む全ツリーを構築
dom.dump();
fs.init();
scheduler.init();      // ← task 0 がプリエンプト可能になる
irq.set_handler();
irq.enable();          // ← 割り込み有効化
scheduler.spawn_task(shell.run);
compositor.run();      // ← 内部で dom.render_all() が初回全画面描画
```

`system/MyKernel/src/kernel/scheduler.mln:268` のコメント:

> Task 0 is the current context: the first timer interrupt saves our SP into
> task_sps[0]... **Interrupts can now safely context-switch!**

`compositor.run()`（修正前、`compositor.mln:31-40`）は `dom.render_all()`（box→column→
button→text と再帰的に描画）を **プリエンプション有効化後** に呼んでいた。最初のタイマー
割り込みが render_all() の途中で task 0 を横取りし shell task へ切り替わると、shell は
即座に `"MyOS> "` を出して `read_char()` でブロックする。control-stdio の
`wait_for_boot()`（"MyOS>" 待ち）はこの時点でリターンしてしまうため、**render_all() が
box/button/text まで描き切る前に "boot完了" と誤認される**。その後 boot task と shell task
が交互にスライスを取り合いながら render_all() の残りが少しずつ進み、完了した時点で画面に
box/button が出現する。

### Proposed Design（実施した修正）

初回のフルペイントを `scheduler.init()`/`irq.enable()` より前に済ませ、プリエンプト
されない状態でアトミックに完了させる。

`compositor.mln`: 初回ペイントを `run()` から独立した関数へ切り出す。

```c
export void paint_first_frame() {
    graphics.show_cursor(1);
    dom.render_all();
    graphics.present();
}
```

`main.mln`: `fs.init()` の直後、`scheduler.init()` より前に呼ぶ。

```c
counter.mount();
dom.dump();
fs.init();

compositor.paint_first_frame();   // ← プリエンプション有効化前にアトミックに完了

debug.println("kernel: enabling interrupts for event queue");
scheduler.init();
irq.set_handler();
irq.enable();
scheduler.spawn_task(shell.run);
compositor.run();                  // run() はもう初回ペイントをしない
```

### Alternatives Considered

- **render_all() 自体をプリエンプト不能にする（割り込み無効化区間を追加）**: 個別の
  低レベル критical section を導入するより、「初回ペイントは割り込みが有効になる前に
  済ませる」という起動順序の入れ替えの方が単純で、他の箇所への副作用がない。
- **damage region ロジックを直す**: 調査の結果 `damage_rect`/`node_in_damage` 自体には
  バグがなかった（union は正しく蓄積される）。原因はレンダリングロジックではなく起動順序
  だったため、ここは変更していない。

### Non-Goals

- render_scene()（差分再描画）側のプリエンプション耐性は対象外。初回フルペイントに限定。
- タイマー割り込み間隔やスケジューラのタイムスライス方式自体の変更はしない。

## Progress

- [x] `compositor.paint_first_frame()` を切り出し
- [x] `main.mln` で `scheduler.init()`/`irq.enable()` より前に呼ぶよう並び替え
- [x] 修正前後で `frame_wait()` を重ねた screenshot 比較により再現・修正確認
- [x] `dom_click_test.py` / `mydomtester` の counter.domscript で回帰確認

## Verification

```
make build
python3 system/MyOS/tests/dom_click_test.py
python3 -m system.MyOS.tests.mydomtester.dsl system/MyOS/tests/dom/counter.domscript
```

tick別の再現確認（修正前後で比較、box/buttonの座標を直接サンプリング）:

```python
# 修正前: tick 0-16 は box=(255,255,255)（未描画）、tick 32 で box=(224,224,224) に変化
# 修正後: tick 0 から box=(224,224,224)、button=(204,204,204)（正しく描画済み）
```

## 完了条件

- [x] クリックなしで `frame_wait()` を重ねても box/button の色が変化しない
  （= tick 0 から常に正しく描画されている）。実機確認済み。
- [x] `dom_click_test.py` が緑（`PASS: clicks: 0 -> 1 -> 3`）。
- [x] `counter.domscript` が最後まで通る（`wait_for text="clicks: 3"` を通過）。

## 関連

- `issues/tickets/MYOS-012_dom-inspector-cli.md`（この調査に使った domscript/inspect CLI）
- `issues/completed/MYOS-002_interrupts.md`（タイマー割り込み・プリエンプションの基盤）
- `system/MyOS/tests/dom/click_artifact_repro.domscript`（再現・診断に使ったスクリプト）
