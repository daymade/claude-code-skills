# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Stage 1 now defaults to "safe mode"**: only low-risk (non-word, high-confidence) corrections are auto-applied. Medium/high-risk ones (common words, ≤2-char, real-word fragments) are tracked to `*_needs_review.md` for human/AI review instead of being applied silently. `Applied: 0` on a clean transcript is now expected, not a bug. Pass `--apply-all` to restore the previous apply-every-level behavior.
- Expanded `utils/common_words.py` with real common words that had been mis-added as correction sources (`多深`, `早生`, `龙虾`, `小龙虾`), so the add-time guard, the risk classifier, and `--audit` all recognize them.
- Context rules are now gated by `review_mode` like dictionary rules (safe mode defers risky ones instead of applying them unconditionally).
- `--audit` runs an advisory jieba heuristic to surface 4+ char "real-word" false-positive rules for human review (see Known limitations). Adds `jieba` to dependencies.
- **Finalize now prescribes `/bin/mv -f` instead of a bare `mv`.** SKILL.md step 9 and new troubleshooting entry #7: on macOS `mv` is commonly aliased to `mv -i`, which skips overwriting an existing target while still exiting 0 — so a finalize `mv *_stage1.md *.md && echo done` reported success while the un-corrected file silently survived as the output. Doc-only change.
- **Native AI Correction step-4 ("Needs verification") now prescribes a local-first search ladder.** Previously the instruction was "Search it, don't guess — WebSearch, or a local grep," which put WebSearch first and left "local grep" vague — so project / person names whose canonical spelling already lived in another `corrections.db` domain or in project delivery docs got escalated to the user instead of resolved locally. The ladder now orders: all `corrections.db` domains (not just the current `--domain`) → project delivery docs → memory → WebSearch (public entities only) → then the user. Doc-only.

### Deprecated
- `--review` is now a no-op (safe mode is the default). Use `--apply-all` for the opposite behavior.

### Fixed
- **False-positive class where the risk guard was computed but then ignored.** `_assess_risk()` already classified risky rules correctly (`多深`→high, `小龙虾`→medium), but `review_mode` defaulted to `False`, so every risk level was applied regardless. On a clean Feishu-ASR transcript this silently corrupted correct text (`抓多深`→`抓多申`, `小龙虾`→`小 Claude`). Safe-mode-by-default now defers all medium/high-risk changes — dictionary **and** context rules. This narrows the class but does NOT fully close it (see Known limitations). Regression tests in `tests/test_common_words_safety.py::TestProductionFalsePositives2026_06`.
- **`_apply_context_rules` now honors `review_mode`.** Previously context (regex) rules were applied unconditionally even in safe mode, and the run summary mis-counted them as "skipped" while the text was already mutated. They are now risk-gated like dictionary rules, so the summary and `*_needs_review.md` are accurate.
- **`fix_transcript_enhanced.py` no longer silently flips to safe mode.** Its hand-built args now pass `apply_all=True`, preserving this automation entry point's historical "apply everything" behavior (the safe-mode default had silently downgraded it with no opt-out).
- **History no longer records non-applied changes.** In safe mode, skipped medium/high Stage-1 changes were persisted to the history table as if applied; only actually-applied changes are now recorded.

### Known limitations
- **Safe mode does NOT catch the "4+ char real-word" false-positive class.** `_assess_risk` labels any rule with `len(from_text) >= 4`, confidence ≥ 0.9, and not in the common-word list as `low`, so it auto-applies — even when `from_text` is itself valid text (`济南大学`→`暨南大学`, `关税证明`→`完税证明`). This is structural: "low risk" is defined by length/confidence/word-list, which is orthogonal to "is this real text." `--audit` now uses a jieba heuristic (`is_likely_valid_phrase`) to **surface** such rules for human review, but it is advisory and low-precision (it also flags many legitimate ASR-garble rules, not just genuine false positives), so it cannot gate auto-application. Fully closing this class needs language-model-grade validity judgment, not a dictionary heuristic.

