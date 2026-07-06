# 命令レベルプロファイラ

MyEmulator に命令レベルのプロファイラを追加した。これまで `--trace`（全命令ログ）や
`--step`（命令数で区切り）はあったが、「**どの関数に時間が集中しているか**」を俯瞰する
手段がなかった。本機能で、実行を1回するだけで4種類のメトリクスを収集し、リンカの
シンボルマップと突き合わせて関数名つきのレポートを出せる。

ゴール: エミュレータの実行ループにフックを1つ足し、**命令数ベース**（実時間ではない）で
ホットスポット・オペコード頻度・コールグラフ・メモリアクセスを集計する。命令数ベースなので
実行ごとに**完全に再現可能**なプロファイルになる。

## 確定した設計判断

- **計測単位は命令数（cycles ではなく retired instructions）**。エミュレータは決定的なので、
  実時間で測るより命令数で測るほうが再現性が高く、最適化前後の比較にそのまま使える。
- **JSON は手書き（serde 等を足さない）**。`Profiler::write_json` が直接文字列を吐く。
  エミュレータの依存クレートを増やさず、ビルドを軽く保つため。整形・集計は Python 側
  （`qa/profile_report.py`）に寄せる。
- **シンボル解決はリンカの `.map` に委譲**。エミュレータは PC の生アドレスだけを記録し、
  関数名への変換はレポート側で行う。そのためにリンカへ `.map` 出力（アドレス→名前）を
  新設した。`global_symbol_table` は元々リンカ内に存在しており、それを1ファイルに書き出す
  だけ。
- **コールグラフはコールスタックモデル**。`CALL`(0x1B) で「呼び出し先エントリ・戻り先アドレス」
  のフレームを push し、`mov pc, lr`（＝戻り）や jump で戻り先アドレスに一致したら pop する。
  フレームに self/inclusive の命令数を溜め、pop 時に関数ごとの集計へ畳み込む。戻りの検出は
  **CALL 時に記録した戻りアドレスにアンカーする**ので、`mov pc, lr` を特別扱いせずとも堅牢。
- **オフはゼロコスト**。`--profile` を渡さなければ `profiler: Option<Profiler>` は `None` で、
  ホットパスの分岐は `is_some()` 1回だけ。メモリヒートマップ用の `profile_mem_read/write`
  も None 時は即 return。

## 収集するメトリクス

| メトリクス | 集計内容 | 集計キー |
|---|---|---|
| ホットスポット | 自己命令数 | PC（アドレス） |
| オペコード頻度 | 実行回数 | 6bit オペコード |
| コールグラフ | self / inclusive 命令数・呼び出し回数・エッジ | 関数エントリPC |
| メモリヒートマップ | read / write 回数 | 4KBページ先頭アドレス |

## CLI

```bash
# エミュレータ単体（--profile <出力先.json>）
myemu -i <image.mbin> --headless --profile profile.json

# Makefile ショートカット
make -C runtime/MyEmulator profile-myemu IN=<image.mbin> PROFILE=profile.json ARGS="--step 300000"

# レポート整形（.map を突き合わせて関数名に解決）
python3 qa/profile_report.py profile.json --map <image>.mbin.map --top 20
```

> **停止しないプログラムは `--step <n>` で区切る。** プロファイルは HALT 時にフラッシュ
> されるため、UIカーネルのように自発停止しないプログラムは命令数で区切ってから計測する。

カーネルは1コマンドで通せる（ビルド→実行→レポート案内まで）:

```bash
python3 qa/run_kernel.py --headless --step 300000 --profile kernel.json
# 実行後に profile_report.py の render コマンドを表示する
```

## 実装の概要

### MyLinker（C++）
- `src/main.cpp`: `--map <file>` フラグを引数列から抜き出す（既存の位置引数はそのまま）。
- `src/Linker.cpp`: `write_map()` を追加。`global_symbol_table`（名前→アドレス）を
  アドレス昇順にソートし `0xADDR NAME` の1行ずつ書く。先頭コメントに text/data の境界を記録。
  `link_objects()` に省略可能な `map_path` を通し、リンク成功後に emit。

### MyEmulator（Rust）
- `src/machine/profiler.rs`（新規）: `Profiler` 本体。`record_instruction` / `record_call` /
  `record_control_flow` / `record_mem_read` / `record_mem_write` と `write_json`。
  `Machine` 向けの薄いフォワーダ `profile_mem_read/write` もここに置く。
