# 验证操作与已知陷阱

按需读取：修复 `AGENTS.md` / `CLAUDE.md` 双入口时看“双入口修复与宿主读回”；评估替代机制时看“替代机制探针”；执行内容迁移或引用验证时看“验证器校准与引用检查”。主文 `SKILL.md` 是当前决策与授权入口，本文件提供操作细节，不自行创建新检查或写权限。

## 双入口修复与宿主读回

由已获授权的执行 agent 操作。验收分别回答：有效规则有没有丢失、目标宿主实际加载了什么、对应任务是否按规则执行。文件相同只回答第一项的一部分；告警消失不能替代其余证据。

### 核对后再选择单一来源

1. 固定仓库、目标宿主、精确 Git 基线及修改范围。读取两个入口的文件类型、链接目标和完整正文；另查目标宿主适用的 override、上层指令与加载预算。告警只提供调查线索，不证明两套契约冲突。
2. 区分同文副本、纯指针、各有有效规则、宿主专用规则及失效链接。纯指针没有独有规则时，保留被指向的完整正文；两份各有有效规则时先按当前权威合并，再考虑软链；有效宿主专用规则保持各自作用域，不为了字节相同强行共享。
3. 选择现有权威正文，不预设必须由某个文件名担任。建立相对软链前，核对被替换入口没有尚未保存或未纳入正文的内容，且目标平台和 Git checkout 支持所选链接形式。Git 基线只保存已提交字节；未提交内容须另行保存。路径身份或授权未明时保留原件并停止替换，禁止直接强制覆盖。
4. 通过已授权的文件编辑替换冗余入口；写后从两个消费入口独立读回。确认相对目标可解析、有效正文完整、Git 提交记录链接类型。相对软链适用于同一作用域且平台支持的入口；它不证明 Windows checkout 或其他宿主也能消费，须在实际目标环境读回。

同目录 `AGENTS.md` 指向 `CLAUDE.md` 时，在仓根执行下面的只读检查。其他布局先按实际入口与权威文件修改路径；正文曾经合并时，把保真检查与原始基线 diff 分开完成。

```bash
python3 - <<'PY'
from pathlib import Path

entry = Path('AGENTS.md')
canonical = Path('CLAUDE.md')
assert entry.is_symlink(), '入口没有保留为软链'
assert str(entry.readlink()) == 'CLAUDE.md', '相对目标不符合本例布局'
assert entry.resolve(strict=True) == canonical.resolve(strict=True), '目标身份不一致'
assert entry.read_bytes() == canonical.read_bytes(), '消费入口正文不同'
print('PASS: 相对链接可解析，两个入口读取同一正文')
PY
git diff --check
git ls-files -s -- AGENTS.md CLAUDE.md
```

`git ls-files` 读的是索引：暂存后链接应为 `120000`；提交后再用 `git ls-tree HEAD -- AGENTS.md CLAUDE.md` 检查提交树。未暂存的旧索引、断链、循环链接或把目标字符串检出成普通文件，都不能报修复完成。发布后还须独立查询远端精确提交；不要用 push 回执代替远端读回。

### 检查真实宿主加载面

从实际消费的 cwd 检查，保留宿主版本、入口与观察边界。Codex 先运行 `codex debug prompt-input --help` 确认当前版本提供原生渲染器；支持时，以下只读配方检查完整正文是否进入模型可见输入，不打印其他私有指令。

```bash
python3 - <<'PY'
import json
import subprocess
from pathlib import Path

expected = Path('CLAUDE.md').read_text()
assert expected.strip(), '权威正文为空，不能用空串通过检查'
result = subprocess.run(
    ['codex', 'debug', 'prompt-input', 'instruction-entry-audit'],
    check=True, stdout=subprocess.PIPE, text=True,
)
items = json.loads(result.stdout)
matches = []
for index, item in enumerate(items):
    content = item.get('content', [])
    if not isinstance(content, list):
        continue
    body = '\n'.join(part.get('text', '') for part in content if isinstance(part, dict))
    if expected in body:
        matches.append(index)
assert matches, '完整正文未出现在原生输入；检查 override、cwd、入口和预算'
print('PASS: 完整项目正文在原生加载面可见；行为遵循尚未由本检查证明')
PY
```