### Security
- API keys are now loaded from the canonical config directory (`~/.transcript-fixer/config.json`) first. Environment variables (`GLM_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`) are treated as explicit overrides only.
- Removed all shell-config-file scraping for secrets.
- Config directory restricted to `0o700` and config file to `0o600`.

### Added
- `scripts/core/defaults.py` — single source of truth for all variable defaults: AI provider/model/base URL/auth header, timeouts, chunk size, file permissions, and database `system_config` defaults.
- Database `system_config` defaults are now written by `CorrectionRepository._initialize_system_config()` from `core.defaults.SYSTEM_CONFIG_DEFAULTS` instead of being hard-coded in `schema.sql`.
- `--validate` now checks that `system_config.api_provider`, `api_model`, and `api_base_url` match the canonical `core.defaults` values and reports drift as an error.
- Added migration `v2.3` to align existing databases with the new canonical defaults.

### Changed
- Updated GLM Anthropic-compatible endpoint authentication from `Authorization: Bearer` to `x-api-key`.
- Updated default AI models to `GLM-5.2` (primary) and `GLM-5-turbo` (fallback).
- Deduplicated sync/async AI processor logic into `scripts/core/ai_utils.py` (single source of truth for chunking, prompt building, and response parsing).
- `fix_transcript_enhanced.py` now calls the correction pipeline directly instead of spawning a `subprocess` wrapper.
- `httpx` clients use `http2=False` to avoid the missing `h2` package.
- `scripts/core/ai_processor.py` and `scripts/core/ai_processor_async.py` now import all AI defaults from `core.defaults`.
- `scripts/utils/config.py` now imports app name/version, timeout, retries, and permission modes from `core.defaults`.
- `scripts/utils/migrations.py` now interpolates default model/provider/base URL/domain from `core.defaults` instead of hard-coding them.
- `scripts/utils/diff_formats/markdown_format.py` now takes an optional `model` parameter and defaults to `DEFAULT_MODEL` instead of a hard-coded model name.
- `scripts/generate_diff_report.py` accepts an optional `--model` argument and passes it to the report generator.
- `scripts/cli/commands.py` passes the actual `ai_processor.model` to `generate_full_report()` during Stage 3.

### Fixed
- Defensive parsing of Anthropic-style API responses with clear errors for unexpected shapes.
- `fix_transcript_enhanced.py` path validation now allows the input file's parent directory and symlinks (needed on macOS `/tmp`).
- `--validate` reports a broken config file as an error instead of a warning.
- `scripts/utils/diff_generator.py` was not directly executable; added `scripts/generate_diff_report.py` as a thin CLI wrapper that produces all four output formats.
- Replaced remaining hard-coded `GLM-4.6` defaults in `scripts/core/schema.sql`, `scripts/utils/migrations.py`, and `scripts/utils/diff_formats/markdown_format.py` with references to `core.defaults`.

### Documentation
- Added a "Maintaining Single Source of Truth" section to `references/best_practices.md`.
- Rewrote `references/glm_api_setup.md` and `references/installation_setup.md` to document config-file-first auth, current models, and `uv` usage.
- Updated `SKILL.md`, `references/troubleshooting.md`, `references/architecture.md`, `references/best_practices.md`, `references/script_parameters.md`, `references/workflow_guide.md`, `references/database_schema.md`, and `references/file_formats.md` to remove outdated env-var-first instructions, stale model names, and non-existent script references.
- Added `generate_diff_report.py` usage to `SKILL.md`, `references/script_parameters.md`, `references/workflow_guide.md`, and `references/best_practices.md`.

## [1.2.1] - 2026-03-16

### Added
- Initial transcript-fixer skill in the daymade-audio suite.
- SQLite-backed correction dictionary with learning engine.
- Stage 1 dictionary corrections and Stage 2 AI corrections.

[Unreleased]: https://github.com/daymade/skills/compare/daymade-audio-v1.2.1...HEAD
[1.2.1]: https://github.com/daymade/skills/releases/tag/daymade-audio-v1.2.1
