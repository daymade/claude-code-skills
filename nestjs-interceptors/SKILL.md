---
name: nestjs-interceptors
description: Crea interceptors NestJS limpios y bien estructurados para logging, transformación de respuestas, formato de errores, timeout, cache y métricas. Usa Logger de @nestjs/common para logs nativos con colores automáticos. Incluye integración automática en InterceptorsModule.
license: MIT
metadata:
  author: diegoleteliers
  version: "1.0.0"
---

# NestJS Interceptors Skill

Este skill crea interceptors NestJS profesionales y limpios que siguen las mejores prácticas del framework, incluyendo un logger robusto basado en wide events.

## Cuándo usar

Usa este skill cuando:
- El usuario quiere agregar interceptors a su API NestJS
- Necesita logging de requests/responses en formato nativo NestJS
- Quiere estandarizar formato de respuestas API
- Necesita manejo de errores consistente
- Quiere timeout para requests lentos
- Necesita cache de respuestas
- Quiere métricas de rendimiento
- Dice "crear interceptor", "agregar logging", "interceptar requests", "añadir cache"

## Preguntas de configuración

Al iniciar, pregunta al usuario:

1. **¿Qué interceptors necesita?** (selección múltiple)
   - Logging (logs nativos con Logger)
   - Transform (estandarizar respuestas)
   - Error Format (manejo de errores)
   - Timeout (cancelar requests lentos)
   - Cache (cachar respuestas)
   - Metrics (métricas de rendimiento)

2. **¿Nivel de complejidad?**
   - Básico: solo archivos de interceptors
   - Completo: interceptors + módulo + integración en AppModule

3. **¿Timeout custom?** (solo si incluye Timeout)
   - Default: 30000ms
   - Consultar si quiere diferente

## Lo que genera

### Logger de Wide Events (siempre incluido)

El logger proporciona logging estructurado con wide events:

```typescript
// src/shared/logger/logger.service.ts
import {
  LoggerService,
  Injectable,
  Optional,
  Inject,
} from '@nestjs/common';
import { Request } from 'express';
import { randomUUID } from 'crypto';

export interface LogContext {
  userId?: string;
  requestId?: string;
  correlationId?: string;
  [key: string]: unknown;
}

export interface WideEvent {
  method: string;
  path: string;
  query?: Record<string, unknown>;
  requestId: string;
  correlationId: string;
  version: string;
  commitHash: string;
  region?: string;
  instanceId?: string;
  environment: string;
  userAgent?: string;
  ip?: string;
  contentLength?: number;
  statusCode?: number;
  outcome?: 'success' | 'error';
  error?: {
    message: string;
    type: string;
    stack?: string;
  };
  timestamp: string;
  durationMs?: number;
  user?: {
    id: string;
    subscription?: string;
  };
  [key: string]: unknown;
}

@Injectable()
export class AppLogger implements LoggerService {
  private context?: string;
  private correlationId?: string;
  private requestId?: string;
  private businessContext: Record<string, unknown> = {};

  private readonly version: string;
  private readonly commitHash: string;
  private readonly environment: string;
  private readonly region?: string;
  private readonly instanceId?: string;

  constructor(
    @Optional() @Inject('CONTEXT') context?: string,
    @Optional() @Inject('APP_VERSION') version?: string,
    @Optional() @Inject('COMMIT_HASH') commitHash?: string,
    @Optional() @Inject('ENVIRONMENT') environment?: string,
    @Optional() @Inject('REGION') region?: string,
    @Optional() @Inject('INSTANCE_ID') instanceId?: string,
  ) {
    this.context = context;
    this.version = version || process.env.APP_VERSION || 'unknown';
    this.commitHash = commitHash || process.env.COMMIT_HASH || 'unknown';
    this.environment = environment || process.env.NODE_ENV || 'development';
    this.region = region || process.env.REGION;
    this.instanceId = instanceId || process.env.INSTANCE_ID;
  }

  setContext(context: string): void { this.context = context; }
  setCorrelationId(correlationId: string): void { this.correlationId = correlationId; }
  setRequestId(requestId: string): void { this.requestId = requestId; }
  addBusinessContext(key: string, value: unknown): void { this.businessContext[key] = value; }
  addUserContext(userId: string, subscription?: string): void {
    this.businessContext['user'] = { id: userId, subscription };
  }
  clearBusinessContext(): void { this.businessContext = {}; }

  private createWideEvent(method: string, path: string, request: Request): WideEvent {
    return {
      method,
      path,
      query: request.query as Record<string, unknown>,
      requestId: this.requestId || randomUUID(),
      correlationId: this.correlationId || '',
      version: this.version,
      commitHash: this.commitHash,
      environment: this.environment,
      ...(this.region && { region: this.region }),
      ...(this.instanceId && { instanceId: this.instanceId }),
      userAgent: request.headers['user-agent'],
      ip: (request.headers['x-forwarded-for'] as string)?.split(',')[0] || request.ip,
      contentLength: parseInt(request.headers['content-length'] || '0', 10) || undefined,
      timestamp: new Date().toISOString(),
    };
  }

  logWideEvent(wideEvent: WideEvent): void {
    console.log(JSON.stringify(wideEvent));
  }

  startRequest(method: string, path: string, request: Request) {
    const startTime = Date.now();
    const wideEvent = this.createWideEvent(method, path, request);
    Object.assign(wideEvent, this.businessContext);

    return (outcome: 'success' | 'error', statusCode?: number, error?: Error) => {
      wideEvent.durationMs = Date.now() - startTime;
      wideEvent.outcome = outcome;
      wideEvent.statusCode = statusCode;
      if (error) {
        wideEvent.error = { message: error.message, type: error.name, stack: error.stack };
      }
      this.logWideEvent(wideEvent);
    };
  }

  log(message: string, context?: string): void { this.logStructured('info', message, context); }
  error(message: string, trace?: string, context?: void): void { this.logStructured('error', message, context, trace); }
  warn(message: string, context?: string): void { this.logStructured('warn', message, context); }
  debug(message: string, context?: string): void { this.logStructured('debug', message, context); }
  verbose(message: string, context?: string): void { this.logStructured('verbose', message, context); }

  private logStructured(
    level: 'info' | 'error' | 'warn' | 'debug' | 'verbose',
    message: string,
    context?: string,
    trace?: string,
  ): void {
    const logEntry = {
      timestamp: new Date().toISOString(),
      level,
      message,
      context: context || this.context || 'App',
      requestId: this.requestId,
      correlationId: this.correlationId,
      ...(trace && { trace }),
      ...Object.keys(this.businessContext).length > 0 && { business: this.businessContext },
    };
    if (level === 'error') console.error(JSON.stringify(logEntry));
    else if (level === 'warn') console.warn(JSON.stringify(logEntry));
    else console.log(JSON.stringify(logEntry));
  }
}

export const LOGGER_TOKEN = 'APP_LOGGER';
```

### 1. Logging Interceptor

```typescript
import {
  Injectable,
  NestInterceptor,
  ExecutionContext,
  CallHandler,
} from '@nestjs/common';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';
import { Request } from 'express';
import { Logger } from '@nestjs/common';

@Injectable()
export class LoggingInterceptor implements NestInterceptor {
  private readonly logger = new Logger('HTTP');

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const request = context.switchToHttp().getRequest<Request>();
    const { method, url, route } = request;
    const handlerName = route?.path || 'HTTP';
    const startTime = Date.now();

    this.logger.log(`${method} ${url}`);

    return next.handle().pipe(
      tap({
        next: () => {
          const duration = Date.now() - startTime;
          const response = context.switchToHttp().getResponse();
          this.logger.log(`${method} ${url} ${response.statusCode} - ${duration}ms`);
        },
        error: (error: Error) => {
          const duration = Date.now() - startTime;
          this.logger.error(`${method} ${url} - ${error.message} - ${duration}ms`, error.stack);
        },
      }),
    );
  }
}
```

### 2. Transform Interceptor

