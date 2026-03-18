# Metrics Interceptor Reference

The Metrics Interceptor tracks request performance metrics including duration, status codes, and error rates.

## Implementation

```typescript
import { Injectable, NestInterceptor, ExecutionContext, CallHandler } from '@nestjs/common';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';

export interface RequestMetrics {
  method: string;
  url: string;
  statusCode: number;
  durationMs: number;
  timestamp: number;
  success: boolean;
}

@Injectable()
export class MetricsInterceptor implements NestInterceptor {
  private metrics: RequestMetrics[] = [];
  private readonly maxMetrics = 1000;

  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const request = context.switchToHttp().getRequest();
    const { method, url } = request;
    const startTime = Date.now();
    const response = context.switchToHttp().getResponse();

    return next.handle().pipe(
      tap(() => {
        const duration = Date.now() - startTime;
        const statusCode = response.statusCode;
        
        this.recordMetric({
          method,
          url,
          statusCode,
          durationMs: duration,
          timestamp: Date.now(),
          success: statusCode < 400,
        });
      }),
      catchError((error) => {
        const duration = Date.now() - startTime;
        const statusCode = error?.status || 500;
        
        this.recordMetric({
          method,
          url,
          statusCode,
          durationMs: duration,
          timestamp: Date.now(),
          success: false,
        });
        
        throw error;
      }),
    );
  }

  private recordMetric(metric: RequestMetrics): void {
    this.metrics.push(metric);
    if (this.metrics.length > this.maxMetrics) {
      this.metrics.shift();
    }
  }

  getMetrics(): RequestMetrics[] {
    return [...this.metrics];
  }

  getAverageDuration(): number {
    if (this.metrics.length === 0) return 0;
    const sum = this.metrics.reduce((acc, m) => acc + m.durationMs, 0);
    return sum / this.metrics.length;
  }

  getErrorRate(): number {
    if (this.metrics.length === 0) return 0;
    const errors = this.metrics.filter(m => !m.success).length;
    return errors / this.metrics.length;
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
      useClass: MetricsInterceptor,
    },
  ],
})
export class InterceptorsModule {}
```

## Available Methods

- `getMetrics()` - Returns all recorded metrics
- `getAverageDuration()` - Returns average request duration in ms
- `getErrorRate()` - Returns error rate as a percentage (0-1)

## Features

- Tracks request duration for all endpoints
- Records HTTP method, URL, and status code
- Calculates error rate automatically
- Provides average duration metrics
- Configurable max metrics storage (default: 1000)
- Useful for performance monitoring and debugging

## Use Cases

- Monitoring API performance
- Identifying slow endpoints
- Tracking error rates
- Generating performance reports
- Alerting on anomalous behavior