先在已知未加载的隔离 cwd 上确认这项检查失败，再在正确 cwd 上确认通过；另以空正文确认它不能假通过。渲染器不可用、格式变化或正文未命中时报告未验证，不改成文件哈希检查冒充宿主证据。Claude Code 用当前 `/memory` 与 `/context` 核对来源和加载面；这些检查不建立模型行为结论。各宿主的入口与限额以当前官方合同及本机观测为准，不互相外推。

加载面通过后，选择一项受本次规则影响的真实任务，检验应该遵循和不应触发的结果；未运行模型时明确记录行为未验证。只初始化或渲染输入不能宣称遵循率提高。达到已声明验收边界后停止，不因为这次成功新增通用 hook 或扩展到未授权平台。

宿主入口依据：[Codex 自定义指令](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[Claude Code 项目指令](https://code.claude.com/docs/en/memory)。原生调试命令的支持和输出结构仍须用当前安装版本实测。

### 有界读取与证据完整性

先解析入口的真实路径，再按当前问题读相关节；需要核对两份是否有独有规则或整体重写时，完整读取目标文件。大文件先取得行数、字节数和哈希，再按工具内外层预算分段读取，不把多份长文拼进一次有上限的响应。记录已读范围；截断后只补未收到的范围，文件变化时重取基线。不能把“命令已运行”或文件长度当成全文已加载。

上述读取由执行 agent 按当前工具预算完成，不新增 hook、工具安装或跨 Skill 文件依赖。

## 替代机制探针

先读真实 hook 实现并确认探针不会触发实际外部动作；使用隔离样例，不执行被测命令本身。下方是历史上校准过的命令模板，须按当前宿主的实际事件字段和 matcher 校准健康/危险两侧。它不证明覆盖所有事件或未来运行存活。

**🚫 缩正文前必须实证「真有别的机制在强制吗」，禁止推断。**
把 L1 正文缩成「由 X 强制 + 指针」之前，构造一条真实的违规命令喂给 X，看它到底拦不拦：

```bash
# ① 名单从「注册表」来，不是从目录来（见下方两个坑）
python3 - <<'PY' > /tmp/registered-hooks.txt
import json, os
s = json.load(open(os.path.expanduser('~/.claude/settings.json')))
for ev, groups in (s.get('hooks') or {}).items():
    for g in groups:
        for h in g.get('hooks', []):
            print(ev, g.get('matcher', '*'), h.get('command', ''))
PY

# ② 从上面的名单里挑一条填进来。用变量而不是 <占位符> —— 在 shell 里 `<` 是重定向符，
#    整块粘贴会得到一个莫名的重定向错误，而不是「这里要你填」
# ⚠️ HOOK_CMD 必须是**数组**：写成字符串 + 不加引号展开 `$HOOK_CMD`，
#    bash 会词分割成「解释器 + 路径」，**zsh 不会**（整串当一个命令名 → exit 127）。
#    实测本块第一版就栽在这，与附录 C 的 REFDIRS 是同一个坑。
HOOK_CMD=(bash /绝对路径/那个hook.sh)      # ← 换成 registered-hooks.txt 里那条（注意它自己的解释器）
BAD_CMD='一条真实的违规命令'                # ← 换成你要试探的那条

# payload 必须完整——缺字段会让判决翻转（见下方第一个坑）
# ⚠️ 必须用 json.dumps 构造，**不能手搓字符串**：BAD_CMD 里只要有 `"` / `\` / 换行，
#    手搓出来就不是合法 JSON，fail-open 的 hook 会答 0 → 你得出「无人强制」并去删规则，
#    而它其实一直拦着。实测同一条含引号的违规命令：手搓 → exit 0，json.dumps → exit 2。
#    **而最典型的探针形状 `git commit -m "msg" --no-verify` 恰好就带引号。**
# ⚠️ 下面三道前置检查不能省。**这个探针所有的失败模式都指向「假放行」** ——
#    而假放行正是会让你去删掉一条其实有效的规则的那个方向（实测过的三种）：
#    ① 没有 python3 → 管道首段崩、hook 收到空 stdin → fail-open 答 0 → 打印「exit=0」
#    ② 只粘贴了探针行、漏掉上面两行赋值 → 同样打印「exit=0」（`set -u` 也救不回，
#       unbound 发生在管道首段的子 shell 里，脚本不死）
#    ③ 贴进 `set -euo pipefail` 脚本时，**hook 拦截（exit 2 = 阳性结果）会先杀死脚本**，
#       `echo` 根本执行不到 → strict 宿主里这个探针只可能打印出「放行」一种判决
command -v python3 >/dev/null || { echo "探针不可用：没有 python3（换机器或先装）" >&2; exit 9; }
: "${BAD_CMD:?探针不可用：BAD_CMD 未赋值——你大概只粘贴了下半段}"
[ "${#HOOK_CMD[@]}" -gt 0 ] || { echo "探针不可用：HOOK_CMD 未赋值" >&2; exit 9; }

# 用 if 包住：`if` 的条件位豁免 set -e，所以「拦截」这个阳性结果也打得出来
if BAD_CMD="$BAD_CMD" python3 -c 'import json,os,sys; sys.stdout.write(json.dumps({
  "hook_event_name":"PreToolUse","tool_name":"Bash",
  "tool_input":{"command":os.environ["BAD_CMD"]},
  "cwd":os.getcwd(),"session_id":"probe","transcript_path":"/dev/null"}))' \
  | "${HOOK_CMD[@]}" >/dev/null 2>&1
