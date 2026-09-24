#!/usr/bin/env python3
"""reconcile_content_diff.py — 合并/重写报告页后的可见信息点对账（防静默丢内容）。

用法:
    uv run --python 3.12 scripts/reconcile_content_diff.py 旧版1.html [旧版2.html ...] 新版.html

最后一个参数是新版，前面全部是旧版（git 历史版可先 `git show <ref>:<path> > /tmp/old.html` 导出）。

原理: 用 Chrome 打开每个 HTML，在 load 后逐个检查文本节点的计算样式、Range
几何、文档边界和 overflow clipping，再从保留下来的节点读取 `innerText`。comment、
script、hidden、aria-hidden、透明/零字号文本、display/visibility 隐藏、零高裁切和
移出文档画布的副本都不能冒充保留。随后抽取「含中文的文本片段」与显著数字，逐个
检查是否仍在新版的初始渲染文本中。共享/CI 环境用
`CHROME_BIN=/absolute/path/to/managed-chrome` 固定浏览器。

边界: 这是「初始渲染状态」对账，不会自动点击 tab、accordion 或执行业务旅程。
交互后才出现的承重内容仍须用页面 Journey/browser harness 遍历目标状态；脚本输出
本来就是候选清单，不能单独证明整页内容完整。

输出是**候选清单、不是判决**——逐条人工判去向:
有意改写（旧句被加长/换说法，子串断了）/ 搬运（挪位置且改写）/ 导航压缩 /
死代码清理 / 自指失效（合并后无意义的互链）/ **真丢失（需要补回）**。

退出码: 0=无候选; 1=有候选待判; 2=用法或读文件错误。
"""
from html.parser import HTMLParser
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

