# NestJS Interceptors Gemini Extension

This extension provides AI agents with capabilities to create professional NestJS interceptors.

## Available Interceptors

1. **Logging Interceptor** - Logs HTTP requests and responses with duration
2. **Transform Interceptor** - Wraps responses in standard format
3. **Error Format Interceptor** - Standardizes error responses
4. **Timeout Interceptor** - Adds timeout to requests
5. **Cache Interceptor** - Caches responses with TTL
6. **Metrics Interceptor** - Tracks request metrics

## Usage

When the user wants to add interceptors to their NestJS application:

- Ask which type of interceptor they need
- Use the patterns from the references to generate the code
- Include the necessary imports from @nestjs/common
- Register interceptors in the module

## Example Prompts

- "Add logging interceptor"
- "Create cache interceptor"
- "Add error formatting"
- "Implement transform response"