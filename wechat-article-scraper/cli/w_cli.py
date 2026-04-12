#!/usr/bin/env python3
"""
微信文章抓取助手 CLI
World-class WeChat Article Scraper Command Line Interface
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Optional, List
from enum import Enum
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich import box

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

app = typer.Typer(
    name="w",
    help="微信文章抓取助手 - World-class WeChat Article Scraper",
    rich_markup_mode="rich",
)

console = Console()

# Config management
CONFIG_DIR = Path.home() / ".wechat-scraper"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


class OutputFormat(str, Enum):
    markdown = "markdown"
    html = "html"
    json = "json"
    pdf = "pdf"


class Strategy(str, Enum):
    auto = "auto"
    fast = "fast"
    adaptive = "adaptive"
    stable = "stable"
    reliable = "reliable"
    zero_dep = "zero_dep"
    jina_ai = "jina_ai"


def init_config():
    """Initialize config directory"""
    CONFIG_DIR.mkdir(exist_ok=True)
    if not CONFIG_FILE.exists():
        default_config = """# 微信文章抓取助手配置
default_format: markdown
default_strategy: auto
download_images: false
output_dir: ~/Downloads/wechat-articles

# 监控默认设置
monitor:
  interval: 3600  # 秒
  max_articles: 10

# API 配置（用于 AI 摘要等）
api:
  openai: null
  deepseek: null
