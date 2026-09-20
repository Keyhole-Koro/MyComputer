# MYOS-021: MBIN v3（セクション表）と /apps

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Done | main | claude-code:opus-5 | 2026-09-20 |

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
- `/apps` ディレクトリ → MFS は平坦（名前 15 文字、ディレクトリ無し）。「ディスク上の MBIN
  ファイルで `@app` 行を持つもの」を installed の定義にした。ディレクトリは FS 側の別チケット
- `sys_spawn` の探索パス → 平坦 FS では意味が無い（名前がそのままパス）。見送り

### Non-Goals

- GUI アプリの .mbin 化（段 5）

## Progress

- [x] ヘッダ version 2（`sections_offset`）：リンカが書き、ローダが 1 / 2 を受ける
- [x] MyStdLib `format/mbin.mln`（ヘッダ、ディレクトリ、`va_to_offset`）、`annotations.in_image()`
- [x] シェル `scan_disk()`：MFS の各 MBIN ファイルのヘッダから `@app` を読み `register_file_app`、ランチャーから `console.spawn_file`
- [x] `user/apps/demo.mln`（`@app(name = "Demo")` を持つユーザプログラム）と `app_framework_test.py` 段 8
- [x] `sys_spawn` の探索パス — 見送り（上記）

## Verification

```
make -C toolchain/MyLinker test-component
make qa
python3 system/MyOS/tests/apps_e2e_test.py
```

## 完了条件

- version 2 ヘッダの .mbin をローダが読み、`hello` が動く（apps_e2e）
- ディスク上の .mbin のセクション表をシェルが読み、ランチャーに載り、起動できる（app_framework_test 段 8）

## 関連

- `docs/design/toolchain-collected-sections.md`、MYOS-015、MYOS-022
