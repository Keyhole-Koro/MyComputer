# MyLang LSP Semantic Diagnostics Integration

## 背景

MyLang には `MySyntaxEngine` と `mylang-syntax-check` があり、LSP 向けの構文診断や token stream の
土台が存在する。一方、MyLangCompiler 側の semantic diagnostics は compiler 実行時に強くなってきている。

今後、LSP で開発体験を上げるには、syntax-level diagnostics だけでなく semantic diagnostics も
editor に出したい。

ただし、compiler parser、syntax engine、LSP server が別々に似た情報を持つと、診断の差異や
token classification のズレが起きやすい。

## 問題

editor 上で次を早く見たい。

- 未定義 identifier
- 未定義 function
- argument count / type mismatch
- return type mismatch
- assignment mismatch
- borrow / move error
- warning diagnostics

現状では、compiler 実行時には見えるが LSP には出ない、または syntax check と compiler 診断の
形式が違う、という状態になりやすい。

## 目標

- compiler semantic diagnostics を LSP が消費しやすい JSON 形式で出す。
- diagnostic code、severity、range、message を安定化する。
- syntax diagnostics と semantic diagnostics の出力形式を揃える。
- LSP server から lightweight に semantic check を呼べるようにする。
- editor 上の diagnostic が compiler CLI と同じ意味になるようにする。

## 非目標

- full incremental compiler は最初は作らない。
- project-wide semantic analysis は後回しにする。
- completion / rename / go-to-definition は別チケットに分ける。

## 設計方針

### 1. Compiler に diagnostics JSON output を追加する

候補 CLI:

```text
mlc --diagnostics-json input.mln
```

出力例:

```json
{
  "diagnostics": [
    {
      "code": "E0001",
      "severity": "error",
      "range": {
        "start": { "line": 3, "character": 12 },
        "end": { "line": 3, "character": 15 }
      },
      "message": "undefined identifier 'foo'"
    }
  ]
}
```

line / character は LSP に合わせて 0-based にするか、CLI と同じ 1-based にするかを明記する。
方針は JSON/LSP では 0-based、human CLI では 1-based で確定する。
この base 差は本チケットの JSON 変換層で吸収し、
semantic stage 内部（ISSUE-016〜019 が生成する診断）は従来通り 1-based の
source location を保持したままとする。診断メッセージ本文の index 表記
（例: `parameter 1`）も 1-based のままとし、変換対象は range の line/character のみ。

### 2. Syntax check と format を揃える

`mylang-syntax-check` 側も同じ diagnostic object に寄せる。
source は `syntax` / `semantic` などで区別できるようにする。

### 3. LSP server は subprocess から始める

初期段階では LSP server が compiler を subprocess として呼ぶ方式でよい。
性能問題が出てから daemon / library 化を検討する。

### 4. Range quality を保つ

semantic diagnostics は AST location に依存する。
AST node の `line` / `col` / `end_line` / `end_col` が欠けている箇所は、LSP integration 前に
fixture で埋める。

ただし、各診断を新規に足すチケット（ISSUE-016〜019）側でも、その診断が指す AST node に
range が付いていることを succeed / fail fixture で担保する責務を持つ。本チケットは
「既存診断の range が LSP に届くこと」を保証するが、新診断の range 品質そのものは
各診断チケットの完了条件に含める（range の穴埋めを本チケットに一括集約しない）。

## 段階移行

### フェーズ1: Compiler JSON diagnostics

- `mlc --diagnostics-json` を追加する。
- semantic fail fixtures で JSON snapshot を確認する。

### フェーズ2: Syntax diagnostics format alignment

- `mylang-syntax-check` の diagnostics output を同じ schema に寄せる。
- syntax / semantic の source field を追加する。

### フェーズ3: LSP subprocess integration

- save / change 時に semantic diagnostics を出す。
- timeout と cancellation を入れる。

### フェーズ4: Project-aware diagnostics

- import file を含む semantic check。
- package symbol resolution と連動する。

## 検証

1. `make -C toolchain/MyLangCompiler all`
2. `python3 toolchain/MyLangCompiler/tests/run_semantic_tests.py`
3. `python3 toolchain/MyLangCompiler/tests/run_syntax_check_tests.py`
4. LSP fixture で undefined identifier が editor diagnostic になることを確認する。

## 変更ファイル（想定）

- `toolchain/MyLangCompiler/src/driver/*`
- `toolchain/MyLangCompiler/src/semantic/semantic_error.c`
- `toolchain/MyLangCompiler/inc/mylang/semantic/semantic_internal.h`
- `toolchain/MyLangCompiler/tests/*`
- `toolchain/MySyntaxEngine/*`
- LSP server 側ファイル

## 完了条件

- semantic diagnostics を JSON で取得できる。
- JSON diagnostic に code / severity / range / message が含まれる。
- LSP が semantic error を editor diagnostic として表示できる。
- CLI human-readable diagnostics は従来通り使える。
