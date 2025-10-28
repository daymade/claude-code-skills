# Setup Guide

Complete installation and configuration guide for transcript-fixer.

## Table of Contents

- [Installation](#installation)
- [API Configuration](#api-configuration)
- [Environment Setup](#environment-setup)
- [Next Steps](#next-steps)

## Installation

### Dependencies

Install required dependencies using uv:

```bash
uv pip install -r requirements.txt
```

Or sync the project environment:

```bash
uv sync
```

**Required packages**:
- `anthropic` - For Claude API integration (future)
- `requests` - For GLM API calls
- `difflib` - Standard library for diff generation

### Database Initialization

Initialize the SQLite database (first time only):

```bash
uv run scripts/fix_transcription.py --init
```

This creates `~/.transcript-fixer/corrections.db` with the complete schema:
- 8 tables (corrections, context_rules, history, suggestions, etc.)
- 3 views (active_corrections, pending_suggestions, statistics)
- ACID transactions enabled
- Automatic backups before migrations

See `file_formats.md` for complete database schema.

## API Configuration

### GLM API Key (Required for Stage 2)

Stage 2 AI corrections require a GLM API key.

1. **Obtain API key**: Visit https://open.bigmodel.cn/
2. **Register** for an account
3. **Generate** an API key from the dashboard
4. **Set environment variable**:

```bash
export GLM_API_KEY="your-api-key-here"
```

**Persistence**: Add to shell profile for permanent access:

```bash
# For bash
echo 'export GLM_API_KEY="your-key"' >> ~/.bashrc
source ~/.bashrc

# For zsh
echo 'export GLM_API_KEY="your-key"' >> ~/.zshrc
source ~/.zshrc
```

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
✅ GLM_API_KEY is set

============================================================
✅ All checks passed! Configuration is valid.
============================================================
```

## Environment Setup

### Python Environment

**Required**: Python 3.8+

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
├── corrections.db              # SQLite database
├── corrections.YYYYMMDD.bak   # Automatic backups
└── (migration artifacts)
```

**Important**: The `.db` file should NOT be committed to Git. Export corrections to JSON for version control instead.

## Next Steps

After setup:
1. Add initial corrections (5-10 terms)
2. Run first correction on a test file
3. Review learned suggestions after 3-5 runs
4. Build domain-specific dictionaries

See `workflow_guide.md` for detailed usage instructions.