"""
        CONFIG_FILE.write_text(default_config, encoding="utf-8")


@app.callback()
def callback():
    """微信文章抓取助手 CLI"""
    init_config()


@app.command("scrape")
def scrape(
    url: str = typer.Argument(..., help="微信文章 URL"),
    format: OutputFormat = typer.Option(OutputFormat.markdown, "--format", "-f", help="输出格式"),
    strategy: Strategy = typer.Option(Strategy.auto, "--strategy", "-s", help="抓取策略"),
    download_images: bool = typer.Option(False, "--images", "-i", help="下载图片"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出文件路径"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细输出"),
    auth: Optional[str] = typer.Option(None, "--auth", "-a", help="使用已保存的微信登录态"),
):
    """抓取单篇微信文章"""
    auth_status = f"[green]{auth}[/]" if auth else "[dim]未使用[/]"
    console.print(Panel.fit(
        f"[bold blue]开始抓取文章[/]\n"
        f"URL: {url}\n"
        f"策略: [green]{strategy.value}[/] | "
        f"格式: [green]{format.value}[/] | "
        f"下载图片: [green]{'是' if download_images else '否'}[/] | "
        f"登录态: {auth_status}",
        title="wechat-scraper",
        border_style="blue"
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("正在抓取...", total=None)

        # Import and run scraper
        try:
            from router import StrategyRouter, Strategy as RouterStrategy

            strategy_map = {
                Strategy.auto: None,
                Strategy.fast: RouterStrategy.FAST,
                Strategy.adaptive: RouterStrategy.ADAPTIVE,
                Strategy.stable: RouterStrategy.STABLE,
                Strategy.reliable: RouterStrategy.RELIABLE,
            }

            router = StrategyRouter()
            router_strategy = strategy_map.get(strategy)

            # 如果使用 stable 策略且有登录态，使用 playwright_scraper 直接抓取
            if auth and router_strategy == RouterStrategy.STABLE:
                import subprocess
                cmd = [
                    sys.executable,
                    str(Path(__file__).parent.parent / "scripts" / "playwright_scraper.py"),
                    url,
                    "--auth", auth,
                    "--auth-dir", "./data/auth"
                ]
                if verbose:
                    cmd.append("--verbose")

                result_json = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120
                ).stdout

                result = json.loads(result_json) if result_json else None
            else:
                # 使用 router 抓取
                route_result = router.route(url, prefer_strategy=router_strategy)
                result = route_result.data if route_result.success else None
                if not route_result.success:
                    raise Exception(route_result.error)

            progress.update(task, completed=True)

        except Exception as e:
            console.print(f"[red]抓取失败: {e}[/]")
            raise typer.Exit(1)

    # Format output
    if result:
        table = Table(title="文章信息", box=box.ROUNDED)
        table.add_column("字段", style="cyan")
        table.add_column("值", style="green")

        # 基本信息
        table.add_row("标题", result.get("title", "N/A"))
        table.add_row("作者", result.get("author", "N/A"))
        table.add_row("发布时间", result.get("publishTime", result.get("publish_time", "N/A")))

        # 互动数据（如果存在）
        engagement = result.get("engagement", {})
        if engagement:
            read_count = engagement.get("readCount", "N/A")
            like_count = engagement.get("likeCount", "N/A")
            watch_count = engagement.get("watchCount", "N/A")  # 在看数
            comment_count = engagement.get("commentCount", "N/A")

            table.add_row("阅读量", str(read_count) if read_count else "[dim]需登录[/]")
            table.add_row("点赞数", str(like_count) if like_count else "[dim]需登录[/]")
            if watch_count:
                table.add_row("在看数", str(watch_count))
            if comment_count:
                table.add_row("评论数", str(comment_count))

            # 显示 WCI 指数（如果有）
            wci = result.get("wci_score")
            if wci:
                table.add_row("WCI 指数", f"[bold cyan]{wci}[/]")
        else:
            # 兼容旧格式
            table.add_row("阅读量", str(result.get("read_count", "N/A")))
            table.add_row("点赞数", str(result.get("like_count", "N/A")))

        # 内容统计
        content = result.get("content", "")
        table.add_row("字数", str(len(content)))
        images = result.get("images", [])
        table.add_row("图片数", str(len(images)))
        videos = result.get("videos", [])
        if videos:
            table.add_row("视频数", str(len(videos)))

        console.print(table)

        # Save to file
        if output:
            output_path = Path(output).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if format == OutputFormat.json:
                output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                output_path.write_text(result.get("content", ""), encoding="utf-8")

            console.print(f"\n[green]已保存到: {output_path}[/]")
    else:
        console.print("[red]未能获取文章内容[/]")


@app.command("batch")
def batch(
    urls_file: Path = typer.Argument(..., help="包含 URLs 的文件路径"),
    output_dir: Path = typer.Option(
        Path.home() / "Downloads/wechat-articles",
        "--output-dir", "-o",
        help="输出目录"
    ),
    format: OutputFormat = typer.Option(OutputFormat.markdown, "--format", "-f"),
    strategy: Strategy = typer.Option(Strategy.auto, "--strategy", "-s"),
    workers: int = typer.Option(3, "--workers", "-w", help="并发数"),
    download_images: bool = typer.Option(False, "--images", "-i"),
):
    """批量抓取文章"""
    urls_path = Path(urls_file).expanduser()

    if not urls_path.exists():
        console.print(f"[red]文件不存在: {urls_path}[/]")
        raise typer.Exit(1)

    urls = [line.strip() for line in urls_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]

    console.print(Panel.fit(
        f"[bold blue]批量抓取模式[/]\n"
        f"URLs: [green]{len(urls)}[/] 个\n"
        f"并发数: [green]{workers}[/] | "
        f"输出目录: [green]{output_dir}[/]",
        title="wechat-scraper batch",
        border_style="blue"
    ))

    output_dir = Path(output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[yellow]正在开发中，当前将按顺序处理 {len(urls)} 个 URL...[/]")


@app.command("search")
def search(
    keyword: str = typer.Argument(..., help="搜索关键词"),
    limit: int = typer.Option(10, "--limit", "-n", help="结果数量"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
    semantic: bool = typer.Option(False, "--semantic", "-s", help="使用语义搜索"),
):
    """搜索微信文章（支持语义搜索）"""
    if semantic:
        console.print(f"[blue]语义搜索: [bold]{keyword}[/][/]")
        console.print(f"[dim]限制: {limit} 条结果 | 模式: [cyan]语义理解[/][/]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="语义搜索中...", total=None)

            try:
                from semantic_search import SemanticSearch
                searcher = SemanticSearch()
                results = searcher.search(keyword, top_k=limit)
            except Exception as e:
                console.print(f"[red]语义搜索失败: {e}[/]")
                raise typer.Exit(1)

        if results:
            table = Table(title=f"语义搜索结果: {keyword}", box=box.ROUNDED)
            table.add_column("#", style="dim", width=3)
            table.add_column("标题", style="cyan", max_width=35)
            table.add_column("公众号", style="green")
            table.add_column("相似度", style="magenta")
            table.add_column("关键词", style="yellow", max_width=20)

            for i, r in enumerate(results, 1):
                keywords = ", ".join(r.matched_keywords[:3]) if r.matched_keywords else "-"
                table.add_row(
                    str(i),
                    r.title[:35],
                    r.account_name,
                    f"{r.similarity_score:.1%}",
                    keywords
                )

            console.print(table)
            console.print(f"\n[dim]找到 {len(results)} 个语义相关结果[/]")
        else:
            console.print("[yellow]未找到相关结果[/]")
            console.print("[dim]提示: 尝试先用 `w semantic index` 索引文章[/]")

    else:
        # 原有搜狗搜索逻辑
        console.print(f"[blue]搜索关键词: [bold]{keyword}[/][/]")
        console.print(f"[dim]限制: {limit} 条结果 | 模式: [cyan]关键词匹配[/][/]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("正在搜索...", total=None)

            try:
                from export import search_articles_via_sogou

                results = search_articles_via_sogou(keyword, limit=limit)
                progress.update(task, completed=True)

            except Exception as e:
                console.print(f"[red]搜索失败: {e}[/]")
                raise typer.Exit(1)

        if results:
            table = Table(title=f"搜索结果: {keyword}", box=box.ROUNDED)
            table.add_column("#", style="dim", width=3)
            table.add_column("标题", style="cyan", max_width=40)
            table.add_column("公众号", style="green")
            table.add_column("发布时间", style="yellow")
            table.add_column("URL", style="dim", max_width=30)

            for i, article in enumerate(results, 1):
                table.add_row(
                    str(i),
                    article.get("title", "N/A")[:40],
                    article.get("author", "N/A"),
                    article.get("publish_time", ""),
                    article.get("url", "")[:30] + "..."
                )

            console.print(table)

            if output:
                output_path = Path(output).expanduser()
                output_path.write_text(
                    json.dumps(results, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                console.print(f"\n[green]已保存到: {output_path}[/]")
        else:
            console.print("[yellow]未找到结果[/]")


@app.command("auth")
def auth(
    action: str = typer.Argument(..., help="操作: login/list/verify/delete"),
    account: Optional[str] = typer.Argument(None, help="账号标识"),
    headless: bool = typer.Option(False, "--headless", help="无头模式登录"),
):
    """管理微信登录态（用于抓取阅读/点赞数）"""
    from wechat_auth import WeChatAuthManager

    auth_dir = Path("./data/auth")
    auth_manager = WeChatAuthManager(str(auth_dir))

    if action == "list":
        accounts = auth_manager.list_accounts()
        if not accounts:
            console.print("[yellow]没有保存的登录态[/]")
            console.print("[dim]使用 'w auth login <账号名>' 添加登录态[/]")
        else:
            table = Table(title="已保存的微信登录态", box=box.ROUNDED)
            table.add_column("账号", style="cyan")
            table.add_column("状态", style="green")
            table.add_column("创建时间", style="dim")
            table.add_column("最后使用", style="dim")

            for acc in accounts:
                status = "[green]✓ 有效[/]" if acc['is_valid'] else "[red]✗ 无效[/]"
                table.add_row(
                    acc['name'],
                    status,
                    acc['created_at'][:10],
                    acc['last_used_at'][:10]
                )
            console.print(table)

    elif action == "login":
        if not account:
            console.print("[red]请提供账号标识，例如: w auth login 个人号[/]")
            raise typer.Exit(1)

        console.print(Panel.fit(
            f"[bold blue]微信登录[/]\n"
            f"账号: [cyan]{account}[/]\n"
            f"模式: [{'无头' if headless else '可视化'}]\n\n"
            "[yellow]请使用微信扫描浏览器中显示的二维码[/]",
            title="wechat-auth"
        ))

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(description="等待登录完成...", total=None)
                session = auth_manager.login_with_qrcode(
                    account,
                    headless=headless,
                    timeout=120
                )

            console.print(f"[green]✓ 登录成功: {session.account_name}[/]")
            console.print(f"[dim]过期时间: {session.expires_at[:10]}[/]")

        except TimeoutError:
            console.print("[red]✗ 登录超时，请重试[/]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]✗ 登录失败: {e}[/]")
            raise typer.Exit(1)

    elif action == "verify":
        if not account:
            console.print("[red]请提供账号标识[/]")
            raise typer.Exit(1)

        console.print(f"正在验证 [cyan]{account}[/]...")
        is_valid = auth_manager.verify_session(account)

        if is_valid:
            console.print(f"[green]✓ 登录态有效: {account}[/]")
        else:
            console.print(f"[red]✗ 登录态无效或已过期: {account}[/]")
            console.print("[dim]请重新登录: w auth login {account}[/]")

    elif action == "delete":
        if not account:
            console.print("[red]请提供账号标识[/]")
            raise typer.Exit(1)

        if auth_manager.delete_session(account):
            console.print(f"[green]✓ 已删除: {account}[/]")
        else:
            console.print(f"[yellow]账号不存在: {account}[/]")

    else:
        console.print(f"[red]未知操作: {action}[/]")
        console.print("[dim]可用操作: login, list, verify, delete[/]")


@app.command("config")
def config(
    show: bool = typer.Option(False, "--show", "-s", help="显示当前配置"),
    edit: bool = typer.Option(False, "--edit", "-e", help="编辑配置文件"),
):
    """管理配置"""
    if show:
        if CONFIG_FILE.exists():
            content = CONFIG_FILE.read_text(encoding="utf-8")
            console.print(Panel(content, title="配置文件", border_style="blue"))
        else:
            console.print("[yellow]配置文件不存在，使用默认配置[/]")

    if edit:
        editor = os.environ.get("EDITOR", "vim")
        try:
            subprocess.run([editor, str(CONFIG_FILE)], check=False)
        except FileNotFoundError:
            console.print(f"[red]编辑器未找到: {editor}[/]")
            raise typer.Exit(1)

    if not show and not edit:
        console.print(f"[dim]配置文件位置: {CONFIG_FILE}[/]")
        console.print("[dim]使用 --show 查看, --edit 编辑[/]")


@app.command("monitor")
def monitor(
    action: str = typer.Argument(..., help="操作: add/list/remove/check/watch/stats"),
    name: Optional[str] = typer.Argument(None, help="公众号名称或标识"),
    interval: int = typer.Option(3600, "--interval", "-i", help="检查间隔(秒)"),
):
    """管理公众号监控订阅 (v1.0 基础版)"""
    from monitor import SubscriptionManager

    manager = SubscriptionManager()

    if action == "list":
        subs = manager.list_subscriptions()
        if not subs:
            console.print("[yellow]暂无订阅[/]")
            return

        table = Table(title="公众号监控订阅", box=box.ROUNDED)
        table.add_column("公众号", style="cyan")
        table.add_column("微信号", style="dim")
        table.add_column("最后检查", style="yellow")
        table.add_column("最新文章", style="green", max_width=30)

        for s in subs:
            table.add_row(
                s.account_name,
                s.wechat_id or "-",
                s.last_check[:10] if s.last_check else "从未",
                (s.last_article_title or "-")[:30]
            )
        console.print(table)

    elif action == "add":
        if not name:
            console.print("[red]请提供公众号名称[/]")
            raise typer.Exit(1)
        if manager.add_subscription(name):
            console.print(f"[green]✓ 已添加订阅: {name}[/]")
        else:
            console.print(f"[yellow]已存在订阅: {name}[/]")

    elif action == "remove":
        if not name:
            console.print("[red]请提供公众号名称[/]")
            raise typer.Exit(1)
        if manager.remove_subscription(name):
            console.print(f"[green]✓ 已移除订阅: {name}[/]")
        else:
            console.print(f"[yellow]未找到订阅: {name}[/]")

    elif action == "check":
        console.print("[blue]正在检查更新...[/]")
        new_articles = manager.check_updates()
        if new_articles:
            console.print(f"[green]发现 {len(new_articles)} 篇新文章:[/]")
            for a in new_articles:
                console.print(f"  • [{a['account_name']}] {a['title'][:40]}")
        else:
            console.print("[dim]暂无新文章[/]")

    elif action == "watch":
        console.print(Panel.fit(
            f"[bold blue]持续监控模式[/]\n"
            f"间隔: [green]{interval}[/] 秒\n"
            "按 Ctrl+C 停止",
            border_style="blue"
        ))
        import time
        try:
            while True:
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                console.print(f"[{now}] 检查更新...", end=" ")
                new_articles = manager.check_updates()
                if new_articles:
                    console.print(f"[green]发现 {len(new_articles)} 篇[/]")
                    for a in new_articles:
                        console.print(f"  • [{a['account_name']}] {a['title'][:40]}")
                else:
                    console.print("[dim]无更新[/]")
                time.sleep(interval)
        except KeyboardInterrupt:
            console.print("\n[yellow]监控已停止[/]")

    elif action == "stats":
        subs = manager.list_subscriptions()
        console.print(Panel.fit(
            f"订阅数: [cyan]{len(subs)}[/]\n"
            f"数据目录: [dim]{manager.data_dir}[/]",
            title="监控统计",
            border_style="blue"
        ))

    else:
        console.print(f"[red]未知操作: {action}[/]")
        console.print("[dim]可用操作: add, list, remove, check, watch, stats[/]")


@app.command("smart-monitor")
def smart_monitor(
    action: str = typer.Argument(..., help="操作: process/stats/keywords/flush-batch"),
    keyword: Optional[str] = typer.Argument(None, help="关键词（用于 keyword-add/remove）"),
):
    """智能监控与告警系统 v2.0 - 高级监控功能"""
    from smart_monitor import SmartMonitor, Priority

    monitor = SmartMonitor()

    if action == "stats":
        stats = monitor.get_stats()
        console.print(Panel.fit(
            f"[bold cyan]智能监控 v2.0 统计[/]\n\n"
            f"文章指纹库: [green]{stats['fingerprints_count']}[/] 条\n"
            f"待批处理: [yellow]{stats['pending_batch_count']}[/] 篇\n"
            f"关键词规则: [blue]{stats['keyword_rules_count']}[/] 个\n\n"
            f"[dim]功能开关:[/]\n"
            f"  智能去重: {'[green]✓[/]' if stats['config']['dedup_enabled'] else '[red]✗[/]'}\n"
            f"  智能批处理: {'[green]✓[/]' if stats['config']['batch_enabled'] else '[red]✗[/]'}\n"
            f"  静默时段: {'[green]✓[/]' if stats['config']['quiet_hours_enabled'] else '[red]✗[/]'}\n"
            f"  速率限制: {'[green]✓[/]' if stats['config']['rate_limit_enabled'] else '[red]✗[/]'}",
            title="Smart Monitor v2.0",
            border_style="cyan"
        ))

    elif action == "keywords":
        rules = monitor.list_keyword_rules()
        if not rules:
            console.print("[yellow]暂无关键词规则[/]")
            console.print("[dim]使用 'w smart-monitor keyword-add <关键词>' 添加[/]")
        else:
            table = Table(title="高优先级关键词规则", box=box.ROUNDED)
            table.add_column("关键词", style="cyan")
            table.add_column("权重", style="yellow")
            table.add_column("优先级提升", style="green")

            for r in rules:
                table.add_row(r.keyword, str(r.weight), r.priority_boost)
            console.print(table)

    elif action == "keyword-add":
        if not keyword:
            console.print("[red]请提供关键词[/]")
            raise typer.Exit(1)
        monitor.add_keyword_rule(keyword, weight=1.0, priority_boost="high")
        console.print(f"[green]✓ 已添加关键词规则: {keyword}[/]")

    elif action == "keyword-remove":
        if not keyword:
            console.print("[red]请提供关键词[/]")
            raise typer.Exit(1)
        monitor.remove_keyword_rule(keyword)
        console.print(f"[green]✓ 已移除关键词规则: {keyword}[/]")

    elif action == "flush-batch":
        summary = monitor.check_and_flush_batch()
        if summary:
            console.print(Panel.fit(
                f"[bold green]批量摘要已发送[/]\n\n"
                f"文章数: [cyan]{summary['total_articles']}[/] 篇\n"
                f"高优先级: [yellow]{summary['high_priority_count']}[/] 篇\n"
                f"涉及账号: [blue]{', '.join(summary['accounts'][:5])}[/]\n"
                f"通知渠道: [green]{summary.get('channels_sent', 0)}[/] 个",
                title="批量摘要",
                border_style="green"
            ))

            if summary['articles']:
                console.print("\n[dim]文章列表:[/]")
                for a in summary['articles'][:5]:
                    emoji = "🔥" if a['priority'] == 'high' else "•"
                    console.print(f"  {emoji} [{a['account']}] {a['title'][:40]}")
        else:
            console.print("[dim]暂无可发送的批量摘要[/]")

    else:
        console.print(f"[red]未知操作: {action}[/]")
        console.print("[dim]可用操作: stats, keywords, keyword-add, keyword-remove, flush-batch[/]")


@app.command("history")
def history(
    action: str = typer.Argument(..., help="操作: crawl/list/progress"),
    account_name: Optional[str] = typer.Argument(None, help="公众号名称"),
    biz: Optional[str] = typer.Option(None, "--biz", help="公众号 biz 参数"),
    token: Optional[str] = typer.Option(None, "--token", help="appmsg_token"),
    cookie: Optional[str] = typer.Option(None, "--cookie", help="Cookie"),
    max_articles: int = typer.Option(0, "--max", "-m", help="最大抓取数量（0=无限制）"),
    no_resume: bool = typer.Option(False, "--no-resume", help="不续传，从头开始"),
):
    """公众号历史文章批量抓取"""
    from history_crawler import HistoryCrawler, CrawlProgress

    progress_dir = Path("./data/progress")
    progress_dir.mkdir(parents=True, exist_ok=True)

    if action == "list":
        # 列出所有进度文件
        progress_files = list(progress_dir.glob("*.json"))
        if not progress_files:
            console.print("[yellow]没有保存的抓取进度[/]")
            return

        table = Table(title="公众号抓取进度", box=box.ROUNDED)
        table.add_column("公众号", style="cyan")
        table.add_column("状态", style="green")
        table.add_column("已抓取", style="yellow")
        table.add_column("总数", style="blue")
        table.add_column("最后更新", style="dim")

        for pf in progress_files:
            try:
                import json
                with open(pf, 'r') as f:
                    data = json.load(f)

                status = "[green]✓ 完成[/]" if data.get('is_complete') else "[yellow]⟳ 进行中[/]"
                if data.get('error_message'):
                    status = "[red]✗ 失败[/]"

                table.add_row(
                    data.get('account_name', pf.stem),
                    status,
                    str(data.get('crawled_count', 0)),
                    str(data.get('total_count', '?')),
                    data.get('last_crawl_time', '')[:10]
                )
            except:
                pass

        console.print(table)

    elif action == "progress":
        if not account_name:
            console.print("[red]请提供公众号名称[/]")
            raise typer.Exit(1)

        progress_file = progress_dir / f"{account_name}.json"
        if not progress_file.exists():
            console.print(f"[yellow]未找到进度: {account_name}[/]")
            return

        try:
            with open(progress_file, 'r') as f:
                data = json.load(f)

            console.print(Panel.fit(
                f"[bold cyan]{data.get('account_name', account_name)}[/]\n\n"
                f"状态: {'[green]✓ 完成[/]' if data.get('is_complete') else '[yellow]⟳ 进行中[/]'}\n"
                f"已抓取: [green]{data.get('crawled_count', 0)}[/] 篇\n"
                f"总数: [blue]{data.get('total_count', '?')}[/] 篇\n"
                f"最后偏移: {data.get('last_offset', 0)}\n"
                f"最后更新: {data.get('last_crawl_time', '')[:19]}\n"
                + (f"[red]错误: {data.get('error_message', '')}[/]" if data.get('error_message') else ""),
                title="抓取进度",
                border_style="blue"
            ))
        except Exception as e:
            console.print(f"[red]读取进度失败: {e}[/]")

    elif action == "crawl":
        if not all([account_name, biz, token]):
            console.print("[red]缺少必要参数: account_name, --biz, --token 必须提供[/]")
            console.print("\n[dim]用法示例:[/]")
            console.print("  w history crawl 公众号名称 --biz=MzI5... --token=xxx")
            raise typer.Exit(1)

        console.print(Panel.fit(
            f"[bold blue]公众号历史文章抓取[/]\n"
            f"公众号: [cyan]{account_name}[/]\n"
            f"biz: [dim]{biz[:30]}...[/]\n"
            f"token: [dim]{token[:20]}...[/]\n"
            f"最大数量: [{'无限制' if max_articles == 0 else max_articles}][/",
            title="wechat-history",
            border_style="blue"
        ))

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("正在抓取...", total=None)

            try:
                crawler = HistoryCrawler(
                    biz=biz,
                    appmsg_token=token,
                    cookie=cookie or "",
                    progress_dir=str(progress_dir)
                )

                articles = []
                count = 0
                for article in crawler.crawl_history(
                    account_name=account_name,
                    max_articles=max_articles,
                    resume=not no_resume
                ):
                    count += 1
                    articles.append({
                        'title': article.title,
                        'link': article.link,
                        'publish_time': article.publish_time,
                        'is_top': article.is_top
                    })
                    progress.update(task, description=f"已抓取 {count} 篇...")

                progress.update(task, completed=True)

            except Exception as e:
                console.print(f"[red]抓取失败: {e}[/]")
                raise typer.Exit(1)

        # 显示结果
        console.print(f"\n[green]✓ 抓取完成！共 {count} 篇文章[/]")

        if articles:
            table = Table(title="抓取结果预览", box=box.ROUNDED)
            table.add_column("#", style="dim", width=4)
            table.add_column("类型", style="cyan", width=6)
            table.add_column("标题", style="green", max_width=40)
            table.add_column("发布时间", style="yellow")

            for i, article in enumerate(articles[:10], 1):
                top_mark = "头条" if article['is_top'] else "次条"
                title = article['title'][:40] if article['title'] else 'N/A'
                pub_time = article['publish_time'][:10] if article['publish_time'] else ''
                table.add_row(str(i), top_mark, title, pub_time)

            if len(articles) > 10:
                table.add_row("...", "", f"还有 {len(articles) - 10} 篇", "")

            console.print(table)

            # 保存到文件
            output_dir = Path("./data/history")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"{account_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'account_name': account_name,
                    'biz': biz,
                    'crawl_time': datetime.now().isoformat(),
                    'article_count': len(articles),
                    'articles': articles
                }, f, ensure_ascii=False, indent=2)

            console.print(f"\n[dim]结果已保存: {output_file}[/]")

    else:
        console.print(f"[red]未知操作: {action}[/]")
        console.print("[dim]可用操作: crawl, list, progress[/]")


@app.command("dashboard")
def dashboard(
    port: int = typer.Option(8080, "--port", "-p", help="服务端口"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="绑定地址"),
    no_browser: bool = typer.Option(False, "--no-browser", help="不自动打开浏览器"),
):
    """启动数据可视化仪表盘 (Dashboard v1.0)"""
    dashboard_dir = Path(__file__).parent.parent / "dashboard"

    if not dashboard_dir.exists():
        console.print("[red]Dashboard 目录不存在[/]")
        raise typer.Exit(1)

    console.print(Panel.fit(
        f"[bold cyan]数据可视化仪表盘 v1.0[/]\n\n"
        f"地址: [blue]http://{host}:{port}[/]\n"
        f"API文档: [blue]http://{host}:{port}/docs[/]\n\n"
        "[dim]按 Ctrl+C 停止服务[/]",
        title="wechat-dashboard",
        border_style="cyan"
    ))

    # 导入并启动服务
    import subprocess
    import sys

    main_py = dashboard_dir / "main.py"

    if not no_browser:
        # 延迟打开浏览器
        import threading
        import webbrowser
        import time

        def open_browser():
            time.sleep(2)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=open_browser, daemon=True).start()

    try:
        subprocess.run([
            sys.executable, str(main_py),
            "--host", host,
            "--port", str(port)
        ], cwd=str(dashboard_dir))
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard 已停止[/]")


@app.command("analyze")
def analyze(
    action: str = typer.Argument(..., help="操作: article/batch/stats/keywords"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="文章URL（用于article）"),
    limit: int = typer.Option(100, "--limit", "-n", help="批量分析数量"),
    provider: str = typer.Option("auto", "--provider", "-p", help="LLM提供商(auto/ollama/openai/deepseek)"),
):
    """AI智能分析 - 情感分析、关键词提取、智能摘要"""
    from ai_analyzer import AIAnalyzer

    analyzer = AIAnalyzer(llm_provider=provider)

    if action == "article":
        if not url:
            console.print("[red]请提供文章URL: w analyze article --url <URL>[/]")
            raise typer.Exit(1)

        console.print(f"[blue]正在抓取并分析文章: {url}[/]")

        # 先抓取文章
        try:
            from router import StrategyRouter
            router = StrategyRouter()
            result = router.route(url)

            if not result.success:
                console.print(f"[red]抓取失败: {result.error}[/]")
                raise typer.Exit(1)

            article_data = result.data

            # AI分析
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(description="AI分析中...", total=None)

                analysis = analyzer.analyze_article(
                    article_data.get('url', url),
                    article_data.get('title', '无标题'),
                    article_data.get('content', '')
                )

            # 显示结果
            console.print(Panel.fit(
                f"[bold cyan]{analysis.title}[/]\n\n"
                f"[bold]情感分析:[/] {analysis.sentiment.sentiment} "
                f"([yellow]{analysis.sentiment.confidence:.0%}[/] 置信度)\n"
                f"[bold]关键词:[/] {', '.join(k.keyword for k in analysis.keywords[:5])}\n\n"
                f"[bold]摘要:[/]\n{analysis.summary.summary[:300]}...\n\n"
                f"[dim]模型: {analysis.model_used} | 预计阅读: {analysis.summary.reading_time}分钟[/]",
                title="AI智能分析结果",
                border_style="blue"
            ))

        except Exception as e:
            console.print(f"[red]分析失败: {e}[/]")
            raise typer.Exit(1)

    elif action == "batch":
        console.print(f"[blue]开始批量分析，最多 {limit} 篇...[/]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(description="AI分析中...", total=None)
            results = analyzer.batch_analyze(limit=limit)
            progress.update(task, completed=True)

        console.print(f"[green]✓ 完成 {len(results)} 篇文章的AI分析[/]")

        # 显示情感分布
        sentiment_dist = {}
        for r in results:
            s = r.sentiment.sentiment
            sentiment_dist[s] = sentiment_dist.get(s, 0) + 1

        table = Table(title="情感分布统计", box=box.ROUNDED)
        table.add_column("情感", style="cyan")
        table.add_column("数量", style="green")
        table.add_column("占比", style="yellow")

        for sent, count in sentiment_dist.items():
            emoji = {"positive": "😊", "negative": "😔", "neutral": "😐"}.get(sent, "")
            pct = count / len(results) * 100 if results else 0
            table.add_row(f"{emoji} {sent}", str(count), f"{pct:.1f}%")

        console.print(table)

    elif action == "stats":
        stats = analyzer.get_sentiment_stats()
        console.print(Panel.fit(
            json.dumps(stats, ensure_ascii=False, indent=2),
            title="情感分析统计",
            border_style="blue"
        ))

    elif action == "keywords":
        cloud = analyzer.get_keyword_cloud()
        console.print("[bold]热门关键词云:[/]\n")
        for kw in cloud[:20]:
            console.print(f"  • {kw['text']}: {kw['value']}次")

    else:
        console.print(f"[red]未知操作: {action}[/]")
        console.print("[dim]可用操作: article, batch, stats, keywords[/]")


@app.command("semantic")
def semantic(
    action: str = typer.Argument(..., help="操作: index/search/similar/cluster/stats"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="搜索查询"),
    article_id: Optional[str] = typer.Option(None, "--id", help="文章ID（用于similar）"),
    limit: int = typer.Option(10, "--limit", "-n", help="结果数量"),
):
    """语义搜索与向量检索 - 理解意图的智能搜索"""
    from semantic_search import SemanticSearch

    searcher = SemanticSearch()

    if action == "index":
        console.print(f"[blue]开始索引文章到向量数据库...[/]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="索引中...", total=None)
            count = searcher.index_articles(limit=limit)

        console.print(f"[green]✓ 成功索引 {count} 篇文章到向量数据库[/]")
        console.print("[dim]现在可以使用 `w search <关键词> --semantic` 进行语义搜索[/]")

    elif action == "search":
        if not query:
            console.print("[red]请提供搜索查询: w semantic search -q '查询内容'[/]")
            raise typer.Exit(1)

        console.print(f"[blue]语义搜索: [bold]{query}[/][/]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(description="语义搜索中...", total=None)
            results = searcher.search(query, top_k=limit)

        if results:
            table = Table(title=f"语义搜索结果: {query}", box=box.ROUNDED)
            table.add_column("#", style="dim", width=3)
            table.add_column("相似度", style="magenta", width=8)
            table.add_column("标题", style="cyan", max_width=35)
            table.add_column("公众号", style="green")

            for i, r in enumerate(results, 1):
                table.add_row(
                    str(i),
                    f"{r.similarity_score:.0%}",
                    r.title[:35],
                    r.account_name
                )

            console.print(table)
            console.print(f"\n[dim]找到 {len(results)} 个语义相关结果[/]")
        else:
            console.print("[yellow]未找到相关结果[/]")
            console.print("[dim]提示: 先运行 `w semantic index` 索引文章[/]")

    elif action == "similar":
        if not article_id:
            console.print("[red]请提供文章ID: w semantic similar --id <article_id>[/]")
            raise typer.Exit(1)

        console.print(f"[blue]查找与文章相似的内容...[/]\n")
        results = searcher.find_similar_articles(article_id, top_k=limit)

        if results:
            table = Table(title="相似文章推荐", box=box.ROUNDED)
            table.add_column("#", style="dim", width=3)
            table.add_column("相似度", style="magenta", width=8)
            table.add_column("标题", style="cyan", max_width=40)
            table.add_column("公众号", style="green")

            for i, r in enumerate(results, 1):
                table.add_row(
                    str(i),
                    f"{r.similarity_score:.0%}",
                    r.title[:40],
                    r.account_name
                )

            console.print(table)
        else:
            console.print("[yellow]未找到相似文章[/]")

    elif action == "cluster":
        console.print("[blue]正在进行文章聚类分析...[/]\n")
        clusters = searcher.cluster_articles(n_clusters=min(limit, 10))

        if clusters:
            for c in clusters:
                console.print(Panel(
                    f"[bold]{c.topic}[/]\n\n"
                    f"文章数: [green]{c.article_count}[/]\n"
                    f"示例: [dim]{', '.join(c.sample_articles[:2])}...[/]",
                    title=f"主题 {c.cluster_id}",
                    border_style="blue"
                ))
        else:
            console.print("[yellow]聚类数据不足[/]")

    elif action == "stats":
        stats = searcher.vector_store.get_stats()
        console.print(Panel.fit(
            f"[bold cyan]向量数据库统计[/]\n\n"
            f"文档总数: [green]{stats['total_documents']}[/]\n"
            f"向量维度: [blue]{stats['dimension']}[/]\n"
            f"VSS支持: {'[green]✓[/]' if stats['has_vss'] else '[yellow]✗ (使用备选)[/]'}\n"
            f"Embedding: [dim]{stats['embedding_provider']}[/]",
            border_style="cyan"
        ))

    else:
        console.print(f"[red]未知操作: {action}[/]")
        console.print("[dim]可用操作: index, search, similar, cluster, stats[/]")




@app.command("workflow")
def workflow(
    action: str = typer.Argument(..., help="操作: create, list, show, enable, disable, delete, trigger, logs, test, server, stats"),
    workflow_id: Optional[str] = typer.Option(None, "--id", help="工作流ID"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="工作流名称"),
    desc: Optional[str] = typer.Option(None, "--desc", "-d", help="工作流描述"),
    trigger_type: str = typer.Option("new_article", "--trigger", "-t", help="触发器类型: new_article, heat_threshold, keyword_match"),
    trigger_config: Optional[str] = typer.Option(None, "--trigger-config", help="触发器配置JSON"),
    actions: Optional[str] = typer.Option(None, "--actions", "-a", help="动作列表JSON"),
    event_data: Optional[str] = typer.Option(None, "--event", "-e", help="事件数据JSON"),
    limit: int = typer.Option(20, "--limit", "-l", help="日志数量限制"),
    port: int = typer.Option(8080, "--port", "-p", help="API服务器端口"),
):
    """自动化工作流引擎 - IFTTT风格的触发-动作系统"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from workflow_engine import WorkflowEngine, TriggerConfig, ActionConfig
    try:
        from workflow_server import app as workflow_app, HAS_FASTAPI
    except:
        HAS_FASTAPI = False
        workflow_app = None

    engine = WorkflowEngine()

    if action == "create":
        if not name:
            console.print("[red]请提供工作流名称: --name <名称>[/]")
            raise typer.Exit(1)

        t_config = json.loads(trigger_config) if trigger_config else {}
        if trigger_type == "new_article":
            t_config.setdefault("account_name", None)
        elif trigger_type == "heat_threshold":
            t_config.setdefault("threshold", 1000)
            t_config.setdefault("operator", ">=")
        elif trigger_type == "keyword_match":
            t_config.setdefault("keywords", [])
            t_config.setdefault("match_mode", "any")

        if actions:
            actions_list = json.loads(actions)
        else:
            actions_list = [{"type": "webhook", "config": {"url": "http://localhost:8080/test", "method": "POST"}}]

        trigger = TriggerConfig(type=trigger_type, config=t_config)
        action_configs = [ActionConfig(type=a["type"], config=a.get("config", {})) for a in actions_list]

        wf = engine.create_workflow(
            name=name,
            description=desc or f"{name} 工作流",
            trigger=trigger,
            actions=action_configs
        )

        console.print(Panel.fit(
            f"[bold green]工作流创建成功![/]\n\n"
            f"ID: [cyan]{wf.id}[/]\n"
            f"名称: [blue]{wf.name}[/]\n"
            f"触发器: [yellow]{trigger_type}[/]\n"
            f"状态: [green]启用[/]",
            border_style="green"
        ))

    elif action == "list":
        workflows = engine.list_workflows()
        if not workflows:
            console.print("[yellow]暂无工作流[/]")
            return

        table = Table(title=f"工作流列表 ({len(workflows)}个)", box=box.ROUNDED)
        table.add_column("ID", style="dim", width=12)
        table.add_column("名称", style="cyan")
        table.add_column("触发器", style="yellow")
        table.add_column("状态", style="green")
        table.add_column("触发次数", justify="right")

        for wf in workflows:
            status_icon = "[green]●[/]" if wf.status == "enabled" else "[red]●[/]"
            table.add_row(wf.id[:12], wf.name[:20], wf.trigger.type, f"{status_icon} {wf.status}", str(wf.trigger_count))
        console.print(table)

    elif action == "trigger":
        if not workflow_id:
            console.print("[red]请提供工作流ID: --id <id>[/]")
            raise typer.Exit(1)

        event = json.loads(event_data) if event_data else {
            "event_type": "manual", "title": "测试文章", "account_name": "测试公众号"
        }

        import asyncio
        log = asyncio.run(engine.trigger_workflow(workflow_id, event, is_manual=True))
        if log:
            status_icon = "[green]✓[/]" if log.status == "success" else "[red]✗[/]"
            console.print(f"{status_icon} 执行完成: {log.status}")
        else:
            console.print("[red]执行失败[/]")

    elif action == "logs":
        logs = engine.get_logs(workflow_id, limit)
        if not logs:
            console.print("[yellow]暂无执行记录[/]")
            return
        for log in logs:
            status = "✓" if log.status == "success" else "✗"
            console.print(f"[{status}] {log.started_at[:16]} {log.workflow_id[:8]}...")

    elif action == "server":
        if not HAS_FASTAPI:
            console.print("[red]需要安装 FastAPI: pip install fastapi uvicorn[/]")
            raise typer.Exit(1)
        console.print(f"[green]启动 API 服务器: http://0.0.0.0:{port}[/]")
        import uvicorn
        uvicorn.run(workflow_app, host="0.0.0.0", port=port)

    elif action == "stats":
        stats = engine.get_stats()
        console.print(f"工作流: {stats['total_workflows']} | 执行: {stats['total_executions']} | 成功率: {stats['success_rate']:.1f}%")

    else:
        console.print(f"[red]未知操作: {action}[/]")
        console.print("[dim]可用: create, list, trigger, logs, server, stats[/]")



