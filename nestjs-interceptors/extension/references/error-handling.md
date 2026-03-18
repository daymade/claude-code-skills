# Error Format Interceptor Reference

The Error Format Interceptor normalizes all error responses to a consistent format.

## Implementation

```typescript
import { Injectable, NestInterceptor, ExecutionContext, CallHandler } from '@nestjs/common';
import { Observable } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { HttpException, HttpStatus } from '@nestjs/common';

export interface ApiError {
  statusCode: number;
  message: string | string[];
  error: string;
  timestamp: string;
  path: string;
}

@Injectable()
export class ErrorFormatInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    const request = context.switchToHttp().getRequest();
    const timestamp = new Date().toISOString();
    const path = request.url;

    return next.handle().pipe(
      catchError((error) => {
        const status = error instanceof HttpException
          ? error.getStatus()
          : HttpStatus.INTERNAL_SERVER_ERROR;
        
        const errorResponse = error instanceof HttpException
          ? error.getResponse()
          : { message: 'Internal server error', error: 'Internal Server Error' };

        const message = typeof errorResponse === 'object' && 'message' in errorResponse
          ? errorResponse.message
          : errorResponse;
        
        const errorType = typeof errorResponse === 'object' && 'error' in errorResponse
          ? errorResponse.error
          : 'Error';

        const response: ApiError = {
          statusCode: status,
          message,
          error: errorType,
          timestamp,
          path,
        };

        throw new HttpException(response, status);
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
      useClass: ErrorFormatInterceptor,
    },
  ],
})
export class InterceptorsModule {}
```

## Error Response Format

```json
{
  "statusCode": 400,
  "message": "Validation failed",
  "error": "Bad Request",
  "timestamp": "2025-01-01T12:00:00.000Z",
  "path": "/api/users"
}
```

## Features

- Normalizes all error responses to consistent format
- Handles both HttpException and generic errors
- Includes HTTP status code, message, and error type
- Adds timestamp and request path for debugging
- Works with validation errors, business logic errors, and system errors
