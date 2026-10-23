# 节点判活与恢复验证（不切用户活动通道）

判定「节点 X 死了没有 / 恢复了没有」的唯一判据是**数据面 url-test**：经该节点向一个 204 URL 发真实 HTTPS 请求，通 = 活。中间层读数（TCP connect 成功、TLS/Reality 有应答）只用于定位坏在哪一层，不能单独下「活/死」结论——两个方向都实测误判过：协议层应答 ≠ 数据面恢复；浏览器一次不通 ≠ 节点死（切换瞬态）。

## 不切通道的独立验证：mihomo delay API

用户当前通道（如 Shadowrocket TUN 里的活动节点）保持不动，用本机第二个客户端 core 起临时实例，绑物理网卡直连被测节点，用 mihomo 的 RESTful delay API 做 url-test。

### 配方（macOS + Shadowrocket + v2rayN 的 mihomo binary）

1. **取节点凭据**。Shadowrocket 节点存于
   `~/Library/Group Containers/group.com.liguangming.Shadowrocket/ServerManager`
   （二进制 plist，NSKeyedArchiver）。写一个脚本完成 plist→yaml 的直转，**任何步骤不打印凭据值**（debug print 是最可能的泄漏环节）。用 plistlib 读 `$objects`，节点是平铺 dict（key 为字面量，值为 UID 引用，解引用取真值）；本机生产中的 `~/scripts/proxy-healer/proxy-healer.sh` 的 `resolve_current_chain()` 是已验证的完整解析器参考（含 `NS.string`/`NS.objects` 分支与深度上限），优先复用其 deref 逻辑。字段映射：`host`（可能是缓存 IP，与域名当前解析不同——优先用 title 里的域名）、`port`、`title`（含 `名称@域名:端口`）、`type`（`Shadowsocks`/`VLESS`）、VLESS 的 uuid 在 **`password`** 字段、Reality SNI 在 `peer`、`publicKey`、`shortId`、`xtls`。注意消歧：条目内另有一个 `uuid` 字段是条目内部标识（`chain` 引用它），与 VLESS 协议 UUID 是两个东西，别取错。
2. **写 mihomo 配置**（敏感凭据只进 0600 临时文件，不进上下文/日志）：

```yaml
interface-name: en0          # 绑物理网卡绕开本机 TUN（按当时实际物理口替换；先 `ipconfig getifaddr en0/en1...` 枚举确认）
mode: global
log-level: warning
external-controller: 127.0.0.1:19090
socks-port: 11080
bind-address: 127.0.0.1
ipv6: false
dns:
  enable: true
  ipv6: false
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  nameserver: [223.5.5.5, 119.29.29.29]
proxies:
  - name: nodename
    type: vless
    server: <host>
    port: 443
    uuid: <password 字段>
    network: tcp
    udp: false
    tls: true
    servername: <peer 字段>
    flow: xtls-rprx-vision
    client-fingerprint: chrome
    reality-opts:
      public-key: <publicKey 字段>
      short-id: <shortId 字段>
```

3. **先校准对照组**：用同样配置模板克隆一份指向**已知活节点**（例如用户当前正在用的那条通道），先测它。对照组不通 = 仪器未校准，被测组一切数据无效，停下修仪器再继续。
4. **起实例并测**：`mihomo -d <workdir> -f <cfg>` 后台起 2s 后：

```bash
curl -s --noproxy '*' --max-time 8 \
  "http://127.0.0.1:19090/proxies/GLOBAL/delay?url=https://www.gstatic.com/generate_204&timeout=5000"
# 活: {"delay":120}；死/未就绪: {"message":"An error occurred in the delay test"}
```

每节点连测 3 次取一致性；单窗口内的连续同结果算一个样本（转发面不稳定是时变的，跨窗口复测才算独立证据）。
5. **收尾**：杀实例、删除含凭据的临时文件；复测用户原通道确认未受影响。

### 坑（实测）

- **多节点共存一个实例时 delay API 全部报错**（节点正常加载、Reality 握手成功、请求发出后无响应；原因未查明）。可靠做法：单节点配置模板克隆，逐一起实例串行测。
- mihomo 的 **socks/http 入站不经 fake-ip**：用 socks 代理方式测域名会在本地（被污染的）DNS 解析后再经节点连假 IP。delay API 由节点侧解析，无此问题——判活用 delay API，不要 curl 经它的 socks 口测域名。
- **Shadowrocket 切换瞬态假阴**：客户端切节点后 1–2 秒内一切请求全 000（连接重建期）。用户口头报「切过去不通」先问等了多久；自己测等 5–10 秒。
- **出口 IP 反推节点归属不可靠**：住宅代理的出口 IP ≠ 节点入口 IP（2026-10-23 实测：一个 Comcast 住宅出口 IP 属于「静态住宅」产品而非所经的机房节点，前三段掩码略）。判归属只能读客户端当前选中状态，不能拿 ifconfig.me 反推。