```typescript
import {
  Injectable,
  NestInterceptor,
  ExecutionContext,
  CallHandler,
} from '@nestjs/common';
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

### 3. Error Format Interceptor

```typescript
import {
  Injectable,
  NestInterceptor,
  ExecutionContext,
  CallHandler,
  HttpException,
  HttpStatus,
} from '@nestjs/common';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';

export interface ApiError {
  statusCode: number;
  message: string;
  error: string;
  timestamp: string;
  path: string;
}

@Injectable()
export class ErrorFormatInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const request = context.switchToHttp().getRequest();

    return next.handle().pipe(
      catchError((error: Error) => {
        const timestamp = new Date().toISOString();
        const path = request.url;

        if (error instanceof HttpException) {
          const response = error.getResponse();
          const status = error.getStatus();
          const errorResponse: ApiError = {
            statusCode: status,
            message: typeof response === 'object' && response !== null
              ? (response as Record<string, unknown>).message as string
              : error.message,
            error: HttpStatus[status] || 'Error',
            timestamp,
            path,
          };
          return throwError(() => new HttpException(errorResponse, status));
        }

        const errorResponse: ApiError = {
          statusCode: HttpStatus.INTERNAL_SERVER_ERROR,
          message: 'Internal server error',
          error: 'InternalServerError',
          timestamp,
          path,
        };
        return throwError(() => new HttpException(errorResponse, HttpStatus.INTERNAL_SERVER_ERROR));
      }),
    );
  }
}
```

### 4. Timeout Interceptor

```typescript
import {
  Injectable,
  NestInterceptor,
  ExecutionContext,
  CallHandler,
  RequestTimeoutException,
} from '@nestjs/common';
import { Observable } from 'rxjs';
import { timeout, catchError } from 'rxjs/operators';

@Injectable()
export class TimeoutInterceptor implements NestInterceptor {
  private readonly timeoutMs: number;

  constructor(timeoutMs: number = 30000) {
    this.timeoutMs = timeoutMs;
  }

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    return next.handle().pipe(
      timeout(this.timeoutMs),
      catchError((err) => {
        if (err.name === 'TimeoutError') {
          throw new RequestTimeoutException('Request timeout');
        }
        throw err;
      }),
    );
  }
}
```

### 5. Cache Interceptor

```typescript
import {
  Injectable,
  NestInterceptor,
  ExecutionContext,
  CallHandler,
} from '@nestjs/common';
import { Observable, of } from 'rxjs';
import { tap } from 'rxjs/operators';

interface CacheEntry<T> {
  data: T;
  expiry: number;
}

@Injectable()
export class CacheInterceptor implements NestInterceptor {
  private cache = new Map<string, CacheEntry<unknown>>();
  private readonly ttl: number;

  constructor(ttlMs: number = 60000) {
    this.ttl = ttlMs;
  }

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const request = context.switchToHttp().getRequest();
    const key = request.url;

    const cached = this.cache.get(key);
    if (cached && cached.expiry > Date.now()) {
      return of(cached.data);
    }

    return next.handle().pipe(
      tap((data) => {
        this.cache.set(key, { data, expiry: Date.now() + this.ttl });
      }),
    );
  }

  clearCache(pattern?: string): void {
    if (!pattern) {
      this.cache.clear();
      return;
    }
    for (const key of this.cache.keys()) {
      if (key.includes(pattern)) this.cache.delete(key);
    }
  }
}
```

### 6. Metrics Interceptor

```typescript
import {
  Injectable,
  NestInterceptor,
  ExecutionContext,
  CallHandler,
} from '@nestjs/common';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';
import { Request } from 'express';

export interface RequestMetrics {
  method: string;
  path: string;
  statusCode: number;
  durationMs: number;
  timestamp: string;
  requestId?: string;
}

@Injectable()
export class MetricsInterceptor implements NestInterceptor {
  private metrics: RequestMetrics[] = [];
  private readonly maxMetrics = 1000;

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const request = context.switchToHttp().getRequest<Request>();
    const { method, url } = request;
    const startTime = Date.now();

