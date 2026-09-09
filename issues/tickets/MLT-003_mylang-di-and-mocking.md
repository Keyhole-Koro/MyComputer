# MyLang Function Mocking Framework

## Status

In progress.  The ABI-v1 verdict bridge and the first compiler-facing generic
building blocks (`Matcher<T>` and `ReturnSequence<T>`) are implemented in
`MyLangTestKit` and run in MyEmulator.  The fluent DSL recognition, typed
dispatcher generation, rule/history engine, and stable dispatch-slot backend
remain to be implemented in MyLangCompiler/TestKit.

## 結論

テストのために production code を DI 化しない。MyLang の関数・メソッドを test build だけで
intercept し、次の API を提供する。

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

DI は、RAM disk / SSD、複数 clock、複数 allocator など、production 自身が実装を交換する必要を
持ったときに採用する設計手法として別に扱う。mockability だけを理由に `Port`、constructor parameter、
service locator、DI container を production API へ追加しない。

## 設計判断

1. mock target は型が解決できる MyLang function / method とする。
2. `mock.of(target)` から target signature を推論する。利用者は target ごとの Mock struct を書かない。
3. 共通の rule / matcher / call history / return sequence は generics で実装する。
4. target 固有の引数 packing と dispatcher だけを compiler が生成する。
5. 安定版は text を書き換えず、test build 専用の dispatch slot を使う。
6. detour は API を早期検証する prototype backend に限定し、最終 backend にはしない。
7. 一つの test case は独立した emulator process で実行し、mock state を case 間で共有しない。
8. test body の正常 return を PASS とし、その前に自動 verification / cleanup を実行する。
9. Mock と Spy は同じ `Mock<F>` engine を使い、unmatched call の方針だけを変える。
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
MyLangCompiler  -- typed lowering / target wrapper generation -->  MyLangTestKit
       ^                                                        (guest runtime)
       |                                                              |
       | test plan / ABI                                               | TEST_FAIL, mock state
       |                                                              v
MyLangTester   -- build / run / verdict ----------------------> MyEmulator
       (host runner)
```

- `MyLangTestKit`: `mock` DSLのruntime helper、matcher/rule/history、verification、verdict、test lifecycle、
  `assert_fail` adapter、prototype用detour supportを持つ。production buildへは入らない。
- `MyLangCompiler`: DSL recognition、signature validation、typed glue、test-build dispatch wrapperを持つ。
  MyLangTestKitのsourceを直接参照せず、定義済みABIに対してcodeを生成する。
- `MyLangTester`: `.test.mln` discovery、plan作成、TestKitのsource追加、build/emulator実行、serial verdict
  の分類を持つ。guest-side mock stateは持たない。
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

### Mock chain は compile-time DSL

`mock.of(...).when(...).ret(...)` を通常の package function / receiver method 群として実装しない。
現状は cross-package method と generic receiver method に制約があり、通常関数として実装しても
`mock.of` の戻り型を target ごとに変えられないためである。

test compile では parser が作った通常の call/member AST を、専用の `lower_test_mock_chains` が
`resolve_method_calls` より前に認識する。chain を状態機械として検査し、生成 support symbol への
通常 call に書き換える。

```text
mock.of(target).when(m1, m2).ret(value)

  -> __mlt_rule_begin_<target>(MOCK_STRICT)
  -> __mlt_rule_match_<target>(m1, m2)
  -> __mlt_rule_ret_<target>(value)
```

これにより fluent API のためだけに一般言語の method dispatch を拡張しない。`mock` は test source
限定の予約 namespace とし、import は不要にする。通常 source で使用した場合は
`mock DSL is only available in test builds` と診断する。

受理する chain を明示的に限定する。

```text
target      := mock.of(function) | mock.spy(function)
stub        := target [ .when(matchers...) ]
               ( .ret([value]) [ .then_ret(value)... ] [ .expect_times(n) ]
               | .answer(function) [ .expect_times(n) ] )
verify      := target .verify(matchers...)
               [ .returned(matcher) ] [ .called_real() ]
               ( .times(n) | .once() | .never()
               | .at_least(n) | .at_most(n) )
inspect     := target .call_count()
             | target .call(index)
               ( .arg(const_index) | .ret() | .path() | .complete() )