@app.command("team")
def team(
    action: str = typer.Argument(..., help="操作: create, list, join, members, invite, collections, stats"),
    team_id: Optional[str] = typer.Option(None, "--id", help="团队ID"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="名称"),
    desc: Optional[str] = typer.Option(None, "--desc", "-d", help="描述"),
    email: Optional[str] = typer.Option(None, "--email", "-e", help="邮箱"),
    invite_code: Optional[str] = typer.Option(None, "--code", "-c", help="邀请码"),
    user_id: Optional[str] = typer.Option(None, "--user", "-u", help="用户ID"),
):
    """团队协作系统 - 多用户、共享工作区"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from team_system import TeamSystem

    engine = TeamSystem()

    if action == "create":
        if not name or not user_id:
            console.print("[red]请提供 --name 和 --user[/]")
            raise typer.Exit(1)
        team = engine.create_team(name, desc or "", user_id)
        console.print(Panel.fit(
            f"[bold green]团队创建成功![/]\n\n"
            f"ID: [cyan]{team.id}[/]\n"
            f"名称: [blue]{team.name}[/]\n"
            f"邀请码: [yellow]{team.invite_code}[/]",
            border_style="green"
        ))

    elif action == "list":
        if not user_id:
            console.print("[red]请提供 --user[/]")
            raise typer.Exit(1)
        teams = engine.list_user_teams(user_id)
        if not teams:
            console.print("[yellow]暂无团队[/]")
            return
        table = Table(title=f"我的团队 ({len(teams)}个)", box=box.ROUNDED)
        table.add_column("ID", style="dim", width=12)
        table.add_column("名称", style="cyan")
        table.add_column("成员", justify="right")
        table.add_column("文章", justify="right")
        for t in teams:
            table.add_row(t.id[:12], t.name, str(t.member_count), str(t.article_count))
        console.print(table)

    elif action == "join":
        if not invite_code or not user_id:
            console.print("[red]请提供 --code 和 --user[/]")
            raise typer.Exit(1)
        member = engine.join_team(invite_code, user_id)
        if member:
            console.print(f"[green]成功加入团队，角色: {member.role}[/]")
        else:
            console.print("[red]邀请码无效[/]")

    elif action == "members":
        if not team_id:
            console.print("[red]请提供 --id[/]")
            raise typer.Exit(1)
        members = engine.list_team_members(team_id)
        table = Table(title=f"团队成员 ({len(members)}人)", box=box.ROUNDED)
        table.add_column("角色", style="yellow")
        table.add_column("姓名", style="cyan")
        table.add_column("邮箱")
        for m in members:
            role_icon = "👑" if m['role'] == 'admin' else "👤"
            table.add_row(f"{role_icon} {m['role']}", m['name'], m['email'])
        console.print(table)

    elif action == "collections":
        if not team_id:
            console.print("[red]请提供 --id[/]")
            raise typer.Exit(1)
        colls = engine.list_team_collections(team_id)
        table = Table(title=f"共享收藏夹 ({len(colls)}个)", box=box.ROUNDED)
        table.add_column("名称", style="cyan")
        table.add_column("文章数", justify="right")
        table.add_column("描述")
        for c in colls:
            table.add_row(c.name, str(c.article_count), c.description[:30])
        console.print(table)

    elif action == "stats":
        if not team_id:
            console.print("[red]请提供 --id[/]")
            raise typer.Exit(1)
        stats = engine.get_team_stats(team_id)
        console.print(Panel.fit(
            f"[bold cyan]团队统计[/]\n\n"
            f"成员数: [green]{stats['member_count']}[/]\n"
            f"收藏夹: [blue]{stats['collection_count']}[/]\n"
            f"收藏文章: [yellow]{stats['collected_articles']}[/]\n"
            f"评论数: [magenta]{stats['comment_count']}[/]",
            border_style="cyan"
        ))

    else:
        console.print(f"[red]未知操作: {action}[/]")


@app.command("sync")
def sync(
    action: str = typer.Argument(..., help="操作: add, list, test, notion, yuque"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="配置名称"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="提供商: notion, yuque, airtable"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="API Token"),
    database: Optional[str] = typer.Option(None, "--database", help="Notion Database ID"),
    repo: Optional[str] = typer.Option(None, "--repo", help="语雀仓库 slug"),
    article_id: Optional[str] = typer.Option(None, "--article", help="文章ID"),
):
    """第三方集成 - Notion/语雀/Airtable 同步"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from integrations import IntegrationManager
    import asyncio

    manager = IntegrationManager()

    if action == "add":
        if not name or not provider or not token:
            console.print("[red]请提供 --name, --provider, --token[/]")
            raise typer.Exit(1)
        config = {"token": token}
        if database:
            config["database_id"] = database
        if repo:
            config["repo_slug"] = repo
        manager.add_config(name, provider, config)
        console.print(f"[green]集成配置已添加: {name}[/]")

    elif action == "list":
        configs = manager.list_configs()
        if not configs:
            console.print("[yellow]暂无集成配置[/]")
            return
        table = Table(title=f"集成配置 ({len(configs)}个)", box=box.ROUNDED)
        table.add_column("名称", style="cyan")
        table.add_column("提供商", style="yellow")
        table.add_column("状态")
        table.add_column("同步次数", justify="right")
        for c in configs:
            status = "[green]✓[/]" if c['enabled'] else "[red]✗[/]"
            table.add_row(c['name'], c['provider'], status, str(c['sync_count']))
        console.print(table)

    elif action == "test":
        if not name:
            console.print("[red]请提供 --name[/]")
            raise typer.Exit(1)
        test_article = {
            "title": "测试文章",
            "account_name": "测试公众号",
            "url": "https://mp.weixin.qq.com/s/test",
            "publish_time": "2025-04-12T10:00:00",
            "read_count": 1000,
            "like_count": 50,
            "tags": ["测试"],
            "content": "测试内容",
            "summary": "测试摘要"
        }
        result = asyncio.run(manager.sync_article(name, test_article))
        if result.get('success'):
            console.print(f"[green]同步测试成功![/]")
        else:
            console.print(f"[red]同步失败: {result.get('error')}[/]")

    else:
        console.print(f"[red]未知操作: {action}[/]")




