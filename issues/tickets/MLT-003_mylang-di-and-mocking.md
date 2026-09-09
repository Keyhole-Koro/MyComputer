# MyLang Function Mocking Framework

## Status

In progress.  The ABI-v1 verdict bridge and the first compiler-facing generic
building blocks (`Matcher<T>`, `ReturnSequence<T>`, and `CallHistory<Args,
Ret>`) are implemented in `MyLangTestKit` and run in MyEmulator.  The generic
`Mock<Args, Ret>` / rule engine, typed hook generation, and stable link-time
interception backend remain to be implemented.

## 結論

MyLang の関数・メソッドを test build でinterceptし、次の API を提供する。

```mylang
mock.of(ssd.read_block)
    .when(2, mock.any())
    .ret(-1);

// subject execution

mock.of(ssd.read_block)
    .verify(2, mock.any())
    .once();
```

`.ret()` を採用する。`.return()` は MyLang の `return` keyword と衝突し、`.returns()` より短い。

## 設計判断

1. mock target は型が解決できる MyLang function / method とする。
2. `mock.of(target)` から target signature を推論する。利用者は target ごとの Mock struct を書かない。
3. 共通の rule / matcher / call history / return sequence は generics で実装する。
4. `Mock<Args, Ret>`、rule、matcher、history、verification は MyLang generics / methods として
   TestKitに実装する。targetごとのbuild supportが`Args` packingとhookを提供する。
5. test buildのlink時に対象symbolへのdirect call relocationを固定hookへ向ける。
6. detour は API を早期検証する prototype backend とする。
7. 一つの test case は独立した emulator process で実行し、mock state を case 間で共有しない。
8. test body の正常 return を PASS とし、その前に自動 verification / cleanup を実行する。
9. Mock と Spy は同じ `Mock<Args, Ret>` engine を使い、unmatched call の方針だけを変える。
10. guest側の test runtime は `toolchain/MyLangTestKit` submodule が所有する。`MyLangTester` は host側の
    discovery / build / emulator runner に限定する。

## Component ownership

`MyLangTestKit` はmockだけの小さなライブラリではなく、MyLang program内で動くtest runtimeとして最初から
独立させる。repository/pathは次で固定する。

```text
github.com/Keyhole-Koro/MyLangTestKit
toolchain/MyLangTestKit
```

```text
MyLangCompiler  -- typed hook/support generation ----------->  MyLangTestKit
       ^                                                        (guest runtime)
       |                                                              |
       | test plan / ABI                                               | TEST_FAIL, mock state
       |                                                              v
MyLangTester   -- build / run / verdict ----------------------> MyEmulator
       (host runner)
```

- `MyLangTestKit`: genericな`Mock<Args, Ret>`、matcher/rule/history、verification、verdict、test lifecycle、
  `assert_fail` adapter、prototype用detour supportを持つ。production buildへは入らない。
- `MyLangCompiler`: signature validationと、target固有のArgs packing / typed hook / real-call thunkを生成する。
  MyLangTestKitのsourceを直接参照せず、定義済みABIに対してcodeを生成する。
- `MyLangTester`: `.test.mln` discovery、plan作成、TestKitのsource追加、build/emulator実行、linkerへ
  interception targetを渡すこと、serial verdictの分類を持つ。guest-side mock stateは持たない。
- `MyStdLib`: productionでも有用な`assert_*`だけを持つ。`extern assert_fail`の実装はTestKitがtest buildへ
  提供する。

TestKitの利用APIはtest buildで自動prelude化するため、test sourceは`import mock ...`を書かない。物理配置は
利用者へ露出しない。

```text
MyLangTestKit/
  runtime/
    mock.mln
    matcher.mln
    rule.mln
    history.mln
    lifecycle.mln
    verdict.mln
  internal/
    detour.masm             # prototype期間のみ
  tests/
```

### ABI version contract

CompilerとTestKitを別submoduleにするため、implicitなsymbol名の一致だけには依存しない。test planに
`testKitAbi: 1`を記録し、compiler generated supportは`__mlt_require_abi_v1`を参照する。TestKitは同symbolを
exportし、異なるABIを組み合わせた場合はlink errorにする。planのtarget descriptorとABI versionはcaseごとの
build artifactに保存する。

ABI v1は次だけを固定する。

- `TEST_PASS:<name>` / `TEST_FAIL:<reason>` verdict format。
- `assert_fail(char*)` adapter。
- generated helperが呼ぶinstall/real/registry entrypointのcalling convention。
- `MockCallPath` のnumeric values。

