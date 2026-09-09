# MyLang Function Mocking Framework

## Status

In progress.

実装済み:

- `MyLangTestKit` submodule と ABI v1 marker。
- `TEST_PASS:<name>` / `TEST_FAIL:<reason>` verdict bridge。
- `MyStdLib/assert.mln` の `assert_fail` adapter。
- `Matcher<T>`、`ReturnSequence<T>`、`CallHistory<Args, Ret>`。
- `Mock<Args, Ret>`、`Rule<Args, Ret>`、Mock/Spy mode、rule hit count、
  return sequence、call history、`clear_calls()`、`reset()`。
- Linker の `--redirect <original>=<entry>`。direct-call relocationだけを
  entryへ向け、entryを定義するobjectからoriginalへのcallは維持する。
- MyLangTesterによるTestKit runtimeの自動link。
- MyLangのgeneric receiver method。receiver-bound type parameterを持つ
  `T (ref Box<T> self) get()` は、`Box<i32>` の具体化時に concrete method
  として生成・登録され、generic receiver typeをimportした側にもその
  method templateが引き継がれる。

次の実装単位は、target固有facadeをMyLangCompilerから生成し、test buildで
redirect metadataをMyLangTester経由でLinkerへ渡す縦接続である。

## Goal

production sourceを変更せず、testから関数の動作と観測方法を設定できるようにする。

```mylang
mock.of(ssd.read_block)
    .when(2, mock.any())
    .ret(-1);

fs.load(...);

mock.of(ssd.read_block)
    .verify(2, mock.any())
    .once();
```

Spyは一致するruleがあれば設定値を返し、それ以外のcallをoriginal functionへ渡す。

```mylang
mock.spy(ssd.read_block)
    .when(2, mock.any())
    .ret(-1);
```

## Responsibilities

### MyLang

mock frameworkが利用する通常の言語機能を提供する。

- generic struct / function。
- generic receiver method。
- method chain。
- function referenceとそのsignature。
- annotation。

mock、spy、test caseを言語組み込みの構文にはしない。

generic receiver methodは次の形を受理する。

```mylang
struct Box<T> {
    T value;
};

T (ref Box<T> box) get() {
    return box.value;
}
```

receiverの`Box<T>`がmethodの型parameter `T`を束縛する。
`Box<i32>`に対するcallではconcreteな`Box<i32>__get`を特殊化する。

### MyLangCompiler

- generic receiver methodをparse、特殊化、型検査する。
- function referenceからparameter / return typeを解決する。
- 通常buildでdirect-call relocationを出力する。
- mock targetの内部Args型、typed facade、test entryを生成する。
- mock target情報をtest objectのmetadataへ出力する。
- test annotationからtest manifestを出力する。

### Linker

test buildのfunction interceptionを担当する。

- function symbolへのdirect-call relocationをtest entryへ向ける。
- original function entryを保持する。
- test entryが識別できるtarget idを割り当てる。
- test objectに記録されたmock target metadataを使用する。

`--redirect <original>=<entry>` はdirect-call relocationだけを対象にする。
`<entry>` を定義するobject内の `<original>` relocation は変更しないため、
Spyのoriginal fallbackはentryから直接呼べる。

Mock / Spyのruleやhistoryは解釈しない。

### MyLangTestKit

MyLang program内で動くtest runtimeを提供する。

- `Mock<Args, Ret>`。
- `Matcher<T>`。
- `Rule<Args, Ret>`。
- `ReturnSequence<Ret>`。
- `CallHistory<Args, Ret>`。
- Mock / Spy mode、target registry、verification、lifecycle。
- verdictと`assert_fail`。

### MyLangTester

host側のtest runnerを担当する。

- `*.test.mln` discovery。
- test case selection。
- compiler / linker / emulatorの起動。
- TestKit runtimeのtest buildへの追加。
- stdin、disk、step、timer等の実行条件。
- PASS / FAIL / timeout / no-verdict / emulator errorの分類。

Mock ruleやguest-side historyは保持しない。

## Runtime model

frameworkの中心は一つのgeneric engineである。

```mylang
struct Mock<Args, Ret> {
    i32 target_id;
    i32 mode;
    Rule<Args, Ret>* rules;
    CallHistory<Args, Ret>* history;
};
```

MockとSpyは同じstateを使う。

| mode | matching rule | unmatched call |
| --- | --- | --- |
| OFF | original | original |
| MOCK | configured behavior | `TEST_FAIL:mock.unexpected` |
| SPY | configured behavior | original |

一つのtest caseは一つのemulator processで実行し、stateをcase間で共有しない。

## Typed public API

`Args`はruntime内部でcall parametersをまとめる型である。test authorには公開しない。

```mylang
// internal representation
struct __MltArgs_ssd_read_block {
    i32 block;
    i32 buffer;
};

Mock<__MltArgs_ssd_read_block, i32> __mlt_mock_ssd_read_block;
```

公開APIはtarget functionのsignatureを使い、`when`のparameterと`ret`の型を決める。

```mylang
mock.of(ssd.read_block)       // fn(i32, i32) -> i32
    .when(2, mock.any())      // Matcher<i32>, Matcher<i32>
    .ret(-1);                 // i32
```

MyLangCompilerがこの型付きfacadeをtarget signatureごとに生成する。共有state、rule、historyは
`Mock<Args, Ret>`へ集約し、facadeは次だけを行う。

- function argumentsを内部`Args`へpackする。
- matcherを該当parameter型へ揃える。
- return / answer typeをtarget return typeへ揃える。
- generic Mock engineを呼ぶ。

