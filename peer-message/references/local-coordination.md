---
name: peer-message-local-coordination
description: >-
  Maintain local task/resource declarations and coordination request lifecycle after installation.
  Read before independent-session ownership lookup, shared-resource windows, native preflight,
  or receiving a peer-coordination envelope. No Agent Fleet dependency.
---

# 本地协调机制

执行者是使用本 Skill 的 Agent。使用包内 `scripts/peer.py` 和
`scripts/coordination.py`；仅需 Python 标准库。首次 `coord` 或发送调用自动创建
`$XDG_STATE_HOME/peer-message/coordination.sqlite3`，未设置时用
`~/.local/state/peer-message/coordination.sqlite3`。所有本机安装副本共用此位置。
不额外安装服务，不让用户建立或维护记录；调用时更新和检查，不做后台广播。
`--state-dir` 只用于明确隔离的测试或不同操作边界，正常协作不各建一份库。

## 开工、范围变化和退出

先核对用户分工、明确任务引用及实际要争用的资源。任务 key 用工单或交付物的稳定
标识；scope 用规范仓库/项目标识；resource 用同一共享资源的精确标识。
不从相似标题推断同一任务，不把每个 clone 都命名成不同的共享发布资源。

```bash
python3 scripts/peer.py coord status --scope '<project>'
python3 scripts/peer.py coord claim --scope '<project>' --task '<issue-or-deliverable>' \
  --resource '<shared-repository>:publish'
```

`registered` 表示记录本人参与范围；`conflict` 返回已登记负责人和待协调原因，退出 3。
直接定位该负责人，不枚举全机再逐个询问。相交资源也会阻止另一负责人登记。
首次使用的空表只表示尚无参与登记，仍核对实际写者；登记是声明，不是资源锁、
权限或“无人占用”的证明。独立范围可并行，交接仍沿实际执行权合同核验。

开始、阶段切换或资源集合变化时由本人更新 claim。负责人的更新时间只表示声明
新鲜度；陈旧声明保留并返回 stale，不自动换负责人。完成或已核实交接后由本人释放：

```bash
python3 scripts/peer.py coord release --scope '<project>' --task '<issue-or-deliverable>'
```

返回 `released`。未释放的陈旧项定向核对，不能通过删库、假身份、超时或重启绕过。
原生 parent/subagent 已有任务树关联，不为每条内部消息调用此板。

## 同一问题只保留一个有效请求

窗口请求是时效性消息。有效期取实际请求的结束时间；相对窗口可用
`--expires-in <seconds>`，已定绝对结束时间则用带时区的 `--expires-at`。
两者不能同时给，不把已过去的窗口换成“从现在再等五分钟”。

```bash
python3 scripts/peer.py send '<exact-target>' request.txt \
  --kind request --topic '<project>:publish-window' --expires-in 300 --json
```

这里的 300 是该请求明确需要的五分钟窗口示例，按真实请求调整。发送前自动 reserve
同一 sender/recipient/topic/event；已有待答记录返回 `suppressed_pending` 和原 message id，
不调用 transport。换措辞不新建请求。过期请求返回 `suppressed_expired`，不入队。
`--event` 仅用于实际新增证据/交付版本，不能填随机数或重试计数规避去重。

普通旧式 send/broadcast 仍支持，按相同正文短期抑制重复投递，不凭正文关键词推断
过期或“无需回复”。新阻塞、不同收件人和不同事项仍可发送。默认去重与声明新鲜度
窗口在实现常量维护；它们是可逆运行默认值，不是用户授权或全局业务阈值。

## 原生跨会话通信

原生工具覆盖收件人时只发送原生消息。本 Skill 维护同一状态，不换 transport：

```bash
python3 scripts/peer.py coord prepare '<exact-target>' request.txt \
  --kind request --topic '<project>:publish-window' --expires-in 300
```

只有 `prepared` 才将输出的 `body` 原样交给原生工具；记录其 `message_id`。
其他 suppression 状态安静结束。随后按原生回执记录结果：

```bash
python3 scripts/peer.py coord commit --message-id '<prepared-id>' --outcome accepted
```

确定未发送用 `not_sent`，结果不明用 `unknown`。accepted 只证明 transport 层。
中断留下的 reserved/unknown 不自动重试，即使窗口已过；先在原通道读回精确消息，
再用 commit 将结果核定为 accepted 或 not_sent。不删除宿主队列，不恢复其他会话。
不能将 `coord prepare` 的 body 再喂给脚本 send；脚本 send 自己准备并拒绝手写协调元数据。

## 收件、回信和关闭

新信封含 `[peer-coordination: ...]`。先保存实际信封并读取：

```bash
python3 scripts/peer.py coord receive received.txt
```

也可从 stdin 读取（`coord receive -`）。`action_needed` 原子领取该记录一次，随后只
处理它仍有效的问题；`already_processing` 不重复执行，也不声称上次动作已成功。
`ignore_expired/ignore_superseded/ignore_closed` 安静收下，不回 ACK、不申请新窗口。
`legacy/unknown/unknown_transport` 回到现有语义分流，保留覆盖缺口，不能丢掉新阻塞。

确需回信时关联原 id；短时请求已过期/关闭时回信也会被发送前抑制：

```bash
python3 scripts/peer.py send '<original-sender>' reply.txt \
  --kind reply --in-reply-to '<original-id>' --json
python3 scripts/peer.py coord finish --message-id '<original-id>'
```

正常收件处理完或问题已有后续证据解决时 finish；返回 `closed`，不证明业务完成。
处理中的会话中断后先核对该消息的实际后续动作，再由参与者 finish；不凭
`already_processing` 自动重做，也不将真正未完成的工作报为完成。
发送状态与收件领取/关闭分别记录。实际信封可能先于发送者的 commit 到达，
接收者仍只领取一次；接收者处理后关闭不会被迟到的发送回执重开。
发送状态未知时，发送者仍需原通道读回，不能自行 finish 抹掉未知；实际已收件
并领取的接收者可在处理后关闭。旧协调库升级保留原领取和关闭事实。
错误身份、损坏库或未知 schema 明确报错并保留数据，不另建空库制造“无人负责”。

## 覆盖与验收

新装可初始化、重复调用使用同一状态、并发同事项只 reserve 一条、过期请求不引发
回应、不同任务不误杀、陈旧负责人不被接管，分别验收。先在隔离 state-dir 运行
`python3 -m unittest discover -s tests -p 'test_*.py'`，再独立读回安装副本的命令面。
合成检查不替代实际消息量和协调成本的长期观察。

本机制不依赖 Fleet，但原生发送绕过 prepare/commit、接收者不执行 receive、
未登记会话或跨机器调用不受本机记录强制控制；安装不修改宿主权限或安装全局 hook。
基础原则参考 [Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html)
和 [Message Expiration](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageExpiration.html)：
重复投递不重复产生协作动作，时效性请求在处理前判断有效期。
