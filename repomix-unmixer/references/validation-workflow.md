# Validation Workflow for Unmixed Content

This guide provides detailed validation procedures for verifying the quality and correctness of unmixed repomix content, with special focus on Claude Code skills.

## Overview

After unmixing a repomix file, validation ensures:
- All files were extracted correctly
- Directory structure is intact
- Content integrity is preserved
- Skills (if applicable) meet Claude Code requirements

## General Validation Workflow

### Step 1: File Count Verification

Compare the extracted file count with the expected count.

**Check extraction output:**
```
✅ Successfully extracted 20 files!
```

**Verify against directory structure:**
```bash
# Count files in the repomix directory structure section
grep -c "^  " repomix-file.xml

# Count extracted files
find /tmp/extracted -type f | wc -l
```

**Expected result:** Counts should match (accounting for any excluded binary files).

### Step 2: Directory Structure Validation

Compare the extracted structure with the repomix directory structure section.

**Extract directory structure from repomix file:**
```bash
# For XML format
sed -n '/<directory_structure>/,/<\/directory_structure>/p' repomix-file.xml
```

**Compare with extracted structure:**
```bash
tree /tmp/extracted
# or
ls -R /tmp/extracted
```

**Validation checks:**
- [ ] All directories present
- [ ] Nesting levels match
- [ ] No unexpected directories

### Step 3: Content Integrity Spot Checks

Randomly select 3-5 files to verify content integrity.

**Check file size:**
```bash
# Compare sizes (should be reasonable)
ls -lh /tmp/extracted/path/to/file.txt
```

**Check content:**
```bash
# Read the file and verify it looks correct
cat /tmp/extracted/path/to/file.txt
```

**Validation checks:**
- [ ] Content is readable (UTF-8 encoded)
- [ ] No obvious truncation
- [ ] Code/markup is properly formatted
- [ ] No XML/JSON escape artifacts (e.g., `&lt;` instead of `<`)

### Step 4: File Type Distribution

Verify that expected file types are present.

**Check file types:**
```bash
# List all file extensions
find /tmp/extracted -type f | sed 's/.*\.//' | sort | uniq -c
```

**Expected distributions:**
- Skills: `.md`, `.py`, `.sh`, `.json`, etc.
- Projects: Language-specific extensions
- Documentation: `.md`, `.txt`, `.pdf`, etc.

## Skill-Specific Validation

For Claude Code skills extracted from repomix files, perform additional validation.

### Step 1: Verify Skill Structure

Check that each skill has the required `SKILL.md` file.

**Find all SKILL.md files:**
```bash
find /tmp/extracted -name "SKILL.md"
```

**Expected result:** One `SKILL.md` per skill directory.

### Step 2: Validate YAML Frontmatter

Each `SKILL.md` must have valid YAML frontmatter with `name` and `description`.

**Check frontmatter:**
```bash
head -n 5 /tmp/extracted/skill-name/SKILL.md
```

**Expected format:**
```yaml
---
name: skill-name
description: Clear description with activation triggers
---
```

**Validation checks:**
- [ ] Opening `---` on line 1
- [ ] `name:` field present
- [ ] `description:` field present
- [ ] Closing `---` present
- [ ] Description mentions when to activate

### Step 3: Verify Resource Organization

Check that bundled resources follow the proper structure.

**Check directory structure:**
```bash
tree /tmp/extracted/skill-name
```

**Expected structure:**
```
skill-name/
├── SKILL.md (required)
├── scripts/ (optional)
│   └── *.py, *.sh
├── references/ (optional)
│   └── *.md
└── assets/ (optional)
    └── templates, images, etc.
```

**Validation checks:**
- [ ] `SKILL.md` exists at root
- [ ] Resources organized in proper directories
- [ ] No unexpected directories (e.g., `__pycache__`, `.git`)

### Step 4: Validate with skill-creator

Use the skill-creator validation tools for comprehensive validation.

