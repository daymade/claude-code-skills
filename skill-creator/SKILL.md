---
name: skill-creator
description: Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends Claude's capabilities with specialized knowledge, workflows, or tool integrations.
license: Complete terms in LICENSE.txt
---

# Skill Creator

This skill provides guidance for creating effective skills.

## About Skills

Skills are modular, self-contained packages that extend Claude's capabilities by providing
specialized knowledge, workflows, and tools. Think of them as "onboarding guides" for specific
domains or tasks—they transform Claude from a general-purpose agent into a specialized agent
equipped with procedural knowledge that no model can fully possess.

### What Skills Provide

1. Specialized workflows - Multi-step procedures for specific domains
2. Tool integrations - Instructions for working with specific file formats or APIs
3. Domain expertise - Company-specific knowledge, schemas, business logic
4. Bundled resources - Scripts, references, and assets for complex and repetitive tasks

### Anatomy of a Skill

Every skill consists of a required SKILL.md file and optional bundled resources:

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter metadata (required)
│   │   ├── name: (required)
│   │   └── description: (required)
│   └── Markdown instructions (required)
└── Bundled Resources (optional)
    ├── scripts/          - Executable code (Python/Bash/etc.)
    ├── references/       - Documentation intended to be loaded into context as needed
    └── assets/           - Files used in output (templates, icons, fonts, etc.)
```

#### SKILL.md (required)

**Metadata Quality:** The `name` and `description` in YAML frontmatter determine when Claude will use the skill. Be specific about what the skill does and when to use it. Use the third-person (e.g. "This skill should be used when..." instead of "Use this skill when...").

#### Bundled Resources (optional)

##### Scripts (`scripts/`)

Executable code (Python/Bash/etc.) for tasks that require deterministic reliability or are repeatedly rewritten.

- **When to include**: When the same code is being rewritten repeatedly or deterministic reliability is needed
- **Example**: `scripts/rotate_pdf.py` for PDF rotation tasks
- **Benefits**: Token efficient, deterministic, may be executed without loading into context
- **Note**: Scripts may still need to be read by Claude for patching or environment-specific adjustments

##### References (`references/`)

Documentation and reference material intended to be loaded as needed into context to inform Claude's process and thinking.

- **When to include**: For documentation that Claude should reference while working
- **Examples**: `references/finance.md` for financial schemas, `references/mnda.md` for company NDA template, `references/policies.md` for company policies, `references/api_docs.md` for API specifications
- **Use cases**: Database schemas, API documentation, domain knowledge, company policies, detailed workflow guides
- **Benefits**: Keeps SKILL.md lean, loaded only when Claude determines it's needed
- **Best practice**: If files are large (>10k words), include grep search patterns in SKILL.md
- **Avoid duplication**: Information should live in either SKILL.md or references files, not both. Prefer references files for detailed information unless it's truly core to the skill—this keeps SKILL.md lean while making information discoverable without hogging the context window. Keep only essential procedural instructions and workflow guidance in SKILL.md; move detailed reference material, schemas, and examples to references files.

##### Assets (`assets/`)

Files not intended to be loaded into context, but rather used within the output Claude produces.

- **When to include**: When the skill needs files that will be used in the final output
- **Examples**: `assets/logo.png` for brand assets, `assets/slides.pptx` for PowerPoint templates, `assets/frontend-template/` for HTML/React boilerplate, `assets/font.ttf` for typography
- **Use cases**: Templates, images, icons, boilerplate code, fonts, sample documents that get copied or modified
- **Benefits**: Separates output resources from documentation, enables Claude to use files without loading them into context

##### Privacy and Path References

**CRITICAL**: Skills intended for public distribution must not contain user-specific or company-specific information:

- **Forbidden**: Absolute paths to user directories (`/home/username/`, `/Users/username/`, `/mnt/c/Users/username/`)
- **Forbidden**: Personal usernames, company names, department names, product names
- **Forbidden**: OneDrive paths, cloud storage paths, or any environment-specific absolute paths
- **Forbidden**: Hardcoded skill installation paths like `~/.claude/skills/` or `/Users/username/Workspace/claude-code-skills/`
- **Allowed**: Relative paths within the skill bundle (`scripts/example.py`, `references/guide.md`)
- **Allowed**: Standard placeholders (`~/workspace/project`, `username`, `your-company`)
- **Best practice**: Reference bundled scripts using simple relative paths like `scripts/script_name.py` - Claude will resolve the actual location

##### Versioning

**CRITICAL**: Skills should NOT contain version history or version numbers in SKILL.md:

- **Forbidden**: Version sections (`## Version`, `## Changelog`, `## Release History`) in SKILL.md
- **Forbidden**: Version numbers in SKILL.md body content
- **Correct location**: Skill versions are tracked in marketplace.json under `plugins[].version`
- **Rationale**: Marketplace infrastructure manages versioning; SKILL.md should be timeless content focused on functionality
- **Example**: Instead of documenting v1.0.0 → v1.1.0 changes in SKILL.md, update the version in marketplace.json only

