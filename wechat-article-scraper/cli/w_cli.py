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
):
    """通过搜狗搜索发现微信文章"""
    console.print(f"[blue]搜索关键词: [bold]{keyword}[/][/]")
    console.print(f"[dim]限制: {limit} 条结果[/]\n")

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
    action: str = typer.Argument(..., help="操作: add/list/remove"),
    biz_id: Optional[str] = typer.Argument(None, help="公众号 biz ID"),
    interval: int = typer.Option(3600, "--interval", "-i", help="检查间隔(秒)"),
):
    """管理公众号监控订阅"""
    if action == "list":
        console.print("[dim]监控列表功能开发中...[/]")

    elif action == "add":
        if not biz_id:
            console.print("[red]请提供公众号 biz ID[/]")
            raise typer.Exit(1)
        console.print(f"[green]添加监控: {biz_id}, 间隔: {interval}秒[/]")

    elif action == "remove":
        if not biz_id:
            console.print("[red]请提供公众号 biz ID[/]")
            raise typer.Exit(1)
        console.print(f"[green]移除监控: {biz_id}[/]")

    else:
        console.print(f"[red]未知操作: {action}[/]")
        console.print("[dim]可用操作: add, list, remove[/]")


@app.command("version")
def version():
    """显示版本信息"""
    console.print(Panel.fit(
        "[bold cyan]微信文章抓取助手[/]\n"
        "[dim]WeChat Article Scraper CLI[/]\n\n"
        "版本: [green]3.21.0[/]\n"
        "策略: [blue]6-level routing[/]\n"
        "作者: [yellow]Claude Code[/]",
        border_style="cyan"
    ))


if __name__ == "__main__":
    app()
