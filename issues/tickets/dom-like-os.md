# DOM 的 OS オブジェクトモデル

## 背景・方向性

MyComputer の OS は、単にプロセスとデバイスを裏で管理するだけではなく、OS 全体を
**DOM のような観測・操作可能なツリー**として扱う方向にする。

ここで借りるのは HTML/CSS/JavaScript 互換ではなく、DOM の次の性質だけ：

- ノードツリー
- ノード ID
- 属性（props）
- 子ノード
- イベント配送
- 再描画
- クエリ
- 差分更新

逆に、最初から背負わないもの：

- HTML タグ仕様
- CSS 全仕様
- JavaScript 互換
- Web ブラウザの複雑な互換性
- Web セキュリティモデル全部

ゴールは「Web ブラウザ互換 OS」ではなく、**OS の状態・UI・デバイス・プロセスを同じ
オブジェクトモデルで扱える MyOS** にすること。

## 基本モデル

OS 内部に Kernel Object Tree を持つ。

```
/system
  /process
    /1
    /2
  /device
    /keyboard
    /mouse
    /display
  /fs
    /home
  /ui
    /desktop
      /window/1
      /window/2
```

UI だけでなく、プロセス、デバイス、ファイル、タイマーなどもノードとして表現する。
描画対象になるノードと、OS 管理用の非表示ノードは同じツリー上に存在してよい。

最小の内部構造案：

```c
typedef u16 NodeId;

typedef enum {
    NODE_ROOT,
    NODE_SYSTEM,
    NODE_PROCESS,
    NODE_DEVICE,
    NODE_DIRECTORY,
    NODE_FILE,
    NODE_DESKTOP,
    NODE_WINDOW,
    NODE_BOX,
    NODE_TEXT,
    NODE_BUTTON,
    NODE_TIMER,
} NodeKind;

typedef struct Node {
    NodeId id;
    NodeKind kind;
    char *name;
    NodeId parent;
    NodeId first_child;
    NodeId next_sibling;
    PropList props;
} Node;
```

64KB 制約のある MyComputer では、最初から汎用 map や可変長文字列を多用しすぎない。
初期実装は固定長配列・小さい props テーブル・短い文字列でよい。

## Props

DOM の属性に相当する値を props と呼ぶ。

最初に必要な型：

- `i32`
- `u16`
- `bool`
- `string`
- `NodeId`

UI ノードの例：

```
title = "Terminal"
x = 20
y = 20
width = 400
height = 240
visible = true
ownerPid = 2
```

プロセスノードの例：

```
pid = 2
name = "shell"
state = "running"
exitCode = 0
```

デバイスノードの例：

```
name = "keyboard"
ready = true
irq = 1
```

## UI ノード

最初の UI ノードは少なくする。

- `Desktop`
- `Window`
- `Box`
- `Text`
- `Button`

レイアウトエンジンは後回しにして、最初は絶対配置でよい。

```tsx
<Window title="Hello" x={10} y={10} width={220} height={120}>
    <Text x={8} y={8}>Hello MyOS</Text>
    <Button x={8} y={40} width={80} height={24}>OK</Button>
</Window>
```

内部では以下のようなノード列に lower される。

```
NODE_WINDOW title="Hello" x=10 y=10 width=220 height=120
  NODE_TEXT x=8 y=8 text="Hello MyOS"
  NODE_BUTTON x=8 y=40 width=80 height=24 text="OK"
```

`Column` / `Row` / `gap` / `padding` などの宣言的レイアウトは、絶対配置で描けるように
なってから追加する。

## Event

イベントも DOM 的に扱う。

最初に必要なイベント：

- `click`
- `keydown`
- `keyup`
- `timer`
- `process_exit`
- `device_ready`
- `message`

イベント構造案：

```c
typedef struct Event {
    u16 type;
    NodeId target;
    NodeId current;
    u16 x;
    u16 y;
    u16 key;
    u16 data0;
    u16 data1;
} Event;
```

最初は捕捉・バブリングを完全実装しない。`target` ノードに配送し、必要なら親へ上げる
程度でよい。後で DOM 風に `capture -> target -> bubble` を追加できる。

