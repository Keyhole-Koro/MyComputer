# MyDOMTranspiler `.mlx` UI DSL Compiler

## 背景・目的

OS DOM を MyLang から直接手続き的に組み立てると、UI の構造が読みにくくなりやすい。
MyLangCompiler 本体へ JSX 風構文をすぐ入れる代わりに、`toolchain/MyDOMTranspiler` を前段として使い、
`.mlx` の宣言的 UI 記述を通常の `.mln` source に変換する。

変換後の `.mln` は既存の MyLangCompiler / linker / emulator pipeline に流す。
また、MyLang source に JSX-like return を含めたい場合も入力は `.mlx` とし、
`return <Window ...>;` の部分だけを展開して、周辺の MyLang source を保持した `.mln` を生成する。

```text
app.mlx
  -> mydomc
app.generated.mln
  -> mlc
app.masm
```

```mylang
DomNode* screen() {
    return <Window title="Settings">
        <Button text="OK" />
    </Window>;
}
```

上は次のように、`return <...>;` の部分だけが DOM construction statement へ置き換わる。

```mylang
DomNode* screen() {
    DomNode* node0 = dom.create_node("Window");
    dom.set_str(node0, "title", "Settings");
    DomNode* node1 = dom.create_node("Button");
    dom.set_str(node1, "text", "OK");
    dom.append_child(node0, node1);
    return node0;
}
```

## 名前

- Project: `MyDOMTranspiler`
- Repository: `https://github.com/Keyhole-Koro/MyDOMTranspiler.git`
- Tool path: `toolchain/MyDOMTranspiler`
- Source extension: `.mlx`
- Initial command name: `mydomc`

`.mlx` は JSX-like DOM syntax を含められる MyLang source として扱う。

## 最小構文

最初は静的 DOM tree だけを対象にする。

```mlx
<Window title="Settings" width={320} height={200}>
    <Button id="ok" text="OK" onClick={handle_ok} />
</Window>
```

初期段階では、以下を扱う。

- JSX-like opening / closing tags
- self-closing tags
- string props
- `{number}` / `{identifier}` props
- nested children
- event handler symbol reference

## 変換イメージ

```mylang
DomNode* root = dom.create_window("Settings", 320, 200);
DomNode* ok = dom.create_button("ok", "OK");
dom.set_on_click(ok, handle_ok);
dom.append_child(root, ok);
```

実際の出力 API 名は `system/MyOS/src/ui/dom.mln` または `system/MyKernel/src/...` 側の
DOM API に合わせて決める。

## 段階移行

### フェーズ1: MyDOMTranspiler tool skeleton

- `toolchain/MyDOMTranspiler` を build できる状態にする。
- `mydomc input.mlx -o output.mln` の CLI を用意する。
- 最小 parser / diagnostics / golden test を追加する。

### フェーズ2: Static DOM lowering

- `Window` / `Button` / `Text` など最小 element を `.mln` に落とす。
- props を DOM node の属性設定に変換する。
- children を `append_child` に変換する。

### フェーズ3: Build integration

- `qa/build_toolchain.py` が `.mlx` を見つけたら先に `mydomc` を実行する。
- generated `.mln` を既存の MyLangCompiler 入力に含める。
- generated file の出力先を `qa/outputs/` 配下などに固定する。
- `qa/run_mylang.py` / `qa/test-all.py` が MyDOMTranspiler を通常 toolchain として build / test する。

### フェーズ4: OS DOM integration

- MyOS / MyKernel の小さい UI sample を `.mlx` で書く。
- DOM renderer / event dispatch と接続する。
- `onClick` の handler symbol が既存 MyLang 関数へ解決されることを確認する。

### フェーズ5: Editor / LSP integration

- VS Code extension が `.mlx` を MyLang family の source として開く。
- LSP server が `.mlx` を MyDOMTranspiler で検証し、diagnostics を publish する。
- `.mlx` の JSX-like tag / prop / number / operator を semantic token として返す。
- `.mlx` の top-level DOM tags を document symbol として返す。