public fluent syntaxやgeneric runtime implementationはABIそのものではなく、compiler/TestKitを同じroot commitで
pinして更新する。

## Generics で消せるもの、消せないもの

公開 API は概念的に `Mock<F>` を使う。`F` は target の function signature である。

```mylang
// mock.of() が返す型の概念表現
Mock<fn(i32, i32) -> i32> *read_mock;
```

次は generic runtime に一度だけ実装できる。

```mylang
Matcher<T>
Rule<Args, Ret>
Call<Args>
ReturnSequence<Ret>
MockState<Args, Ret>
```

一方、通常の generics は function signature `F` を引数列と戻り値へ分解したり、任意個の引数を
tuple に詰めたりできない。reflection、variadic generics、function-type decomposition がないため、
target ごとに次の薄い glue は必要になる。

```mylang
// compiler-generated, source-level API には現れない
struct SsdReadBlockArgs {
    i32 block;
    i32 buffer;
};

MockState<SsdReadBlockArgs, i32> __mock_ssd_read_block;
```

生成されるのは target ごとの公開 Mock struct ではなく、`Args`、引数 packing、dispatcher、実関数への
fallback thunk だけである。generics は mock engine の重複を消し、compiler generation は signature
の違いを橋渡しする。

### Mock API

`mock` packageのfunctionとreceiver methodでMockを構成する。`Mock<Args, Ret>` がrule、sequence、
historyを保持し、targetごとのbuild supportがArgs descriptorを提供する。

```mylang
// `ReadBlockArgs` はtarget signatureから生成されるinternal type。
Mock<ReadBlockArgs, i32> read = mock.of(ssd.read_block);
read.when(ReadBlockArgs { block: 2, buffer: mock.any() })
    .ret(-1)
    .then_ret(-2);
```

`Mock<Args, Ret>` はtarget descriptorを保持する。descriptorはtest planが割り当てたtarget id、
hook address、real entry address、state storageへの参照から成る。通常のmethod型検査で`ret`、
`answer`、matcher、verificationの型を検査する。関数signatureをArgs / Retへ分解する機能は不要で、
target固有のArgs descriptorを生成するbuild supportが橋渡しする。

対象の有効化は`mock.of(target)` / `mock.spy(target)` が実行された時点で行う。sourceにchainが
存在するだけでは有効化しない。`verify(...)` / `call(...)` はlookupだけを行い新規有効化しない。
未有効化targetの観測は `target was not activated before observation` としてfailureにする。
同一targetのMock / Spy mode競合はruntimeでfailureにする。

## 利用 API

### 全呼び出しを固定値へ置換

```mylang
mock.of(clock.now)
    .ret(1234);
```

全引数に `any` を指定した `when(...)` と同義だが、単純なケースでは省略できる。引数ゼロの関数では
`when()` と同義になる。

### void function

初期版から scalar return に加えて `void` target を扱う。`void` では引数なしの `.ret()` を使う。

```mylang
mock.of(serial.putc)
    .when('A')
    .ret();
```

`void` target に `.ret(value)`、非 `void` target に `.ret()`、`void` rule に `.then_ret(...)` を使うと
compile error にする。runtime は `MockStateVoid<Args>` specialization を持ち、call record には戻り値を
保存しないが、経路と `complete` は保存する。aggregate return は引き続き初期版の対象外とする。

### 条件付き return

```mylang
mock.of(ssd.read_block)
    .when(2, mock.any())
    .ret(-1);
```

同じ target に複数 rule を登録できる。最後に登録した一致 rule を採用する。これにより broad な
default rule の後から特定条件を上書きできる。

### 連続 return

```mylang
mock.of(ssd.read_block)
    .when(mock.any(), mock.any())
    .ret(0)
    .then_ret(0)
    .then_ret(-1);
```

列を使い切った後は最後の値を繰り返す。

### Answer callback

```mylang
i32 fake_read(i32 block, i32 buffer) {
    // test-specific behavior
    return -1;
}

mock.of(ssd.read_block)
    .when(mock.any(), mock.any())
    .answer(fake_read);
```

`answer` は target と完全に同じ signature を要求する。型や引数数が違えば compile error にする。

### Verification

```mylang
mock.of(ssd.read_block).when(2, mock.any()).ret(-1);
mock.of(ssd.write_block); // strict modeで有効化。呼ばれたらその場で失敗

// subject execution

mock.of(ssd.read_block)
    .verify(2, mock.any())
    .times(1);

mock.of(ssd.write_block)
    .verify(mock.any(), mock.any())
    .never();
```

