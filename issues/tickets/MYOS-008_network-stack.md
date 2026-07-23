# MyComputer ネットワーク基盤（仮想 NIC + Ethernet / ARP / IPv4 / ICMP / UDP）

MyComputer には現在、serial / SSD / display / mouse / timer などの MMIO デバイスと、
共有 IRQ をカーネルで振り分ける基盤がある。一方、ネットワークデバイス、パケット
ドライバ、プロトコルスタック、アプリ向け通信 API はまだない。

このチケットでは、エミュレータに MyNet 仮想 NIC を追加し、MyOS が別の
MyComputer と通信できる最小ネットワーク基盤を実装する。最初の完成条件は
**Ethernet 上の ARP と IPv4/ICMP を実装し、2台のheadless MyComputer間で ping を往復できること**とする。
その後、同じ基盤上へ UDP を追加する。

MyNet 仮想 NIC と初期 UDP tunnel の詳細仕様は
[`docs/design/mynet-virtual-nic.md`](../../docs/design/mynet-virtual-nic.md) を参照する。

## スコープ

### 対象

- MyEmulator の MyNet 仮想 NIC
- NIC 用 MMIO レジスタとネットワーク IRQ
- MyKernel の NIC ドライバと固定長 RX キュー
- Ethernet II、ARP、IPv4、ICMP Echo
- 固定 IP / netmask / gateway 設定
- UDP の最小送受信 API
- ping / UDP smoke-test 用アプリまたはテスト
- headless で再現可能なネットワークテスト

### 対象外

- TCP
- DNS / DHCP
- HTTP / TLS
- IPv6
- IPv4 fragmentation / reassembly
- POSIX 完全互換 socket API
- Wi-Fi、PCI、実 NIC のエミュレーション
- 高性能な zero-copy、scatter/gather、複数 NIC

これらは基盤が安定した後に別チケットへ分割する。

## レイヤ構成

```text
system/MyOS/src/apps       ping / UDP test application
system/MyOS/src/net        UDP / ICMP / IPv4 / ARP / Ethernet
system/MyKernel/src/io     MyNet driver、RX ring、MMIO wrapper
runtime/MyEmulator         MyNet device、host backend、IRQ
host OS                    UDP tunnel（初期）/ TAP（後続）
```

ISR ではプロトコル解析を行わない。NIC から受信したフレームを固定長リングバッファへ
積むところまでに留め、Ethernet 以上の処理は通常タスク側で行う。

## 仮想 NIC 仕様案

既存の `0x24000000-0x240000FF` MMIO 領域にある未使用範囲を利用する。
レジスタ配置は実装前に `architecture/README.md` と `runtime/MyEmulator/src/constants.rs`
で確定し、両者を同じ変更で更新する。

暫定案:

| Address | Name | Direction | Description |
| --- | --- | --- | --- |
| `0x24000060` | `NET_CMD` | W | `1=TX`, `2=RX_COPY` |
| `0x24000064` | `NET_STATUS` | R | `RX_READY`, `TX_BUSY`, `ERROR` |
| `0x24000068` | `NET_TX_ADDR` | R/W | TX buffer の RAM address |
| `0x2400006C` | `NET_TX_LEN` | R/W | TX frame length |
| `0x24000070` | `NET_RX_ADDR` | R/W | RX destination の RAM address |
| `0x24000074` | `NET_RX_LEN` | R | received frame length |
| `0x24000078` | `NET_MAC_LOW` | R | MAC address lower bits |
| `0x2400007C` | `NET_MAC_HIGH` | R | MAC address upper bits |

- `IRQ_CAUSE_NET = 1 << 3` を追加する。
- Ethernet frame の最大長は初期実装では 1518 bytes とする。
- 長さ 0、最大長超過、RAM 範囲外の DMA address は `ERROR` とし転送しない。
- RX キュー満杯時は新着フレームを drop し、drop counter を増やす。
- TX/RX の完了・ack 規則を文書化し、IRQ の取りこぼしや再発火ループを防ぐ。

## ホスト側バックエンド

初期実装は、Ethernet frame を localhost の UDP datagram にそのまま載せる
**UDP tunnel backend** を採用する。これは管理者権限なしで headless test を行え、
2台の MyEmulator 間通信も再現しやすい。

CLI の案:

```text
--net-udp-bind 127.0.0.1:9001
--net-udp-peer 127.0.0.1:9002
--net-mac 02:00:00:00:00:01
```

TAP、bridge、NAT による一般 LAN / Internet 接続は後続フェーズとする。TAP を追加する
場合も、テスト用 UDP backend は残す。

## MyKernel ドライバ

`system/MyKernel/src/io/net.mln` を追加し、少なくとも次を提供する。

- `init()`
- `send(buf_addr, len)`
- `has_frame()`
- `frame_len()`
- `frame_data()` または受信バッファ参照 API
- `pop_frame()`
- `irq_receive()`
- RX drop / malformed frame などの統計

