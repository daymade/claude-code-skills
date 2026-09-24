#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow", "numpy"]
# ///
"""crop_segments.py — 超长报告页截图切段，供逐段 Read 自验。

用法:
    uv run scripts/crop_segments.py page.png [--segments 5] [--scale 0.5] [--out-dir DIR]

为什么存在: Chrome headless 按 window-size 截图，超长页要传很大的 H（如 17000），
底部会留一大段背景空白；整张又超出单次 Read 的可读尺寸。本脚本
① 自动检测内容真实底部（与左上角背景色亮度差 >12 的最后一行，再放 40px 余量），
② 均分成 N 段，③ 默认缩到一半分辨率（Read 读图更稳），输出 <stem>-seg1.png…。

参数取值依据:
- 亮度差阈值 12: 暖纸底(#FBF9F4)与正文/边框的最小实测差远大于 12，抗 JPEG 噪点又不误裁淡色块。
- 余量 40px: 保住最后一行的下缘阴影/边框。
- scale 0.5: 1400px 宽页缩到 700px，单段仍能看清 13px 正文，且体积可控。
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def main() -> None:
    ap = argparse.ArgumentParser(description="超长截图切段供逐段 Read")
    ap.add_argument("png", help="render_report.sh 或 Chrome headless 截出的整页 PNG")
    ap.add_argument("--segments", type=int, default=5, help="切几段（默认 5）")
    ap.add_argument("--scale", type=float, default=0.5, help="每段缩放比（默认 0.5）")
    ap.add_argument("--out-dir", default=None, help="输出目录（默认与输入同目录）")
    args = ap.parse_args()

    src = Path(args.png)
    if not src.is_file():
        print(f"❌ 找不到文件: {src}", file=sys.stderr)
        sys.exit(2)
    if args.segments < 1:
        print("❌ --segments 至少为 1", file=sys.stderr)
        sys.exit(2)

    img = Image.open(src)
    w, h = img.size
    gray = np.asarray(img.convert("L"))
    bg = int(gray[10, 10])  # 左上角当背景样本（报告页四周留白，这里必是底色）
    rows = np.where(np.abs(gray.astype(int) - bg).max(axis=1) > 12)[0]
    bottom = min(h, int(rows.max()) + 40) if len(rows) else h
    print(f"画布 {w}x{h} · 内容底部 ≈ {bottom}px")

    # 截断检测。Chrome 严格按 --window-size 截图、不会自动增高，而 render_report.sh 的
    # PNG 校验只证明字节是合法 PNG——页面长过传入的 H 时尾部被静默裁掉，此后作者 Read
    # 的这张图、切出来的每一段、交给独立审阅的截图，看的都是一张尾部从未渲染过的页。
    # design-principles §6 要求把最强的结论放最后（「每页有落锤」），所以被裁的正是它。
    # 判据：内容一直贴到画布最后一行 → 画布切在了内容中间，而不是内容自然结束在画布内。
    #
    # 这个判据有一个真实的假阳性，而且它的"标准处方"在该情形下不收敛，所以必须一起写出来：
    # 页面里任何用 vh/svh/lvh/dvh 定尺寸的元素（典型是 `max-height:78vh` 的内嵌滚动面板），
    # 在 headless 下 1vh = --window-size 的 H/100 —— H 调大，那个元素跟着长高，页面总高
    # 永远追着画布跑，内容于是永远贴底。此时"再调大 H"是一个无限循环：作者会一路把 H
    # 从 3000 试到 40000，每次都拿到同一条警告，最后学会无视它 —— 而一道被训练成噪音的
    # 闸门，对真截断也不再有效（误杀健康输入比漏报更贵，就贵在这里）。
    # 判别只要一次：换一个明显不同的 H 再跑本脚本，比较两次的"内容底部"。
    if len(rows) and int(rows.max()) >= h - 2:
        print(
            f"⚠️  内容一直延伸到画布最后一行（{h}px）。两种成因，处置相反，先判别再动手：\n"
            f"   ① 真截断（页面比 H 长，尾部从未渲染）→ 调大 H 重渲染。\n"
            f"   ② 页面用了 vh 单位（如内嵌滚动面板 max-height:78vh）→ headless 下 1vh 随 H 变，\n"
            f"      页面高度追着画布跑，调大 H 永远不收敛，别进这个循环。\n"
            f"   判别法：换一个明显不同的 H 再渲染一次并重跑本脚本——\n"
            f"      「内容底部」几乎不变 = ①，已解决；仍≈新画布高 = ②，改用一个大到\n"
            f"      board 高度 /(1 - vh占比) 以上的 H 让它自然收敛，或临时改掉那条 vh 规则。\n"
            f"   在判别出结论之前，别把这张图当作完整页拿去 Read 或交给独立审阅。",
            file=sys.stderr,
        )

    out_dir = Path(args.out_dir) if args.out_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    n = args.segments
    step = (bottom + n - 1) // n
    for i in range(n):
        top = i * step
        if top >= bottom:
            break
        seg = img.crop((0, top, w, min(top + step, bottom)))
        if args.scale != 1:
            seg = seg.resize(
                (max(1, int(w * args.scale)), max(1, int(seg.height * args.scale)))
            )
        out = out_dir / f"{src.stem}-seg{i + 1}.png"
        seg.save(out)
        print(f"  {out}  {seg.size[0]}x{seg.size[1]}")
    print("→ 逐段 Read 核对（版式/SVG 是否画出/文字截断），再交付。")


if __name__ == "__main__":
    main()
