#!/bin/bash
# Build script for wechat-article-scraper CLI single-file executable

set -e

echo "=== Building wechat-article-scraper CLI ==="

# Create virtual environment if not exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
uv pip install -q pyinstaller typer rich pyyaml requests beautifulsoup4 html2text markdownify openpyxl reportlab scrapling jinja2

# Clean previous builds
rm -rf dist build

# Build with PyInstaller
echo "Building single-file executable..."
pyinstaller w.spec --clean

# Show result
echo ""
echo "=== Build complete ==="
ls -lh dist/w
echo ""
echo "Test: ./dist/w version"
./dist/w version
