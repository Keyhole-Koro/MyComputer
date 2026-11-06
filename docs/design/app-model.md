# アプリのモデル：状態、宣言、反映

**Status:** Draft 1（2026-11-07）。実装前。

**Scope:** アプリの入口、`@app` の役割、画面の宣言と更新、イベント、アプリと DOM の境界

**Supersedes:** `system/MyAppFramework/docs/APP_FRAMEWORK.md` の `@app`、`ref=`、ハンドラの節

---

## 0. 一言で

アプリは状態を持って変える。フレームワークはそれを画面に映す。

| 責務 | 持ち主 |
| --- | --- |
| 状態の定義と初期値 | アプリ（`struct`、`start`） |
| 状態の変え方 | アプリ（ハンドラ） |
| 状態と画面の対応の宣言 | アプリ（`view`） |
| インスタンスの生成 | フレームワーク（`app.run<T>`） |
| ノードの ID と画面の更新 | フレームワーク |
| ウィンドウの配置 | シェル |

## 1. 三つの部品

**規則 A1（`@app` は目録）** `@app` は `struct` に付ける。シェルが実行ファイルを起動せずに読む
データだけを持つ。名前、`single`、`opens`。振る舞いは持たない。

**規則 A2（`App` は約束）** アプリの型は `App` を実装する。形はコンパイラが検査する。

```c
export trait App {
    Self start();
    View (Self self) view();
    void (borrow Self self) open(str path) { }
    void (borrow Self self) close() { }
}
```

**規則 A3（`main` は入口）** プログラムの入口は普通の `main` で、動かす型を書く。

```c
i32 main() { return app.run<Counter>(); }
```

`@key` と `@timer` は、キーや周期というデータなので注釈のまま残す。`@open` と `@on_close` は
`App` のメソッドになる。

## 2. 状態と画面

**規則 A4（`view` は読むだけ）** `view` の受け手は `(Self c)` なので、状態を書き換えられない
（規則 P1）。

**規則 A5（値の表示）** 属性に状態を書くと、その値が変わった時に画面が変わる。

```c
<Label text={"clicks: %d", c.clicks} />
<Checkbox checked={c.step == 2} onChange={c.set_double} />
```

`.dom.mln` の展開が、状態に依存する属性を更新する関数を生成する。実行時はハンドラの後でそれを
呼ぶ。画面全体は作り直さない。

**規則 A6（DOM が持つ値）** 入力中の値と大きな値は DOM が持つ。アプリは部品を持ち、部品の
操作だけができる。ノードの ID には触らない。

| 部品 | できること | 例 |
| --- | --- | --- |
| `TextField` | 読む、書く、消す | 入力欄、Editor の本文 |
| `TextLog` | 末尾に足す | Terminal の出力 |

```c
<TextInput field={n.title} placeholder="Title" onChange={n.changed} />
```

**規則 A7（構造）** 項目数が変わる部分は値として渡す。出すかどうかは `when=` で決める。

```c
<List items={f.rows} selected={f.selected} onChange={f.select} />
<Dialog when={f.asking} text="Delete this file?" onConfirm={f.delete} onCancel={f.cancel} />
```

**規則 A8（イベントは値を運ぶ）** ハンドラは必要な値だけを受け取る。ノードの ID は渡らない。

```c
void (borrow Counter c) click() { ... }
void (borrow Notes n) changed(str text) { ... }
void (borrow Counter c) set_double(bool on) { ... }
```

## 3. 動く順番

1. シェルが実行ファイルの `@app` の行を読み、ランチャーに並べる。
2. 起動すると、プロセスの `main` から `app.run<T>()` に入る。
3. `run` が `T::start()` で状態を作り、`view()` で画面を作る。
4. イベントが来ると、ハンドラを呼び、状態に依存する属性を更新する。
5. 閉じると `close()` を呼んで終わる。

アプリは 1 プロセスに 1 つなので、状態は `run` が持つ。

## 4. 消えるもの

`ref=`、アプリの `NodeId` のフィールド、`refresh()`、`ui.is_checked`、`text_copy`、ハンドラの
`NodeId id`、`app_main` の `sbrk` とゼロ埋め、`@open`、`@on_close`、注釈の関数番地と `size`、
`<Window>` の `x` と `y`。

## 5. 決まっていないこと

- **`when=` で消えたものの中の部品。** 再び出た時に値を残すかどうか。
- **`items=` の型。** 今は改行区切りの `Text<N>`。`Vec` が共有値になれば置き換える（MLC-025）。
- **Terminal の子プロセスの出力。** OS が DOM へ直接流すので、`TextLog` から ID を渡す道が要る。
- **属性の更新の粒度。** 全部の束縛を毎回比べるか、書き換えたフィールドで絞るか。まず全部比べる。

## 6. 移行

1. Counter を新しい形で動かす（`App`、`app.run`、値の属性）。
2. Notes で `TextField` を固める。
3. Files で `items=` と `when=` を固める。
4. Editor と Terminal を移す。
5. `ref=`、`@open`、`@on_close`、`app_main` の生ポインタを消す。