### Progressive Disclosure Design Principle

Skills use a three-level loading system to manage context efficiently:

1. **Metadata (name + description)** - Always in context (~100 words)
2. **SKILL.md body** - When skill triggers (<5k words)
3. **Bundled resources** - As needed by Claude (Unlimited*)

*Unlimited because scripts can be executed without reading into context window.

### Skill Creation Best Practice

Anthropic has wrote skill authoring best practices, you SHOULD retrieve it before you create or update any skills, the link is https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices.md

## ⚠️ CRITICAL: Edit Skills at Source Location

**NEVER edit skills in `~/.claude/plugins/cache/`** — that's a read-only cache directory. All changes there are:
- Lost when cache refreshes
- Not synced to source control
- Wasted effort requiring manual re-merge

**ALWAYS verify you're editing the source repository:**
```bash
# WRONG - cache location (read-only copy)
~/.claude/plugins/cache/daymade-skills/my-skill/1.0.0/my-skill/SKILL.md

# RIGHT - source repository
/path/to/your/claude-code-skills/my-skill/SKILL.md
```

**Before any edit**, confirm the file path does NOT contain `/cache/` or `/plugins/cache/`.

## Skill Creation Process

To create a skill, follow the "Skill Creation Process" in order, skipping steps only if there is a clear reason why they are not applicable.

### Step 1: Understanding the Skill with Concrete Examples

Skip this step only when the skill's usage patterns are already clearly understood. It remains valuable even when working with an existing skill.

To create an effective skill, clearly understand concrete examples of how the skill will be used. This understanding can come from either direct user examples or generated examples that are validated with user feedback.

For example, when building an image-editor skill, relevant questions include:

- "What functionality should the image-editor skill support? Editing, rotating, anything else?"
- "Can you give some examples of how this skill would be used?"
- "I can imagine users asking for things like 'Remove the red-eye from this image' or 'Rotate this image'. Are there other ways you imagine this skill being used?"
- "What would a user say that should trigger this skill?"

To avoid overwhelming users, avoid asking too many questions in a single message. Start with the most important questions and follow up as needed for better effectiveness.

Conclude this step when there is a clear sense of the functionality the skill should support.

### Step 2: Planning the Reusable Skill Contents

To turn concrete examples into an effective skill, analyze each example by:

1. Considering how to execute on the example from scratch
2. Determining the appropriate level of freedom for Claude
3. Identifying what scripts, references, and assets would be helpful when executing these workflows repeatedly

**Match specificity to task risk:**
- **High freedom (text instructions)**: Multiple valid approaches exist; context determines best path (e.g., code reviews, troubleshooting, content analysis)
- **Medium freedom (pseudocode with parameters)**: Preferred patterns exist with acceptable variation (e.g., API integration patterns, data processing workflows)
- **Low freedom (exact scripts)**: Operations are fragile, consistency critical, sequence matters (e.g., PDF rotation, database migrations, form validation)

Example: When building a `pdf-editor` skill to handle queries like "Help me rotate this PDF," the analysis shows:

1. Rotating a PDF requires re-writing the same code each time
2. A `scripts/rotate_pdf.py` script would be helpful to store in the skill

Example: When designing a `frontend-webapp-builder` skill for queries like "Build me a todo app" or "Build me a dashboard to track my steps," the analysis shows:

1. Writing a frontend webapp requires the same boilerplate HTML/React each time
2. An `assets/hello-world/` template containing the boilerplate HTML/React project files would be helpful to store in the skill

Example: When building a `big-query` skill to handle queries like "How many users have logged in today?" the analysis shows:

1. Querying BigQuery requires re-discovering the table schemas and relationships each time
2. A `references/schema.md` file documenting the table schemas would be helpful to store in the skill

To establish the skill's contents, analyze each concrete example to create a list of the reusable resources to include: scripts, references, and assets.

### Step 3: Initializing the Skill

At this point, it is time to actually create the skill.

Skip this step only if the skill being developed already exists, and iteration or packaging is needed. In this case, continue to the next step.

When creating a new skill from scratch, always run the `init_skill.py` script. The script conveniently generates a new template skill directory that automatically includes everything a skill requires, making the skill creation process much more efficient and reliable.

Usage:

```bash
scripts/init_skill.py <skill-name> --path <output-directory>
```

The script:

- Creates the skill directory at the specified path
- Generates a SKILL.md template with proper frontmatter and TODO placeholders
- Creates example resource directories: `scripts/`, `references/`, and `assets/`
- Adds example files in each directory that can be customized or deleted

After initialization, customize or remove the generated SKILL.md and example files as needed.

### Step 4: Edit the Skill

When editing the (newly-generated or existing) skill, remember that the skill is being created for another instance of Claude to use. Focus on including information that would be beneficial and non-obvious to Claude. Consider what procedural knowledge, domain-specific details, or reusable assets would help another Claude instance execute these tasks more effectively.

