# Known Claude Code Plugin Issues

This document tracks known bugs and issues related to Claude Code plugins.

## Open Issues

### GitHub #17832 - Plugins Not Auto-Enabled After Install

**Status:** OPEN
**URL:** https://github.com/anthropics/claude-code/issues/17832

**Problem:** When installing a plugin from a marketplace, Claude Code adds the plugin to `installed_plugins.json` but does NOT add it to `settings.json` `enabledPlugins`.

**Impact:** Plugins appear "installed" but don't function. Skills silently fail to load.

**Workaround:** Manually enable via CLI or edit settings.json:
```bash
claude plugin enable plugin-name@marketplace
```

---

### GitHub #19696 - installed_plugins.json Naming Misleading

**Status:** OPEN
**URL:** https://github.com/anthropics/claude-code/issues/19696

**Problem:** The file `installed_plugins.json` contains ALL plugins ever registered, including disabled ones. The actual enabled state is tracked separately in `settings.json`.

**Impact:** Confusing for developers - file shows many plugins but only some are active.

**Note:** This is a naming/documentation issue, not a functional bug.

---

### GitHub #17089 - Local Plugins Breaking After 2.1.x Update

**Status:** Reported
**URL:** https://github.com/anthropics/claude-code/issues/17089

**Problem:** Local plugins no longer persist after the 2.1.x update.

**Workaround:** Create a marketplace wrapper structure for local plugins.

---

### GitHub #13543 - MCP Servers from Marketplace Not Available

**Status:** Reported
**URL:** https://github.com/anthropics/claude-code/issues/13543

**Problem:** After updating to Claude Code 2.0.64, MCP servers defined in marketplace plugins were no longer available.

---

### GitHub #16260 - Contradictory Scope Error Messages

**Status:** Reported
**URL:** https://github.com/anthropics/claude-code/issues/16260

**Problem:** CLI gives contradictory error messages about plugin scope.

**Workaround:** Manually edit settings.json to fix scope issues.

## Resolved Issues

(Add resolved issues here as they are fixed)

## Related Documentation

- [Plugins Reference](https://code.claude.com/docs/en/plugins-reference)
- [Claude Code Settings](https://code.claude.com/docs/en/settings)
