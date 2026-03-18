# Transform Interceptor Reference

The Transform Interceptor wraps all API responses in a standardized format.

## Implementation

```typescript
import { Injectable, NestInterceptor, ExecutionContext, CallHandler } from '@nestjs/common';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

export interface ApiResponse<T> {
  data: T;
  timestamp: string;
  path: string;
}

@Injectable()
export class TransformInterceptor<T> implements NestInterceptor<T, ApiResponse<T>> {
  intercept(context: ExecutionContext, next: CallHandler): Observable<ApiResponse<T>> {
    const request = context.switchToHttp().getRequest();
    
    return next.handle().pipe(
      map((data) => ({
        data,
        timestamp: new Date().toISOString(),
        path: request.url,
      })),
    );
  }
}
```

## Usage in Module

```typescript
import { Module } from '@nestjs/common';
import { APP_INTERCEPTOR } from '@nestjs/core';

@Module({
  providers: [
    {
      provide: APP_INTERCEPTOR,
      useClass: TransformInterceptor,
    },
  ],
})
export class InterceptorsModule {}
```

## Response Format

```json
{
  "data": { ... },
  "timestamp": "2025-01-01T12:00:00.000Z",
  "path": "/api/users"
}
```

## Features

- Wraps response data in standardized format
- Adds ISO timestamp to every response
- Includes request path for debugging
- Works with any return type (objects, arrays, primitives)
- Global or route-specific application