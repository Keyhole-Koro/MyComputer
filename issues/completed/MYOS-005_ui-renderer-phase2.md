# UI レンダラーと描画機構の実装（DOM-like OS フェーズ2）

## 背景
DOM-like OS のフェーズ1（Kernel Object Tree の構築）が完了し、カーネル内に `Node` のツリー構造を保持・操作できるようになりました。次のステップとして、このツリー情報を元に画面へUIを描画する仕組み（フェーズ2）を実装します。

## 目標
`Window`, `Text`, `Button` などの UI ノードを解釈し、実際の画面（フレームバッファ）に描画するレンダラーを作成する。

## タスク一覧

### 1. エミュレータ側のディスプレイデバイス実装（必要な場合）
現状の `MyEmulator` に画面描画機能（フレームバッファ）がない場合は、メモリアップされた VRAM 領域と、それをホスト側（SDLやターミナルなど）に出力する仕組みを追加する。
- 画面サイズ・色深度の決定（例: 320x240, 8bit/16bit/32bit color など、リソース制約に合わせて）
- VRAM アドレスのマッピング

### 2. カーネル側の描画プリミティブ実装
VRAM に対して直接ピクセルを書き込む、低レイヤーの描画関数群を実装する。
- `fill_rect(x, y, w, h, color)`: 矩形の塗りつぶし
- `draw_rect(x, y, w, h, color)`: 矩形の枠線描画
- `draw_char(x, y, char, color)`: 固定幅フォントの1文字描画
- `draw_text(x, y, text, color)`: 文字列の描画

### 3. レンダラーの実装
Kernel Object Tree（`/system/ui/desktop` 配下）をトラバースし、各ノードの種別とプロパティ（現在はまだ未実装なので絶対座標等の情報を持たせる拡張が必要）に応じて描画を行う。
- `NODE_WINDOW`: 枠線と背景、タイトルバーを描画
- `NODE_TEXT`: 指定座標に文字列を描画
- `NODE_BUTTON`: 枠線つきで文字列を描画

### 4. DOMツリーへの絶対座標・サイズ情報の追加
現在の `Node` 構造体には `id`, `kind`, `name`, ツリーの親子情報しかありません。描画に必要な座標やサイズを持たせるため、`Prop` の仕組みを導入するか、`Node` 構造体に拡張フィールド（`x`, `y`, `width`, `height`）を追加する。

## 検証方法
カーネルの初期化処理（`kernel_init`）にて以下のようなツリーを構築し、エミュレータ上で正しくウインドウとテキストが表示されることを確認する。

```text
Node(id=xx, kind=NODE_WINDOW, x=10, y=10, w=200, h=100)
  Node(id=xy, kind=NODE_TEXT, x=20, y=20, text="Hello MyOS")
  Node(id=xz, kind=NODE_BUTTON, x=20, y=50, w=60, h=20, text="OK")
```

## 関連
- `dom-like-os.md` (フェーズ1-5の全体設計)
