# 公告与社区读数的时间、来源和覆盖

先保存实际 HTTP/CLI 响应及获取时刻，再读取候选完整正文。使用离线辅助命令整理元数据：

```bash
uv run python scripts/signal_readings.py --source radar --input <timeline.json> \
  --posts-file <original-posts.json> --checked-at <实际获取时刻ISO>
uv run python scripts/signal_readings.py --source runway --input <status.json> \
  --checked-at <实际获取时刻ISO>
uv run python scripts/signal_readings.py --source community-x --input <thread.json> \
  --window-start <本轮反馈窗口起点ISO> --checked-at <实际获取时刻ISO>
```

`examined/displayed/omitted` 区分输入条数与输出条数；展示上限由
[signal_readings.py](../scripts/signal_readings.py) 的 `--limit` 参数定义。
调整 `--limit` 读取剩余定位。脚本不联网、不改原响应、不回显长正文。
按 `source_record` 或 `body_pointer` 回原文件读完整候选及承重 parent、quote、图片；
元数据成功不证明正文已读或来源穷尽。

## 区分来源时刻与查询时刻

- `source_posted_at`：原帖发布时间；通过独立取得的原帖响应按 status ID 绑定。
- `operator_observed_at`：追踪站运营者声称观察到状态变化的时刻，不是原帖时间。
- `queried_at`：本轮实际获取响应的时刻，不是页面里的相对倒计时。

保留原 `announced_at/announcedAt` 为 `index_announced_at`。Radar 的
`source=operator-observed` 与 Runway 的 `source.origin=operator` 都属于运营者观测；
前者可能继续挂旧 X 帖链接，并把 `announced_at` 更新成观测时间。
有原帖链接不消除 operator 来源；缺独立原帖时，operator 行的发布时间保留 null。
只有 tracker 标签、`confirmed=true`、`reset_observed` 或 `reset_completed` 时，
`official_completion` 仍为 `not_inferred`；回官方正文或账号事件证据判定完成和范围。

字段缺失、null 或空时间保留 unknown/null；无时区、坏时间或错误集合形状显式失败。
同一个原帖 ID 对应冲突的发布时间也失败，不按顺序静默选一个。

## 社区反馈按观察窗口使用

给每条反馈保留原链接、发帖时刻、查询时刻以及性质：情绪/玩梗、未绑定的个人自述、
带身份与前后读数的产品观测、官方声明。语义分类由执行者读完整材料完成；辅助脚本
只给 `window_relation`，不以关键词把“本周收到过”判成“本轮已到账”。

X 线程返回若干条回复只证明本次样本；主帖、回复与未知作者条目分别判断。
使用 `window_counts`、`latest_observed_at` 和未显示数量说明新鲜度，
不把窗口前的催促外推成当前没有人到账，也不把零条窗口内回复称为全域无反馈。
页面发帖时间晚于查询时刻时标 future/待核，不能当新完成信号。

Reddit 等页面只给“几分钟前”且无法核实绝对时刻时，标为较早或时间未知的讨论；
不能当作当前实时反馈。实时接口失败与已读缓存正文分别记录，不用旧页补成新覆盖。
群聊图片、语音、视频依来源 Skill 的处理与原件核验报告；未读媒体保持 partial/uncovered，
不从上下文猜到账。转发同一官宣不是多个独立账号观测，样本情绪也不是总体比例。

已有证据足以决定当前账号是否能继续工作时先报告可用额度、备用现值及查询时刻；
本轮事件归因、运营者观测和全员范围分别说明。不得因官方确认尚缺而隐去已核现值，
也不得为给出肯定结论降低 `reset_attribution.py` 的 claim gate。

### 回复样本判读

执行者先保留原集合，再按 status ID、作者、原始时间及可取得的 parent/thread 关系辨认
主帖、相关回复和无关或关系未核条目。相关性不能仅由作者相同、包含 `reset` 或出现在同一
响应中决定；关系字段缺失时沿原帖补证，仍取不到就保留未核。引用帖不自动算主帖的回复。

需要报告覆盖数量时分别给原始项数、已确认相关回复数与无关／未核项数；未分类完就不报
有效回复总数。广告、推荐、主帖或旧帖可能占用返回项，固定返回 50 项不证明读到了 50 条回复。
没有接口的穷尽标记和明确范围，只能说样本内未见某信号；有界网页观察也仍是 `partial`。

`signal_readings.py` 只整理已有响应的时间和来源，不认证任意条目的线程归属或回复穷尽；
本段由执行者核对原文与关系证据，不能拿脚本成功或 `examined` 数值代替。