then ec=0; else ec=$?; fi
echo "exit=$ec   # 2 = 拦截（这条规则有人强制），0 = 放行"
```

**这个探针有两个会让你得出相反结论的坑，都实测踩过：**

- **payload 缺字段 → 判决翻转。** 真实事件还带 `cwd`/`session_id`/`transcript_path`/`hook_event_name`，
  很多 hook 读它们。实测同一条 `rm -rf important-data`：**不带 `cwd` → exit 0**（该 guard 的设计是
  「相对路径 + 无 cwd = 判不出，放行」），**带 `cwd` → exit 2**。用精简 payload 探，你会给一条
  **真的有防护**的规则判「无人强制」，然后动手拆掉它的正文。
- **枚举目录 ≠ 枚举注册表，而且两个方向都错。** 实测某机器：注册 28 条，其中 **1 条在 hooks 目录之外
  且是 `.py`**（拿 `bash` 跑它 → 语法错 → 非 2 → 被记成「没拦」＝**漏**）；目录里反而躺着一个
  `.json` 配置和一个陈旧的 `*.sh.bak-*`（被误当 hook 跑出 exit 2 → 记成「有人强制」＝**误**，
  于是授权你删掉真正在起作用的正文）。此外项目级 `.claude/settings.json`、plugin 自带 hook
  都不在那个目录里，而 `matcher` 决定某个 hook 根本不对这个工具开火。**权威源是 settings.json 的
  `hooks` 块（配合 `claude --debug`），不是 `ls` 一个目录。**

（hook 事件 schema / 注册方式 / exit 语义的完整说明见 `daymade-claude-code:claude-code-hooks` skill。）
**从「装了 N 个 hook」推断「这条被覆盖了」是最危险的一步** —— 若 X 其实不存在，你就
亲手拆掉了唯一在起作用的防线，还留下一句让后来者以为有保护的谎。实测比推断便宜得多
（详见 `references/progressive_disclosure_principles.md` 案例 18）。

## 验证器校准与引用检查

下方筛查命令只覆盖它明确解析的输入格式；对未知根、空格路径、裸文件名和零命中，要回到精确源文件与其相对路径上下文确认。不得因打印 `MISSING` 或 exit 0 就自动下结论。`SKILL.md` Step 5 的字节/语义/宿主/任务检查仍各自独立。

#### 5.0 先标定判据本身 —— 验证器会骗你，而且两个方向都会

下面 5a/5b 全建立在 `grep`/`find` 上。**一个错的判据会和对的判据一样自信地报告结果**，
而这一步的产物（「这段已经下沉了」「这个指针是真的」）会被当成事实写进交付。
所以：**先在一个你已知答案的样本上跑一遍判据，确认它真的会命中，再用它去查你不知道答案的。**
这一行成本，把「我查过了」变成「我用标定过的判据查过了」。

实测踩过的形态如下。**注意它们的坏法不一样**——多数是静默假阴性（0 命中被读成「内容丢了」），
但有一条给**假阳性**（为有损搬运开脱，最危险），还有一条是**响亮报错**（exit 2，在 `2>/dev/null` 的
脚本里同样被吞成「没找到」）。所以标定时**别只看有没有输出，要看 exit code**：

| 陷阱 | 症状 | 修法 |
|---|---|---|
| **递归搜索悄悄跳过 symlink** | reference 目录里只要有一个 symlink（**skill 安装、SSOT 外置极常见**），整片内容对验证器不可见 → 把「已下沉」误报成「未下沉」 | **别去挑递归 flag —— 先把路径解析成真身再读**：`readlink -f <path>` 拿到真实文件，或 `find -L <dir> -type f -name '*.md'` 枚举后逐个读（两种都不依赖任何实现，实测三种 grep + BSD/GNU find 行为一致）。⚠️ **递归 flag 的 symlink 语义因实现而异，且没有可移植组合**——挑哪个都会坑掉一部分读者；三实现实测矩阵见案例 17 ①，此处不复述数值（会漂） |
| **代理判据**（拿 A 的存在证明 B 已完成） | 用「日期锚点是否出现在 reference」判是否已下沉 —— 而 reference 的**节标题里带个日期**就让整段显示为「已下沉」，实际那节里一条子发现都没有 | 判据必须落在**被判对象本身**上：抽该段的 3–5 个**特异串**（具体值/命令/专名）逐个查 |
| **行级度量高估工作量** | 「含该锚点的整行」包含大量**不需搬**的规则正文，量到的是「含有它的行的总长」而非内容本身 | 按**段落**量，不按含关键词的行的字节数 |
| **`grep -F` 对多行原句退化成「按行 OR」**（唯一会给**假阳性**的一条，最危险） | 验 verbatim 搬运时，原句是多行的：`grep -F` 把它当成**多个独立 pattern**，命中任意一行就报成功。**搬运时丢了半个段落，判据照样报「还在」** —— 它为一次有损搬运出具了无罪证明，而这正是 5b 存在的理由 | 存原句到临时文件用 `python3 - <<'PY'` 做**整串子串判断**（`需要的原文 in 目标文件内容`）—— 它要求连续完整匹配，丢一行就 False。**必须 `python3`**：裸 `python` 在 stock macOS（12.3 起）已被移除。⚠️ 精简 Linux 镜像（如 `debian:*-slim`）**两个都没有**，实测 `python3` 也 ABSENT —— 那种环境下先装再用，别以为换成 `python3` 就一定跑得起来 |
| **探针串含正则元字符**（**三种**坏法，且同一字符换个位置就换一种） | 实测（BSD 2.6.0 / GNU 3.11）：① 中段 `*`（`use * wildcard`）→ 两边都 **静默** exit 1，长得就像「内容丢了」；② **开头的 `**`（markdown 粗体 —— CLAUDE.md 里最常见的探针形状）→ BSD **响亮报错** exit 2 `repetition-operator operand invalid`，而 GNU **exit 0 命中** —— 同一个串，一边硬错一边成功；③ 方括号日期 `[2026-07-26]` → 两边都 exit 2（BSD `invalid character range` / GNU `Invalid range end`）。**报错在 `2>/dev/null` 的脚本里和「没找到」长得一模一样。** | 一律 `grep -F`（固定串），或走上面的 python3 子串判断。**脚本里别把 stderr 丢掉** —— exit 2（判据坏了）和 exit 1（真没命中）必须分开处理 |

**⚠️ 别把「重新折行」算进上面第 4 行**：搬运时重新折行**本身就违反反模式 6「原样复制，不改一字」**，
判据判它失败是**对的**，不是误伤。python3 子串判断在这种情况下同样返回 False（实测）——
它不是用来给折行开脱的，**没有任何判据该给折行开脱**。

**完整战例（判据陷阱如何连环误导同一个执行者）→ `references/progressive_disclosure_principles.md` 案例 17**
（该案例覆盖上表前三行；第 4、5 行来自同期对判据本身的实测，无独立战例）。

**判据陷阱有第二层，比第一层更隐蔽**：不只**判据**会骗你，**修法**也会。
一个依赖具体实现的修法（换个 flag、加个选项）在你机器上验证通过，换台机器静默失效 ——
而你不会收到任何信号。**优先选不依赖实现的做法**（解析路径而非调递归 flag、
子串判断而非行级匹配）；实在要用 flag，就在**标准实现**（`/usr/bin/<tool>`）上复验一次。

> **这一条是在写它的过程中自己撞出来的**，所以它不是理论。为修上表第一行的 symlink 问题，
> 作者写了一段 `find -L` 的替代脚本 —— **在 bash 下完全正确，在 zsh 下把 4 个真实存在的
> 章节全报「NOT FOUND」**。原因是 `for d in $REFDIRS` 依赖词分割：bash 有，**zsh 没有**，
> 而 zsh 是现代 macOS 的默认登录 shell。改成数组 `"${ARR[@]}"` 后两个 shell 输出一致。
> **教训**：「修法也会骗你」不只跨 *工具实现*（BSD/GNU），还跨 ***shell***、跨 locale、跨版本。
> 所以定案标准不是「我跑通了」，是「**我在读者最可能用的那个环境里跑通了**」——
> 对 macOS 读者，那至少意味着 bash 和 zsh 各跑一遍。

**元规则**：本节几条的共同点不是「grep 用法要小心」，而是
**判据与被判对象之间只要隔了一层代理，缝隙里就能穿过去东西**。
写任何一条验证命令时问一句：*它测的到底是不是我想知道的那件事？*

#### 5a. 引用文件存在性

```bash
# 抓出正文里所有反引号包起来的 .md 路径（不写死 docs/references/——用户级布局是
# ~/.claude/references/，写死会一条都抓不到）
# 尾巴不能省，但**也不能写成 `|| true`**：
#   · 为什么需要：一条指针都没有时 grep exit 1。在 **`set -e` 与 `pipefail` 同时开**时
#     （单开任一个都不会）整条管道致命，整块在打印任何东西之前就死 —— 而「0 条」
#     正是下面要报的那种情况。实测：`set -o pipefail` 单开跑完、`set -e` 单开跑完、
#     `set -eo pipefail` 输出为空 exit 1。
#   · 为什么不能用 `|| true`：它把 grep 的 **exit 2（判据坏了，如 cwd 里根本没有 CLAUDE.md）**
#     和 **exit 1（真的 0 命中）** 一起吞掉，于是误报「抓到 0 条 + 🚨 模式没命中」还 exit 0 ——
#     正好违反本文件 5.0 表第 5 行「exit 2 和 exit 1 必须分开处理」。
#   · `|| [ $? -eq 1 ]` 只放行 exit 1；exit 2 仍然响亮致死（两 shell 实测）。
grep -oh '`[^`]*\.md`' CLAUDE.md | tr -d '`' | sort -u > /tmp/pointers.txt || [ $? -eq 1 ]

