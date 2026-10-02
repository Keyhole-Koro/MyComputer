# MLC-020: ABI透過な不透明newtype

| Status | Branch | Agent | Updated |
| --- | --- | --- | --- |
| Proposed | - | codex:gpt-6 | 2026-10-02 |

## Summary

`Pid`、`Fd`、`NodeId`、`ChannelId`などを相互代入できない型にしながら、基底整数と同じ
1ワードABIで渡せる不透明newtypeを追加する。

## Background

システム境界の識別子は現在ほぼすべて `i32` である。異なるIDを渡しても型検査を通り、
structで包むと現在のaggregate ABIでは1ワード整数と同じ呼び出し規約にならない。
通常の`typedef`は別名なので、識別子同士の混同を防げない。

## Design

### Proposed Design

宣言は次の形にする。

```mylang
export newtype Pid = i32;
export newtype NodeId = u16;
```

newtypeはnominal type identityを持ち、値の幅、alignment、引数・戻り値のABIは基底型と同じにする。
生成と取り出しは明示的に行う。

```mylang
Pid pid = Pid(raw);
i32 raw = pid.raw();
```

比較は同じnewtype同士だけ許可する。算術、bit演算、別newtypeとの変換は基底値を明示的に
取り出した場合だけ許可する。package export/import metadataにnominal identityを含める。
古い`i32`識別子APIは残さず、契約から内側へ段階的に移行する。

### Alternatives Considered

- `typedef`は構造的に基底型と同じため目的を満たさない。
- 1field structは現行aggregate ABIで隠しpointer渡しになり、syscallやwire layoutを変えるため採用しない。
- payload enumはtag分の記憶領域が増える。

### Non-Goals

- 単位付き数値の自動演算。
- 任意のaggregateをABI透過にする仕組み。

## Progress

- [ ] lexer・parser・ASTへnewtype宣言を追加
- [ ] nominal identityをsemantic typeとmodule metadataへ追加
- [ ] constructor、raw取り出し、比較、cast規則を実装
- [ ] codegen data layoutと呼び出しABIを基底scalarへ委譲
- [ ] Pid、Fd、NodeId、ChannelIdを契約から移行
- [ ] grammarとLSPを更新

## Verification

```bash
make -C toolchain/MyLangCompiler test-component
make -C toolchain/MyLangCompiler test-e2e
make qa
```

## 完了条件

- 同じ基底型を持つ異なるnewtypeの代入・引数渡しがsemantic errorになる。
- newtypeのsizeof、global layout、引数、戻り値が基底scalarと同じになる。
- 主要なシステム識別子APIから裸の`i32`がなくなる。

## 関連

- MLC-003 MyLang Package Symbol Resolution
- MLC-005 MyLang Typed Intermediate Representation