**Run quick validation:**
```bash
~/.claude/plugins/marketplaces/anthropics-skills/skill-creator/scripts/quick_validate.py \
  /tmp/extracted/skill-name
```

**Expected output:**
```
✅ Skill structure is valid
✅ YAML frontmatter is valid
✅ Description is informative
✅ All resource references are valid
```

**Common validation errors:**
- Missing or malformed YAML frontmatter
- Description too short or missing activation criteria
- References to non-existent files
- Improper directory structure

### Step 5: Content Quality Checks

Verify the content quality of each skill.

**Check SKILL.md length:**
```bash
wc -l /tmp/extracted/skill-name/SKILL.md
```

**Recommended:** 100-500 lines for most skills (lean, with details in references).

**Check for TODOs:**
```bash
grep -i "TODO" /tmp/extracted/skill-name/SKILL.md
```

**Expected result:** No TODOs (unless intentional).

**Check writing style:**
```bash
# Should use imperative/infinitive form
head -n 50 /tmp/extracted/skill-name/SKILL.md
```

**Validation checks:**
- [ ] Uses imperative form ("Extract files from..." not "You extract files...")
- [ ] Clear section headings
- [ ] Code examples properly formatted
- [ ] Resources properly referenced

### Step 6: Bundled Resource Validation

Verify bundled scripts, references, and assets are intact.

**Check scripts are executable:**
```bash
ls -l /tmp/extracted/skill-name/scripts/
```

**Check for shebang in Python/Bash scripts:**
```bash
head -n 1 /tmp/extracted/skill-name/scripts/*.py
head -n 1 /tmp/extracted/skill-name/scripts/*.sh
```

**Expected:** `#!/usr/bin/env python3` or `#!/bin/bash`

**Verify references are markdown:**
```bash
file /tmp/extracted/skill-name/references/*.md
```

**Expected:** All files are text/UTF-8

**Validation checks:**
- [ ] Scripts have proper shebangs
- [ ] Scripts are executable (or will be made executable)
- [ ] References are readable markdown
- [ ] Assets are in expected formats

## Automated Validation Script

For batch validation of multiple skills:

```bash
#!/bin/bash
# validate_all_skills.sh

EXTRACTED_DIR="/tmp/extracted"
SKILL_CREATOR_VALIDATOR="$HOME/.claude/plugins/marketplaces/anthropics-skills/skill-creator/scripts/quick_validate.py"

echo "Validating all skills in $EXTRACTED_DIR..."

for skill_dir in "$EXTRACTED_DIR"/*; do
    if [ -d "$skill_dir" ] && [ -f "$skill_dir/SKILL.md" ]; then
        skill_name=$(basename "$skill_dir")
        echo ""
        echo "=== Validating: $skill_name ==="

        # Run quick validation
        if [ -f "$SKILL_CREATOR_VALIDATOR" ]; then
            python3 "$SKILL_CREATOR_VALIDATOR" "$skill_dir"
        else
            echo "⚠️  Skill creator validator not found, skipping automated validation"
        fi

        # Check for TODOs
        if grep -q "TODO" "$skill_dir/SKILL.md"; then
            echo "⚠️  Warning: Found TODOs in SKILL.md"
        fi

        # Count files
        file_count=$(find "$skill_dir" -type f | wc -l)
        echo "📁 Files: $file_count"
    fi
done

echo ""
echo "✅ Validation complete!"
```

**Usage:**
```bash
bash validate_all_skills.sh
```

## Quality Assurance Checklist

Use this checklist after unmixing:

### General Extraction Quality
- [ ] File count matches expected count
- [ ] Directory structure matches repomix directory listing
- [ ] No extraction errors in console output
- [ ] All files are UTF-8 encoded and readable
- [ ] No binary files incorrectly extracted as text