# 中文起头、后续允许夹带数字/字母/常用标点的片段
CJK_RUN = re.compile(
    r"[一-鿿][一-鿿0-9A-Za-z×÷%·、，。：；？！“”‘’《》（）.+=≈<>/ -]*"
)
# 3 位以上独立数字（业务数；更短的数字噪音太大不收）
NUM_TOKEN = re.compile(r"(?<![\w.])\d{3,}(?:\.\d+)?(?![\w.])")
HARVEST_ID = "rwh-visible-text"
HARVEST_SCRIPT = r"""
<script id="rwh-visible-text-harvester">
(() => {
  let harvested = false;
  function alphaIsZero(color) {
    if (!color) return false;
    if (color === 'transparent') return true;
    const match = color.match(/^rgba?\((.*)\)$/i);
    if (!match) return false;
    const parts = match[1].replace(/\//g, ',').split(/[,\s]+/).filter(Boolean);
    return parts.length >= 4 && Number.parseFloat(parts[3]) === 0;
  }
  function overlaps(a, b, axis) {
    return axis === 'x'
      ? a.right > b.left && a.left < b.right
      : a.bottom > b.top && a.top < b.bottom;
  }
  function opacityFilterIsHidden(filter) {
    const match = filter && filter.match(/(?:^|\s)opacity\(([^)]+)\)/i);
    if (!match) return false;
    const raw = match[1].trim();
    const opacity = raw.endsWith('%')
      ? Number.parseFloat(raw) / 100
      : Number.parseFloat(raw);
    return Number.isFinite(opacity) && opacity <= 0.01;
  }
  function clipPathIsHidden(clipPath, element) {
    if (!clipPath || clipPath === 'none') return false;
    const bounds = element.getBoundingClientRect();
    const circle = clipPath.match(/^circle\(\s*([^\s)]+)/i);
    if (circle) {
      const radius = circle[1].endsWith('%')
        ? Math.min(bounds.width, bounds.height) * Number.parseFloat(circle[1]) / 100
        : Number.parseFloat(circle[1]);
      return Number.isFinite(radius) && radius <= 1;
    }
    const inset = clipPath.match(/^inset\(\s*([^)]*?)(?:\s+round\s+.*)?\)$/i);
    if (inset) {
      const tokens = inset[1].trim().split(/\s+/);
      const expanded = tokens.length === 1
        ? [tokens[0], tokens[0], tokens[0], tokens[0]]
        : tokens.length === 2
          ? [tokens[0], tokens[1], tokens[0], tokens[1]]
          : tokens.length === 3
            ? [tokens[0], tokens[1], tokens[2], tokens[1]]
            : tokens.slice(0, 4);
      if (expanded.length === 4) {
        const toPixels = (token, size) => token.endsWith('%')
          ? size * Number.parseFloat(token) / 100
          : Number.parseFloat(token);
        const top = toPixels(expanded[0], bounds.height);
        const right = toPixels(expanded[1], bounds.width);
        const bottom = toPixels(expanded[2], bounds.height);
        const left = toPixels(expanded[3], bounds.width);
        if ([top, right, bottom, left].every(Number.isFinite)) {
          const visibleWidth = Math.max(0, bounds.width - left - right);
          const visibleHeight = Math.max(0, bounds.height - top - bottom);
          const originalArea = bounds.width * bounds.height;
          return originalArea <= 0 || visibleWidth * visibleHeight / originalArea <= 0.01;
        }
      }
    }
    return false;
  }
  function textNodeIsVisible(node) {
    if (!node.nodeValue || !node.nodeValue.trim()) return true;
    const textStyle = getComputedStyle(node.parentElement);
    if (
      textStyle.visibility === 'hidden'
      || textStyle.visibility === 'collapse'
      || Number.parseFloat(textStyle.fontSize) === 0
      || (alphaIsZero(textStyle.webkitTextFillColor || textStyle.color)
        && textStyle.textShadow === 'none')
    ) return false;

    let element = node.parentElement;
    while (element) {
      const style = getComputedStyle(element);
      if (
        element.hidden
        || element.getAttribute('aria-hidden') === 'true'
        || style.display === 'none'
        || style.contentVisibility === 'hidden'
        || Number.parseFloat(style.opacity) <= 0.01
        || opacityFilterIsHidden(style.filter)
        || style.clip === 'rect(0px, 0px, 0px, 0px)'
        || clipPathIsHidden(style.clipPath, element)
      ) return false;
      element = element.parentElement;
    }

    const range = document.createRange();
    range.selectNodeContents(node);
    const rects = Array.from(range.getClientRects()).filter(
      (rect) => rect.width > 0 && rect.height > 0
    );
    range.detach();
    if (!rects.length) return false;

    const doc = document.documentElement;
    const page = {
      left: -window.scrollX,
      top: -window.scrollY,
      right: Math.max(doc.clientWidth, doc.scrollWidth) - window.scrollX,
      bottom: Math.max(doc.clientHeight, doc.scrollHeight) - window.scrollY
    };
    return rects.some((rect) => {
      if (!overlaps(rect, page, 'x') || !overlaps(rect, page, 'y')) return false;
      let ancestor = node.parentElement;
      while (ancestor && ancestor !== document.body && ancestor !== doc) {
        const style = getComputedStyle(ancestor);
        const bounds = ancestor.getBoundingClientRect();
        const overflowX = style.overflowX;
        const overflowY = style.overflowY;
        if (['hidden', 'clip'].includes(overflowX) && !overlaps(rect, bounds, 'x')) return false;
        if (['hidden', 'clip'].includes(overflowY) && !overlaps(rect, bounds, 'y')) return false;
        ancestor = ancestor.parentElement;
      }
      return true;
    });
  }
  function harvest() {
    if (harvested || !document.body) return;
    harvested = true;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);
    textNodes.forEach((node) => {
      if (!textNodeIsVisible(node)) node.nodeValue = '';
    });
    const readerText = document.body.innerText;
    // 只追加收割节点，不重写 document.documentElement：解析器只取这个 <pre>，
    // 而在 load 的同步 handler 里替换整棵文档树会与 --dump-dom 的导出时机竞态，
    // 表现为 Chrome 间歇性挂住（实测约 1/4，与页面大小无关）。
    const out = document.createElement('pre');
    out.id = 'rwh-visible-text';
    out.textContent = readerText;
    document.body.appendChild(out);
  }
  // 必须在 load 的同步 handler 里收割：--dump-dom 在 load 之后立即 dump，
  // 而 requestAnimationFrame 要等下一帧、赶不上（曾靠 --virtual-time-budget
  // 让 setTimeout 立即触发来绕开，但该 flag 在 Chrome 150 headless 下会永久挂起）。
  // getComputedStyle 本身强制同步布局，所以此处不需要等帧也能拿到最终可见性。
  window.addEventListener('load', harvest, {once: true});
  setTimeout(harvest, 2000);   // 兜底：仅在有别的驱动方式（非 --dump-dom）时才会轮到它
})();
</script>
"""

CHROME_TIMEOUT_SECONDS = 60
CHROME_ATTEMPTS = 2
OWNED_PROCESS_CLEANUP_SECONDS = 2
RECONCILE_INPUT_COUNT = 2
RECONCILE_STARTUP_MARGIN_SECONDS = 12


