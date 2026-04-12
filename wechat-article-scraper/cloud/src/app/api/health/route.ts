/**
 * Health Check API v3.47.0
 *
 * Comprehensive system diagnostics:
 * - Database connectivity (PostgreSQL + pgvector)
 * - External API status (Kimi, Notion, etc.)
 * - Storage status
 * - Real-time metrics (queue depth, error rates)
 * - Dependency versions
 */

import { NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase';
import { version as supabaseJsVersion } from '@supabase/supabase-js/package.json';

interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string;
  version: string;
  services: {
    database: ServiceStatus;
    storage: ServiceStatus;
    realtime: ServiceStatus;
    kimiApi?: ServiceStatus;
    notion?: ServiceStatus;
  };
  metrics: {
    uptime: number;
    responseTime: number;
    memoryUsage: NodeJS.MemoryUsage;
    activeConnections?: number;
    queueDepth?: number;
    errorRate?: number;
  };
  dependencies: {
    supabaseJs: string;
    node: string;
    pgvector?: boolean;
  };
}

interface ServiceStatus {
  status: 'up' | 'down' | 'unknown';
  latency?: number;
  message?: string;
  version?: string;
}

interface SystemMetrics {
  failedJobs: number;
  pendingJobs: number;
  totalArticles: number;
  annotationsCount: number;
}

export async function GET(): Promise<NextResponse> {
  const startTime = Date.now();
  const status: HealthStatus = {
    status: 'healthy',
    timestamp: new Date().toISOString(),
    version: process.env.NEXT_PUBLIC_APP_VERSION || '3.47.0',
    services: {
      database: { status: 'unknown' },
      storage: { status: 'unknown' },
      realtime: { status: 'unknown' },
    },
    metrics: {
      uptime: process.uptime(),
      responseTime: 0,
      memoryUsage: process.memoryUsage(),
    },
    dependencies: {
      supabaseJs: supabaseJsVersion,
      node: process.version,
    },
  };

  try {
    const supabase = createClient();

    // Check database connectivity
    const dbStart = Date.now();
    const { error: dbError } = await supabase.from('articles').select('id').limit(1);

    if (dbError) {
      status.services.database = {
        status: 'down',
        message: dbError.message,
      };
      status.status = 'unhealthy';
    } else {
      status.services.database = {
        status: 'up',
        latency: Date.now() - dbStart,
      };
    }

    // Check pgvector extension
    const { error: pgvectorError } = await supabase.rpc('check_pgvector');
    status.dependencies.pgvector = !pgvectorError;

    // Check storage
    const storageStart = Date.now();
    const { error: storageError } = await supabase.storage.getBucket('exports');

    if (storageError && storageError.message !== 'Bucket not found') {
      status.services.storage = {
        status: 'down',
        message: storageError.message,
      };
      if (status.status === 'healthy') {
        status.status = 'degraded';
      }
    } else {
      status.services.storage = {
        status: 'up',
        latency: Date.now() - storageStart,
      };
    }

    // Check realtime
    const realtimeStart = Date.now();
    try {
      const channel = supabase.channel('health-check');
      await channel.subscribe((status) => {
        if (status === 'SUBSCRIBED') {
          channel.unsubscribe();
        }
      });
      status.services.realtime = {
        status: 'up',
        latency: Date.now() - realtimeStart,
      };
    } catch (error) {
      status.services.realtime = {
        status: 'down',
        message: error instanceof Error ? error.message : 'Realtime connection failed',
      };
    }

    // Check Kimi API (optional)
    if (process.env.KIMI_API_KEY) {
      const kimiStart = Date.now();
      try {
        const response = await fetch('https://api.kimi.com/coding/', {
          method: 'HEAD',
          headers: {
            Authorization: `Bearer ${process.env.KIMI_API_KEY}`,
          },
        });

        status.services.kimiApi = {
          status: response.ok ? 'up' : 'down',
          latency: Date.now() - kimiStart,
        };
      } catch {
        status.services.kimiApi = {
          status: 'down',
          message: 'Connection failed',
        };
      }
    }

    // Check Notion (optional)
    if (process.env.NOTION_CLIENT_ID) {
      const notionStart = Date.now();
      try {
        const response = await fetch('https://api.notion.com/v1/users/me', {
          headers: {
            'Authorization': `Bearer ${process.env.NOTION_TOKEN}`,
            'Notion-Version': '2022-06-28',
          },
        });

        status.services.notion = {
          status: response.ok ? 'up' : 'down',
          latency: Date.now() - notionStart,
        };
      } catch {
        status.services.notion = {
          status: 'down',
          message: 'Connection failed',
        };
      }
    }

    // Get system metrics
    try {
      const { data: metrics } = await supabase.rpc('get_system_metrics');
      if (metrics) {
        status.metrics.activeConnections = metrics.active_connections;
        status.metrics.queueDepth = metrics.pending_jobs;
        status.metrics.errorRate = metrics.error_rate;
      }
    } catch {
      // Metrics not critical
    }

    status.metrics.responseTime = Date.now() - startTime;

    return NextResponse.json(status, {
      status: status.status === 'healthy' ? 200 : status.status === 'degraded' ? 200 : 503,
    });
  } catch (error) {
    status.status = 'unhealthy';
    status.services.database = {
      status: 'down',
      message: error instanceof Error ? error.message : 'Unknown error',
    };

    return NextResponse.json(status, { status: 503 });
  }
}

// Detailed health check with more diagnostics
export async function POST(): Promise<NextResponse> {
  const diagnostics = {
    environment: {
      nodeVersion: process.version,
      platform: process.platform,
      env: process.env.NODE_ENV,
    },
    features: {
      syncEnabled: !!process.env.NEXT_PUBLIC_SUPABASE_URL,
      aiEnabled: !!process.env.KIMI_API_KEY,
      notionEnabled: !!process.env.NOTION_CLIENT_ID,
    },
    dependencies: {
      supabase: !!process.env.NEXT_PUBLIC_SUPABASE_URL,
      kimi: !!process.env.KIMI_API_KEY,
    },
  };

  return NextResponse.json(diagnostics);
}
