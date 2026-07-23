# MyNet Virtual NIC + UDP Tunnel Design

**Status:** Draft 1  
**Parent ticket:** [MYOS-008](../../issues/tickets/MYOS-008_network-stack.md)  
**Initial implementation ticket:** EMU-003（未作成）

レイヤ構造、packet schema、送受信sequenceを学習目的で読む場合は
[MyNetで学ぶネットワーク](../learn/mynet-network-path.md) を先に参照する。

## 1. Purpose

MyNet は MyComputer 向けの単純な仮想 Ethernet NIC である。MyOS からは MMIO と
共有 IRQ で操作するネットワークデバイスとして見え、MyEmulator は NIC が送受信する
Ethernet frame をホスト OS の UDP socket で別の MyEmulator へ運ぶ。

初期設計の目的は、管理者権限や host network の bridge 設定なしで、2台の
headless MyComputer 間に決定的かつ自動テスト可能な Ethernet link を提供することである。

```text
MyComputer A                                            MyComputer B
MyOS driver                                             MyOS driver
    | MMIO / IRQ                                            ^ MMIO / IRQ
    v                                                       |
MyNet device A -- UDP datagram over host loopback --> MyNet device B
                    payload = one Ethernet frame
```

MyNet は Ethernet frame の内容を解釈しない。ARP、IPv4、ICMP、UDP などの protocol は
後続の MyOS network stack が実装する。

## 2. Goals and non-goals

### Goals

- Ethernet II frame を透過的に送受信する。
- 既存の MMIO、共有 IRQ、RAM buffer の設計に合わせる。
- host UDP socket を使い、一般ユーザー権限で2台を直結できる。
- network disabled 時に既存の emulator の挙動を変えない。
- malformed command、範囲外 DMA、oversized datagram を安全に拒否する。
- GUIなしの unit / integration test を可能にする。

### Non-goals

- 実在 NIC、PCI、virtio-net との互換性
- Ethernet switch、複数 peer、broadcast domain の host 側実装
- TAP、bridge、NAT、一般 LAN / Internet への接続
- packet retransmission、delivery guarantee、暗号化
- checksum offload、scatter/gather、zero-copy
- link speed、collision、PHY の精密なエミュレーション

UDP は host transport にのみ使用する。UDP 自体の不達、重複、順序入れ替えは Ethernet
link 上の drop、duplicate、reorder と同等に扱い、MyNet は補償しない。

## 3. Components

```text
runtime/MyEmulator/src/
├── constants.rs              MMIO address、bit、最大frame長
├── cli.rs                    --net-* options
└── machine/
    ├── mod.rs                Machine が MyNetDevice を所有
    ├── net.rs                RX FIFO、UDP socket、command処理
    ├── memory_bus.rs         MyNet MMIO read/write
    ├── interrupts.rs         NET cause の配送
    └── run_loop.rs           nonblocking RX poll
```

MyNet の host socket は nonblocking mode とし、background thread は使用しない。
CPU run loop の service point で `recv_from` を空になるまで呼び、`WouldBlock` で終了する。

## 4. Link model

初期版は peer を1つだけ持つ point-to-point link である。

- UDP 1 datagram は Ethernet 1 frame に対応する。
- UDP payload は Ethernet frame の raw bytes のみとし、独自 tunnel header は付けない。
- Ethernet frame は destination MAC から payload 末尾までを含む。
- preamble、SFD、FCS、inter-frame gap は含めない。
- 最小 frame を満たすための padding は sender 側 MyOS の責務としない。MyNet は
  14 bytes 以上であれば短い frame も運べる。受信側 protocol parser が必要な長さを検証する。
- 最大 payload は `MYNET_MAX_FRAME_SIZE = 1518` bytes とする。
- UDP source address が configured peer と異なる datagram は drop する。
- zero-length、1518 bytes 超過、UDP receive buffer で truncated した datagram は drop する。

独自 tunnel header を設けないことで packet capture と test fixture を単純に保つ。
versioning、multi-link ID、fault injection metadata が必要になった時点で別 backend または
versioned framing を追加し、初期 raw backend との互換性を維持する。

## 5. CLI and lifecycle

CLI 案:

```text
myemu \
  --net-udp-bind 127.0.0.1:9001 \
  --net-udp-peer 127.0.0.1:9002 \
  --net-mac 02:00:00:00:00:01
```

| Option | Required when enabled | Meaning |
| --- | --- | --- |
| `--net-udp-bind <ip:port>` | yes | host UDP socket の local endpoint |
| `--net-udp-peer <ip:port>` | yes | Ethernet frame の送信先かつ許可する受信元 |
| `--net-mac <mac>` | no | guest に公開する MAC address |

- bind と peer の両方がない場合、network は disabled である。
- 片方だけ指定された場合は起動時エラーとする。
- MAC 省略時は locally administered unicast address を生成する。ただしE2Eテストでは
  明示指定し、実行ごとの再現性を確保する。
- bind 失敗、無効な address、multicast/broadcast MAC の指定は起動時エラーとする。
- disabled NIC の status は `LINK_UP=0`。TX command は `ERROR` になり frame を送らない。

