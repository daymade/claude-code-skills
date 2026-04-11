#!/usr/bin/env python3
"""
Setup script for wechat-article-scraper CLI
"""

from setuptools import setup, find_packages
from pathlib import Path

README = (Path(__file__).parent / "README.md").read_text(encoding="utf-8")

setup(
    name="wechat-article-scraper-cli",
    version="3.20.0",
    description="World-class WeChat Article Scraper CLI",
    long_description=README,
    long_description_content_type="text/markdown",
    author="Claude Code",
    packages=find_packages(),
    install_requires=[
        "typer[all]>=0.9.0",
        "rich>=13.0.0",
        "pyyaml>=6.0",
        "requests>=2.28.0",
        "beautifulsoup4>=4.11.0",
        "html2text>=2020.1.16",
        "markdownify>=0.11.0",
        "openpyxl>=3.0.10",
        "reportlab>=3.6.0",
        "scrapling>=0.3.0",
        "jinja2>=3.1.0",
    ],
    entry_points={
        "console_scripts": [
            "w=w_cli:app",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
