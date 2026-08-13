# MyNetで学ぶネットワーク：アプリから仮想ケーブルまで

この文書は、MyNetの実装仕様そのものではなく、MyComputerへネットワーク機能を追加する
過程で「各レイヤが何を担当し、データがどう流れるか」を理解するための学習ガイドである。

実装時の正確なレジスタ値やエラー規則は
[MyNet Virtual NIC + UDP Tunnel Design](../design/mynet-virtual-nic.md) を参照する。

## 1. 最初に全体像を見る

ネットワーク通信は、アプリが直接NICを操作する仕組みではない。送信データは複数の
レイヤを下り、受信側では逆順に上る。

```text
MyComputer A                                      MyComputer B

ping application                                 ping application
      | ICMP Echo Request                              ^ ICMP Echo Reply
      v                                                |
ICMP                                                   ICMP
      | ICMP message                                   ^
      v                                                |
IPv4                                                   IPv4
      | IPv4 packet                                    ^
      v                                                |
Ethernet                                               Ethernet
      | Ethernet frame                                 ^
      v                                                |
MyNet driver                                           MyNet driver
      | MMIO + RAM                                     ^ MMIO + RAM
      v                                                |
MyNet virtual NIC === host UDP tunnel ===============> MyNet virtual NIC
```

ここで重要なのは、各レイヤが「すぐ下のレイヤに渡すデータ」を作る点である。

| Layer | 主な役割 | 識別に使うもの |
| --- | --- | --- |
| Application | pingなど利用者向けの動作 | アプリ固有 |
| ICMP / UDP | Echo、アプリ間データ配送 | ICMP type / UDP port |
| IPv4 | 異なるIP endpoint間の配送 | IP address |
| Ethernet | 同じlink上のNIC間配送 | MAC address |
| MyNet driver | frameと仮想NIC間の受け渡し | MMIO register |
| UDP tunnel | emulator間でframeを運ぶ | host IP address + UDP port |

## 2. 「内側のUDP」と「外側のUDP」

MyNetのUDP tunnelと、将来MyOSが実装するUDPは別物である。

```text
Host UDP datagram（MyEmulatorが作る）
+---------------------------------------------------------+
| Host IP | Host UDP | Ethernet frame                    |
|                   +-------------------------------------+
|                   | Ethernet | Guest IPv4 | Guest UDP  |
|                   |          |            | app data   |
+---------------------------------------------------------+
```

- **外側のUDP**は、Rust製MyEmulatorがホストOSのsocketを使って送る。
- **内側のUDP**は、MyOS自身がpacket bytesを組み立てて送る。
- 外側は仮想LANケーブルの実装方法であり、MyComputerからは見えない。
- 内側はMyComputerのnetwork stackであり、学習・実装対象になる。

初期のpingはUDPではなくICMPを使うため、内側は次の形になる。

```text
Host UDP datagram
└── Ethernet frame
    └── IPv4 packet
        └── ICMP Echo message
```

## 3. カプセル化：ヘッダを前に付けていく

アプリのデータは下のレイヤへ渡るたびにheaderが付く。これをカプセル化という。

例として、4 bytesのUDP payload `PING` を送る場合を考える。

```text
Application
+-------------------+
| P | I | N | G     |
+-------------------+

UDP
+-------------------+-------------------+
| UDP header        | P | I | N | G     |
+-------------------+-------------------+

IPv4
+-------------------+-------------------+-------------------+
| IPv4 header       | UDP header        | P | I | N | G     |
+-------------------+-------------------+-------------------+

Ethernet
+-------------------+-------------------+-------------------+---------+
| Ethernet header   | IPv4 header       | UDP header        | PING    |
+-------------------+-------------------+-------------------+---------+
```

受信側では逆に、Ethernet headerを検証して外し、IPv4 headerを検証して外し、UDPの
宛先portへpayloadを渡す。検証に失敗したpacketは上位へ渡さずdropする。

## 4. Ethernet frameのスキーマ

MyNet tunnelで運ぶ1 datagramのpayloadは次のEthernet frameそのものである。

```text
byte offset
0                 6                12      14
+-----------------+----------------+--------+--------------------+
| Destination MAC | Source MAC     | Type   | Payload            |
| 6 bytes         | 6 bytes        | 2 B    | 0..1504 bytes      |
+-----------------+----------------+--------+--------------------+
```

代表的なEtherType:

| Value | Payload |
| --- | --- |
| `0x0806` | ARP message |
| `0x0800` | IPv4 packet |

