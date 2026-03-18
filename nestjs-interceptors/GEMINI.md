# NestJS Interceptors Gemini Extension

This extension provides AI agents with capabilities to create professional NestJS interceptors for Claude Code and Gemini CLI.

## What This Extension Provides

- **Logging Interceptor** - Request/response logging with native NestJS Logger
- **Transform Interceptor** - Standardized API response format
- **Error Format Interceptor** - Consistent error responses
- **Timeout Interceptor** - Request timeout handling
- **Cache Interceptor** - In-memory response caching with TTL
- **Metrics Interceptor** - Request performance metrics
- **Wide Events Logger** - Structured logging with correlation IDs

## Installation

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

## Reference Files

- `extension/references/interceptors.md` - Overview of all interceptor types
- `extension/references/logging.md` - Logging interceptor patterns
- `extension/references/transform.md` - Transform interceptor patterns
- `extension/references/error-handling.md` - Error handling patterns
- `extension/references/cache.md` - Cache interceptor patterns
- `extension/references/metrics.md` - Metrics interceptor patterns

## Resources

- [NestJS Documentation](https://docs.nestjs.com)
- [NestJS Interceptors](https://docs.nestjs.com/interceptors)

## License

MIT