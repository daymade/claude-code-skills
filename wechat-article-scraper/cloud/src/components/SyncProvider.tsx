'use client';

/**
 * Sync Provider Component
 *
 * Integrates SyncEngine with React context for offline-first sync
 * across devices with real-time collaboration support.
 */

import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
} from 'react';
import { SyncEngine, SyncConfig, SyncState } from '@/lib/sync-engine';
import { Annotation } from '@/lib/annotation-engine';

interface SyncContextValue {
  syncEngine: SyncEngine | null;
  syncState: SyncState;
  isInitialized: boolean;
  pendingChanges: number;
  lastSyncAt: string | null;
  conflicts: any[];
  // Actions
  sync: () => Promise<void>;
  resolveConflict: (conflictId: string, choice: 'local' | 'remote' | 'merged', mergedData?: any) => Promise<void>;
  queueAnnotation: (annotation: Annotation) => Promise<void>;
  queueReadingProgress: (progress: { articleId: string; percentage: number }) => Promise<void>;
}

const SyncContext = createContext<SyncContextValue | null>(null);

interface SyncProviderProps {
  children: React.ReactNode;
  userId: string;
  config: SyncConfig;
  onSyncError?: (error: Error) => void;
}

export function SyncProvider({
  children,
  userId,
  config,
  onSyncError,
}: SyncProviderProps) {
  const syncEngineRef = useRef<SyncEngine | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);
  const [syncState, setSyncState] = useState<SyncState>({
    lastSyncAt: null,
    pendingChanges: 0,
    isOnline: typeof navigator !== 'undefined' ? navigator.onLine : true,
    isSyncing: false,
  });
  const [conflicts, setConflicts] = useState<any[]>([]);

  // Initialize sync engine
  useEffect(() => {
    if (syncEngineRef.current) return;

    const engine = new SyncEngine(config, userId);
    syncEngineRef.current = engine;

    engine.init()
      .then(() => {
        setIsInitialized(true);
        setSyncState(engine.getState());

        // Subscribe to state changes
        window.addEventListener('sync-state-change', ((e: CustomEvent) => {
          setSyncState(e.detail);
        }) as EventListener);

        // Subscribe to conflicts
        engine.getConflicts().then(setConflicts);
      })
      .catch((err) => {
        console.error('[SyncProvider] Failed to initialize:', err);
        onSyncError?.(err);
      });

    return () => {
      // Cleanup subscriptions
      window.removeEventListener('sync-state-change', (() => {}) as EventListener);
    };
  }, [config, userId, onSyncError]);

  // Manual sync trigger
  const sync = useCallback(async () => {
    if (!syncEngineRef.current) return;

    try {
      await syncEngineRef.current.sync();
      // Refresh conflicts after sync
      const newConflicts = await syncEngineRef.current.getConflicts();
      setConflicts(newConflicts);
    } catch (err) {
      console.error('[SyncProvider] Sync failed:', err);
      onSyncError?.(err as Error);
    }
  }, [onSyncError]);

  // Resolve conflict
  const resolveConflict = useCallback(
    async (conflictId: string, choice: 'local' | 'remote' | 'merged', mergedData?: any) => {
      if (!syncEngineRef.current) return;

      try {
        await syncEngineRef.current.resolveConflictManually(conflictId, choice, mergedData);
        // Refresh conflicts
        const newConflicts = await syncEngineRef.current.getConflicts();
        setConflicts(newConflicts);
      } catch (err) {
        console.error('[SyncProvider] Failed to resolve conflict:', err);
        onSyncError?.(err as Error);
      }
    },
    [onSyncError]
  );

  // Queue annotation for sync
  const queueAnnotation = useCallback(async (annotation: Annotation) => {
    if (!syncEngineRef.current) return;

    try {
      await syncEngineRef.current.queueChange('annotations', {
        id: annotation.id,
        article_id: annotation.articleId,
        quote: annotation.quote,
        comment: annotation.comment,
        color: annotation.color,
        tags: annotation.tags,
        position: annotation.position,
        created_at: annotation.createdAt,
        updated_at: annotation.updatedAt,
      });
    } catch (err) {
      console.error('[SyncProvider] Failed to queue annotation:', err);
    }
  }, []);

  // Queue reading progress for sync
  const queueReadingProgress = useCallback(async (progress: { articleId: string; percentage: number }) => {
    if (!syncEngineRef.current) return;

    try {
      await syncEngineRef.current.queueChange('reading_progress', {
        article_id: progress.articleId,
        progress_percentage: progress.percentage,
        last_read_at: new Date().toISOString(),
      });
    } catch (err) {
      console.error('[SyncProvider] Failed to queue reading progress:', err);
    }
  }, []);

  // Auto-sync when coming back online
  useEffect(() => {
    const handleOnline = () => {
      if (syncEngineRef.current) {
        syncEngineRef.current.sync();
      }
    };

    window.addEventListener('online', handleOnline);
    return () => window.removeEventListener('online', handleOnline);
  }, []);

  const value: SyncContextValue = {
    syncEngine: syncEngineRef.current,
    syncState,
    isInitialized,
    pendingChanges: syncState.pendingChanges,
    lastSyncAt: syncState.lastSyncAt,
    conflicts,
    sync,
    resolveConflict,
    queueAnnotation,
    queueReadingProgress,
  };

  return <SyncContext.Provider value={value}>{children}</SyncContext.Provider>;
}