初期版はIPv4/IPv6の host UDP endpointをCLI parserが受け付けてもよいが、同一 address
family の bind/peerのみを保証対象とする。

## 6. MMIO register interface

MyNet は既存 I/O window `0x24000000-0x240000FF` の `0x60-0x7C` を使用する。
すべてのレジスタは 32-bit little/big endian の byte layout を外部へ公開せず、CPUの
既存 `read_word` / `write_word` の値として扱う。

| Address | Register | Access | Reset | Description |
| --- | --- | --- | --- | --- |
| `0x24000060` | `NET_CMD` | W | — | commandを書き込む |
| `0x24000064` | `NET_STATUS` | R/W1C | `0` | link、RX、busy、error flags |
| `0x24000068` | `NET_TX_ADDR` | R/W | `0` | TX source RAM address |
| `0x2400006C` | `NET_TX_LEN` | R/W | `0` | TX frame length |
| `0x24000070` | `NET_RX_ADDR` | R/W | `0` | RX destination RAM address |
| `0x24000074` | `NET_RX_LEN` | R | `0` | RX FIFO先頭のframe length |
| `0x24000078` | `NET_MAC_LOW` | R | config | MAC bytes 0..3 |
| `0x2400007C` | `NET_MAC_HIGH` | R | config | low 16 bitsにMAC bytes 4..5 |

### 6.1 Commands

| Value | Name | Effect |
| --- | --- | --- |
| `1` | `NET_CMD_TX` | RAMからframeをcopyしconfigured peerへ送る |
| `2` | `NET_CMD_RX_COPY` | RX FIFO先頭をRAMへcopyし、成功時のみpopする |
| `3+` | reserved | `ERROR`を立て、状態を変更しない |

TX/RX command に指定した RAM buffer は command 完了後に guest が再利用できる。
初期版のcopyとhost UDP sendは command write の処理中に完了するため、`TX_BUSY` は通常
guestから観測できない。ただし公開状態機械にbusyを残し、将来の非同期化を可能にする。

### 6.2 Status bits

| Bit | Name | Meaning |
| --- | --- | --- |
| `0` | `LINK_UP` | UDP backend が有効 |
| `1` | `RX_READY` | RX FIFO が空でない |
| `2` | `TX_BUSY` | TX command 処理中 |
| `3` | `RX_OVERRUN` | RX FIFO満杯によるdropが発生 |
| `4` | `ERROR` | command、DMA、socket errorが発生 |

`RX_OVERRUN` と `ERROR` は sticky bit であり、対応bitへ1を書いてclearする（W1C）。
`LINK_UP`、`RX_READY`、`TX_BUSY` へのwriteは無視する。

### 6.3 MAC register encoding

MAC `02:00:00:00:00:01` は次の値として読む。

```text
NET_MAC_LOW = 0x02000000
NET_MAC_HIGH = 0x00000001
```

各byteの意味を明確にするため、driverはwordをmemoryへそのままstoreせず、shift/maskで
Ethernet headerへ書き出す。

## 7. Transmit operation

Guestは次の順序で送信する。

1. `NET_STATUS.LINK_UP == 1` と `TX_BUSY == 0` を確認する。
2. RAMにEthernet frameを構築する。
3. `NET_TX_ADDR`へ先頭addressを書く。
4. `NET_TX_LEN`へlengthを書く。
5. `NET_CMD_TX`を書く。
6. `NET_STATUS.ERROR`を確認する。

Deviceの処理:

1. `TX_BUSY=1`。
2. link、length、`addr + len` overflow、RAM範囲を検証する。
3. RAMからdevice-owned temporary bufferへframeをcopyする。
4. UDP `send_to(peer)`を1回呼ぶ。
5. 全bytes送信できた場合は成功。それ以外は`ERROR=1`。
6. `TX_BUSY=0`。

TX completion IRQ は初期版では発生させない。host UDP送信の成功はpeerによる受信を
保証しない。

## 8. Receive operation

### 8.1 Host receive

run loopはnonblocking UDP socketをpollする。valid datagramを受け取るとdevice-owned
RX FIFOへframeをcopyする。

- FIFO capacity: 32 frames
- FIFO entry: `Vec<u8>` または最大1518 bytesのowned buffer
- emptyからnon-emptyへ変化した時、`RX_READY=1`、`IRQ_CAUSE_NET`を立てる。
- FIFOが既にnon-emptyでも新着frameは追加する。NET causeがack済みなら再度立てる。
- FIFO満杯なら新着をdropし、`RX_OVERRUN=1`、overrun counterを増やす。
- `NET_RX_LEN`は常にFIFO先頭のlengthを返し、空なら0を返す。

### 8.2 Guest receive

GuestはIRQ後、次をFIFOが空になるまで繰り返す。

1. `NET_STATUS.RX_READY`を確認する。
2. `NET_RX_LEN`を読む。
3. 十分なRAM bufferを用意して`NET_RX_ADDR`へ書く。
4. `NET_CMD_RX_COPY`を書く。
5. `ERROR`がなければRAM上のframeをRX queueへ移す。