## 非目標

- MyLangCompiler 本体への JSX 構文追加。
- HTML / CSS / JavaScript 互換。
- 条件分岐、ループ、component state、style cascade。
- full LSP support。まずは CLI diagnostics と golden tests を優先する。

## 検証

1. `make -C toolchain/MyDOMTranspiler all`
2. `toolchain/MyDOMTranspiler/build/mydomc sample.mlx -o sample.generated.mln`
3. `make -C toolchain/MyLangCompiler all`
4. `toolchain/MyLangCompiler/mlc sample.generated.mln sample.masm`
5. `.mlx -> .mln` の golden output test を追加して通す。

## 変更ファイル（想定）

- `toolchain/MyDOMTranspiler/*`
- `qa/build_toolchain.py`
- `system/MyOS/src/**/*.mlx`
- `system/MyOS/docs/*`
- `issues/tickets/dom-like-os.md`
- `issues/tickets/mykernel-ui-automation.md`

## 完了条件

- `.mlx` から `.mln` へ deterministic に変換できる。
- 静的 DOM tree の最小 sample が MyLangCompiler で compile できる。
- build pipeline が `.mlx` を自動変換できる。
- OS DOM sample が MyDOMTranspiler 経由で構築される。

---

## OS DOM 統合の設計（2026-07-10 確定）

`toolchain/MyDOMTranspiler`（skeleton 実装済み）と `system/MyOS/src/ui/dom.mln`
（DOM_SPEC.md フェーズ1完了 / フェーズ2一部）を実際に噛み合わせるための設計。
以下の方針で進める。

### 方針の一行まとめ

- **mlx の記法は変えない**（`<Button text="OK" onClick={h}/>` の見た目は固定）。
- **transpiler の出力先だけを OS DOM の実在 API に向ける**。カーネルは軽いまま。
- **座標は mlx に明示**（layout エンジンは今回スコープ外）。
- **state / useState は今回スコープ外**（動的更新はハンドラが dom API を直接叩く）。
- **`system/MyOS/src/ui/graphics.mln` は変更しない**。mlx と graphics の間に
  dom.mln が挟まっており、mlx 統合は dom ノード層だけの話。

```text
mlx (.mlx)
  └─ mydomc ─▶ dom.mln ノードツリー   ← 統合で触る層
                   └─ renderer が走査 ─▶ graphics.fill_rect / draw_text …  ← 不変
```

### 解決した中心課題: transpiler 出力 ↔ dom.mln API のズレ

skeleton の Generator は「汎用 DOM」を仮定し、以下を吐く（`embedded_return.expected.mln`）:

```mylang
DomNode* node0 = dom.create_node("Window");     // kind が文字列
dom.set_str(node0, "title", "Settings");        // set_str / set_i32 / set_ref は
dom.set_i32(node0, "width", 320);               //   dom.mln に存在しない
dom.set_ref(node1, "onClick", handle_ok);
```

一方 dom.mln の実在 API は「有限 kind の enum + 固定スロット」:

```mylang
i32  create_node(i32 kind, char *name)   // kind は NODE_WINDOW=8 等の enum 値
void set_bounds(i32 id, i32 x, i32 y, i32 w, i32 h)
void set_text(i32 id, char *text)
void set_role(i32 id, i32 role)
void set_state_flag(i32 id, i32 flag, i32 on) / i32 get_state_flag(...)
void append_child(i32 parent_id, i32 child_id)
Node* get_node(i32 id) / void dump() / void init()
```

**→ transpiler が汎用 DOM を吐く限り現状の dom.mln では compile が通らない。**
DOM_SPEC.md が「props は固定スロット、任意 key/value は当面持たない」と決めている
ため、transpiler 側を OS DOM に合わせる（＝ tag/prop を実在 helper へ直接下ろす）。

### tag → dom.mln API 対応表

