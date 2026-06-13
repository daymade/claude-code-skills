# Report Templates

Detailed report templates referenced from `SKILL.md`. The core report format and classification legend live in SKILL.md; this file holds the longer, fill-in-the-blank templates so they load only when needed.

## Docker Report: Required Object-Level Detail

Docker reports must list every individual object, not just categories:

```markdown
#### Dangling Images (no tag, no container references)
| Image ID | Size | Created | Safe? |
|----------|------|---------|-------|
| a02c40cc28df | 884 MB | 2 months ago | ✅ No container uses it |
| 555434521374 | 231 MB | 3 months ago | ✅ No container uses it |

#### Stopped Containers
| Name | Image | Status | Size |
|------|-------|--------|------|
| ragflow-mysql | mysql:8.0 | Exited 2 weeks ago | 1.2 GB |

#### Volumes
| Volume | Size | Mounted By | Contains |
|--------|------|------------|----------|
| ragflow_mysql_data | 1.8 GB | ragflow-mysql | MySQL databases |
| redis_data | 500 MB | (none - dangling) | Redis dump |

#### 🔴 Database Volumes Requiring Inspection
| Volume | Inspected Contents | User Decision |
|--------|--------------------|---------------|
| ragflow_mysql_data | 8 databases, 45 tables | Still need? |
```

## High-Quality Report Template (Chinese)

After multi-layer exploration, present findings using this proven template:

```markdown
## 📊 磁盘空间深度分析报告

**分析日期**: YYYY-MM-DD
**使用工具**: Mole CLI + 多层目录探索
**分析原则**: 安全第一，价值优于虚荣

---

### 总览

| 区域 | 总占用 | 关键发现 |
|------|--------|----------|
| **Home** | XXX GB | Library占一半(XXX GB) |
| **App Library** | XXX GB | 与Home/Library重叠统计 |
| **Applications** | XXX GB | 应用本体 |

---

### 🟢 绝对安全可删除 (约 X.X GB)

| 项目 | 大小 | 位置 | 删除后影响 | 清理命令 |
|------|------|------|-----------|---------|
| **废纸篓** | XXX MB | ~/.Trash | 无 - 你已决定删除的文件 | 清空废纸篓 |
| **npm _npx** | X.X GB | ~/.npm/_npx | 下次 npx 命令重新下载 | `rm -rf ~/.npm/_npx` |
| **Homebrew 旧版本** | XX MB | /opt/homebrew | 无 - 已被新版本替代 | `brew cleanup --prune=0` |

**废纸篓内容预览**:
- [列出主要文件]

---

### 🟡 需要你确认的项目

#### 1. [项目名] (X.X GB) - [状态描述]

| 子目录 | 大小 | 最后使用 |
|--------|------|----------|
| [子目录1] | X.X GB | >X个月 |
| [子目录2] | X.X GB | >X个月 |

**问题**: [需要用户回答的问题]

---

#### 2. Downloads 中的旧文件 (X.X GB)

| 文件/目录 | 大小 | 年龄 | 建议 |
|-----------|------|------|------|
| [文件1] | X.X GB | - | [建议] |
| [文件2] | XXX MB | >X个月 | [建议] |

**建议**: 手动检查 Downloads，删除已不需要的文件。

---

#### 3. 停用的 Docker 项目 Volumes

| 项目前缀 | 可能包含的数据 | 需要你确认 |
|---------|--------------|-----------|
| `project1_*` | MySQL, Redis | 还在用吗？ |
| `project2_*` | Postgres | 还在用吗？ |

**注意**: 我不会使用 `docker volume prune -f`，只会在你确认后删除特定项目的 volumes。

---

### 🔴 不建议删除的项目 (有价值的缓存)

| 项目 | 大小 | 为什么要保留 |
|------|------|-------------|
| **Xcode DerivedData** | XX GB | [项目名]的编译缓存，删除后下次构建需要X分钟 |
| **npm _cacache** | X.X GB | 所有下载过的 npm 包，删除后需要重新下载 |
| **~/.cache/uv** | XX GB | Python 包缓存，重新下载在中国网络下很慢 |
| [其他有价值的缓存] | X.X GB | [保留原因] |

---

### 📋 其他发现

| 项目 | 大小 | 说明 |
|------|------|------|
| **OrbStack/Docker** | XX GB | 正常的 VM/容器占用 |
| [其他发现] | X.X GB | [说明] |

---

### ✅ 推荐操作

**立即可执行** (无需确认):
```bash
# 1. 清空废纸篓 (XXX MB)
# 手动: Finder → 清空废纸篓

# 2. npm _npx (X.X GB)
rm -rf ~/.npm/_npx

# 3. Homebrew 旧版本 (XX MB)
brew cleanup --prune=0
```

**预计释放**: ~X.X GB

---

**需要你确认后执行**:

1. **[项目1]** - [确认问题]
2. **[项目2]** - [确认问题]
3. **Docker 项目** - 告诉我哪些项目确定不用了
```