宛先MACが自分のMACまたはbroadcast `ff:ff:ff:ff:ff:ff` でなければ、初期実装ではdropする。

## 5. ARP messageのスキーマ

IPv4で通信したくても、Ethernet headerには宛先MACが必要である。ARPは「このIP addressを
持っているNICのMAC addressを教えて」と同じlink上へ問い合わせるprotocolである。

```text
+----------+----------+------+-------+------+----------------+
| HTYPE    | PTYPE    | HLEN | PLEN  | OPER | sender/target  |
| 2 B      | 2 B      | 1 B  | 1 B   | 2 B  | addresses      |
+----------+----------+------+-------+------+----------------+

addresses:
+------------+------------+------------+------------+
| Sender MAC | Sender IP  | Target MAC | Target IP  |
| 6 B        | 4 B        | 6 B        | 4 B        |
+------------+------------+------------+------------+
```

初期Ethernet/IPv4用の値:

| Field | Value |
| --- | --- |
| HTYPE | `1`（Ethernet） |
| PTYPE | `0x0800`（IPv4） |
| HLEN | `6` |
| PLEN | `4` |
| OPER | `1=request`, `2=reply` |

ARP requestは宛先MACがまだ分からないためEthernet broadcastで送る。

```text
A: Who has 10.0.0.2? Tell 10.0.0.1
B: 10.0.0.2 is at 02:00:00:00:00:02
```

AはreplyをARP cacheへ保存し、以降はBのMACをEthernet destinationに使う。

## 6. IPv4 packetの最小スキーマ

MyOS初期版はoptionのない20-byte header（IHL=5）だけを扱う。

```text
byte  0       1       2               4               8
     +-------+-------+---------------+---------------+
     |Ver/IHL| DSCP  | Total Length  | Identification|
     +-------+-------+---------------+---------------+
     |Flags/Fragment Offset          | TTL | Protocol|
     +-------------------------------+-----+---------+
     | Header Checksum                             |
     +---------------------------------------------+
     | Source IPv4 address                         |
     +---------------------------------------------+
     | Destination IPv4 address                    |
     +---------------------------------------------+
     | Payload ...                                 |
     +---------------------------------------------+
```

実際のfieldはnetwork byte order（big-endian）で格納する。例えば16-bit値`0x1234`は
memory上で`12 34`となる。

最低限検証する項目:

- versionが4か
- IHLが5か
- total lengthが受信frame内に収まるか
- fragmentではないか
- header checksumが正しいか
- destination IPが自分宛てか
- TTLが0でないか
- protocolが対応済みか（ICMP=`1`、UDP=`17`）

## 7. ICMP Echoのスキーマ

pingが使うICMP Echoは比較的小さい。

```text
+--------+--------+----------+------------+----------+---------+
| Type   | Code   | Checksum | Identifier | Sequence | Payload |
| 1 B    | 1 B    | 2 B      | 2 B        | 2 B      | N B     |
+--------+--------+----------+------------+----------+---------+
```

| Message | Type | Code |
| --- | --- | --- |
| Echo Request | `8` | `0` |
| Echo Reply | `0` | `0` |

受信側はRequestのidentifier、sequence、payloadを維持し、typeをReplyへ変えてchecksumを
再計算する。

## 8. UDP datagramの最小スキーマ

MyOS側UDPはIPv4 payloadとして次を持つ。

```text
+-------------+------------------+--------+----------+---------+
| Source Port | Destination Port | Length | Checksum | Payload |
| 2 B         | 2 B              | 2 B    | 2 B      | N B     |
+-------------+------------------+--------+----------+---------+
```

EthernetはMAC、IPv4はIP、UDPはportを見て配送先を決める。例えば同じMyComputer上でも、
port 7のecho appとport 53のDNS clientは別の受信先として扱える。

## 9. MMIOはCPUとデバイスの会話

MyComputerでは、NICに関数を直接呼ぶのではなく、決められたmemory addressへ値を
読み書きする。これがmemory-mapped I/O（MMIO）である。

```text
CPUの命令                       MyNet側の意味

write NET_TX_ADDR, 0x00100000   frameはRAMのここにある
write NET_TX_LEN,  42           frameは42 bytesある
write NET_CMD,     TX           送信を開始せよ
read  NET_STATUS                成功したか確認する
```

通常のRAMと違い、MMIOへのwriteはdeviceの動作を起こす。`NET_CMD=TX`は単に数値1を
保存する操作ではなく、RAM検証、frame copy、host UDP送信を開始するcommandになる。

## 10. TXシーケンス