@app.command("export")
def export_cmd(
    format: str = typer.Argument(..., help="格式: excel, pdf, word, markdown, json, csv"),
    output: str = typer.Option("./export", "--output", "-o", help="输出路径"),
    article_ids: Optional[str] = typer.Option(None, "--ids", help="文章ID列表(JSON数组)"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="筛选查询"),
):
    """导出文章 - 支持Excel/PDF/Word/Markdown/JSON/CSV"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from export_engine import ExportEngine
    from advanced_filter import AdvancedFilter

    engine = ExportEngine()

    # 获取文章数据
    if article_ids:
        import json
        ids = json.loads(article_ids)
        # 从数据库获取
        articles = []
        db_path = Path.home() / ".wechat-scraper" / "articles.db"
        if db_path.exists():
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            placeholders = ",".join(["?"] * len(ids))
            cursor = conn.execute(f"SELECT * FROM articles WHERE id IN ({placeholders})", ids)
            articles = [dict(row) for row in cursor.fetchall()]
            conn.close()
    else:
        console.print("[yellow]请使用 --ids 指定要导出的文章ID[/]")
        raise typer.Exit(1)

    if not articles:
        console.print("[red]没有找到文章[/]")
        raise typer.Exit(1)

    # 确保输出目录存在
    output_path = Path(output)
    if output_path.suffix == "":
        output_path.mkdir(parents=True, exist_ok=True)
        output_file = output_path / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format if format != 'excel' else 'xlsx'}"
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_file = output_path

    def progress(current, total, message):
        if current % 5 == 0 or current == total:
            console.print(f"  [{current}/{total}] {message}")

    console.print(f"[blue]正在导出 {len(articles)} 篇文章为 {format}...[/]")
    success = engine.export(articles, format, str(output_file), progress_callback=progress)

    if success:
        console.print(f"[green]导出成功: {output_file}[/]")
    else:
        console.print("[red]导出失败[/]")


@app.command("filter")
def filter_cmd(
    action: str = typer.Argument(..., help="操作: create, list, apply, delete"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="模板名称"),
    field: Optional[str] = typer.Option(None, "--field", "-f", help="筛选字段"),
    operator: Optional[str] = typer.Option(None, "--op", help="操作符: eq, gt, lt, contains, in"),
    value: Optional[str] = typer.Option(None, "--value", "-v", help="筛选值"),
    template_id: Optional[str] = typer.Option(None, "--template", "-t", help="模板ID"),
):
    """高级筛选 - 多条件组合筛选、模板保存"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from advanced_filter import AdvancedFilter, FilterCondition

    engine = AdvancedFilter()

    if action == "create":
        if not all([name, field, operator, value]):
            console.print("[red]请提供 --name, --field, --op, --value[/]")
            raise typer.Exit(1)

        condition = FilterCondition(field=field, operator=operator, value=value)
        template = engine.create_template(name=name, description="", conditions=[condition])
        console.print(f"[green]筛选模板已创建: {template.id}[/]")

    elif action == "list":
        templates = engine.list_templates()
        if not templates:
            console.print("[yellow]暂无筛选模板[/]")
            return
        table = Table(title=f"筛选模板 ({len(templates)}个)", box=box.ROUNDED)
        table.add_column("ID", style="dim", width=12)
        table.add_column("名称", style="cyan")
        table.add_column("条件", style="yellow")
        table.add_column("创建时间")
        for t in templates:
            conds = f"{len(t.conditions)}个条件"
            table.add_row(t.id, t.name, conds, t.created_at[:10])
        console.print(table)

    elif action == "apply":
        if not template_id:
            console.print("[red]请提供 --template[/]")
            raise typer.Exit(1)

        template = engine.get_template(template_id)
        if not template:
            console.print(f"[red]模板不存在: {template_id}[/]")
            raise typer.Exit(1)

        db_path = Path.home() / ".wechat-scraper" / "articles.db"
        if not db_path.exists():
            console.print("[red]数据库不存在[/]")
            raise typer.Exit(1)

        results = engine.filter_from_db(
            str(db_path), template.conditions,
            template.sort_by, template.sort_order, template.limit
        )

        stats = engine.get_stats(results)
        console.print(Panel.fit(
            f"[bold cyan]筛选结果[/]\n\n"
            f"匹配文章: [green]{stats['total']}[/]\n"
            f"涉及公众号: [blue]{stats['accounts']}[/]\n"
            f"时间范围: [yellow]{stats['date_range']}[/]\n"
            f"总阅读量: [magenta]{stats['total_reads']:,}[/]\n"
            f"平均阅读: [dim]{stats['avg_reads']:,}[/]",
            border_style="cyan"
        ))

        if results:
            table = Table(title="筛选结果预览", box=box.ROUNDED)
            table.add_column("标题", style="cyan", max_width=40)
            table.add_column("公众号", style="green")
            table.add_column("阅读", justify="right")
            for r in results[:10]:
                table.add_row(r.get('title', '')[:40], r.get('account_name', ''), str(r.get('read_count', 0)))
            console.print(table)
            if len(results) > 10:
                console.print(f"[dim]... 还有 {len(results) - 10} 篇 ...[/]")

    elif action == "delete":
        if not template_id:
            console.print("[red]请提供 --template[/]")
            raise typer.Exit(1)
        if engine.delete_template(template_id):
            console.print(f"[green]模板已删除[/]")
        else:
            console.print(f"[red]模板不存在[/]")

    else:
        console.print(f"[red]未知操作: {action}[/]")