- `src/machine/mod.rs`: `profiler: Option<Profiler>` フィールドと、
  `enable_profiler(entry_pc)` / `write_profile(path)` を追加。
- `src/machine/run_loop.rs`: 実行ループで命令実行後にフック。オペコードを1回だけデコードし、
  `CALL` なら `record_call(landed_pc, link_register)`、それ以外は `record_control_flow(landed_pc)`
  を呼ぶ。`program_counter`/`link_register` がジャンプ後の値になった状態で給餌する。
- `src/machine/cpu_exec.rs`: LD/ST/LDB/STB（`0x03/0x04/0x1C/0x1D`）のデータアクセス経路で
  `profile_mem_read/write(addr)` を呼ぶ（命令フェッチやスタックは対象外）。
- `src/cli.rs` / `src/app.rs`: `--profile <path>` を追加。実行**前**に `enable_profiler` で
  コールグラフのルートをエントリPCに固定し、実行後（break/step の途中終了含む）に `write_profile`。
- `Makefile`: `profile-myemu` ターゲット。

### qa（Python）
- `qa/build_toolchain.py`: リンク時に `<output>.mbin.map` を自動生成（`mllinker --map …`）。
- `qa/profile_report.py`（新規）: プロファイルJSONと `.map` を突き合わせて4セクションを整形。
  PC は「直前のシンボル＋オフセット」で解決。メモリのページは、イメージ範囲外なら
  スタック/MMIO/VRAM の**領域名**にフォールバックし、遠いコードシンボルへ誤って
  帰属させない。
- `qa/run_kernel.py`: `--profile [name]` を追加。セッションディレクトリに出力し、
  実行後に `profile_report.py` の render コマンドを案内する。

## 出力例（カーネルを `--step 300000` で計測）

```
=== Hotspots (self instructions; total=300000) ===
  self%         count  location
  47.2%        141480  __START__
  33.9%        101808  mouse_has_event
   4.3%         12847  mem_write_word
   3.1%          9219  serial_putc

=== Call graph (functions by self time) ===
  self%    incl%     calls  function
  47.1%    81.1%         1  __START__+0x950
  33.9%    33.9%      5656  mouse_has_event

=== Memory writes (by 4KB page; total=14279) ===
  freq%         count  page
  93.9%         13405  0x1FFFF000 [stack]
   3.1%           443  0x24000000 [MMIO]
```

この例からは「ブートループが `mouse_has_event` のポーリングで inclusive 約81%を消費」
「書き込みの94%がスタックページ」といった傾向が即座に読める。

## 検証

- **リンカ**: `make -C toolchain/MyLinker test-integration`（既存の2テストが pass）。
  ビルドしたカーネルに対し `main_linked.mbin.map` が 160 シンボルで生成されることを確認。
- **エンドツーエンド**: `python3 qa/run_kernel.py --headless --step 300000 --profile kernel.json`
  でカーネルをビルド・実行し、有効なプロファイルJSON（`total_instructions=300000`）が
  出ること、`profile_report.py` が4セクションすべてを関数名解決つきで描画することを確認。

## 既知の留保・次段

- **`.map` には参照されたシンボルのみが載る**（未参照のローカルラベルは出ない）。リンカの
  既存仕様（narrow scope）で、プロファイラは解決できない PC を生アドレスにフォールバックする。
  エントリ点や被呼び出し関数はエッジ経由で載るので、実用上の穴は小さい。
- **フラッシュは HALT/終了時のみ**。長時間・非停止のプログラム全体像が欲しくなったら、
  「Nステップごとにインクリメンタル出力」を将来拡張できる。
- 割り込みハンドラ（`irq_trampoline` → `irq_dispatch_dispatch`）は、CALL/戻りのアンカー則で
  コールスタックに載る。ただし `iret`（0x20）はコールスタックを直接は畳まないため、
  ハンドラのフレームは戻り先PCが一致した時点で pop される。ネスト割り込みが増えたら要再検証。

## 変更ファイル

- 変更: `toolchain/MyLinker/src/{main.cpp,Linker.cpp}`、`toolchain/MyLinker/inc/Linker.h`、
  `runtime/MyEmulator/src/{cli.rs,app.rs,Makefile}`、
  `runtime/MyEmulator/src/machine/{mod.rs,run_loop.rs,cpu_exec.rs}`、
  `qa/{build_toolchain.py,run_kernel.py}`。
- 新規: `runtime/MyEmulator/src/machine/profiler.rs`、`qa/profile_report.py`。
