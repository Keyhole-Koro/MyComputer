# MyLang Diagnostic Code Registry

## 背景

MyLangCompiler の semantic diagnostics には安定した error code が付いている
（ISSUE-010 で導入）。現状の code は `semantic_walk.c` の `#define` として定義され、
以下のカテゴリ別採番になっている。

- `E00xx`: 名前解決（undefined identifier / function）
- `E01xx`: 関数呼び出し（argument count など）
- `E02xx`: return
- `E03xx`: 式の型（assignment / binary / condition）

ただし、この「先頭2桁=カテゴリ」という規則はコード上の慣習として存在するだけで、
どこにも文書化されていない。

## 問題

採番規則が暗黙のままだと、以下が起きる。

- 新しい診断を足すチケット（ISSUE-016 の `E0102`、ISSUE-019 の `E04xx` など）が、
  既存 code と衝突しないかを各自で判断せざるを得ない。
- カテゴリの境界が曖昧になり、同じ意味の診断が別カテゴリに散る。
- `mylang-lsp-semantic-diagnostics-integration.md`（ISSUE-021）の JSON 出力や docs が
  参照すべき正典（single source of truth）を持てない。
- warning code（ISSUE-012）と error code の帯の関係も未整理。

## 目標

- diagnostic code のカテゴリ採番規則を明文化する。
- 既存 code（`E0001`〜`E0303` と warning code）を一覧化する。
- 予約済みカテゴリ帯を記録する（例: `E04xx` = package、ISSUE-019）。
- 新しい code を足す時の参照先を 1 箇所に定める。
- code 定義が `semantic_walk.c` に散在している現状を、参照しやすい形へ寄せる。

## 非目標

- code の大規模な再採番（既存 code の値変更）はしない。既存値は固定する。
- code ごとの i18n / message catalog は扱わない。
- LSP quick-fix との紐付けは扱わない。

## 設計方針

### 1. カテゴリ帯を確定する

| 帯 | カテゴリ | 例 |
| --- | --- | --- |
| `E00xx` | 名前解決 | `E0001` undefined identifier |
| `E01xx` | 関数呼び出し | `E0101` arg count, `E0102` arg type（ISSUE-016） |
| `E02xx` | return | `E0201` return type mismatch |
| `E03xx` | 式の型 | `E0301`〜`E0303` |
| `E04xx` | package / import | `E0401`〜`E0403`（ISSUE-019 が予約） |

未使用帯（`E05xx` 以降）は将来カテゴリ用に空けておく。

### 2. 正典 docs を置く

`toolchain/MyLangCompiler/docs/diagnostic-codes.md`（または既存 docs 内）に一覧を置き、
新 code を足すチケットはここに追記することを規約にする。

### 3. code 定義の集約を検討する

`semantic_walk.c` に散る `#define SEMCODE_*` を、専用ヘッダ
（例: `inc/mylang/semantic/diagnostic_codes.h`）へ集約するか検討する。
必須ではないが、docs との二重管理を減らす。

### 4. warning code との関係を書く

ISSUE-012 で入った warning severity の code 帯（例: `W0xxx`）との住み分けを明記する。

## 段階移行

### フェーズ1: 現状棚卸し

- `semantic_walk.c` の `#define SEMCODE_*` を全列挙する。
- warning code を列挙する。

### フェーズ2: docs 作成

- カテゴリ表と既存 code 一覧を docs 化する。
- 予約帯（`E04xx` = package）を記録する。

### フェーズ3: 参照の一本化

- 新 code を足す各チケット（ISSUE-016 / ISSUE-019 等）から docs を参照させる。
- 任意で `#define` をヘッダへ集約する。

## 検証

1. `make -C toolchain/MyLangCompiler clean all`
2. `python3 toolchain/MyLangCompiler/tests/run_semantic_tests.py`
3. docs の code 一覧と実コードの `#define` が一致することを確認する。

## 変更ファイル（想定）

- `toolchain/MyLangCompiler/docs/*`
- `toolchain/MyLangCompiler/src/semantic/semantic_walk.c`
- `toolchain/MyLangCompiler/inc/mylang/semantic/*`（ヘッダ集約する場合）

## 完了条件

- diagnostic code のカテゴリ採番規則が docs に明文化されている。
- 既存 error / warning code が一覧化されている。
- `E04xx` = package などの予約帯が記録されている。
- 新 code を足すチケットが参照すべき正典が 1 箇所に定まっている。