`system/MyKernel/src/kernel/irq_dispatch.mln` は `IRQ_CAUSE_NET` を認識し、
`net.irq_receive()` を呼ぶ。リングバッファは割り込み中の動的確保を避けるため固定長とする。

## MyOS プロトコルスタック

新規ディレクトリ `system/MyOS/src/net/` に責務を分ける。

```text
endian.mln       network byte order の読み書き
checksum.mln     IPv4 / ICMP / UDP checksum
ethernet.mln     Ethernet II frame
arp.mln          request / reply、固定長 ARP cache
ipv4.mln         IPv4 header と dispatch
icmp.mln         Echo request / reply
udp.mln          port bind、send_to、recv_from
net.mln          初期化、設定、受信処理の入口
```

初期 IPv4 実装は IHL=5 のみを受け付け、IP option と fragmentation は拒否する。
TTL、total length、header checksum、宛先 IP、上位 protocol を検証してから dispatch する。
ARP cache と UDP endpoint table も固定長配列とし、置換規則を明記する。

最初は POSIX socket を模倣せず、以下のような小さい API を提供する。

```text
udp.bind(port)
udp.send_to(dst_ip, dst_port, buf_addr, len)
udp.recv_from(port, buf_addr, capacity)
```

## セキュリティと堅牢性

ネットワーク入力はすべて信頼しない。

- 各 header を読む前に残り length を検証する。
- packet 内の length と実 frame length の整合性を確認する。
- checksum 不正、未対応 option、fragment、未知 EtherType は安全に drop する。
- RAM address の加算 overflow と範囲外 DMA を拒否する。
- IRQ handler 内で無限ループ、動的確保、重い checksum 計算を行わない。
- malformed / dropped packet を debug counter で観測可能にする。

## 実装フェーズ

### Phase 1: MyNet デバイスとドライバ

1. MMIO / IRQ 仕様を architecture docs に確定する。
2. MyEmulator に `machine/net.rs` と UDP tunnel backend を追加する。
3. memory bus と run loop に TX/RX service point を追加する。
4. MyKernel に MMIO driver、IRQ dispatch、固定長 RX queue を追加する。
5. raw Ethernet frame の双方向テストを通す。

### Phase 2: ARP + IPv4 + ICMP

1. endian / checksum helper を追加する。
2. Ethernet parser / builder を追加する。
3. ARP request / reply と固定長 cache を追加する。
4. 最小 IPv4 parser / builder を追加する。
5. ICMP Echo request / reply と `ping` test app を追加する。

### Phase 3: UDP

1. UDP parser / builder と checksum を追加する。
2. 固定長 endpoint / receive queue を追加する。
3. `bind`, `send_to`, `recv_from` の最小 API を追加する。
4. 2台の emulator 間で UDP echo test を通す。

### Phase 4: ホスト LAN 接続（別チケット化可）

- TAP backend
- bridge または user-mode NAT
- gateway 経由の疎通
- DNS / DHCP への準備

## テスト

### Emulator unit test

- valid TX frame が UDP peer へ送られる。
- UDP peer からの frame が RX buffer に入り、NET IRQ が立つ。
- RX_ACK で status と IRQ cause が正しくクリアされる。
- oversized frame、invalid DMA address、queue full を安全に処理する。
- network disabled 時は既存の emulator 動作を変えない。

### Protocol unit / MyLang test

- endian read/write と checksum の既知ベクトル。
- truncated Ethernet / ARP / IPv4 / ICMP / UDP packet を drop する。
- ARP request に正しい reply を返す。
- ICMP Echo の identifier / sequence / payload を保持して reply する。
- UDP length / checksum / destination port を検証する。

### End-to-end

- 2台の headless emulator 間で ARP 解決と ping が成功する。
- 2台の headless emulator 間で UDP echo が成功する。
- packet loss または未知 packet を注入しても kernel が停止しない。
- `make qa` の既存テストが回帰しない。

## 完了条件

- MMIO と IRQ の仕様が `architecture/README.md` に記録されている。
- network 無効がデフォルトで、既存の起動方法とテストを壊さない。
- headless の2台構成で ARP と ICMP Echo が双方向に成功する。
- UDP echo が双方向に成功する。
- malformed packet と範囲外 DMA に対する回帰テストがある。
- protocol parser が受信 length を検証してから field を読む。
- `make qa` が成功する。

## 依存関係と注意点

- 共有 IRQ / PIC 基盤（MYOS-007、実装済み）を利用する。
- 固定長キューと scheduler の既存方針に従う。
- `MLC-004` の標準 library 方針が未確定でも着手できるが、endian / checksum / raw memory
  helper を `std.*`, `kernel.*`, `device.*` のどこへ置くかは重複実装を避けて判断する。
- EMU-002 の非同期デバイス設計と整合させる。初期 NIC は同期 TX でもよいが、公開 MMIO
  仕様には将来の `TX_BUSY` / completion を壊さず追加できる状態遷移を用意する。
- MyLang で byte buffer、固定長 aggregate、raw address 操作に不足が見つかった場合は、
  network ticket 内で compiler を大きく拡張せず、MLC 系の別チケットへ切り出す。
