# MYOS-021: MBIN v3（セクション表）と /apps

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Proposed | - | - | 2026-09-20 |

## Summary

実行形式にセクション表を足し（リンカが image に出している `__sections` と同じ行）、
ローダとシェルがファイルから読めるようにする。`/apps` ディレクトリを mkfs が作り、
ランチャーはそれを列挙して `@app` 行をヘッダから読む。`sys_spawn` に探索パスを足す。
`docs/design/os-app-boundaries.md` の段 4。MYOS-018（Done）とは独立。

## Background

MBIN v2（`MyLinker/src/Linker.cpp:539`, `MyKernel/src/kernel/loader.mln`）は
text / data / bss の位置しか持たない。アノテーション表は image の `__sections` 経由でしか
読めず、`boot/main.mln` がアプリを明示 import する TODO が残っている。

## Design

### Current State

- ヘッダ 32B：magic, version, entry, text_offset/size, data_offset/size, bss_size
- リンカは image 末尾に `__sections`（`[name, start, size]` 行 + 終端 + 名前）を出す
- `console.mln:206` が MFS からファイルを読んで `loader.spawn_from_buffer`

### Proposed Design

- v3：ヘッダに `sections_offset`（ファイル内）を足す。表の中身は image と同じ。`--mbin` の
  リンカが書き、ローダが読んで `__section_<name>` 相当を持つ
- MyStdLib `memory/section.mln` はそのまま（`__sections` を歩く）。シェルがファイルから
  読むための `section.from_header(buf)` を足す
- `/apps`：`tools/mkfs.py` がディレクトリを作り、`build_user_apps.py` の出力を置く。
  ランチャーは `/apps` を列挙して各ヘッダの `annotations` 行から `@app` を読み、
  レジストリに「ファイル起動」として登録（段 5 まで GUI アプリはまだ無いので、
  この段ではコンソールプログラムの `@app` 無し .mbin が並ぶだけ）
- `sys_spawn(path)`：`/` で始まらなければ `/bin`, `/apps` の順に探す

### Alternatives Considered

- ELF 互換 → リロケーション・動的リンクは要らない（VA 空間がプロセスごと）。却下
- 表を別ファイル（manifest）に → ソースの `@app` が唯一の真実であるべき。却下

### Non-Goals

- GUI アプリの .mbin 化（段 5）

## Progress

- [ ] MBIN v3（リンカ・ローダ・`obj-viewer`）
- [ ] `section.from_header`
- [ ] `/apps` と mkfs、ランチャーの列挙
- [ ] `sys_spawn` の探索パス

## Verification

```
make -C toolchain/MyLinker test-component
make qa
python3 system/MyOS/tests/apps_e2e_test.py
```

## 完了条件

- v3 の .mbin をローダが読み、`hello` が動く
- `/apps` に置いた .mbin のセクション表をシェルが読める（テスト追加）

## 関連

- `docs/design/toolchain-collected-sections.md`、MYOS-015、MYOS-022