    return next.handle().pipe(
      tap({
        next: () => {
          const duration = Date.now() - startTime;
          const response = context.switchToHttp().getResponse();
          this.recordMetric(method, url, response.statusCode, duration);
        },
        error: () => {
          const duration = Date.now() - startTime;
          this.recordMetric(method, url, 500, duration);
        },
      }),
    );
  }

  private recordMetric(method: string, path: string, statusCode: number, duration: number): void {
    const metric: RequestMetrics = {
      method,
      path,
      statusCode,
      durationMs: duration,
      timestamp: new Date().toISOString(),
    };
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
    const errors = this.metrics.filter((m) => m.statusCode >= 400).length;
    return errors / this.metrics.length;
  }
}
```

## Estructura de archivos (Completo)

```
src/shared/
├── logger/
│   ├── logger.service.ts
│   ├── logger.module.ts
│   └── index.ts
└── interceptors/
    ├── logging.interceptor.ts
    ├── transform.interceptor.ts
    ├── error-format.interceptor.ts
    ├── timeout.interceptor.ts
    ├── cache.interceptor.ts
    ├── metrics.interceptor.ts
    ├── interceptors.module.ts
    └── index.ts
```

## Módulo de Interceptors (Completo)

```typescript
import { Module, Global } from '@nestjs/common';
import { APP_INTERCEPTOR } from '@nestjs/core';
import { LoggingInterceptor } from './logging.interceptor';
import { TransformInterceptor } from './transform.interceptor';
import { ErrorFormatInterceptor } from './error-format.interceptor';
import { TimeoutInterceptor } from './timeout.interceptor';
import { CacheInterceptor } from './cache.interceptor';
import { MetricsInterceptor } from './metrics.interceptor';

@Global()
@Module({
  providers: [
    {
      provide: APP_INTERCEPTOR,
      useClass: LoggingInterceptor,
    },
    {
      provide: APP_INTERCEPTOR,
      useClass: TransformInterceptor,
    },
    {
      provide: APP_INTERCEPTOR,
      useClass: ErrorFormatInterceptor,
    },
    {
      provide: APP_INTERCEPTOR,
      useClass: TimeoutInterceptor,
    },
    {
      provide: APP_INTERCEPTOR,
      useClass: CacheInterceptor,
    },
    {
      provide: APP_INTERCEPTOR,
      useClass: MetricsInterceptor,
    },
    LoggingInterceptor,
    TransformInterceptor,
    ErrorFormatInterceptor,
    TimeoutInterceptor,
    CacheInterceptor,
    MetricsInterceptor,
  ],
  exports: [
    LoggingInterceptor,
    TransformInterceptor,
    ErrorFormatInterceptor,
    TimeoutInterceptor,
    CacheInterceptor,
    MetricsInterceptor,
  ],
})
export class InterceptorsModule {}
```

## Integración en AppModule

```typescript
import { Module } from '@nestjs/common';
import { InterceptorsModule } from './shared/interceptors';

@Module({
  imports: [
    // ...otros módulos
    InterceptorsModule,
  ],
})
export class AppModule {}
```

## Formato de respuesta

```json
{
  "data": { ... },
  "timestamp": "2026-03-18T12:00:00.000Z",
  "path": "/api/v1/users"
}
```

## Formato de error

```json
{
  "statusCode": 404,
  "message": "Resource not found",
  "error": "NotFound",
  "timestamp": "2026-03-18T12:00:00.000Z",
  "path": "/api/v1/users/123"
}
```

## Logging en terminal

```
[Nest] 50109 - 03/18/2026, 1:47:29 AM     LOG [HTTP] GET /api/v1/users
[Nest] 50109 - 03/18/2026, 1:47:30 AM     LOG [HTTP] GET /api/v1/users 200 - 300ms
[Nest] 50109 - 03/18/2026, 1:47:30 AM   ERROR [HTTP] GET /api/v1/users/123 404 - 25ms
```

## Notas

- Usa `Logger` de `@nestjs/common` (NO console.log)
- Los interceptors se aplican globalmente via `APP_INTERCEPTOR`
- El logger incluye wide events para debugging avanzado
- Cache y Metrics se pueden usar a nivel de controlador con `@UseInterceptors()`