activate    := mock.of(function) | mock.spy(function)
maintenance := mock.clear_calls(function) | mock.reset(function)
```

`ret` と `answer` の併用、`then_ret` の前の `ret` 欠落、terminal operation 後の chain、target のない
matcher は compile error にする。fluent chain の途中値は runtime value として保存・受け渡しせず、
一つの式全体を compiler が lowering する。

standalone activation または stub registration の `mock.of(target)` / `mock.spy(target)` が実行された
時点でtargetを有効化する。sourceにchainが存在するだけでは有効化しないため、setupより前に行われた
呼び出しは記録・置換されない。`verify(...)` / `call(...)` chainの先頭にある `mock.of` / `mock.spy` は
lookupだけを行い、
新規に有効化しない。未有効化targetのverification/inspectionは
`target was not activated before observation` として失敗させる。これにより、実行後に初めて Spy を置いて
過去の呼び出しを検査できたように見える誤用を防ぐ。

同じ test case に `mock.of(target)` と `mock.spy(target)` が静的に混在する場合は compile error にする。
将来、条件分岐等で静的判定できない形を許した場合に備え、runtime にも mode conflict guard を残す。

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

ArgumentCaptor相当は、target固有のArgs structを公開せず、call historyへのcompile-time DSLで提供する。

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

matcher の `T` は target の該当 parameter から推論するため、利用者は `mock.any<i32>()` や
`mock.eq_i32(...)` と書かない。これは一般言語の return-context type inference ではなく、mock DSL
lowering が型付き helper を生成する規則である。pointer expression は意味が曖昧なので暗黙 `eq` にせず、
address identity は `mock.same(ptr)`、文字列内容は `mock.str_eq(text)` を明記する。

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

## Stable backend: test-build dispatch slot

安定版では function entry の machine code を実行時に変更しない。mock target だけを test build で
次の形へ lower する。

```text
normal build
  caller -> ssd_read_block

test build
  caller -> ssd_read_block$dispatch
               |
               +-- slot == 0 -> ssd_read_block$real
               |
               +-- slot != 0 -> generated mock dispatcher
                                      |
                                      +-- matching rule -> ret / answer
                                      +-- unmatched     -> real(Spy) / TEST_FAIL(Mock)
```

conceptual lowering:

```mylang
i32 __mock_slot_ssd_read_block = 0;

i32 ssd_read_block(i32 block, i32 buffer) {
    i32 target = __mock_slot_ssd_read_block;
    if (target == 0) {
        return __real_ssd_read_block(block, buffer);
    }
    return target(block, buffer);
}

i32 __real_ssd_read_block(i32 block, i32 buffer) {
    // original body
}
```

global data initializer は function address relocation を持たないため、slot は zero 初期化する。zero は
「originalへ直行」を意味し、test setup が mock dispatcher address を書き込む。

slot を別 module から直接書かせない。mock target を持つ module は test build で次の内部 control
symbols も生成する。

```mylang
void __mlt_install_ssd_read_block(i32 dispatcher) {
    __mock_slot_ssd_read_block = dispatcher;
}