初期版の terminal operation は次とする。

- `times(n)`
- `once()`
- `never()`
- `at_least(n)`
- `at_most(n)`

setup 時に期待回数まで宣言する場合は rule へ連結できる。

```mylang
mock.of(ssd.read_block)
    .when(2, mock.any())
    .ret(-1)
    .expect_times(1);
```

`expect_times` は test epilogue の `verify_all()` が検査する。単なる stub は「必ず呼ばれる期待」に
暗黙変換しない。

### Rule と count の厳密な意味

- ruleは登録順を持ち、呼び出し時に新しいruleから最初の一致を選ぶ。後から追加したruleは将来の
  呼び出しだけに影響し、既存historyを書き換えない。
- `.ret(a).then_ret(b)` は、そのruleが選択された回数だけcursorを進める。他ruleやunmatched callは
  sequenceを消費しない。末尾到達後は最後の値を返し続ける。
- `.expect_times(n)` は、そのruleが実際に選択されたhit数を検査する。同じmatcherを持つ、より新しい
  ruleに奪われたcallは数えない。
- `.verify(matchers...).times(n)` はruleとは独立にcall historyをfilterし、経路を問わず一致件数を数える。
  `.returned(...)` と `.called_real()` はこのfilterへ追加条件を加える。
- strict unmatched callも診断用に `UNEXPECTED, complete = 0` としてrecordを予約してからfailする。
  通常のverificationへ戻ることはないが、runnerが最後のcallを表示できる。

negative count、容量を超える `expect_times`、空のreturn sequenceはcompile errorにする。countがruntime
式の場合は登録時に検査してfailする。

### Mock と Spy

`mock.of(target)` は strict mock とする。rule に一致しない呼び出しは、引数を含む
`TEST_FAIL:unexpected call <target>(...)` を出す。外部 I/O を意図せず実行しない安全側の既定である。

```mylang
mock.of(ssd.read_block)
    .when(2, mock.any())
    .ret(-1);

// block 2 は -1。それ以外は unexpected call。
```

`mock.spy(target)` は全呼び出しを記録し、rule に一致しない呼び出しを original function へ流す。
rule を一つも登録しない pure spy も許可する。

```mylang
mock.spy(ssd.read_block);

fs.init();

mock.spy(ssd.read_block)
    .verify(mock.any(), mock.any())
    .at_least(1);
```

一部だけ置換する partial spy:

```mylang
mock.spy(ssd.read_block)
    .when(2, mock.any())
    .ret(-1);

// block 2 は -1。それ以外は本物の ssd.read_block。
```

`mock.of` と `mock.spy` は同じ target registry entry を返す。一つの test case 内で同じ target を
両モードに登録した場合は設定ミスとして即時失敗にする。同じモードでの再取得は idempotent とし、
stubbing と verification の双方から利用できる。

### Lifecycle と reset

一つの test case 内で Arrange / Act を複数回行えるよう、次を提供する。

```mylang
mock.clear_calls(ssd.read_block); // rulesは維持し、履歴とrule hit countを0へ戻す
mock.reset(ssd.read_block);       // expectationを検査後、rules/history/modeを消してslotを0へ戻す
```

`clear_calls` は return sequence の cursor を戻さない。既に消費した stub behavior が巻き戻ると、観測の
checkpoint と動作の reset が混ざるためである。`expect_times` は維持され、clear 後の hit count に対して
epilogue で検査される。

`reset` は未達 expectation を黙って捨てない。target 単位で先に verify し、成功した場合だけ uninstall
する。test epilogue は全 target を verify した後、内部の unchecked cleanup で slot を0にする。
assertion や unexpected call が即時 halt した場合は cleanup されないが、case ごとに emulator process を
分離するため次 case へ状態は漏れない。

### Spy の記録内容

call record は次を持つ。

- 呼び出し時の引数値。pointer / ref は address identity を記録し、指し先を copy しない。
- scalar return value。
- `void` target では return value なし。
- `REAL`, `RET`, `ANSWER`, `UNEXPECTED` のどの経路を選んだか。
- return まで到達したか。real function が halt した場合は incomplete のままになる。

初期版のverificationは引数、回数、保存済みscalar return、実行経路を対象とする。

```mylang
mock.spy(ssd.read_block)
    .verify(mock.any(), mock.any())
    .returned(0)
    .called_real()
    .once();
```

`.returned(...)` は非`void` targetだけに許可し、`.called_real()` は`REAL` pathのrecordだけを数える。
条件はANDで合成し、上の例は「return 0かつoriginalを呼んだcallが1回」を意味する。