DeviceはRX FIFO先頭frame全体のRAM範囲を検証し、copy成功後にだけそのframeをpopする。
失敗時はframeを保持して`ERROR=1`とする。pop後にFIFOが空なら`RX_READY=0`、まだあれば
`RX_READY=1`を維持する。

Kernel IRQ handlerはprotocol parseを行わず、MyKernel側の固定長ringへframeを移すだけに
する。重いchecksumやARP応答は通常task contextで処理する。

## 9. Interrupt semantics

既存の共有cause registerへ次を追加する。

```text
IRQ_CAUSE_NET = 1 << 3
```

MyNetはRX FIFOがnon-emptyになった時にNET causeと`pending_irq`を立てる。Kernelの共有
dispatcherはcauseをW1Cでackした後、MyNet driverを呼ぶ。driverはhardware RX FIFOを
空になるまでdrainする。

raceを避けるため、emulatorはservice pointの終了時にRX FIFOがnon-emptyでNET causeが
clearされていればcauseを再assertする。これにより、IRQ処理中にframeが到着した場合も
次のinterruptが配送される。

RX FIFOが空の時に`NET_CMD_RX_COPY`を書いてもIRQ状態は変えず、`ERROR=1`とする。
TX成功ではIRQを発生させない。

## 10. State model

```text
Disabled
  LINK_UP=0
  TX -> ERROR

Enabled / RX empty
  LINK_UP=1, RX_READY=0
       |
       | valid host datagram
       v
Enabled / RX pending
  LINK_UP=1, RX_READY=1, NET IRQ asserted
       |
       | RX_COPY succeeds and FIFO becomes empty
       v
Enabled / RX empty
```

`ERROR`と`RX_OVERRUN`は上記状態と直交するsticky diagnostic flagsである。

## 11. Validation and error handling

### DMA validation

TXとRXはいずれもcopy前に次を確認する。

- `len > 0`
- `len <= MYNET_MAX_FRAME_SIZE`
- `addr` がRAM内
- `addr + len` がoverflowしない
- `[addr, addr + len)` がRAM終端を越えない

validation failureではRAM、RX FIFO、host socketを変更せず`ERROR=1`とする。

### Host input validation

- configured peer以外からのdatagramはsilent dropしcounterを増やす。
- 0 bytesまたは1518 bytes超過はdropする。
- receive bufferを1519 bytes確保し、1519 bytes受信した場合はoversizedとしてdropする。
- malformed Ethernetの判定はMyNetでは行わず、guest network stackへ委ねる。

### Observability

最低限、verbose logまたはdiagnosticsから次を観測可能にする。

- TX frames / bytes
- RX frames / bytes
- RX overrun drops
- invalid peer drops
- invalid length drops
- DMA errors
- socket errors

通常実行ではframeごとのlogを出さない。

## 12. Test plan

### Rust unit tests

- reset時のregister値とdisabled状態。
- valid TX commandが1つのUDP datagramを送る。
- datagram payloadがguest RAMのframeとbyte一致する。
- valid datagramで`RX_READY`とNET causeが立つ。
- `RX_LEN`が先頭frame長を返す。
- `RX_COPY`がRAMへcopyし、成功時だけFIFOをpopする。
- 複数frameをFIFO順に受信する。
- FIFO overrunでdropしsticky flagを立てる。
- invalid command、zero/oversized length、RAM範囲外、address overflow。
- unknown peerとoversized UDP datagramをdropする。
- cause ack後もFIFOが残る場合にIRQを再assertする。
- disabled networkが既存machine実行を変えない。

unit testではloopback UDPのephemeral portを使用し、固定port競合を避ける。

### Emulator integration test

2つのMyNet deviceまたは2 processをloopback UDPで相互接続し、異なるpayloadのframeを
双方向に100回送る。全frameの境界、順序、内容が保たれることを確認する。

初期EMU-003の完了条件はRust側でのraw frame往復までとする。MyLang driver、ARP、pingは
後続チケットの完了条件であり、EMU-003を不必要にblockしない。

## 13. Future extensions

- async TX completionとTX IRQ
- packet loss / latency / reorder injection backend
- TAP backend
- user-mode NAT backend
- multi-peer Ethernet switch process
- packet capture (`pcap`) 出力
- configurable MTU / jumbo frame

拡張時もMMIOのreserved command/status bitを利用し、既存guest driverとの互換性を保つ。

## 14. Open decisions before implementation

次の項目はEMU-003開始時に確定する。

1. `NET_STATUS.ERROR`を単一flagのままにするか、read-only error code registerを追加するか。
2. RX FIFOを`VecDeque<Vec<u8>>`と固定長slot配列のどちらで実装するか。
3. generated MACをbind endpointから決定的に導出するか、起動ごとにrandom生成するか。
4. run loopの1 service pointあたりの最大受信数を設け、host flood時のCPU starvationを防ぐか。

推奨値は、初期版から最大32 datagram/serviceのbudgetを設け、RX FIFOは実装が単純な
`VecDeque<Vec<u8>>`、E2EではMAC必須指定、error詳細はdiagnostic counterで保持する構成である。