export function useSync() {
  const context = useContext(SyncContext);
  if (!context) {
    throw new Error('useSync must be used within a SyncProvider');
  }
  return context;
}

// Sync status indicator component
export function SyncStatusIndicator() {
  const { syncState, pendingChanges, lastSyncAt, sync } = useSync();

  const formatLastSync = (date: string | null) => {
    if (!date) return '从未同步';
    const d = new Date(date);
    const now = new Date();
    const diff = now.getTime() - d.getTime();

    if (diff < 60000) return '刚刚';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
    return d.toLocaleDateString('zh-CN');
  };

  return (
    <button
      onClick={sync}
      disabled={syncState.isSyncing || !syncState.isOnline}
      className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg bg-gray-100 hover:bg-gray-200 transition-colors disabled:opacity-50"
      title={syncState.isOnline ? `上次同步: ${formatLastSync(lastSyncAt)}` : '离线模式'}
    >
      {syncState.isSyncing ? (
        <>
          <span className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
          <span>同步中...</span>
        </>
      ) : !syncState.isOnline ? (
        <>
          <span>📴</span>
          <span>离线</span>
          {pendingChanges > 0 && (
            <span className="ml-1 px-1.5 py-0.5 text-xs bg-orange-500 text-white rounded-full">
              {pendingChanges}
            </span>
          )}
        </>
      ) : pendingChanges > 0 ? (
        <>
          <span>⬆️</span>
          <span>{pendingChanges} 待同步</span>
        </>
      ) : (
        <>
          <span>✓</span>
          <span>{formatLastSync(lastSyncAt)}</span>
        </>
      )}
    </button>
  );
}

// Conflict resolution modal
export function ConflictResolver() {
  const { conflicts, resolveConflict } = useSync();
  const [selectedConflict, setSelectedConflict] = useState<any>(null);

  if (conflicts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50">
      {!selectedConflict ? (
        <button
          onClick={() => setSelectedConflict(conflicts[0])}
          className="flex items-center gap-2 px-4 py-2 bg-orange-500 text-white rounded-lg shadow-lg hover:bg-orange-600 transition-colors"
        >
          <span>⚠️</span>
          <span>{conflicts.length} 个同步冲突需解决</span>
        </button>
      ) : (
        <div className="w-96 bg-white rounded-xl shadow-2xl p-4 border border-gray-200">
          <h3 className="font-semibold mb-4">解决同步冲突</h3>

          <div className="space-y-4 mb-4">
            <div className="p-3 bg-blue-50 rounded-lg">
              <div className="text-sm font-medium text-blue-700 mb-1">本地版本</div>
              <div className="text-sm text-blue-600">
                {selectedConflict.local?.quote || selectedConflict.local?.comment || '无内容'}
              </div>
              <div className="text-xs text-blue-400 mt-1">
                {selectedConflict.local_device_id}
              </div>
            </div>

            <div className="p-3 bg-green-50 rounded-lg">
              <div className="text-sm font-medium text-green-700 mb-1">远程版本</div>
              <div className="text-sm text-green-600">
                {selectedConflict.remote?.quote || selectedConflict.remote?.comment || '无内容'}
              </div>
              <div className="text-xs text-green-400 mt-1">
                {selectedConflict.remote_device_id}
              </div>
            </div>
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => {
                resolveConflict(selectedConflict.id, 'local');
                setSelectedConflict(null);
              }}
              className="flex-1 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
            >
              使用本地
            </button>
            <button
              onClick={() => {
                resolveConflict(selectedConflict.id, 'remote');
                setSelectedConflict(null);
              }}
              className="flex-1 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600"
            >
              使用远程
            </button>
            <button
              onClick={() => setSelectedConflict(null)}
              className="px-3 py-2 text-gray-500 hover:bg-gray-100 rounded-lg"
            >
              稍后
            </button>
          </div>

          {conflicts.length > 1 && (
            <div className="text-center text-sm text-gray-500 mt-3">
              还有 {conflicts.length - 1} 个冲突待解决
            </div>
          )}
        </div>
      )}
    </div>
  );
}