pointer が指す buffer の before/after snapshot は自動取得しない。必要なテストは `answer` または
呼び出し後の通常 assertion で検査する。

`char*` の `str_eq` は rule 選択時にはその場で評価する。call history は address しか保持しないため、
verification 時の `str_eq` はその address を再度読む。literal や test 終了まで有効な buffer に限定して
使い、寿命や内容変更が問題になる場合は `answer` 内で値を検査・copy する。暗黙の memory snapshot は
行わない。

### Spy call inspection

ArgumentCaptor相当は、target固有のArgs structを公開せず、typed `Mock<Args, Ret>` methodと
generated accessorで提供する。

```mylang
i32 count = mock.spy(ssd.read_block).call_count();
i32 first_block = mock.spy(ssd.read_block).call(0).arg(0);
i32 first_buffer = mock.spy(ssd.read_block).call(0).arg(1);
i32 first_return = mock.spy(ssd.read_block).call(0).ret();
MockCallPath first_path = mock.spy(ssd.read_block).call(0).path();
```

`call(index)` はtarget内のintercept順で0始まりとし、index自体はruntime expressionを許す。`arg(index)` の
indexは戻り型を決めるためcompile-time constantを要求し、範囲外はcompile errorにする。compilerはたとえば
`.call(i).arg(0)` を `__mlt_call_t0_arg0(i)` へloweringし、正確なparameter typeを返す。

call indexのruntime範囲外、未有効化target、不完全recordの`.ret()`はreason付きfailureにする。`void`
targetでは`.ret()` inspectionをcompile errorにする。pointer/ref引数から得られるのはcall時のaddressであり、
指し先snapshotではない。`MockCallPath` はtest preludeが自動提供し、`path()` は `MOCK_CALL_REAL`,
`MOCK_CALL_RET`, `MOCK_CALL_ANSWER` のいずれかを返す。
strict unexpectedは即時haltするため通常はinspectionへ到達しない。

inspectionはSpyだけでなく同じengineを使うstrict Mockにも許可する。ただし`mock.of` / `mock.spy`のmodeは
有効化時と一致しなければならず、inspection自体はtargetを有効化しない。cross-targetのglobal call orderは
初期版では扱わない。

### Original call

test-build dispatcher は real implementation address を保持するため、answer から original を呼べる。
API は再帰的な `mock.of()` lookup を避けるため、生成された typed handle を callback へ渡す形式にする。
初期版では複雑さを避け `answer` と automatic fallback までとし、明示 `call_real` は後続で追加する。

### 再帰とnested call

Spy dispatcher が original を選んだ現在の一呼び出しだけを `$real` symbol へ送る。real body から
同じ公開関数を再帰呼び出しした場合、その子呼び出しは再び dispatcher を通り、別 call として記録する。
これは関数入口を観測する Spy として一貫した動作である。

同じ target の Mock / Spy が `answer` 実行中に公開 target を直接呼ぶと再び同じ rule に一致し得るため、
初期版では runtime の target-local `answer_active` guard で検出し、`reentrant mock call` として失敗させる。
compiler が callback body の全経路を証明する必要はない。後続の typed `call_real` は現在の一段だけを
`$real` へ送るため、この再入を起こさない。

### Method target

初期版は通常 function を対象とする。method は compiler 内では receiver を第一引数にした関数へ
lowering されるので、後続では同じ engine を利用できる。

```mylang
// 全 instance の method implementation を Spy
mock.spy(User.rename)
    .verify(mock.any(), mock.str_eq("alice"))
    .once();

// 一つの instance だけを対象にする bound Spy
mock.spy(user.rename)
    .verify(mock.str_eq("alice"))
    .once();
```

type method target は receiver matcher を明示引数として扱う。bound method target は compiler が
receiver identity matcher を暗黙追加し、他 instance の呼び出しを original へ流す。初期対応は
pointer / `ref` receiver に限定し、move を伴う value receiver は対象外とする。

## Matchers

最初の対応範囲は次に限定する。

- integer / enum: literal/expressionによる implicit `eq`、`mock.eq`, `mock.ne`, `mock.any`
- pointer identity: `same`, `is_null`, `not_null`, `any`
- `char*`: `str_eq`
- custom predicate: `matches`

```mylang
// 2 は mock.eq(2) へ暗黙変換される
mock.spy(ssd.read_block)
    .verify(2, mock.any())
    .once();
```