transpiler は既知 element を固定スロット helper へ下ろす。id 型は `i32`
（`DomNode*` ではない。dom.mln の id は i32、Node* は get_node で取る）。

| mlx element | 生成する dom API | 備考 |
|---|---|---|
| `<Window title=.. x=.. y=.. w=.. h=..>` | `create_window(title, x, y, w, h)` | kind=NODE_WINDOW, role=ROLE_WINDOW |
| `<Button text=.. x=.. y=.. w=.. h=.. onClick={h}>` | `create_button(text, x, y, w, h)` ＋ `set_on_click(id, h)` | kind=NODE_BUTTON, role=ROLE_BUTTON |
| `<Text text=.. x=.. y=..>` | `create_text(text, x, y)` | kind=NODE_TEXT, role=ROLE_TEXT |
| （子）| `append_child(parent_id, child_id)` | 既存 API |

未知 element / 未知 prop は transpiler が diagnostics でエラーにする（白名単制）。
これにより mlx の語彙は OS の有限 element に限定される。

生成イメージ（`create_button("CLICK ME",120,130,150,60)` に下りる例）:

```mylang
i32 node0 = dom.create_window("MyKernel Window", 100, 100, 600, 400);
i32 node1 = dom.create_button("CLICK ME", 120, 130, 150, 60);
dom.set_on_click(node1, on_click);
dom.append_child(node0, node1);
i32 node2 = dom.create_text("clicks: 0", 320, 150);
dom.append_child(node0, node2);
```

### props 仕様（今回の白名単）

- `title` / `text`（string）→ create helper の第1引数 / `set_text`。
- `x` / `y` / `w` / `h`（number）→ create helper の bounds 引数。**mlx に明示**。
  未指定は 0。layout（Column/Row 自動配置）は今回スコープ外・将来チケット。
- `onClick`（identifier）→ `set_on_click(id, fnptr)`。handler symbol は
  周辺 MyLang source 内の関数として解決される（transpiler は名前を通すだけ）。
- 上記以外の prop 名は今はエラー。必要になった element/prop を都度追加する。

### dom.mln 側の小追加（graphics は不変）

mlx 統合のために dom.mln へ追加が要るもの（DOM_SPEC.md で未実装の分）:

1. UI create helper: `create_window` / `create_button` / `create_text`
   （kind + role + bounds + text + state をまとめて設定。DOM_SPEC フェーズ2の残り）。
2. `set_on_click(i32 id, <fnptr> handler)`: handler slot。DOM_SPEC には未記載の新規。
   Node に handler スロット（`u16`/`i32` 幅の関数ポインタ）を1つ足す。**要検討**:
   MyLang の関数ポインタ幅と struct レイアウト（現 sizeof=30→32 の余白）への影響。
   click 配送は既存イベントループ（DOM_SPEC 例3 find_at → target）から呼ぶ。

### state / useState について（今回はやらない）

- ISSUE-025 非目標のとおり component state は入れない。transpiler は静的ツリーを
  1回組むだけ（`build_dom()` / `return <...>` 展開）で、再レンダー・diff・closure を持たない。
- 動的更新（例: `clicks: 0 → 1`）は **ハンドラが dom API を直接叩く**（DOM_SPEC 例4）:
  ```mylang
  void on_click(i32 btn_id) {
      g_clicks = g_clicks + 1;
      dom.set_text(g_label_id, /* 整形済みバッファ */);
      // 次フレームの render(desktop) が新しい text を描く（diff なし・全描画）
  }
  ```
- 将来: (B) `<Text text={ident}/>` を許し render が毎フレーム値を拾う軽量案、
  (C) reactive state（setState→再実行→diff）は別チケット。今の非目標を変えない。

### 段階計画（このズレ解消を織り込んだ実行順）

1. **dom.mln に UI helper を実装**（`create_window/button/text`）。DOM_SPEC フェーズ2の残り。
   カーネル起動 dump で props 付きノードが出ることを確認（既に一部検証済み）。