@app.command("batch")
def batch_cmd(
    action: str = typer.Argument(..., help="操作: export, edit, sync, status, list"),
    article_ids: Optional[str] = typer.Option(None, "--ids", help="文章ID列表(JSON数组)"),
    format: Optional[str] = typer.Option(None, "--format", "-f", help="导出格式"),
    tags: Optional[str] = typer.Option(None, "--tags", help="设置标签(JSON数组)"),
    task_id: Optional[str] = typer.Option(None, "--task", "-t", help="任务ID"),
):
    """批量操作 - 批量导出/编辑/同步/删除"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from batch_operations import BatchOperationEngine
    import json

    engine = BatchOperationEngine()

    if action == "export":
        if not article_ids or not format:
            console.print("[red]请提供 --ids 和 --format[/]")
            raise typer.Exit(1)
        ids = json.loads(article_ids)
        output_dir = str(Path.home() / ".wechat-scraper" / "exports")
        task = engine.create_task("export", ids, {"format": format, "output_dir": output_dir})
        console.print(f"[green]批量导出任务已创建: {task.id}[/]")
        console.print(f"  格式: {format}")
        console.print(f"  数量: {len(ids)} 篇文章")
        console.print(f"[dim]使用 `w batch status --task {task.id}` 查看进度[/]")

    elif action == "edit":
        if not article_ids:
            console.print("[red]请提供 --ids[/]")
            raise typer.Exit(1)
        ids = json.loads(article_ids)
        edits = {}
        if tags:
            edits["tags"] = json.loads(tags)
        if not edits:
            console.print("[red]请提供至少一个编辑字段，如 --tags[/]")
            raise typer.Exit(1)
        task = engine.create_task("edit", ids, {"edits": edits})
        console.print(f"[green]批量编辑任务已创建: {task.id}[/]")

    elif action == "list":
        tasks = engine.list_tasks(limit=20)
        if not tasks:
            console.print("[yellow]暂无批量任务[/]")
            return
        table = Table(title="批量任务", box=box.ROUNDED)
        table.add_column("ID", style="dim", width=12)
        table.add_column("类型", style="cyan")
        table.add_column("状态", style="green")
        table.add_column("进度", justify="right")
        for t in tasks:
            status_color = {
                "completed": "[green]",
                "failed": "[red]",
                "running": "[yellow]",
                "pending": "[dim]"
            }.get(t.status, "[white]")
            progress = f"{t.completed}/{t.total}" if t.total > 0 else "-"
            table.add_row(t.id[:12], t.operation_type, f"{status_color}{t.status}[/]", progress)
        console.print(table)

    elif action == "status":
        if not task_id:
            console.print("[red]请提供 --task[/]")
            raise typer.Exit(1)
        task = engine.get_task(task_id)
        if not task:
            console.print(f"[red]任务不存在[/]")
            raise typer.Exit(1)
        console.print(Panel.fit(
            f"[bold cyan]任务详情: {task.id[:12]}[/]\n\n"
            f"类型: [blue]{task.operation_type}[/]\n"
            f"状态: [{'green' if task.status == 'completed' else 'yellow' if task.status == 'running' else 'red'}]{task.status}[/]\n"
            f"进度: [green]{task.completed}[/]/[blue]{task.total}[/] ([red]{task.failed}[/] 失败)\n"
            f"创建: [dim]{task.created_at[:16]}[/]",
            border_style="cyan"
        ))
        if task.errors:
            console.print(f"[red]错误 ({len(task.errors)}个):[/]")
            for e in task.errors[:5]:
                console.print(f"  [dim]- {e}[/]")

    else:
        console.print(f"[red]未知操作: {action}[/]")




@app.command("sentiment")
def sentiment_cmd(
    action: str = typer.Argument(..., help="操作: word, brand, alert, trend, stats, scan"),
    name: str = typer.Option(None, "--name", "-n", help="敏感词/品牌名"),
    category: str = typer.Option(None, "--category", "-c", help="类别: political, porn, violence, gambling, drugs, fraud, custom"),
    level: str = typer.Option("warning", "--level", "-l", help="预警级别: critical, warning, info"),
    content: str = typer.Option(None, "--content", help="要扫描的内容/文章ID"),
    db: str = typer.Option(None, "--db", help="文章数据库路径"),
):
    """舆情监控 - 敏感词检测、品牌追踪、危机预警"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from sentiment_monitor import SentimentMonitor

    monitor = SentimentMonitor()

    if action == "word":
        if name:
            # 添加敏感词
            monitor.add_sensitive_word(name, category or "custom")
            console.print(f"[green]已添加敏感词: {name} ({category or 'custom'})[/]")
        else:
            # 列出敏感词
            words = monitor.list_sensitive_words()
            table = Table(title=f"敏感词列表 ({len(words)}个)")
            table.add_column("词汇", style="cyan")
            table.add_column("类别", style="blue")
            table.add_column("风险级别", style="yellow")
            for w in words[:50]:
                risk_color = {"high": "red", "medium": "yellow", "low": "green"}.get(w.risk_level, "white")
                table.add_row(w.word, w.category, f"[{risk_color}]{w.risk_level}[/{risk_color}]")
            console.print(table)

    elif action == "brand":
        if name:
            # 添加品牌追踪
            monitor.add_brand_keyword(name)
            console.print(f"[green]已添加品牌追踪: {name}[/]")
        else:
            # 列出品牌追踪
            brands = monitor.list_brand_keywords()
            table = Table(title=f"品牌追踪 ({len(brands)}个)")
            table.add_column("品牌", style="cyan")
            table.add_column("提及次数", style="blue")
            table.add_column("最后提及", style="dim")
            for b in brands:
                table.add_row(b.keyword, str(b.mention_count), b.last_mention[:16] if b.last_mention else "-")
            console.print(table)

    elif action == "alert":
        # 查看预警
        alerts = monitor.get_active_alerts(min_level=level)
        if not alerts:
            console.print("[green]当前无活跃预警[/]")
        else:
            table = Table(title=f"活跃预警 ({len(alerts)}个)")
            table.add_column("级别", style="red")
            table.add_column("类型", style="cyan")
            table.add_column("描述", style="white")
            table.add_column("时间", style="dim")
            for a in alerts:
                level_color = {"critical": "red", "warning": "yellow", "info": "blue"}.get(a.level, "white")
                table.add_row(
                    f"[{level_color}]{a.level}[/{level_color}]",
                    a.alert_type,
                    a.description[:50],
                    a.created_at[:16]
                )
            console.print(table)

    elif action == "trend":
        # 情感趋势
        if db:
            articles = monitor._get_recent_articles(db, days=7)
            trend = monitor.analyze_sentiment_trend(articles)
            console.print(Panel.fit(
                f"[bold cyan]情感趋势分析 (最近7天)[/]\n\n"
                f"总文章: [blue]{trend.total_articles}[/]\n"
                f"正面: [green]{trend.positive_count} ({trend.positive_pct:.1f}%)[/]\n"
                f"中性: [white]{trend.neutral_count} ({trend.neutral_pct:.1f}%)[/]\n"
                f"负面: [red]{trend.negative_count} ({trend.negative_pct:.1f}%)[/]\n\n"
                f"趋势: [{'green' if trend.sentiment_score > 0 else 'red'}]{trend.trend}[/{'green' if trend.sentiment_score > 0 else 'red'}]\n"
                f"情感得分: {trend.sentiment_score:+.2f}",
                border_style="cyan"
            ))
        else:
            console.print("[yellow]请指定数据库路径: --db <path>[/]")

    elif action == "stats":
        stats = monitor.get_monitor_stats()
        console.print(Panel.fit(
            f"[bold cyan]舆情监控统计[/]\n\n"
            f"敏感词: [blue]{stats['sensitive_words']}[/]\n"
            f"品牌追踪: [blue]{stats['brand_keywords']}[/]\n"
            f"活跃预警: [red]{stats['active_alerts']}[/]\n"
            f"总预警: [dim]{stats['total_alerts']}[/]\n"
            f"扫描文章: [green]{stats['scanned_articles']}[/]",
            border_style="cyan"
        ))

    elif action == "scan":
        if not content:
            console.print("[red]请指定要扫描的内容: --content <text>[/]")
            return
        result = monitor.scan_content(content)
        if result["has_sensitive"]:
            console.print(f"[red]检测到 {len(result['matches'])} 个敏感词:[/]")
            for m in result['matches']:
                console.print(f"  - {m['word']} ({m['category']}, 风险: {m['risk_level']})")
        else:
            console.print(f"[green]未检测到敏感词 (情感: {result['sentiment']})[/]")

    else:
        console.print(f"[red]未知操作: {action}[/]")