## Process と UI の分離

プロセスノードと表示ノードは分ける。

```
/system/process/2
  name = "editor"
  state = "running"

/system/ui/desktop/window/7
  title = "Editor"
  ownerPid = 2
```

プロセスは UI ノードを所有できるが、プロセスそのものを window の子にしない。
これで scheduler / process 管理と renderer の責務が混ざりにくくなる。

## Renderer

renderer は UI ノードだけを走査して framebuffer へ描画する。

最初に必要な描画プリミティブ：

- 塗りつぶし矩形
- 枠線
- 固定幅フォントの文字列
- マウスカーソル

描画対象：

- `Desktop`
- `Window`
- `Box`
- `Text`
- `Button`

非描画対象：

- `Process`
- `Device`
- `File`
- `Directory`
- `Timer`

ただし非描画ノードも query できるようにすることで、デバッガやシェルから OS 状態を
ツリーとして見られる。

## mylang との接続

mylang には TSX 風の UI リテラルを足す余地がある。

```tsx
i32 main() {
    NodeId win = os_create(
        <Window title="Hello" x={10} y={10} width={220} height={120}>
            <Text x={8} y={8}>Hello MyOS</Text>
            <Button x={8} y={40} width={80} height={24}>OK</Button>
        </Window>
    );

    os_run();
    return 0;
}
```

最初は UI リテラルを専用 AST にせず、関数呼び出しへ lower するのがよい。

```c
NodeId win = os_create(
    node_window(
        props(title("Hello"), x(10), y(10), width(220), height(120)),
        node_text(props(x(8), y(8)), "Hello MyOS"),
        node_button(props(x(8), y(40), width(80), height(24)), "OK")
    )
);
```

これなら compiler/codegen 側の変更を小さく始められる。

## 段階移行

### フェーズ1: Kernel Object Tree

- `Node` / `NodeKind` / `Prop` を kernel 側に追加。
- root / system / process / device / ui の固定ノードを起動時に作る。
- ノード作成・削除・子追加・props 読み書き API を作る。
- シリアル出力でツリーを dump できるようにする。

### フェーズ2: 最小 UI と renderer

- `Desktop` / `Window` / `Text` / `Button` を追加。
- framebuffer または emulator display に矩形と文字を描画する。
- 絶対配置だけで window を表示する。

### フェーズ3: Event

- keyboard / mouse / timer から Event を作る。
- hit test で `click` の target node を決める。
- target へイベント配送する。
- button click で props 更新や message 送信ができるようにする。

### フェーズ4: mylang UI リテラル

- mylang parser に UI literal を追加する。
- UI literal を `node_*` 関数呼び出しへ lower する。
- `os_create` / `os_set_prop` / `os_listen` / `os_run` の最小 runtime API を用意する。

### フェーズ5: 宣言的更新

- 状態変更に応じて subtree を再生成する。
- 差分更新は後回しでよい。最初は小さい subtree を作り直す。
- 必要になったら node key / retained node / dirty flag を導入する。

## 実装時に詰める点

- **NodeId の寿命**: 削除済み ID の再利用を許すか。世代番号を持つか。
- **props の表現**: 固定スロットにするか、小さい key/value 配列にするか。
- **文字列管理**: kernel heap 上に置くか、固定長 inline string にするか。
- **権限**: プロセスが他プロセス所有の UI / process / device ノードを書き換えられるか。
- **イベントキュー**: グローバル 1 本にするか、process ごとに持つか。
- **renderer の責務**: window manager と renderer を分けるか、初期は一体にするか。
- **デバッグ API**: シリアルから tree dump / query / prop set できると検証が楽。

## 検証

1. 起動時に固定ツリーを作り、シリアルへ dump できること。
2. process ノードが task/scheduler の状態と一致すること。
3. window / text / button ノードを作ると画面に描画されること。
4. mouse click から target node が決まり、button の event handler が呼ばれること。
5. mylang から UI ノードを作成し、kernel tree に反映されること。

## 関連

- `kernel-heap.md`
- `shared-frontend.md`
- `syntax-engine-generic.md`