2. **transpiler Generator を書き換え**、tag→helper・onClick→`set_on_click`・
   append_child を吐くようにする。golden fixture（basic/nested/embedded_return）を
   新 API 出力に更新。id 型を `DomNode*`→`i32` に。
3. **`set_on_click` と handler slot** を dom.mln に足す（関数ポインタ幅を先に確認）。
4. **最小 mlx sample を縦に1本通す**: `system/MyOS/src/apps/*.mlx` を書き、
   `mydomc → mlc → emulator` まで通す。`qa/build_toolchain.py` の `.mlx` 前処理を確認。
5. renderer を DOM 駆動へ（DOM_SPEC 例2）・find_at hit-test（例3）・snapshot（ISSUE-024）は
   既存フェーズのまま継続。

### 検証（この統合の受け入れ）

1. mlx の `<Window><Button/><Text/></Window>` が新 Generator で dom.mln 実在 API のみを
   使う `.mln` に変換される（存在しない `set_str`/`set_i32`/`set_ref` を吐かない）。
2. 生成 `.mln` が `mlc` で compile できる（未定義 API エラーが出ない）。
3. `onClick={fn}` が `set_on_click(id, fn)` になり、fn が周辺 source の関数へ解決される。
4. 最小 sample が emulator で描画され、click でハンドラが dom API を叩いて text が更新される。

### 実装状況（2026-07-10）

段階計画のうち縦1本を通し切った。**mlx → dom → emulator が動作**。

- ✅ **間接呼び出しを MyLangCompiler に追加**（onClick 配送の前提）。関数ポインタ変数の
  `f(args)` を `movi lr, ret; mov pc, r2` で実装（`codegen_call.c`）、semantic は変数名の
  呼び出しを許可（`semantic_walk.c`）。r0 は常に 0 の不変条件（`cmp reg,0`→`cmp reg,r0`）を
  守るため callee アドレスは r2 に置く。integration 52/52・semantic 全通過。
- ✅ **dom.mln に UI helper**：`create_window`/`create_button`/`create_text`・`desktop_id`・
  `first_child`/`next_sibling`・`set_on_click`/`get_on_click`/`dispatch_click`。`Node` に
  `on_click`（i32 関数ポインタ）スロット追加（sizeof 30→36、alloc 36）。`NODE_*/ROLE_*/STATE_*`
  は cast せず bare で渡す（`(i32)STATE_VISIBLE` は `undefined identifier` になるため）。
- ✅ **MyDOMTranspiler Generator を書き換え**：tag→helper・onClick→`set_on_click`・
  append_child・id 型 `i32` を出力。未知 element/prop は compile error（白名単）。
  golden fixture 更新、error テスト追加（golden 8/8）。
- ✅ **build_toolchain**：`.mlx` の generated `.mln` を **元の .mlx と同じ dir** に出して
  compile し後始末（相対 import と package 検出が source 位置基準のため）。
- ✅ **最小 sample** `system/MyOS/src/apps/counter.mlx`：`<Window><Button onClick><Text>` が
  dom ツリーに落ち、`dispatch_click` が間接呼び出しで handler を 2 回叩き **R1=2**。
  dump に `Counter [role=3 ...]` / `CLICK ME [role=4 ...]` / `clicks: 0 [role=5 ...]` が出る。
- ⬜ **未了（次フェーズ）**：renderer を DOM 駆動へ（`graphics.*` で実描画）、find_at hit-test、
  snapshot()、`.mlx` の LSP 対応。cross-package で `dom.STATE_*` 定数を読むには
  `import dom_STATE_VISIBLE` が要る制約は別途（今回は sample 側で回避）。

**既知の注意点**: `SourceTranspiler` は comment/string 内を無視せず `return <` を JSX として
拾う。`.mlx` の comment に `return <...>` と書くと `unterminated JSX return element` になる。
