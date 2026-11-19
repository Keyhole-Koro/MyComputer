# 方針（層をまたぐ決まり）

## policy.sdk-no-myos  SDK は MyOS を import しない
方針

境界はプロトコルだけ。共有するのはデータだけの契約（[[schema.request]] など）。新しい機能は、契約と SDK の関数の組で足す。