matcher の `T` は通常のmethod parameter型から解決できる場合に推論する。解決できない場合は
`mock.any<i32>()` のように明示する。将来の`when(2, mock.any())` sugarはtarget parameter型から
型引数を補うが、runtime APIの前提にはしない。pointer expressionは意味が曖昧なので暗黙`eq`にせず、
address identityは`mock.same(ptr)`、文字列内容は`mock.str_eq(text)`を明記する。

implicit `eq` にできるexpressionは、通常のassignment規則でparameter型へ入れられるscalar/enumに限る。
`mock.matches(predicate)` のpredicateは `i32 predicate(T actual)` を要求し、0をfalse、非0をtrueとする。
predicateがhaltした場合はそのtestもhaltし、matcherの副作用順には依存しないものとする。

matcher は tagged value として表現し、`INT_MIN` などの magic sentinel は使わない。引数ごとに
`Matcher<T>` を生成し、matcher の型や個数が target signature と違えば compile error にする。

struct by-value、array、aggregate return、variadic function は初期版の mock 対象外とし、compiler が
明確な diagnostic を出す。scalar / pointer return と `void`、pointer / ref 経由の struct は最初から
許可する。

## Target eligibility

初期版でmock/spyできるtargetは、build graph内の`.mln` sourceに本体を持ち、resolverが一意のlink symbolと
concrete signatureを解決できる通常functionに限定する。importされたexport functionとtest source内の
functionは対象にできる。

次は初期版ではcompile errorにする。

- declarationだけのextern、builtin、intrinsic、`.masm`でのみ定義されたsymbol。
- generic functionそのもの、およびgeneric instantiation。後者はinstantiation固有link nameとownershipを
  planに表現してから追加する。
- function literal、closure、実行時function pointer value。mockはcallable valueではなく定義symbolを
  interceptする。
- aggregate/array by-value parameter、aggregate return、variadic function。
- unresolved symbol、および別moduleのprivate symbol。private functionをtestのためだけに公開へ変えない。

対象外targetには、たとえば
`cannot mock serial_write_raw: target has no MyLang function body in the build graph` のように理由を示す。
method targetは前述のとおり通常functionの安定版完了後に追加する。

## Stable backend: link-time interception

test buildのlink時に、test planで指定されたtargetへの**direct call relocation**を、targetごとの固定hook
symbolへ解決する。hookのmachine codeは
test binary作成時に一度だけ生成され、その後のMock / Spy / rule切替えはMyLangTestKitのruntime stateだけを
変更する。ruleごと、test中のconfiguration変更ごとに再linkしない。

```text
normal build
  fs_load -> ssd_read_block

test build (link redirect)
  fs_load -> __mlt_hook_t0
                 |
                 +-- state OFF  -> ssd_read_block (real address)
                 +-- matching rule -> configured return / answer
                 +-- Spy unmatched -> ssd_read_block (real address)
                 +-- Mock unmatched -> TEST_FAIL
```

`fs_load`や他callerのsourceへif文を足さない。linkerが`ssd_read_block`を参照するrelocationをhook addressへ
付け替えるため、同じtargetを直接callする全moduleから観測できる。hookは引数を`Args`へpackし、call開始を
historyへ記録してTestKit rule engineを呼ぶ。`REAL` pathだけがlinkerの保存したoriginal entry addressへ
tail call / typed callを行い、戻り後にreturn valueとcompleteをhistoryへ記録する。

```masm
__mlt_hook_t0:                    ; i32 ssd_read_block(i32 block, i32 buffer)
    ; R5/R6をArgsへpackし、TestKitのstateを照会
    call __mlt_dispatch_t0
    ; decision = RET / ANSWER / REAL / UNEXPECTED
    ; RET/ANSWERはconfigured valueを返す
    ; REALだけsaved real addressへ跳ぶ
```

linkerの責務はsymbol relocationのredirectとoriginal entry addressの保存だけに留める。signatureを知る必要が
あるArgs packing、return ABI、TestKit call、条件分岐はcompilerまたはgenerated test-support moduleがtyped hook
として生成する。これによりlinkerはtarget固有のMock semanticsを持たない。

`mock.of` / `mock.spy` はhookをinstallするのではなく、既存hookが読むtarget stateをOFF / MOCK / SPYへ変更する。
`reset` とtest epilogue cleanupはOFFへ戻す。したがってsetupより前のboot code等は観測されず、一つのbinary内で
複数のArrange / Act / Verify checkpointを安全に実行できる。

MyLangTesterはcaseごとのtest planをbuild toolchainとlinkerへ渡す。planにはcanonical target id、link name、
signature、hook symbolを含める。生成内部symbolはlink nameを連結せずplan-local idを使い、例えば
`__mlt_hook_t0`、`__mlt_dispatch_t0`とする。target集合が変わるときだけtest binaryを再build/relinkする。

