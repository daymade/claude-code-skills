# Setup Guide

Complete installation and configuration guide for transcript-fixer.

## Table of Contents

- [Installation](#installation)
- [API Configuration](#api-configuration)
- [Environment Setup](#environment-setup)
- [Next Steps](#next-steps)

## Installation

### Dependencies

所有脚本使用 PEP 723 内联元数据，`uv run` 会自动安装依赖。只需要安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 即可。

```bash
# 直接运行（推荐）
uv run scripts/fix_transcription.py --help
```

如需手动安装依赖：

```bash
uv pip install -r requirements.txt
```

**Required packages**:
- `httpx>=0.24.0` - 用于 GLM API 调用
- `filelock>=3.13.0` - 用于线程安全操作

### Database Initialization

Initialize the SQLite database (first time only):

```bash
uv run scripts/fix_transcription.py --init
```

This creates `~/.transcript-fixer/` with the complete schema:
- 8 tables (corrections, context_rules, history, suggestions, etc.)
- 3 views (active_corrections, pending_suggestions, statistics)
- ACID transactions enabled
- Automatic backups before migrations
- Config directory restricted to `0o700`

See `file_formats.md` for complete database schema.

## API Configuration

### GLM API Key (Required for Stage 2)

Stage 2 AI corrections require a GLM API key.

1. **Obtain API key**: Visit https://open.bigmodel.cn/
2. **Register** for an account
3. **Generate** an API key from the dashboard
4. **Write to config file**:

```bash
# 先初始化目录
uv run scripts/fix_transcription.py --init
```

然后编辑 `~/.transcript-fixer/config.json`：

```json
{
  "environment": "development",
  "database": {
    "path": "~/.transcript-fixer/corrections.db",
    "max_connections": 5,
    "connection_timeout": 30.0
  },
  "api": {
    "api_key": "your-glm-api-key",
    "base_url": null,
    "timeout": 60.0,
    "max_retries": 3
  },
  "paths": {
    "config_dir": "~/.transcript-fixer",
    "data_dir": "~/.transcript-fixer/data",
    "log_dir": "~/.transcript-fixer/logs",
    "cache_dir": "~/.transcript-fixer/cache"
  },
  "resources": {
    "max_text_length": 1000000,
    "max_file_size": 10000000,
    "max_concurrent_tasks": 10
  },
  "features": {
    "enable_learning": true,
    "enable_metrics": true,
    "enable_auto_approval": false
  },
  "debug": false
}
```

### Environment Variable Overrides (Optional)

环境变量仅用于临时覆盖或 CI/容器场景：

```bash
export GLM_API_KEY="your-api-key-here"
export ANTHROPIC_API_KEY="your-api-key-here"
export ANTHROPIC_BASE_URL="https://open.bigmodel.cn/api/anthropic"
export TRANSCRIPT_FIXER_CONFIG_DIR="/custom/config/dir"
```

**不要**把 `GLM_API_KEY` 写进 `~/.bashrc` 或 `~/.zshrc` 持久化。

### Verify Configuration

Run validation to check setup:

```bash
uv run scripts/fix_transcription.py --validate
```

**Expected output**:
```
🔍 Validating transcript-fixer configuration...

✅ Configuration directory exists: ~/.transcript-fixer
✅ Database valid: 0 corrections
✅ All 8 tables present
✅ API key is configured

============================================================
✅ All checks passed! Configuration is valid.
============================================================
```

## Environment Setup

### Python Environment

**Required**: Python 3.10+

**Recommended**: Use uv for all Python operations:

```bash
# Never use system python directly
uv run scripts/fix_transcription.py  # ✅ Correct

# Don't use system python
python scripts/fix_transcription.py  # ❌ Wrong
```

### Directory Structure

After initialization, the directory structure is:

```
~/.transcript-fixer/
├── config.json                 # API key and settings (0o600)
├── corrections.db              # SQLite database
├── corrections.YYYYMMDD.bak   # Automatic backups
├── data/                       # Application data
├── logs/                       # Log files
└── cache/                      # Cache files
```

**Important**: The `.db` and `config.json` files should NOT be committed to Git. Export corrections to JSON for version control instead.

## Next Steps

After setup:
1. Add initial corrections (5-10 terms)
2. Run first correction on a test file
3. Review learned suggestions after 3-5 runs
4. Build domain-specific dictionaries

See `workflow_guide.md` for detailed usage instructions.