```text
MyOS             MyNet driver        MMIO/MyNet          Host UDP
 |                    |                   |                   |
 | build frame        |                   |                   |
 |------------------->|                   |                   |
 |                    | write TX_ADDR/LEN |                   |
 |                    |------------------>|                   |
 |                    | write CMD=TX      |                   |
 |                    |------------------>| validate RAM      |
 |                    |                   | copy frame        |
 |                    |                   |------------------>| send_to
 |                    | read STATUS       |                   |
 |                    |<------------------|                   |
```

設計上、deviceはcommandを受け取った時点でRAMから一度copyする。これによりcommand完了後、
MyOSが元のbufferを書き換えても送信中frameが壊れない。

## 11. RXシーケンス

```text
Host UDP        MyNet/RX FIFO          IRQ         Driver          MyOS
   |                  |                 |             |              |
   | Ethernet frame   |                 |             |              |
   |----------------->| enqueue         |             |              |
   |                  | RX_READY=1      |             |              |
   |                  |---------------> | interrupt   |              |
   |                  |                 |-----------> |              |
   |                  |<-----------------------------| read RX_LEN  |
   |                  |<-----------------------------| RX_COPY      |
   |                  | copy to RAM/pop |             |              |
   |                  |--------------------------------------------->| queue
```

IRQ handlerが行うのはhardware FIFOからkernel ring bufferへの移動までである。Ethernetや
IPv4の解析をIRQ中にしない理由は、割り込みを短く保ち、他のtimer/mouse/serial IRQを
長時間待たせないためである。

## 12. バッファの所有権

送受信で「誰がそのbytesを書き換えてよいか」を明確にしないと、処理途中のframeが壊れる。

```text
TX:
MyOS buffer --CMD_TX時にcopy--> MyNet temporary buffer --send--> host socket
     ^ command完了後は再利用可

RX:
host socket --> MyNet RX FIFO --RX_COPY--> driver buffer --> MyOS protocol queue
                   ^ copy成功時だけpop
```

RXのRAM addressが不正な場合にFIFOをpopしないのは、受信frameを失わずdriverが別bufferで
再試行できるようにするためである。

## 13. なぜ最初からインターネットへ接続しないのか

一般のInternetへ接続するには、MyOSのnetwork stack以外にもhost側で次が必要になる。

```text
MyComputer
  -> virtual NIC
  -> TAP または user-mode NAT
  -> host routing / firewall
  -> LAN router
  -> Internet
```

この経路を最初から使うと、packetが届かない原因がMyOS、emulator、host routing、権限、
firewallのどこか判断しにくい。UDP tunnelで2台を直結すると、まずEthernet/ARP/IPv4を
閉じた環境で検証できる。

## 14. 実装しながら観察するポイント

各段階で、次の問いに答えられるログまたはtestを作る。

### MyNet device

- RAMの何番地から何bytes送ったか。
- host UDP datagramとRAMのbytesは一致したか。
- 受信frameでIRQが立ったか。

### Ethernet / ARP

- EtherTypeは何か。
- requestはbroadcastで送られたか。
- IPからMACを解決してcacheへ保存できたか。

### IPv4 / ICMP

- source/destination IPは何か。
- checksumは一致したか。
- Echo RequestとReplyでidentifier/sequence/payloadは維持されたか。

### UDP

- destination portに対応するendpointはあるか。
- UDP lengthはIPv4 payload内に収まっているか。
- appへ渡ったpayloadは送信時と一致したか。

## 15. 用語集

| 用語 | このプロジェクトでの意味 |
| --- | --- |
| NIC | Network Interface Controller。MyNetが仮想的に再現するdevice |
| MMIO | memory addressのread/writeでdeviceを操作する方式 |
| Frame | Ethernet layerの送受信単位 |
| Packet | 主にIPv4 layerの送受信単位 |
| Datagram | UDPの送受信単位。文脈によりhost tunnelまたはMyOS UDPを指す |
| MAC address | 同一Ethernet link上でNICを識別する48-bit address |
| IP address | IPv4 network上のendpointを識別する32-bit address |
| Port | UDP/TCPで同じhost内の通信先を識別する16-bit番号 |
| ARP | IPv4 addressから同一link上のMAC addressを問い合わせるprotocol |
| IRQ | deviceがCPUへイベント発生を通知するinterrupt request |
| FIFO | first-in, first-outのqueue。受信順にframeを取り出す |
| Drop | frame/packetを上位へ渡さず破棄すること |
| Checksum | header/dataの破損を検出するための計算値 |