初期対応は通常のMyLang direct callに限る。実行時function pointer値、extern/builtin、`.masm`のみで定義された
symbol、inlining後にdirect relocationを持たないcallはinterceptionしない。self-recursionはhookを再通過し、
別recordとして扱う。

original addressを保持するためSpyのautomatic fallbackが安全である。同じ固定hookでstrict Mock、pure Spy、
partial Spyを切替えられる。target signatureからArgs packingとreturn ABIを型どおりに生成する。

## Prototype backend: detour

最終 API を compiler/linker 変更より先に検証するため、初期 prototype は実測済みの detour を使える。
target entry の先頭一語を fake dispatcher への `jmp` に置換する方式である。

制約:

- test build 限定。
- writable text が必要。
- inline 後の call は捕捉できない。
- original call-through には安全な trampoline が必要。
- nested patch の restore order を管理する必要がある。

したがって detour prototype が検証するのは strict Mock の `.ret` / `.answer` / call recording までとする。
pure Spy、partial Spy、`REAL` path recording は安全な original call-through を持つ link-time interception backend
から開始する。prototype 用だけの不完全な trampoline は作らない。

`mock.of(...).when(...).ret(...)` はbackend共通のAPIとする。link-time interception backendの完成後、
detour backendは削除する。ISA opcode encoding は MyStdLib ではなく
MyLangTestKitのinternal runtime内に閉じ込める。

## Mock storage

heap allocator 自身を mock/test できるよう、mock runtime は heap allocation に依存しない。target
ごとの生成 state に固定長 storage を持つ。

- rule: target ごとに 8 件
- recorded calls: target ごとに 32 件
- return sequence: rule ごとに 8 件

上限超過時は古い情報を捨てず、reason 付き `TEST_FAIL` で即時停止する。容量は test metadata で
上書き可能にする。

dispatcher の処理順を固定する。

1. capacity と target-local `answer_active` を検査する。
2. call slot を予約し、引数と `complete = 0` を記録する。
3. rule を新しい順に評価する。
4. `RET`, `ANSWER`, `REAL` の経路を決めて実行する。strict unmatched は理由付きで停止する。
5. 正常 return した場合だけ戻り値、経路、`complete = 1` を記録する。
6. caller へ同じ戻り値を返す。

rule matcher と verification matcher は副作用を持たせない契約とする。初期版ではcompilerがpredicateの
purityを証明しない。return sequence の cursor はruleごとに保持する。verificationはcall historyを
変更しないため、同じ条件を複数回検査できる。
`returned(...)` は `complete = 1` の record だけを対象とする。

失敗メッセージは少なくとも target link name、期待回数、実回数、scalar argument values を含める。
pointer は address を表示し、任意 memory の自動 dereference はしない。

machine-readable prefixを固定する。

```text
TEST_FAIL:mock.unexpected target=ssd.read_block link=ssd_read_block args=[2,0x00102000]
TEST_FAIL:mock.verify target=ssd.read_block expected=exactly:1 actual=0
TEST_FAIL:mock.expect target=ssd.read_block rule=1 expected=1 actual=0
TEST_FAIL:mock.capacity target=ssd.read_block storage=calls limit=32
TEST_FAIL:mock.reentrant target=ssd.read_block path=answer
```

`verify_all()` はplan-local target id順、同一target内はrule登録順で検査し、常に同じ最初の失敗を返す。
compile-time diagnosticにはtest名、source位置、targetのcanonical signatureを含める。

初期版は single CPU / single-threaded test を前提にする。IRQ handler から mock target を呼ぶ場合は
設定完了後に IRQ を有効化し、call history の並行更新を行わない。preemptive test が必要になった
時点で critical-section hook を追加する。

## Test discovery と生成

現行 `TestParser.java` の文字列解析を mock syntax まで拡張しない。compiler frontend が test source を
解析して manifest を出力する。

```json
{
  "testKitAbi": 1,
  "tests": [
    {
      "name": "read failure is surfaced",
      "entry": "read_failure_is_surfaced",
      "step": 10000000,
      "mockTargets": [
        {
          "id": "t0",
          "source": "system/MyOS/src/fs/ssd.mln",
          "sourceName": "read_block",
          "linkName": "ssd_read_block",
          "params": ["i32", "i32"],
          "return": "i32",
          "signature": "fn(i32,i32)->i32"
        }
      ]
    }
  ]
}
```