### Skill Quality (if applicable)
- [ ] Each skill has a valid `SKILL.md`
- [ ] YAML frontmatter is well-formed
- [ ] Description includes activation triggers
- [ ] Writing style is imperative/infinitive
- [ ] Resources are properly organized (scripts/, references/, assets/)
- [ ] No TODOs or placeholder text
- [ ] Scripts have proper shebangs and permissions
- [ ] References are informative markdown
- [ ] skill-creator validation passes

### Content Integrity
- [ ] Random spot-checks show correct content
- [ ] Code examples are properly formatted
- [ ] No XML/JSON escape artifacts
- [ ] File sizes are reasonable
- [ ] No truncated files

### Ready for Use
- [ ] Extracted to appropriate location
- [ ] Scripts made executable (if needed)
- [ ] Skills ready for installation to `~/.claude/skills/`
- [ ] Documentation reviewed and understood

## Common Issues and Solutions

### Issue: File Count Mismatch

**Symptom:** Fewer files extracted than expected.

**Possible causes:**
- Binary files excluded (expected)
- Malformed file blocks in repomix file
- Wrong format detection

**Solution:**
1. Check repomix `<file_summary>` section for exclusion notes
2. Manually inspect repomix file for file blocks
3. Verify format detection was correct

### Issue: Malformed YAML Frontmatter

**Symptom:** skill-creator validation fails on YAML.

**Possible causes:**
- Extraction didn't preserve line breaks correctly
- Content had literal `---` that broke frontmatter

**Solution:**
1. Manually inspect `SKILL.md` frontmatter
2. Ensure opening `---` is on line 1
3. Ensure closing `---` is on its own line
4. Check for stray `---` in description

### Issue: Missing Resource Files

**Symptom:** References to scripts/references not found.

**Possible causes:**
- Resource files excluded from repomix
- Extraction path mismatch

**Solution:**
1. Check repomix file for resource file blocks
2. Verify resource was in original packed content
3. Check extraction console output for errors

### Issue: Permission Errors on Scripts

**Symptom:** Scripts not executable.

**Possible causes:**
- Permissions not preserved during extraction
- Scripts need to be marked executable

**Solution:**
```bash
# Make all scripts executable
find /tmp/extracted -name "*.py" -exec chmod +x {} \;
find /tmp/extracted -name "*.sh" -exec chmod +x {} \;
```

### Issue: Encoding Problems

**Symptom:** Special characters appear garbled.

**Possible causes:**
- Repomix file not UTF-8
- Extraction script encoding mismatch

**Solution:**
1. Verify repomix file encoding: `file -i repomix-file.xml`
2. Re-extract with explicit UTF-8 encoding
3. Check original files for encoding issues

## Post-Validation Actions

### For Valid Skills

**Install to Claude Code:**
```bash
# Copy to skills directory
cp -r /tmp/extracted/skill-name ~/.claude/skills/

# Restart Claude Code to load the skill
```

**Package for distribution:**
```bash
~/.claude/plugins/marketplaces/anthropics-skills/skill-creator/scripts/package_skill.py \
  /tmp/extracted/skill-name
```

### For Invalid Skills

**Document issues:**
- Create an issues list
- Note specific validation failures
- Identify required fixes

**Fix issues:**
- Manually edit extracted files
- Re-validate after fixes
- Document changes made

**Re-package if needed:**
- Once fixed, re-validate
- Package for distribution
- Test in Claude Code

## Best Practices

1. **Always validate before use** - Don't skip validation steps
2. **Extract to temp first** - Review before installing
3. **Use automated tools** - skill-creator validation for skills
4. **Document findings** - Keep notes on any issues
5. **Preserve originals** - Keep the repomix file as backup
6. **Spot-check content** - Don't rely solely on automated checks
7. **Test in isolation** - Install one skill at a time for testing

## References

- Skill creator documentation: `~/.claude/plugins/marketplaces/anthropics-skills/skill-creator/SKILL.md`
- Skill authoring best practices: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices.md
- Claude Code skills directory: `~/.claude/skills/`
