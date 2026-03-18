# NestJS Interceptors Reference

This document describes the available interceptors and their implementation patterns.

## Interceptor Types

### 1. Logging Interceptor
- Logs incoming requests and outgoing responses
- Includes request method, URL, and duration
- Uses NestJS Logger from @nestjs/common

### 2. Transform Interceptor
- Wraps responses in a standardized format
- Adds timestamp and path to all responses
- Format: `{ data, timestamp, path }`

### 3. Error Format Interceptor
- Normalizes error responses
- Includes status code, message, and error type
- Adds timestamp and path

### 4. Timeout Interceptor
- Adds timeout to request handling
- Throws HttpException on timeout

### 5. Cache Interceptor
- In-memory caching with TTL
- Uses request URL as cache key
- Supports cache clearing

### 6. Metrics Interceptor
- Tracks request duration
- Calculates error rate
- Provides average duration metrics