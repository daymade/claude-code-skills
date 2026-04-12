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


@app.command("version")
def version():
    """显示版本信息"""
    console.print(Panel.fit(
        "[bold cyan]微信文章抓取助手[/]\n"
        "[dim]WeChat Article Scraper CLI[/]\n\n"
        "版本: [green]3.25.0[/]\n"
        "策略: [blue]6-level routing[/]\n"
        "作者: [yellow]Claude Code[/]",
        border_style="cyan"
    ))


if __name__ == "__main__":
    app()