@app.command("analytics")
def analytics_cmd(
    action: str = typer.Argument(..., help="操作: trends, top, metrics, report, heatmap, compare, insights, topics"),
    account: str = typer.Option(None, "--account", "-a", help="指定公众号"),
    days: int = typer.Option(30, "--days", "-d", help="分析天数"),
    limit: int = typer.Option(10, "--limit", "-n", help="显示数量"),
    accounts: str = typer.Option(None, "--accounts", help="对比账号列表(逗号分隔)"),
    export: str = typer.Option(None, "--export", "-o", help="导出路径"),
):
    """数据可视化与智能分析 - 仪表盘/竞品分析/AI洞察/热点追踪"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

    if action == "trends":
        from analytics_dashboard import AnalyticsDashboard
        dashboard = AnalyticsDashboard()
        trends = dashboard.get_reading_trends(days, account)
        console.print(f"\n[bold cyan]阅读趋势 ({len(trends)}天)[/]\n")
        for t in trends[-10:]:
            change = f"({t.change_pct:+.1f}%)" if t.change_pct != 0 else ""
            console.print(f"  {t.date}: {t.value:,} 阅读 {change}")

    elif action == "top":
        from analytics_dashboard import AnalyticsDashboard
        dashboard = AnalyticsDashboard()
        articles = dashboard.get_top_articles(limit, days=days)
        console.print(f"\n[bold cyan]热门文章 Top {len(articles)}[/]\n")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("排名", style="dim")
        table.add_column("标题", style="cyan", max_width=40)
        table.add_column("公众号", style="blue")
        table.add_column("阅读", style="green", justify="right")
        table.add_column("互动率", style="yellow")
        for i, a in enumerate(articles, 1):
            table.add_row(str(i), a.title[:40], a.account_name, f"{a.read_count:,}", f"{a.engagement_rate:.2f}%")
        console.print(table)

    elif action == "metrics":
        from analytics_dashboard import AnalyticsDashboard
        dashboard = AnalyticsDashboard()
        metrics = dashboard.get_account_metrics()
        console.print(f"\n[bold cyan]公众号指标 ({len(metrics)}个)[/]\n")
        for m in metrics:
            console.print(Panel.fit(
                f"[bold]{m.account_name}[/]\n"
                f"文章: {m.total_articles} | 总阅读: {m.total_reads:,}\n"
                f"平均: {m.avg_reads:,} | 互动率: {m.engagement_rate:.2f}%\n"
                f"健康度: [green]{m.health_score:.1f}/100[/] | 增长率: {m.growth_rate:+.1f}%",
                border_style="cyan"
            ))

    elif action == "report":
        from analytics_dashboard import AnalyticsDashboard
        dashboard = AnalyticsDashboard()
        report = dashboard.generate_report(days)
        console.print(Panel.fit(
            f"[bold cyan]数据分析报告[/]\n"
            f"统计周期: {report.period}\n"
            f"总阅读: [blue]{report.summary['total_reads']:,}[/]\n"
            f"总文章: {report.summary['total_articles']}[/]\n"
            f"活跃账号: {report.summary['active_accounts']}[/]\n"
            f"平均互动率: {report.summary['avg_engagement_rate']:.2f}%",
            border_style="cyan"
        ))
        console.print("\n[bold]数据洞察:[/]")
        for insight in report.insights[:5]:
            console.print(f"  • {insight}")

    elif action == "heatmap":
        from analytics_dashboard import AnalyticsDashboard
        dashboard = AnalyticsDashboard()
        heatmap = dashboard.get_publish_heatmap(days)
        console.print(f"\n[bold cyan]发布时间热力图[/]\n")
        # 简化热力图显示
        console.print("[dim]小时: 0-23 (X轴) | 日期: 周一到周日 (Y轴)[/]")

    elif action == "compare":
        if not accounts:
            console.print("[red]请指定对比账号: --accounts '账号1,账号2'[/]")
            return
        from competitor_analyzer import CompetitorAnalyzer
        analyzer = CompetitorAnalyzer()
        account_list = [a.strip() for a in accounts.split(',')]
        scores = analyzer.calculate_competitive_scores(account_list, days)
        console.print(f"\n[bold cyan]竞争力对比 ({len(scores)}个账号)[/]\n")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("排名", style="dim")
        table.add_column("账号", style="cyan")
        table.add_column("综合得分", style="green")
        table.add_column("影响力", style="blue")
        table.add_column("互动", style="yellow")
        for s in scores:
            table.add_row(str(s.rank), s.account_name, f"{s.overall_score:.1f}", f"{s.reach_score:.1f}", f"{s.engagement_score:.1f}")
        console.print(table)

    elif action == "insights":
        from ai_insights import AIInsightsGenerator
        generator = AIInsightsGenerator()
        report = generator.generate_report(days)
        console.print(Panel.fit(
            f"[bold cyan]AI智能洞察[/]\n"
            f"健康评分: [{ 'green' if report.score >= 80 else 'yellow' if report.score >= 60 else 'red' }]{report.score}/100 ({report.health_status})[/]\n"
            f"{report.summary}",
            border_style="cyan"
        ))
        if report.recommendations:
            console.print("\n[bold]AI建议:[/]")
            for r in report.recommendations[:3]:
                icon = "🔴" if r.priority == "high" else "🟡"
                console.print(f"  {icon} [bold]{r.title}[/]: {r.description[:60]}...")

    elif action == "topics":
        from hot_topics import HotTopicsTracker
        tracker = HotTopicsTracker()
        topics = tracker.discover_hot_topics(days)
        console.print(f"\n[bold cyan]热点话题 ({len(topics)}个)[/]\n")
        for i, t in enumerate(topics[:10], 1):
            status_emoji = {'emerging': '🌱', 'peaking': '🔥', 'stable': '📊', 'declining': '📉'}.get(t.status, '•')
            console.print(f"{i}. {status_emoji} [bold]{t.name}[/] (热度: {t.heat_score:.1f}, 提及: {t.mention_count})")

    else:
        console.print(f"[red]未知操作: {action}[/]")


@app.command("writing")
def writing_cmd(
    action: str = typer.Argument(..., help="操作: title, summary, rewrite, analyze, material"),
    content: str = typer.Option(None, "--content", "-c", help="内容或文件路径"),
    style: str = typer.Option("professional", "--style", "-s", help="风格: professional/casual/marketing/story/academic/news/marketing/minimal"),
    count: int = typer.Option(5, "--count", "-n", help="生成数量"),
    material_type: str = typer.Option("text", "--type", "-t", help="素材类型: text/image/link"),
    title: str = typer.Option(None, "--title", help="素材标题"),
    tags: str = typer.Option(None, "--tags", help="标签(逗号分隔)"),
):
    """智能写作助手 - AI标题生成/摘要/改写/素材库"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

    if action == "title":
        from writing_assistant import TitleGenerator
        generator = TitleGenerator()
        if not content:
            console.print("[red]请提供内容: --content <text>[/]")
            return
        titles = generator.generate_titles(content, count)
        console.print(f"\n[bold cyan]生成的标题 ({len(titles)}个):[/]\n")
        for i, t in enumerate(titles, 1):
            icon = "👑" if i == 1 else f"{i}."
            console.print(f"{icon} [bold]{t.title}[/]")
            console.print(f"   [dim]公式: {t.formula} | 预测CTR: {t.predicted_ctr:.0%} | 评分: {t.score}[/]")

    elif action == "summary":
        from writing_assistant import Summarizer
        summarizer = Summarizer()
        if not content:
            console.print("[red]请提供内容: --content <text>[/]")
            return
        summary = summarizer.generate_summary(content, style, 200)
        console.print(f"\n[bold cyan]{summary.style}摘要:[/]\n")
        console.print(Panel(summary.text, border_style="cyan"))
        console.print(f"[dim]长度: {summary.length}字[/]")

    elif action == "rewrite":
        from writing_assistant import ContentRewriter
        rewriter = ContentRewriter()
        if not content:
            console.print("[red]请提供内容: --content <text>[/]")
            return
        result = rewriter.rewrite(content, style)
        console.print(f"\n[bold cyan]改写结果 ({result.style})[/]\n")
        console.print(Panel(result.text, border_style="green"))
        console.print(f"[dim]可读性: {result.readability_score}/100[/]")

    elif action == "analyze":
        from writing_assistant import WritingAssistant
        assistant = WritingAssistant()
        if not content:
            console.print("[red]请提供内容: --content <text>[/]")
            return
        result = assistant.full_analysis(content)
        console.print(Panel.fit(
            f"[bold cyan]内容分析报告[/]\n"
            f"字数: {result['content_stats']['word_count']} | "
            f"句子: {result['content_stats']['sentence_count']} | "
            f"预计阅读: {result['content_stats']['reading_time_minutes']}分钟",
            border_style="cyan"
        ))
        console.print("\n[bold]推荐标题:[/]")
        for t in result['titles'][:3]:
            console.print(f"  • {t['title']} (评分: {t['score']})")

    elif action == "material":
        from material_library import MaterialLibrary
        library = MaterialLibrary()
        if not content:
            # 列出素材
            materials = library.search_materials(limit=10)
            console.print(f"\n[bold cyan]最近素材 ({len(materials)}个):[/]\n")
            for m in materials:
                icon = library.MATERIAL_TYPES.get(m.type, {}).get('icon', '📄')
                title = m.title or m.content[:30] + "..."
                console.print(f"{icon} [bold]{title}[/] [dim]({m.usage_count}次使用)[/]")
        else:
            # 添加素材
            if not title:
                title = content[:30] + "..."
            material = library.add_material(
                material_type=material_type,
                content=content,
                title=title,
                tags=tags.split(',') if tags else []
            )
            console.print(f"[green]素材已添加: {material.id}[/]")

    else:
        console.print(f"[red]未知操作: {action}[/]")




