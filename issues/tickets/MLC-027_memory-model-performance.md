# MLC-027: メモリモデルの性能（計測と最適化）

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| In Progress | - | - | 2026-11-07 |

## Summary

共有値のカウントの増減、書く前のコピー、範囲検査で増える命令を測り、コンパイラと CPU の
両方で取り返す。共有値を入れる前に、決まった結果が出る基準を作って記録しておく。

## Background

- 参照数 +1 は `load` / `addis` / `store` の3命令、−1 は 0 の判定を含めて5命令前後。
  atomic にすると `cas` の再試行ループで5〜6命令。
- 今のコード生成は、変数を毎回スタックに書いて読み戻す。`return p->z;` だけの関数が19命令
  になり、必要なのは3命令（2026-10-30）。rc で増える分より、この無駄の方が大きい。
- 範囲検査は `chk` 命令（2026-10-30）で1命令になった。
- カーネルの末尾は `0x1FB3CC` で、21 ビット即値の上限 `0x200000` まで約 19 KB。

### 計測について分かっていること（2026-11-05）

- `run_system.py --screenshot` の「最初の WFI で止まる」は、今は起きない。
  `--step 200000000` を使い切って止まる。
- タイマーは実時間で動くので、同じイメージでも命令の流れが毎回少し変わる。起動の
  200M 命令は、スケジューラ（`thread_set_current_slot` 15.8%、`thread_sleeping_until`
  11.0%）と `fs_read` 11.3% が大半だった。
- そのため、起動の命令数は基準に向かない。止まるまで動く、決まった処理を基準にする。
  候補はコンパイラの e2e（143本、止まった時の命令数）と、QA のカーネルのテスト
  （DOM、FS、heap）。

### 基準（2026-11-07）

`qa/baselines/e2e-instructions.json` が e2e 157 本の停止時の命令数で、rc の前の記録。
2 回測って表はバイト単位で一致した。

```bash
python3 tools/MyProfiler/myprofiler.py bench after.json
python3 tools/MyProfiler/myprofiler.py bench-diff qa/baselines/e2e-instructions.json after.json
```

合計 2,479,903,423 命令のうち 96.2% が `genericI32ToString` の 1 本で、合計だけを見ると他の
変化が隠れる。ケースごとの差を見ること。原因は `i32.to_string` の `value % 10` と
`value / 10`（`text/str.unsafe.mln:390-391`）で、除算が引き算の繰り返しなので商に比例して
命令が増える。MyProfiler の `arith` に 99.9% が出る。

## Design

### Proposed Design

1. **基準。** 止まるまで動くプログラムの命令数を、表にして記録するスクリプト。rc の前後で
   比べる。
2. **参照数の最適化。** 引数で渡すだけなら増減しない。最後の使用は move にする。増やして
   減らす組を消す。関数の外に出ないオブジェクトはスタックに置く。1スレッドのプロセスでは
   atomic にしない。
3. **コード生成。** 変数をレジスタに置き、書いてすぐ読み戻す無駄をなくす。
4. **CPU の命令。** オフセットつきの `load`/`store`（reg,reg 形式の空いている16ビット）、
   1命令の fetch-and-add。エミュレータ、アセンブラ、コンパイラ、Verilog、
   `architecture/README.md` を合わせて直す。

## Progress

- [x] 決まった結果が出る基準と、rc の前の記録
- [ ] 参照数の最適化
- [ ] レジスタ割り当て
- [ ] オフセットつきの `load`/`store`
- [ ] fetch-and-add

## 完了条件

- rc の前後の命令数の比較が、このチケットに記録されている。
- 基準のプログラムで、rc の後の命令数が rc の前を超えない。

## 関連

- `docs/design/mylang-values.md`
- `docs/implemented/profiler.md`
- MLC-025 値だけのメモリモデル
