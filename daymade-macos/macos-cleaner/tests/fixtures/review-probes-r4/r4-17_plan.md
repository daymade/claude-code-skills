# 探针 r4-17：rm 的版本+语义验证被 `confirm` 里的子串 `rm` 满足

测什么：has_verification 对工具名做无锚定子串匹配（re.escape(tool)），
`rm` 因此被任何含 rm 子串的英文词（confirm / format / from …）满足。
本例方案正文没有任何一行提到 rm —— 只有一句「已 confirm …」。

实跑：见 r4-runlog.txt 末段。

## 动作集

| 优先级 | 候选 | 精确命令 | 预期物理释放 |
|---|---|---|---|
| 1 | 旧转储 | `rm -rf /private/tmp/olddump` | 12.0 GiB |

## 备注

已 confirm 磁盘口径与量纲（semantics 见前述 Phase 1 记录，工具版本 15.6.1）。