filesystem path だけ、またはsource中のalias名だけではなく `(repo-relative canonical source, link name)` を
target identity とする。source name は診断表示、signatureはplan/build間の整合性検査に使う。
absolute pathはartifactへ保存せず、別checkoutでも同じplanが読めるようにする。同じlink nameを別sourceが
定義した場合は通常linkerと同じduplicate-symbol errorにする。

annotation移行前と移行後で、compile backendに渡すplan形式は変えない。

移行中は case ごとに次を行う。

1. 現行 `TestParser.java` が一つのtest bodyを generated `.mln` にする。
2. `mlc -emit-mock-plan <generated.mln> <plan.json>` がimportを解決し、`mock.of` / `mock.spy` callから
   canonical target descriptorとTestKit ABI versionを出す。このmodeはmachine codeを生成しない。
3. MyLangTesterがMyLangTestKit runtime sourceを追加し、全source compileへ `-test-plan <plan.json>` を付ける。
4. compilerがgenerated test support moduleへtyped hook / Args packing / real-call thunkを生成し、linkerが
   targetへのdirect call relocationをhookへredirectする。TestKitはhookが使うgeneric stateとverdict runtimeを提供する。
5. bodyの正常return後、`verify_all`、cleanup、PASS出力、haltを行う。

annotation移行後は、`mlc -emit-test-manifest <source.test.mln> <manifest.json>` がtest metadataとcase別mock
targetを同時に出し、手順1と2を置き換える。mytestは選択したcaseから同じ`plan.json`をmaterializeする。
この二段階により、link-time interception backendをannotation完成まで待たせず、後でbuild側を作り直さずに済む。

plan emissionとactual compileは同じtarget resolutionを通す。planに無いtargetをactual compile中に発見した場合は、
`mock target missing from test plan` としてfailureにする。

一つの source に複数 test があっても、初期版は case ごとに別 binary / emulator process を使う。
global、SSD、IRQ、mock rule を完全に分離する。

## Annotation 形式

test declaration は最終的に compiler が正式に読む annotation へ移行する。

```mylang
@test("read failure is surfaced")
@step(10000000)
void read_failure_is_surfaced() {
    mock.of(ssd.read_block)
        .when(mock.any(), mock.any())
        .ret(-1);

    fs.init();
    // assertions; normal return means PASS
}
```

`stdin`, `step`, `timer_interval`, `disk`, `skip` は runner metadata annotation とする。mock target は
`mock.of(...)` / `mock.spy(...)` から静的に抽出できるため、`@mockable` や `@mock` annotation は
要求しない。

## Test verdict protocol

test body の正常 return 後に runner-generated epilogue が次を実行する。

1. `verify_all()`。
2. mock slot / test resource cleanup。
3. `TEST_PASS:<name>` 出力。
4. halt。

assertion、strict unmatched call、未達 expectation、capacity overflow は `TEST_FAIL:<reason>` を出して
即時 halt する。`test.pass()` は互換期間後に廃止する。

| emulator result | mytest result |
| --- | --- |
| `TEST_PASS:<name>` | PASS |
| `TEST_FAIL:<reason>` | FAIL と reason |
| step limit | TIMEOUT と step |
| verdict なしで halt | FAIL: no verdict |
| emulator non-zero exit | ERROR と exit status |

## 実装フェーズ

### Phase 0: MyLangTestKit foundation

- `toolchain/MyLangTestKit` submoduleを追加する。
- runtime source layout、package名、`__mlt_require_abi_v1`、TestKit ABI v1を固定する。
- MyLangTesterがrepository rootからTestKitを解決し、test buildだけにsourceを追加できるようにする。
- MyStdLibの`assert_fail` externをTestKit verdict adapterで解決する最小testを通す。

### Phase A: test lifecycle / diagnostics

- `TEST_FAIL:<reason>` の構造化認識。
- halt / step-limit / emulator error の分類。
- TestKitによる`assert_fail` runtime hook の一元提供。
- body normal return による automatic PASS。

### Phase B: Mock API prototype

- scalar引数・scalar return の target 一つから開始する。
- detour backend でstrict Mockの `.when().ret()`、call history、`verify().times()` を実証する。
- prototypeではSpy/original fallbackを提供せず、APIを同名のlink-time interception backendへ移せることを確認する。
- filesystem から `ssd.read_block` を直接呼ぶ構造は変更しない。

### Phase C: 型付き generic mock core

