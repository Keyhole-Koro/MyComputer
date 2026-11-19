# エミュレータ（MyEmulator）

## emulator.timer.clock  タイマーの時計
レジスタ・runtime/MyEmulator/src/machine/timer.rs の clock
レジスタ：0x24000088
フィールド tick 数（31–8）：それまでの tick。止めていた間の分も数える
フィールド 進み（7–0）：今の tick の中でどこまで進んだか（256 分の何）

1 tick を 256 に刻んだ時計。時刻を書くと、その時刻の後の最初の tick まで割り込みを止める（[[kernel.idle-hold]]）。0 を書けば毎 tick。

![[fig.clock-word]]

## fig.clock-word  時計の 1 語の中身
図・runtime/MyEmulator/src/machine/timer.rs の clock
図：figures/fig.clock-word.svg

上位 24 ビットが tick 数、下位 8 ビットが今の tick の進み。tick は 2^24 で一周する（既定の 1 ms tick で約 4.6 時間）ので、[[kernel.cpu-time]] は前回からの差で数える。
