
# Logging Interceptor Reference

The Logging Interceptor logs all HTTP requests and responses with timing information.

## Implementation

```typescript
import { Injectable, NestInterceptor, ExecutionContext, CallHandler, Logger } from '@nestjs/common';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';

@Injectable()
export class LoggingInterceptor implements NestInterceptor {
  private readonly logger = new Logger('HTTP');

  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const request = context.switchToHttp().getRequest();
    const { method, url } = request;
    const response = context.switchToHttp().getResponse();
    const handlerName = context.getHandler().name;

    const startTime = Date.now();

    return next.handle().pipe(
      tap(() => {
        const duration = Date.now() - startTime;
        const statusCode = response.statusCode;
        this.logger.log(`${method} ${url} ${statusCode} - ${duration}ms [${handlerName}]`);
      }),
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
      useClass: LoggingInterceptor,
    },
  ],
})
export class InterceptorsModule {}
```

## Features

- Logs HTTP method, URL, status code, and response time
- Includes handler/controller method name
- Uses NestJS native Logger with colors
- Global or route-specific application
