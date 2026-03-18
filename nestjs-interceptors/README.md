# NestJS Interceptors

An AI agent skill for creating professional NestJS interceptors with logging, transformation, error handling, timeout, caching, and metrics.

Supports Claude Code, Codex CLI, Gemini CLI, and Vercel skills.

## What This Skill Provides

This skill empowers AI agents to assist with:

- **Logging Interceptor** - Request/response logging with native NestJS Logger
- **Transform Interceptor** - Standardized API response format
- **Error Format Interceptor** - Consistent error responses
- **Timeout Interceptor** - Request timeout handling
- **Cache Interceptor** - In-memory response caching with TTL
- **Metrics Interceptor** - Request performance metrics
- **Wide Events Logger** - Structured logging with correlation IDs

## Installation

### Vercel skills (npx)

```bash
npx skills add https://github.com/diegoleteliers10/nestjs-interceptors-skill --skill nestjs-interceptors
```

### Claude Code

Install from marketplace:

```bash
claude plugin marketplace add diegoleteliers10/nestjs-interceptors-skill
claude plugin install nestjs-interceptors
```

Or install manually:

```bash
git clone https://github.com/diegoleteliers10/nestjs-interceptors-skill /tmp/nestjs-interceptors

# User-wide (available in all projects)
mv /tmp/nestjs-interceptors/skill ~/.claude/skills/nestjs-interceptors

# Project-specific (check into your repo)
mv /tmp/nestjs-interceptors/skill .claude/skills/nestjs-interceptors
```

### Codex CLI

Use the built-in installer:

```bash
skill-installer https://github.com/diegoleteliers10/nestjs-interceptors-skill --path skill
```

Or install manually:

```bash
git clone https://github.com/diegoleteliers10/nestjs-interceptors-skill /tmp/nestjs-interceptors

# User-wide
mv /tmp/nestjs-interceptors/skill ~/.codex/skills/nestjs-interceptors

# Project-specific
mv /tmp/nestjs-interceptors/skill .codex/skills/nestjs-interceptors
```

**Note:** Run Codex with `--enable skills` if skills aren't loading automatically.

### Gemini CLI

Install the extension directly:

```bash
gemini extensions install https://github.com/diegoleteliers10/nestjs-interceptors-skill
```

## Usage Examples

Once installed, the agent will automatically use this skill for NestJS tasks:

- "Add a logging interceptor to my API"
- "Create a transform interceptor to standardize responses"
- "Add error formatting with proper status codes"
- "Implement caching for GET endpoints"
- "Add timeout handling to prevent slow requests"
- "Add metrics to track request performance"
- "Create an interceptor module"

## Contents

```
nestjs-interceptors/
├── .claude-plugin/
│   └── marketplace.json        # Claude marketplace config
├── skill/
│   └── SKILL.md               # Main skill instructions
├── extension/
│   └── references/            # Gemini extension references
├── gemini-extension.json      # Gemini extension config
├── GEMINI.md                  # Gemini extension instructions
├── LICENSE                    # MIT License
└── README.md                  # This file
```

## Resources

- [NestJS Documentation](https://docs.nestjs.com)
- [NestJS Interceptors](https://docs.nestjs.com/interceptors)
- [@nestjs/common](https://www.npmjs.com/package/@nestjs/common)

## License

MIT