@app.command("scheduler")
def scheduler_cmd(
    action: str = typer.Argument(..., help="操作: create, list, run, toggle, delete, history, stats, daemon"),
    name: str = typer.Option(None, "--name", "-n", help="任务名称"),
    cron: str = typer.Option(None, "--cron", help="Cron表达式 (如 '0 9 * * *')"),
    task_type: str = typer.Option("custom", "--type", "-t", help="类型: scrape/export/backup/cleanup/custom"),
    command: str = typer.Option(None, "--cmd", "-c", help="自定义命令"),
    task_id: str = typer.Option(None, "--id", help="任务ID"),
    desc: str = typer.Option("", "--desc", "-d", help="描述"),
):
    """定时任务调度器 - Cron定时/自动采集/任务通知"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from task_scheduler import TaskScheduler

    scheduler = TaskScheduler()

    if action == "create":
        if not name or not cron:
            console.print("[red]请提供 --name 和 --cron[/]")
            return
        task = scheduler.create_task(
            name=name,
            task_type=task_type,
            cron=cron,
            command=command,
            description=desc
        )
        console.print(f"[green]任务已创建: {task.id}[/]")
        console.print(f"  下次执行: {task.next_run}")

    elif action == "list":
        tasks = scheduler.list_tasks()
        console.print(f"\n[bold cyan]定时任务 ({len(tasks)}个)[/]\n")
        for t in tasks:
            status = "✅" if t.enabled else "🚫"
            console.print(f"{status} [{t.id}] {t.name}")
            console.print(f"   类型: {t.task_type} | Cron: {t.cron_expression}")
            console.print(f"   下次: {t.next_run or 'N/A'} | 执行: {t.run_count}次成功")

    elif action == "run":
        if not task_id:
            console.print("[red]请提供 --id[/]")
            return
        console.print(f"[blue]执行任务: {task_id}[/]")
        execution = scheduler.run_task(task_id)
        icon = "✅" if execution.status == "success" else "❌"
        console.print(f"{icon} 结果: {execution.status} (耗时 {execution.duration_seconds:.2f}秒)")

    elif action == "toggle":
        if not task_id:
            console.print("[red]请提供 --id[/]")
            return
        if scheduler.toggle_task(task_id):
            task = scheduler.get_task(task_id)
            status = "启用" if task.enabled else "禁用"
            console.print(f"[green]任务已{status}: {task_id}[/]")

    elif action == "delete":
        if not task_id:
            console.print("[red]请提供 --id[/]")
            return
        if scheduler.delete_task(task_id):
            console.print(f"[green]任务已删除: {task_id}[/]")

    elif action == "history":
        history = scheduler.get_execution_history(task_id, 20)
        console.print(f"\n[bold cyan]执行历史 ({len(history)}条)[/]\n")
        for h in history[:10]:
            icon = "✅" if h.status == "success" else "❌"
            console.print(f"{icon} [{h.started_at[:19]}] {h.status} ({h.duration_seconds:.1f}s)")

    elif action == "stats":
        stats = scheduler.get_stats()
        console.print(Panel.fit(
            f"[bold cyan]调度器统计[/]\n\n"
            f"总任务: {stats['total_tasks']}\n"
            f"已启用: {stats['enabled_tasks']} | 已禁用: {stats['disabled_tasks']}\n"
            f"总执行: {stats['total_runs']} | 成功率: {stats['success_rate']:.1f}%\n"
            f"24小时: {stats['runs_24h']} 次执行\n"
            f"平均耗时: {stats['avg_duration_seconds']:.2f}秒",
            border_style="cyan"
        ))

    elif action == "daemon":
        console.print("[yellow]启动调度器守护进程...[/]")
        scheduler.start_scheduler()
        console.print("[green]调度器运行中，按 Ctrl+C 停止[/]")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]停止调度器...[/]")
            scheduler.stop_scheduler()

    else:
        console.print(f"[red]未知操作: {action}[/]")


@app.command("extension")
def extension_cmd(
    action: str = typer.Argument(..., help="操作: install, pack, check"),
    browser: str = typer.Option("chrome", "--browser", "-b", help="浏览器: chrome, firefox"),
):
    """浏览器扩展管理 - Chrome/Firefox 插件"""
    ext_dir = Path(__file__).parent.parent / "extension"

    if action == "install":
        if browser == "chrome":
            chrome_ext = ext_dir / "chrome"
            console.print(Panel.fit(
                f"[bold cyan]Chrome 扩展安装指南[/]\n\n"
                f"1. 打开 Chrome 浏览器\n"
                f"2. 访问: [blue]chrome://extensions/[/]\n"
                f"3. 开启 [yellow]开发者模式[/]\n"
                f"4. 点击 [yellow]加载已解压的扩展程序[/]\n"
                f"5. 选择目录: [green]{chrome_ext}[/]\n\n"
                f"快捷键: [bold]Ctrl+Shift+S[/] 快速抓取",
                border_style="cyan"
            ))
        else:
            firefox_ext = ext_dir / "firefox"
            console.print(Panel.fit(
                f"[bold orange3]Firefox 扩展安装指南[/]\n\n"
                f"1. 打开 Firefox 浏览器\n"
                f"2. 访问: [blue]about:debugging[/]\n"
                f"3. 点击 [yellow]此 Firefox[/]\n"
                f"4. 点击 [yellow]临时载入附加组件[/]\n"
                f"5. 选择文件: [green]{firefox_ext / 'manifest.json'}[/]\n\n"
                f"快捷键: [bold]Ctrl+Shift+S[/] 快速抓取",
                border_style="orange3"
            ))

    elif action == "pack":
        console.print(f"[blue]打包 {browser} 扩展...[/]")
        import shutil
        import zipfile

        src_dir = ext_dir / browser
        if not src_dir.exists():
            console.print(f"[red]扩展目录不存在: {src_dir}[/]")
            raise typer.Exit(1)

        output_file = ext_dir / f"wechat-scraper-{browser}-v2.0.0.zip"

        with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file_path in src_dir.rglob('*'):
                if file_path.is_file() and '__pycache__' not in str(file_path):
                    arc_name = file_path.relative_to(src_dir)
                    zf.write(file_path, arc_name)

        console.print(f"[green]扩展已打包: {output_file}[/]")

    elif action == "check":
        chrome_ok = (ext_dir / "chrome" / "manifest.json").exists()
        firefox_ok = (ext_dir / "firefox" / "manifest.json").exists()

        console.print(Panel.fit(
            f"[bold cyan]扩展文件检查[/]\n\n"
            f"Chrome 扩展: [{'green' if chrome_ok else 'red'}]{'✓' if chrome_ok else '✗'}[/]\n"
            f"Firefox 扩展: [{'green' if firefox_ok else 'red'}]{'✓' if firefox_ok else '✗'}[/]\n\n"
            f"共享资源: [green]✓[/]",
            border_style="cyan"
        ))

    else:
        console.print(f"[red]未知操作: {action}[/]")


@app.command("ai-write")
def ai_write_cmd(
    action: str = typer.Argument(..., help="操作: title, summary, rewrite, batch, stats, config"),
    content: str = typer.Option(None, "--content", "-c", help="内容或文件路径"),
    provider: str = typer.Option("deepseek", "--provider", "-p", help="模型提供商: openai/anthropic/deepseek/baidu/alibaba"),
    model: str = typer.Option(None, "--model", "-m", help="模型名称 (如 gpt-4, claude-3-opus, deepseek-chat)"),
    style: str = typer.Option("professional", "--style", "-s", help="风格: professional/casual/marketing/news/minimal/story"),
    count: int = typer.Option(3, "--count", "-n", help="生成数量"),
    api_key: str = typer.Option(None, "--api-key", help="API Key (或设置环境变量)"),
    file_list: str = typer.Option(None, "--files", "-f", help="批量处理文件列表(逗号分隔)"),
):
    """AI智能写作引擎 v2.0 - 真LLM驱动/多模型/成本追踪"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from ai_writer_engine import AIWriterEngine, ModelProvider

    engine = AIWriterEngine()

    # 设置API key (如果提供)
    if api_key:
        import os
        provider_upper = provider.upper()
        os.environ[f"{provider_upper}_API_KEY"] = api_key

    if action == "title":
        if not content:
            console.print("[red]请提供内容: --content <text>[/]")
            return
        console.print(f"[blue]使用 {provider} 生成标题...[/]")
        result = engine.generate_title(
            content=content,
            provider=ModelProvider(provider),
            model=model,
            style=style,
            count=count
        )
        console.print(f"\n[bold cyan]生成的标题 ({len(result['titles'])}个):[/]\n")
        for i, t in enumerate(result['titles'], 1):
            icon = "👑" if i == 1 else f"{i}."
            console.print(f"{icon} [bold]{t['title']}[/]")
            console.print(f"   [dim]评分: {t['score']}/100 | 长度: {t['length']}字[/]")
        console.print(f"\n[dim]总耗时: {result['metadata']['total_time']:.2f}s | "
                     f"输入token: {result['metadata']['input_tokens']} | "
                     f"输出token: {result['metadata']['output_tokens']} | "
                     f"成本: ${result['metadata']['cost']:.4f}[/]")

    elif action == "summary":
        if not content:
            console.print("[red]请提供内容: --content <text>[/]")
            return
        console.print(f"[blue]使用 {provider} 生成摘要...[/]")
        result = engine.generate_summary(
            content=content,
            provider=ModelProvider(provider),
            model=model,
            style=style
        )
        console.print(f"\n[bold cyan]摘要 ({result['summary_style']}风格):[/]\n")
        console.print(Panel(result['summary'], border_style="cyan"))
        console.print(f"\n[dim]字数: {result['word_count']} | "
                     f"原文压缩比: {result['compression_ratio']:.1%} | "
                     f"质量评分: {result['quality_score']}/100[/]")
        console.print(f"[dim]成本: ${result['metadata']['cost']:.4f}[/]")

    elif action == "rewrite":
        if not content:
            console.print("[red]请提供内容: --content <text>[/]")
            return
        console.print(f"[blue]使用 {provider} 改写内容 ({style}风格)...[/]")
        result = engine.rewrite_content(
            content=content,
            provider=ModelProvider(provider),
            model=model,
            target_style=style
        )
        console.print(f"\n[bold cyan]改写结果:[/]\n")
        console.print(Panel(result['rewritten_content'], border_style="green"))
        console.print(f"\n[dim]原文: {result['original_word_count']}字 | "
                     f"改写: {result['rewritten_word_count']}字 | "
                     f"保持率: {result['content_retention']:.1%}[/]")
        console.print(f"[dim]成本: ${result['metadata']['cost']:.4f}[/]")

    elif action == "batch":
        if not file_list:
            console.print("[red]请提供文件列表: --files 'file1.txt,file2.txt'[/]")
            return
        files = file_list.split(',')
        console.print(f"[blue]批量处理 {len(files)} 个文件...[/]")
        results = engine.batch_generate(
            contents=files,
            provider=ModelProvider(provider),
            task_type="title"
        )
        console.print(f"\n[bold cyan]批量处理结果:[/]\n")
        for i, r in enumerate(results, 1):
            status = "✅" if 'titles' in r else "❌"
            cost = r.get('metadata', {}).get('cost', 0)
            console.print(f"{status} 文件{i}: 成本 ${cost:.4f}")
        total_cost = sum(r.get('metadata', {}).get('cost', 0) for r in results if 'metadata' in r)
        console.print(f"\n[dim]总成本: ${total_cost:.4f}[/]")

    elif action == "stats":
        stats = engine.get_usage_stats(days=30)
        console.print(Panel.fit(
            f"[bold cyan]AI写作引擎使用统计 (30天)[/]\n\n"
            f"总请求: {stats['total_requests']}\n"
            f"总token: {stats['total_tokens']:,}\n"
            f"总成本: ${stats['total_cost']:.4f}\n"
            f"平均质量: {stats['avg_quality_score']:.1f}/100\n"
            f"成功率: {stats['success_rate']:.1f}%",
            border_style="cyan"
        ))
        if stats.get('provider_stats'):
            console.print("\n[bold]提供商统计:[/]")
            for p, s in stats['provider_stats'].items():
                console.print(f"  {p}: {s['requests']}次, ${s['cost']:.4f}")

    elif action == "config":
        console.print(Panel.fit(
            "[bold cyan]AI写作引擎配置指南[/]\n\n"
            "环境变量设置:\n"
            "  OPENAI_API_KEY - OpenAI API密钥\n"
            "  ANTHROPIC_API_KEY - Anthropic API密钥\n"
            "  DEEPSEEK_API_KEY - DeepSeek API密钥\n"
            "  BAIDU_API_KEY - 百度文心API密钥\n"
            "  BAIDU_SECRET_KEY - 百度Secret Key\n"
            "  ALIBABA_API_KEY - 阿里云通义API密钥\n\n"
            "支持的模型:\n"
            "  openai: gpt-4, gpt-4-turbo, gpt-3.5-turbo\n"
            "  anthropic: claude-3-opus, claude-3-sonnet\n"
            "  deepseek: deepseek-chat, deepseek-coder\n"
            "  baidu: ernie-bot, ernie-bot-4\n"
            "  alibaba: qwen-turbo, qwen-plus, qwen-max",
            border_style="cyan"
        ))

    else:
        console.print(f"[red]未知操作: {action}[/]")