# ⚠️ 先标定：抓到 0 条 ≠ 全部通过，而是「这个模式没匹配上你的写法」
n=$(wc -l < /tmp/pointers.txt | tr -d ' ')     # BSD wc 会补空格，去掉
echo "抓到 $n 条指针"
# 用 if 而不是 `[ … ] && echo`：后者在 n>0 时整行 rc=1。
# ⚠️ 别把这说成「会中断 set -e 脚本」——实测 bash/zsh 都**不会**（POSIX 豁免 AND 列表
# 非末位的失败）。真正会出事的是它**作为最后一行**时把 rc=1 泄漏成整个脚本的退出码。
# 用 if 是 rc 中性的卫生做法，不是在修一个「中断」bug。
if [ "$n" -eq 0 ]; then
  echo "🚨 0 条 = 模式没命中，不是没问题——先手工确认正文到底怎么写引用的"
fi

while read -r f; do
  # ⚠️ 分「可判定 / 不可判定」，别把散文里的东西一律报成断链（见下方真实语料实测）
  case "$f" in
    *\**|*\?*)   echo "– 跳过(glob):      $f"; continue ;;
    *\<*|*\>*)   echo "– 跳过(模板占位):  $f"; continue ;;
    *" "*)       echo "– 跳过(含空格,散文): $f"; continue ;;
    */*)         ;;
    *)           echo "– 跳过(裸文件名,无根): $f"; continue ;;
  esac
  case "$f" in
    /*|\~/*|./*) p="${f/#\~/$HOME}" ;;   # 绝对 / 家目录 / 显式相对 → 可判定
    *)  # 相对路径：首段在 cwd 里存在才可判定。**这条不能省** ——
        # Step 3 规定的命名就是 `docs/references/{主题}-sop.md`（无 ./ 前缀），
        # 一律当「未知根」跳过 = 5a 对本 skill 自己规定的布局一条都不检
        first="${f%%/*}"
        if [ -d "$first" ]; then p="$f"
        else echo "– 跳过(相对未知根): $f"; continue; fi ;;
  esac
  [ -e "$p" ] && echo "✓ $f" || echo "✗ MISSING: $f"
done < /tmp/pointers.txt
```

> **为什么要那段标定**：原版把 `docs/references/` 写死在模式里。在本 skill 自己定义的
> 用户级布局（`~/.claude/references/`）上跑，它匹配 0 条 → while 循环一次都不进 →
> **零输出、exit 0**，和「所有引用都存在」的输出**完全一样**。实测：一份含真断链的
> CLAUDE.md 被它判为干净。这正是 5.0 那条「`0 命中` 必须双向读」，而 5a 自己没做。
>
> **为什么要分「可判定 / 不可判定」**：这段的第一版**只在合成 fixture 上验过**、全绿。
> 拿**真实语料**（一份 120KB 的全局 CLAUDE.md）一跑，32 条候选里 **10 条「MISSING」是误报** ——
> 散文里提到的裸文件名（`incident-2026-04-18-*.md`）、glob（`*/memory/*.md`）、
> 带占位符的模板（`<config>/…`），以及一对被反引号连在一起、中间有箭头的两个路径。
> 按本 skill 自己的规矩：**误杀健康输入比漏报更糟** —— 31% 的误报率会直接训练读者忽略这个检查。
> 分类后：可判定 21 条全部正确，不可判定 11 条单独列出待人工确认，**误报 0**。
> 而那一轮**真的抓到 1 条断链**（指向的 memory 文件被挪进了 `.memory-archive-*` dot 目录，
> 且路径大小写也变了）—— 合成 fixture 永远造不出这种形状。
>
> 本段命令已在 **bash 与 zsh 下各跑一遍、输出字节一致**。
> **为什么要跨 shell 验**：见附录 C 里那个「字符串 + 词分割」的坑 —— 同一段脚本
> bash 全对、zsh 全错，而 zsh 是现代 macOS 的默认 shell。