- TestKitに`Matcher<T>`, `Rule<Args, Ret>`, `MockState<Args, Ret>` を追加する。
- TestKitに`MockStateVoid<Args>` を追加する。
- target signature から Args struct、typed hook、real-call thunkを生成する。
- `Mock<Args, Ret>` methodの型検査で matcher / `ret` / `answer` を検査する。
- target descriptorを`Mock<Args, Ret>`へ渡すsupportを生成する。
- `-emit-mock-plan` とplan consistency checkを追加する。

### Phase D: link-time interception backend

- test manifest から mock target を build pipeline へ渡す。
- build toolchainから全source compileへ `-test-plan` を渡す。
- targetごとのfixed hookとreal entry descriptorを生成する。
- linkerがtargetへのdirect call relocationをhook addressへredirectする。
- Spy の automatic original fallback / Mock の strict mode / no-inline を実装する。
- Mock の unexpected-call failure と Spy の original fallback を同じ dispatcher に実装する。
- typed `call(i).arg(j)` / `ret()` / `path()` getterを生成する。
- detour backend を削除する。

### Phase E: annotation / multiple cases

- `@test` と runner metadata annotation を追加する。
- `mlc -emit-test-manifest` を追加し、`-emit-mock-plan` の役割を統合する。
- Java の手書き source parser を manifest reader へ置き換える。
- test case ごとの isolated build/run と artifact 保存を追加する。

### Phase F: Python runner 移行

- SSD failure、heap exhaustion、clock、scheduler failure を mock で再現する。
- `disk`, `reg`, `panic`, `expect_not` 等、mock で置き換えられない runner capability だけを追加する。
- host-level compiler / assembler / linker test は `.test.mln` へ移さない。

## 検証計画

- compiler succeed:
  - local / imported function target、条件付き rule、answer、original fallback。
  - generic matcher と return sequence。
  - fluent chain lowering と、Spy 経由の再帰 call 記録。
- compiler fail:
  - matcher の型・個数不一致、`ret` の型不一致、answer signature 不一致。
  - unsupported aggregate / variadic target。
  - 同一 target の Mock / Spy mode conflict、invalid chain、planとのsignature不一致。
- MyLangTester:
  - canonical target descriptor 抽出、ケース別 build、automatic verify / cleanup。
  - PASS / FAIL / timeout / no-verdict / emulator error の分類。
- MyLangTestKit:
  - ABI v1 mismatchがlink errorになること。
  - matcher / rule / history / verdict adapterのguest-side unit / integration test。
- emulator integration:
  - strict Mockについてdetour prototypeとlink-time interception backendが同じobservable behaviorを持つ。
  - Mock unmatched failure、Spy original fallback、pure/partial Spy、rule override。
  - sequence exhaustion、typed call inspection、call path記録、capacity overflow。
  - answerから同一targetへの直接再入がruntime failureになる。
  - `void` targetのstub、record、verifyが動く。
- regression:
  - normal production build の symbol / code path / performance が変わらない。
  - mock target でない関数は test build でも通常どおり direct call になる。

## 完了条件

- `mock.of(ssd.read_block).when(...).ret(...)` で `fs.mln` を変更せず異常系を再現できる。
- target、matcher、return、answer の signature mismatch が compile error になる。
- Spy の unmatched fallback と Mock の strict failure の両方が動く。
- pure Spy と partial Spy が引数・回数を記録し、unmatched call を original へ渡す。
- `call(i).arg(j)` がtarget signatureに対応する型で履歴を返し、公開target固有structを要求しない。
- `verify` と epilogue expectation failure が reason 付きで表示される。
- production binaryは既存のsymbol、code path、performanceを維持する。
- rootがMyLangCompiler、MyLangTester、MyLangTestKitの互換submodule revisionをpinする。
- 一つの `.test.mln` に複数 case を書け、各 case が独立した emulator state で動く。
- stable backendは固定hookとdirect-call relocationで動作する。

## 非目標

- mockability のためだけの production DI。
- Spring 互換の runtime bean container。
- reflection による runtime signature discovery。
- private / unresolved symbol の無制限な mock。
- 初期版での aggregate / variadic target、cross-mock call ordering。
- compiler / assembler / linker unit test をすべて `*.test.mln` へ移すこと。

## 関連

- [MLT-002](MLT-002_mylang-test-framework.md): `.test.mln` discovery、case lowering、runnerの基盤。
- [MLT-001](MLT-001_mylang-test-diagnostics-strategy.md): `TEST_FAIL`、timeout、no-verdictの切り分け。
- [MLC-014](../completed/MLC-014_mylang-function-signature-type-checking.md): target / answer / matcherのsignature検査に使う型情報。