@app.command("agent")
def agent_cmd(
    action: str = typer.Argument(..., help="操作: search, ask, recommend"),
    query: str = typer.Option(None, "--query", "-q", help="搜索查询/问题"),
    article_id: str = typer.Option(None, "--article", "-a", help="基于文章ID推荐"),
    author: str = typer.Option(None, "--author", help="作者筛选/基于作者推荐"),
    topic: str = typer.Option(None, "--topic", "-t", help="基于主题推荐"),
    limit: int = typer.Option(5, "--limit", "-l", help="结果数量"),
):
    """智能Agent搜索 - 语义检索/问答/推荐 (需Node.js)"""
    import subprocess
    import shutil

    # Check if Node.js is available
    if not shutil.which("node"):
        console.print("[red]错误: 需要 Node.js 环境来运行 Agent[/]")
        console.print("[yellow]请安装 Node.js: https://nodejs.org/[/]")
        return

    agents_dir = Path(__file__).parent.parent / "agents"
    cli_path = agents_dir / "dist" / "cli.js"

    if not cli_path.exists():
        console.print("[yellow]Agent 尚未编译，正在构建...[/]")
        try:
            result = subprocess.run(
                ["npm", "install"],
                cwd=agents_dir,
                capture_output=True,
                text=True
            )
            result = subprocess.run(
                ["npx", "tsc"],
                cwd=agents_dir,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                console.print(f"[red]编译失败: {result.stderr}[/]")
                return
        except Exception as e:
            console.print(f"[red]构建失败: {e}[/]")
            return

    # Build command
    cmd = ["node", str(cli_path)]

    if action == "search":
        if not query:
            console.print("[red]请提供搜索查询: --query <text>[/]")
            return
        cmd.extend(["search", query, "-l", str(limit)])
        if author:
            cmd.extend(["-a", author])

    elif action == "ask":
        if not query:
            console.print("[red]请提供问题: --query <question>[/]")
            return
        cmd.extend(["ask", query, "-s", str(limit)])

    elif action == "recommend":
        cmd.append("recommend")
        if article_id:
            cmd.extend(["-a", article_id])
        if author:
            cmd.extend(["-A", author])
        if topic:
            cmd.extend(["-t", topic])
        cmd.extend(["-l", str(limit)])

    else:
        console.print(f"[red]未知操作: {action}[/]")
        return

    # Execute
    try:
        console.print(f"[blue]运行 Agent: {action}...[/]\n")
        result = subprocess.run(cmd, capture_output=False, text=True)
    except Exception as e:
        console.print(f"[red]执行失败: {e}[/]")


@app.command("kg")
def kg_cmd(
    action: str = typer.Argument(..., help="操作: extract, network, topics, clusters, trend, author, industry"),
    target: str = typer.Option(None, "--target", "-t", help="目标(作者/主题/行业)"),
    target2: str = typer.Option(None, "--target2", help="对比目标"),
    author: str = typer.Option(None, "--author", "-a", help="作者名称"),
    topic: str = typer.Option(None, "--topic", help="主题名称"),
):
    """知识图谱与智能洞察 - 实体抽取/网络分析/趋势报告 (需Node.js + Neo4j)"""
    import subprocess
    import shutil

    if not shutil.which("node"):
        console.print("[red]错误: 需要 Node.js 环境[/]")
        return

    agents_dir = Path(__file__).parent.parent / "agents"
    cli_path = agents_dir / "dist" / "cli.js"

    if not cli_path.exists():
        console.print("[yellow]Agent 尚未编译，正在构建...[/]")
        try:
            subprocess.run(["npm", "install"], cwd=agents_dir, capture_output=True)
            subprocess.run(["npx", "tsc"], cwd=agents_dir, capture_output=True)
        except Exception as e:
            console.print(f"[red]构建失败: {e}[/]")
            return

    cmd = ["node", str(cli_path)]

    if action in ["extract", "network", "topics", "clusters"]:
        cmd.extend(["graph", action])
        if author:
            cmd.extend(["-A", author])
        if topic:
            cmd.extend(["-t", topic])
    elif action in ["trend", "author", "industry", "compare"]:
        cmd.extend(["insight", action])
        if target:
            cmd.extend(["-t", target])
        if target2:
            cmd.extend(["-t2", target2])
    else:
        console.print(f"[red]未知操作: {action}[/]")
        return

    try:
        console.print(f"[blue]运行知识图谱: {action}...[/]\n")
        subprocess.run(cmd)
    except Exception as e:
        console.print(f"[red]执行失败: {e}[/]")


@app.command("version")
def version():
    """显示版本信息"""
    console.print(Panel.fit(
        "[bold cyan]微信文章抓取助手[/]\n"
        "[dim]WeChat Article Scraper CLI[/]\n\n"
        "版本: [green]3.36.0[/]\n"
        "策略: [blue]6-level routing[/]\n"
        "作者: [yellow]Claude Code[/]",
        border_style="cyan"
    ))


if __name__ == "__main__":
    app()