#### Start with Reusable Skill Contents

To begin implementation, start with the reusable resources identified above: `scripts/`, `references/`, and `assets/` files. Note that this step may require user input. For example, when implementing a `brand-guidelines` skill, the user may need to provide brand assets or templates to store in `assets/`, or documentation to store in `references/`.

Also, delete any example files and directories not needed for the skill. The initialization script creates example files in `scripts/`, `references/`, and `assets/` to demonstrate structure, but most skills won't need all of them.

**When updating an existing skill**: Scan all existing reference files to check if they need corresponding updates. New features often require updates to architecture, workflow, or other existing documentation to maintain consistency.

#### Reference File Naming

Filenames must be self-explanatory without reading contents.

**Pattern**: `<content-type>_<specificity>.md`

**Examples**:
- ❌ `commands.md`, `cli_usage.md`, `reference.md`
- ✅ `script_parameters.md`, `api_endpoints.md`, `database_schema.md`

**Test**: Can someone understand the file's contents from the name alone?

#### Update SKILL.md

**Writing Style:** Write the entire skill using **imperative/infinitive form** (verb-first instructions), not second person. Use objective, instructional language (e.g., "To accomplish X, do Y" rather than "You should do X" or "If you need to do X"). This maintains consistency and clarity for AI consumption.

To complete SKILL.md, answer the following questions:

1. What is the purpose of the skill, in a few sentences?
2. When should the skill be used?
3. In practice, how should Claude use the skill? All reusable skill contents developed above should be referenced so that Claude knows how to use them.

### Step 5: Security Review

Before packaging or distributing a skill, run the security scanner to detect hardcoded secrets and personal information:

```bash
# Required before packaging
python scripts/security_scan.py <path/to/skill-folder>

# Verbose mode includes additional checks for paths, emails, and code patterns
python scripts/security_scan.py <path/to/skill-folder> --verbose
```

**Detection coverage:**
- Hardcoded secrets (API keys, passwords, tokens) via gitleaks
- Personal information (usernames, emails, company names) in verbose mode
- Unsafe code patterns (command injection risks) in verbose mode

**First-time setup:** Install gitleaks if not present:

```bash
# macOS
brew install gitleaks

# Linux/Windows - see script output for installation instructions
```

**Exit codes:**
- `0` - Clean (safe to package)
- `1` - High severity issues
- `2` - Critical issues (MUST fix before distribution)
- `3` - gitleaks not installed
- `4` - Scan error

**Remediation for detected secrets:**

1. Remove hardcoded secrets from all files
2. Use environment variables: `os.environ.get("API_KEY")`
3. Rotate credentials if previously committed to git
4. Re-run scan to verify fixes before packaging

### Step 6: Packaging a Skill

Once the skill is ready, it should be packaged into a distributable zip file that gets shared with the user. The packaging process automatically validates the skill first to ensure it meets all requirements:

```bash
scripts/package_skill.py <path/to/skill-folder>
```

Optional output directory specification:

```bash
scripts/package_skill.py <path/to/skill-folder> ./dist
```

The packaging script will:

1. **Validate** the skill automatically, checking:
   - YAML frontmatter format and required fields
   - Skill naming conventions and directory structure
   - Description completeness and quality
   - **Path reference integrity** - all `scripts/`, `references/`, and `assets/` paths mentioned in SKILL.md must exist

2. **Package** the skill if validation passes, creating a zip file named after the skill (e.g., `my-skill.zip`) that includes all files and maintains the proper directory structure for distribution.

**Common validation failure:** If SKILL.md references `scripts/my_script.py` but the file doesn't exist, validation will fail with "Missing referenced files: scripts/my_script.py". Ensure all bundled resources exist before packaging.

If validation fails, the script will report the errors and exit without creating a package. Fix any validation errors and run the packaging command again.

### Step 7: Update Marketplace

After packaging, update the marketplace registry to include the new or updated skill.

**For new skills**, add an entry to `.claude-plugin/marketplace.json`:

```json
{
  "name": "skill-name",
  "description": "Copy from SKILL.md frontmatter description",
  "source": "./",
  "strict": false,
  "version": "1.0.0",
  "category": "developer-tools",
  "keywords": ["relevant", "keywords"],
  "skills": ["./skill-name"]
}
```

**For updated skills**, bump the version in `plugins[].version` following semver:
- Patch (1.0.x): Bug fixes, typo corrections
- Minor (1.x.0): New features, additional references
- Major (x.0.0): Breaking changes, restructured workflows

**Also update** `metadata.version` and `metadata.description` if the overall plugin collection changed significantly.

### Step 8: Iterate

After testing the skill, users may request improvements. Often this happens right after using the skill, with fresh context of how the skill performed.

**Iteration workflow:**
1. Use the skill on real tasks
2. Notice struggles or inefficiencies
3. Identify how SKILL.md or bundled resources should be updated
4. Implement changes and test again

**Refinement filter:** Only add what solves observed problems. If best practices already cover it, don't duplicate.