i32 __mlt_real_ssd_read_block(i32 block, i32 buffer) {
    return __real_ssd_read_block(block, buffer);
}
```

generated test support moduleはTestKit runtimeのregistryと、target ownerの`install` / `real`だけを参照する。
これなら linker に data-section relocation を追加せず、現行の function symbol relocation だけで縦通しを
作れる。cleanup は `install(0)` を呼ぶ。

target の wrapper は binary 作成時から存在するが、slot は0なので通常どおり real を呼ぶ。最初の
`mock.of` / `mock.spy` helper が registry を初期化して `install(dispatcher)` を呼び、`reset` または
epilogue cleanup が `install(0)` を呼ぶ。したがって test setup より前の boot code、global initializer、
別 test helper の呼び出しを意図せず観測しない。

MyLangTesterのbuild integrationはcaseごとのtest plan pathを全 `.mln` compile commandへ
`-test-plan <plan.json>` として渡し、同時にMyLangTestKitのruntime sourceをtest buildだけへ追加する。
target descriptorをcommand lineに展開しないので、型・pathのescapingとcommand lengthを増やさずに済む。
定義を所有するmoduleだけがcanonical sourceとlink nameの一致を検出してwrapperを生成し、caller objectは
従来どおり公開symbolをcallするため変更不要である。targetが一つもないsourceは通常のtest buildと同じ
codeを生成する。

生成内部 symbol はlink nameをそのまま連結せず、planがcanonical target順に割り当てたplan-local idを使う。
`__mlt_install_t0`、`__mlt_real_t0` のようにすれば、長いmangle名や将来のmethod symbolを安全に扱える。
planにはidとcanonical signatureも保存し、discovery時と各module compile時でsignatureが変わった場合はbuildを
止める。

この方式の利点:

- production source に DI や function-pointer field を追加しない。
- production build に indirect call cost を残さない。
- text write / RWX mapping に依存しない。
- original implementation が binary に残るため unmatched fallback が安全。
- 同じ dispatcher で Mock / Spy の両方を実装できる。
- target signature を compiler が知っているため `ret` / matcher / answer を型検査できる。
- test build では target を自動的に no-inline にできる。

同一 module 内 call、import 越し call、関数値取得がすべて dispatch symbol を指すよう symbol rewrite を
一箇所で行う。real body 内の自己再帰 call の扱いは「dispatchを再通過する」で統一し、必要なら後続で
`call_real` 専用 symbol を公開する。

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
pure Spy、partial Spy、`REAL` path recording は安全な original call-through を持つ dispatch-slot backend
から開始する。prototype 用だけの不完全な trampoline は作らない。

この制約を利用者 API へ漏らさない。`mock.of(...).when(...).ret(...)` は backend 非依存とし、dispatch
slot が完成した時点で detour backend を削除する。ISA opcode encoding は MyStdLib ではなく
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
2. `mlc -emit-mock-plan <generated.mln> <plan.json>` がimportを解決し、mock chainを検査してcanonical
   target descriptorとTestKit ABI versionを出す。このmodeはmachine codeを生成しない。
3. MyLangTesterがMyLangTestKit runtime sourceを追加し、全source compileへ `-test-plan <plan.json>` を付ける。
4. compilerがtarget定義moduleへreal body / dispatch thunk / control symbolsを、generated test moduleへ
   typed dispatcher / `kernel_main` を生成する。TestKitはそこから使うgeneric stateとverdict runtimeを提供する。
5. bodyの正常return後、`verify_all`、cleanup、PASS出力、haltを行う。

annotation移行後は、`mlc -emit-test-manifest <source.test.mln> <manifest.json>` がtest metadataとcase別mock
targetを同時に出し、手順1と2を置き換える。mytestは選択したcaseから同じ`plan.json`をmaterializeする。
この二段階により、dispatch-slot backendをannotation完成まで待たせず、後でbuild側を作り直さずに済む。

`lower_test_mock_chains` は function literal hoist 後、`resolve_method_calls` 前に実行する。plan emissionでも
同じsymbol resolutionとchain validationを通し、actual compileではplanに記録したtarget idへlowering
する。planに無いtargetをactual compile中に発見した場合は、黙ってwrapperなしで進めず
`mock target missing from test plan` として失敗する。

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
- prototypeではSpy/original fallbackを提供せず、APIを同名のdispatch-slot backendへ移せることを確認する。
- filesystem から `ssd.read_block` を直接呼ぶ構造は変更しない。

### Phase C: 型付き generic mock core

- TestKitに`Matcher<T>`, `Rule<Args, Ret>`, `MockState<Args, Ret>` を追加する。
- TestKitに`MockStateVoid<Args>` を追加する。
- target signature から Args struct と typed dispatcher を生成する。
- `lower_test_mock_chains` で fluent chain を通常 helper call へ書き換える。
- `ResolverFunctionInfo` を使い matcher / `ret` / `answer` を検査する。
- `-emit-mock-plan` とplan consistency checkを追加する。

first-class function type と generic receiver method は mock framework の必須条件にしない。一般言語機能
として導入された場合は内部生成量を減らせるが、mock target の型は既存 resolver から取得できる。

### Phase D: dispatch-slot backend

- test manifest から mock target を build pipeline へ渡す。
- build toolchainから全source compileへ `-test-plan` を渡す。
- target body rename、dispatch thunk、zero-init slot を生成する。
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
  - strict Mockについてdetour prototypeとdispatch-slot backendが同じobservable behaviorを持つ。
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
- production binary に mock runtime、dispatch slot、indirect call overhead が含まれない。
- rootがMyLangCompiler、MyLangTester、MyLangTestKitの互換submodule revisionをpinする。
- 一つの `.test.mln` に複数 case を書け、各 case が独立した emulator state で動く。
- stable backend が writable text と inline 禁止へ依存しない。

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
