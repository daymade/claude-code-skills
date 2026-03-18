# Cache Interceptor Reference

The Cache Interceptor provides in-memory caching for API responses with TTL support.

## Implementation

```typescript
import { Injectable, NestInterceptor, ExecutionContext, CallHandler } from '@nestjs/common';
import { Observable, of } from 'rxjs';
import { tap } from 'rxjs/operators';

interface CacheEntry {
  data: any;
  expiry: number;
}

@Injectable()
export class CacheInterceptor implements NestInterceptor {
  private cache = new Map<string, CacheEntry>();
  private readonly ttl = 60000; // 60 seconds default

  constructor(ttl?: number) {
    if (ttl) this.ttl = ttl;
  }

  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const request = context.switchToHttp().getRequest();
    const key = request.originalUrl || request.url;
    const now = Date.now();

    const cached = this.cache.get(key);
    if (cached && cached.expiry > now) {
      return of(cached.data);
    }

    return next.handle().pipe(
      tap((data) => {
        const expiry = now + this.ttl;
        this.cache.set(key, { data, expiry });
      }),
    );
  }

  clearCache(key?: string): void {
    if (key) {
      this.cache.delete(key);
    } else {
      this.cache.clear();
    }
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
      useClass: CacheInterceptor,
    },
  ],
})
export class InterceptorsModule {}
```

## Custom TTL

```typescript
@Injectable()
export class CustomCacheInterceptor extends CacheInterceptor {
  constructor() {
    super(300000); // 5 minutes TTL
  }
}
```

## Features

- In-memory cache using Map
- Configurable TTL (time-to-live)
- Uses request URL as cache key
- Clear cache method for manual invalidation
- Ideal for GET endpoints with expensive computations
- Not recommended for data that changes frequently

## Use Cases

- Caching database queries
- Caching external API responses
- Caching computed values
- Reducing server load for expensive operations