def reconcile_cli_timeout_seconds(
    *,
    chrome_timeout: float = CHROME_TIMEOUT_SECONDS,
    attempts: int = CHROME_ATTEMPTS,
    input_count: int = RECONCILE_INPUT_COUNT,
    cleanup_timeout: float = OWNED_PROCESS_CLEANUP_SECONDS,
    startup_margin: float = RECONCILE_STARTUP_MARGIN_SECONDS,
) -> float:
    """Outer timeout budget for the CLI's two independently retried inputs."""
    return input_count * attempts * (chrome_timeout + cleanup_timeout) + startup_margin


class HarvestParser(HTMLParser):
    """Extract the browser-generated harvest node and nothing else."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._parts: list[str] = []
        self.found = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {name.lower(): (value or "") for name, value in attrs}
        if self._depth:
            self._depth += 1
        elif tag.lower() == "pre" and attrs_map.get("id") == HARVEST_ID:
            self._depth = 1
            self.found = True

    def handle_endtag(self, tag: str) -> None:
        if self._depth:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._depth:
            self._parts.append(data)

    def text(self) -> str:
        lines = [
            re.sub(r"[ \t\f\v]+", " ", line).strip()
            for line in "".join(self._parts).splitlines()
        ]
        return "\n".join(line for line in lines if line)


def chrome_binary() -> str:
    override = os.environ.get("CHROME_BIN")
    if override:
        path = Path(override)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        raise RuntimeError(f"CHROME_BIN 不可执行: {override}")
    mac = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if mac.is_file() and os.access(mac, os.X_OK):
        return str(mac)
    for name in ("google-chrome", "chromium", "chromium-browser"):
        if candidate := shutil.which(name):
            return candidate
    raise RuntimeError("找不到 Chrome；共享/CI 环境请显式设置 CHROME_BIN。")


def load(path: Path) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"❌ 文件不存在: {path}", file=sys.stderr)
        sys.exit(2)
    except UnicodeDecodeError:
        # fail-fast: 读不出就报错退出，不拿残缺数据继续对账（结论会假阴）
        print(f"❌ 非 UTF-8、读不出: {path}", file=sys.stderr)
        sys.exit(2)


def inject_harvester(text: str) -> str:
    doctype = re.match(r"(?is)(\s*<!doctype[^>]*>)", text)
    if doctype:
        return text[: doctype.end()] + HARVEST_SCRIPT + text[doctype.end() :]
    return HARVEST_SCRIPT + text


def run_in_own_process_group(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    """Run one command and always reap the process group created for it."""
    process = subprocess.Popen(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    # start_new_session makes the direct child the process-group leader. Record the
    # identifier immediately; TimeoutExpired does not expose it.
    process_group = process.pid
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        original_error = sys.exc_info()[1]
        cleanup_error: BaseException | None = None
        # The direct child may have exited while a renderer still holds the pipes,
        # or an interrupt may have unwound communicate(). The group remains ours.
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError as exc:
            cleanup_error = exc
        try:
            process.communicate(timeout=OWNED_PROCESS_CLEANUP_SECONDS / 2)
        except subprocess.TimeoutExpired as exc:
            cleanup_error = cleanup_error or exc
            if process.poll() is None:
                process.kill()
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
            try:
                process.wait(timeout=OWNED_PROCESS_CLEANUP_SECONDS / 2)
            except subprocess.TimeoutExpired as wait_exc:
                cleanup_error = cleanup_error or wait_exc
        except (OSError, ValueError) as exc:
            cleanup_error = cleanup_error or exc
        if cleanup_error is not None and original_error is None:
            raise cleanup_error


def visible_text(path_text: str) -> str:
    path = Path(path_text).resolve()
    source = load(path)
    try:
        chrome = chrome_binary()
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(2)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=".rwh-reconcile-",
            suffix=".html",
            dir=path.parent,
            delete=False,
        ) as handle:
            handle.write(inject_harvester(source))
            temp_path = Path(handle.name)
        # Chrome headless 偶发挂起（实测 2026-08-03 约 1/12，与页面大小无关，非确定性
        # 失败）——所以只对「超时」这一种失败重试，其余（Chrome 找不到、参数错、退出码
        # 非零）一次即报，不用重试掩盖真问题。不重试的话这道闸门会偶尔无故变红，而偶尔
        # 变红的闸门会训练出反射性绕过，比没有闸门更糟。
        attempts = CHROME_ATTEMPTS
        for attempt in range(1, attempts + 1):
            with tempfile.TemporaryDirectory(prefix="rwh-reconcile-profile-") as profile:
                try:
                    result = run_in_own_process_group(
                        [
                            chrome,
                            "--headless",
                            "--disable-gpu",
                            "--no-sandbox",
                            "--allow-file-access-from-files",
                            f"--user-data-dir={profile}",
                            "--run-all-compositor-stages-before-draw",
                            # 不加 --virtual-time-budget：Chrome 150 headless 下它会让进程
                            # 永久挂起（实测 2026-08-03，裸 --dump-dom 秒退、加该 flag 必被
                            # timeout 杀）。收割改在 load 的同步 handler 里做，见上方注入脚本。
                            "--dump-dom",
                            temp_path.as_uri(),
                        ],
                        timeout=CHROME_TIMEOUT_SECONDS,
                    )
                    break
                except subprocess.TimeoutExpired:
                    if attempt < attempts:
                        print(
                            f"⚠️  Chrome 提取超时，重试一次（{attempt}/{attempts}）: {path}",
                            file=sys.stderr,
                        )
                        continue
                    print(
                        f"❌ Chrome 提取可见文本连续 {attempts} 次超时: {path}\n"
                        "   两种成因，别混为一谈：\n"
                        "   · 偶发挂起——再跑一次通常就过。\n"
                        "   · 该输入稳定挂——同一文件连续多轮都超时，就不是偶发。已知有这类\n"
                        "     输入存在（2026-08-04 实测：数个纯英文测试页 5 次尝试 100% 超时，\n"
                        "     而同量级中文页 100% 通过；根因未定位，不是进程残留、不是页面大小、\n"
                        "     不是 DOCTYPE 缺失，这三项都已排除）。撞上这种输入时，本工具给不出\n"
                        "     结论——**当作「没有对账」处理，不要当作「没有丢失」**。",
                        file=sys.stderr,
                    )
                    sys.exit(2)
    except OSError as exc:
        print(f"❌ 无法创建临时浏览器副本: {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        print(f"❌ Chrome 提取可见文本失败: {path}", file=sys.stderr)
        if detail:
            print(detail[-2000:], file=sys.stderr)
        sys.exit(2)

    parser = HarvestParser()
    try:
        parser.feed(result.stdout)
        parser.close()
    except Exception as exc:
        print(f"❌ Chrome 输出解析失败: {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    reader_text = parser.text()
    if not parser.found:
        print(
            f"❌ 页面没有产出可见文本标记（脚本被 CSP/页面逻辑阻断）: {path}",
            file=sys.stderr,
        )
        sys.exit(2)
    return reader_text


def fragments(reader_text: str) -> set[str]:
    out: set[str] = set()
    for run in CJK_RUN.findall(reader_text):
        run = run.strip(" ")
        if len(run) >= 2:
            out.add(run)
    out.update(NUM_TOKEN.findall(reader_text))
    return out


def main(argv: list) -> None:
    if len(argv) < 3:
        print(__doc__)
        sys.exit(2)
    *old_paths, new_path = argv[1:]
    new_text = visible_text(new_path)
    total = 0
    thin = []          # 抽取过少的文件——这个 ✅ 对它们没有判别力
    for op in old_paths:
        frags = fragments(visible_text(op))
        if len(frags) < 20:
            thin.append((op, len(frags)))
        lost = [f for f in sorted(frags, key=len, reverse=True) if f not in new_text]
        total += len(lost)
        # 抽取数必须逐文件报：抽取器只收 CJK 起始的连续串，一张英文页上它几乎抽不到
        # 东西，于是「删光了正文」和「什么都没删」输出完全相同。而按总数报又会让
        # 「一个文件抽空、另一个正常」被平均掉。
        print(f"=== {op}: 抽到 {len(frags)} 个可见片段，其中 {len(lost)} 个在新版找不到 ===")
        for x in lost:
            print("  •", x[:110])
    if thin:
        for op, k in thin:
            print(
                f"⚠️  {op} 只抽到 {k} 个片段——抽取器按 CJK 起始的连续串取样，非中文页面会"
                "几乎抽空。对这个文件，下面的结论只说明「没东西可比」，不说明「没丢内容」。",
                file=sys.stderr,
            )
    if total == 0:
        print("✅ 上列各文件抽到的片段，全部能在新版初始渲染文本中找到（子串级）。")
    else:
        print(f"\n共 {total} 个候选——这是清单不是判决：逐条判去向，真丢的补回新版。")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main(sys.argv)