test authorがtarget固有のstructやfacadeを定義することはない。

## Interception contract

既存function内のdirect callをMock / Spyで観測するには、そのcallがTestKitのentryを通る必要がある。

```text
test
  -> fs_load
       -> ssd_read_block relocation
            -> test entry
                 -> TestKit state
                      OFF  -> original
                      MOCK -> rule / unexpected failure
                      SPY  -> rule / original
```

test entryはtest binaryのlink時に一度だけ決まる。テスト実行中の
`mock.of`、`mock.spy`、`reset`はruntime stateを変更するため、再linkしない。

linkerとTestKitの境界は次の情報で構成する。

```text
target_id
original_entry
call arguments
return value
```

初期対応はscalar / pointer parameter、scalar / pointer return、`void`、
通常のdirect callとする。

## Rule semantics

同じtargetへ複数ruleを登録できる。新しいruleから順に評価し、最初に一致したruleを選ぶ。

```mylang
mock.of(ssd.read_block)
    .when(mock.any(), mock.any())
    .ret(0);

mock.of(ssd.read_block)
    .when(2, mock.any())
    .ret(-1);
```

return sequenceはruleが選ばれた回数だけ進み、末尾到達後は最後の値を返す。

```mylang
mock.of(ssd.read_block)
    .when(2, mock.any())
    .ret(0)
    .then_ret(0)
    .then_ret(-1);
```

`answer`はtargetと同じsignatureのfunctionを受け取る。

```mylang
i32 fake_read(i32 block, i32 buffer) {
    return -1;
}

mock.of(ssd.read_block)
    .when(mock.any(), mock.any())
    .answer(fake_read);
```

## Verification and Spy history

```mylang
mock.spy(ssd.read_block);

fs.load(...);

mock.spy(ssd.read_block)
    .verify(2, mock.any())
    .once();
```

verification operation:

- `times(n)`
- `once()`
- `never()`
- `at_least(n)`
- `at_most(n)`
- `returned(matcher)`
- `called_real()`

call recordはparameters、return value、path、complete flagを保持する。

```mylang
i32 count = mock.spy(ssd.read_block).call_count();
i32 block = mock.spy(ssd.read_block).call(0).arg(0);
i32 result = mock.spy(ssd.read_block).call(0).ret();
MockCallPath path = mock.spy(ssd.read_block).call(0).path();
```

pathは`REAL`、`RET`、`ANSWER`、`UNEXPECTED`のいずれかである。

## Lifecycle

```mylang
mock.clear_calls(ssd.read_block);
mock.reset(ssd.read_block);
```

- `clear_calls`: rulesを維持し、historyとrule hit countをclearする。
- `reset`: expectationをverifyし、rules、history、modeをclearする。
- test epilogue: `verify_all()`、cleanup、PASS出力、halt。

`clear_calls`はreturn sequence cursorを維持する。

## Storage

TestKit runtimeはcaller-owned fixed-capacity storageを使う。

- rules: targetごとに8。
- calls: targetごとに32。
- return values: ruleごとに8。

capacity超過は既存recordを捨てず、`TEST_FAIL:mock.capacity`を出す。

## Verdict protocol

| emulator output/state | MyLangTester result |
| --- | --- |
| `TEST_PASS:<name>` | PASS |
| `TEST_FAIL:<reason>` | FAIL |
| step limit | TIMEOUT |
| verdictなしでhalt | FAIL: no verdict |
| emulator non-zero exit | ERROR |

## Annotation

```mylang
@test("read failure is surfaced")
@step(10000000)
void read_failure_is_surfaced() {
    mock.of(ssd.read_block)
        .when(mock.any(), mock.any())
        .ret(-1);

    fs.init();
}
```

`stdin`、`step`、`timer_interval`、`disk`、`skip`はtest metadata annotationとする。
MyLangCompilerがmanifestを出力し、MyLangTesterがbuild / runへ使用する。

## Implementation order

1. MyLang generic receiver method。
2. TestKit `Rule<Args, Ret>` / `Mock<Args, Ret>` / verification。
3. scalar function一つでtyped public APIを縦通しする。
4. linker test interception entryとoriginal fallback。
5. strict Mock、pure Spy、partial Spy。
6. `void`、pointer matcher、answer。
7. annotation manifestとmultiple test cases。
8. existing Python runner migration。

## Acceptance criteria

- test authorはtarget固有のArgs / Mock structを定義しない。
- `mock.of(target).when(...).ret(...)`を通常のmethod chainとして記述できる。
- matcher、return、answerの型をtarget signatureに対して検査する。
- Mock unmatched callはreason付きで失敗する。
- Spy unmatched callはoriginal functionを実行する。
- Spyはparameters、return、path、call countを記録する。
- Mock / Spy / resetを一つのtest binaryで切り替えられる。
- test実行中のconfiguration変更で再linkしない。
- production buildはTestKit runtimeとtest entryを含まない。
- 各test caseは独立したemulator processで実行する。

## Initial exclusions

- aggregate / array by-value parameter。
- aggregate return。
- variadic function。
- function pointerを経由したindirect call。
- cross-target global call order。
- pointer先memoryの自動snapshot。

## Related

- [MLT-002](MLT-002_mylang-test-framework.md)
- [MLT-001](MLT-001_mylang-test-diagnostics-strategy.md)
- [MLC-014](../completed/MLC-014_mylang-function-signature-type-checking.md)
