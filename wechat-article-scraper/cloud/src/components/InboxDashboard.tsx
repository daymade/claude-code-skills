'use client';

import { useState, useEffect, useCallback } from 'react';
import { InboxItemCard } from './InboxItemCard';
import { InboxEngine, InboxItem, InboxStatus, ContentPriority, InboxStats, InboxFilters } from '@/lib/inbox-engine';

interface InboxDashboardProps {
  userId: string;
  supabaseUrl: string;
  supabaseKey: string;
}

type ViewMode = 'grid' | 'list' | 'compact';
type SortOption = 'score' | 'addedAt' | 'readTime' | 'priority';

export function InboxDashboard({ userId, supabaseUrl, supabaseKey }: InboxDashboardProps) {
  const [engine] = useState(() => new InboxEngine(supabaseUrl, supabaseKey));
  const [items, setItems] = useState<InboxItem[]>([]);
  const [stats, setStats] = useState<InboxStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [sortBy, setSortBy] = useState<SortOption>('score');

  // Filters
  const [selectedStatus, setSelectedStatus] = useState<InboxStatus | 'all'>('inbox');
  const [selectedPriority, setSelectedPriority] = useState<ContentPriority | 'all'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [availableTime, setAvailableTime] = useState<number | null>(null);
  const [showRecommendations, setShowRecommendations] = useState(false);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const filters: InboxFilters = {};

      if (selectedStatus !== 'all') {
        filters.status = [selectedStatus];
      }
      if (selectedPriority !== 'all') {
        filters.priority = [selectedPriority];
      }
      if (searchQuery) {
        filters.searchQuery = searchQuery;
      }
      if (availableTime && showRecommendations) {
        filters.maxReadTime = availableTime;
      }

      const result = await engine.getInboxItems(userId, filters, {
        sortBy,
        limit: 50,
      });

      setItems(result.items);
    } catch (error) {
      console.error('Failed to fetch inbox items:', error);
    } finally {
      setLoading(false);
    }
  }, [engine, userId, selectedStatus, selectedPriority, searchQuery, sortBy, availableTime, showRecommendations]);

  const fetchStats = useCallback(async () => {
    try {
      const s = await engine.getInboxStats(userId);
      setStats(s);
    } catch (error) {
      console.error('Failed to fetch inbox stats:', error);
    }
  }, [engine, userId]);

  useEffect(() => {
    fetchItems();
    fetchStats();
  }, [fetchItems, fetchStats]);

  const handleStatusChange = async (itemId: string, status: InboxStatus) => {
    try {
      await engine.updateStatus(itemId, status, userId);
      await fetchItems();
      await fetchStats();
    } catch (error) {
      console.error('Failed to update status:', error);
    }
  };

  const handleGetRecommendations = async () => {
    if (!availableTime) return;
    setShowRecommendations(true);
    setLoading(true);
    try {
      const recommendations = await engine.getRecommendations(userId, availableTime, 5);
      setItems(recommendations);
    } catch (error) {
      console.error('Failed to get recommendations:', error);
    } finally {
      setLoading(false);
    }
  };

  const statusTabs: { id: InboxStatus | 'all'; label: string; icon: string; count?: number }[] = [
    { id: 'all', label: '全部', icon: '📚', count: stats?.total },
    { id: 'inbox', label: '收件箱', icon: '📥', count: stats?.byStatus.inbox },
    { id: 'reading', label: '阅读中', icon: '📖', count: stats?.byStatus.reading },
    { id: 'later', label: '稍后读', icon: '⏰', count: stats?.byStatus.later },
    { id: 'favorite', label: '收藏', icon: '⭐', count: stats?.byStatus.favorite },
    { id: 'archived', label: '已归档', icon: '✓', count: stats?.byStatus.archived },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">智能收件箱</h1>
              <p className="text-sm text-gray-500 mt-1">
                {stats ? (
                  <>
                    共 {stats.total} 篇文章 · 预计阅读时间 {stats.estimatedTotalReadTime} 分钟
                    {stats.unreadCount > 0 && (
                      <span className="ml-2 text-blue-600">· {stats.unreadCount} 篇未读</span>
                    )}
                  </>
                ) : (
                  '加载中...'
                )}
              </p>
            </div>

            {/* Quick Add Button */}
            <button
              onClick={() => {/* TODO: Open add modal */}}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
            >
              <span>+</span>
              <span>添加文章</span>
            </button>
          </div>

          {/* Status Tabs */}
          <div className="flex items-center gap-1 mt-4 overflow-x-auto pb-2">
            {statusTabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setSelectedStatus(tab.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
                  selectedStatus === tab.id
                    ? 'bg-blue-100 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                <span>{tab.icon}</span>
                <span>{tab.label}</span>
                {typeof tab.count === 'number' && (
                  <span className={`ml-1 px-1.5 py-0.5 text-xs rounded-full ${
                    selectedStatus === tab.id
                      ? 'bg-blue-200 text-blue-800'
                      : 'bg-gray-200 text-gray-700'
                  }`}>
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Smart Recommendations */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="bg-gradient-to-r from-blue-500 to-purple-600 rounded-xl p-6 text-white">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">📚 智能推荐阅读</h2>
              <p className="text-blue-100 mt-1">
                根据你的可用时间，推荐最适合阅读的内容
              </p>
            </div>
            <div className="flex items-center gap-3">
              <select
                value={availableTime || ''}
                onChange={(e) => setAvailableTime(e.target.value ? Number(e.target.value) : null)}
                className="px-4 py-2 rounded-lg text-gray-900 bg-white/90 border-0 focus:ring-2 focus:ring-white"
              >
                <option value="">选择可用时间...</option>
                <option value={5}>5分钟</option>
                <option value={10}>10分钟</option>
                <option value={15}>15分钟</option>
                <option value={30}>30分钟</option>
                <option value={60}>1小时</option>
              </select>
              <button
                onClick={handleGetRecommendations}
                disabled={!availableTime}
                className="px-4 py-2 bg-white text-blue-600 rounded-lg font-medium hover:bg-blue-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                获取推荐
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Filters & Controls */}
      <div className="max-w-7xl mx-auto px-4 pb-6">
        <div className="flex flex-wrap items-center justify-between gap-4 bg-white p-4 rounded-lg border border-gray-200">
          <div className="flex items-center gap-4">
            {/* Search */}
            <div className="relative">
              <input
                type="text"
                placeholder="搜索文章..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 w-64"
              />
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                🔍
              </span>
            </div>

            {/* Priority Filter */}
            <select
              value={selectedPriority}
              onChange={(e) => setSelectedPriority(e.target.value as ContentPriority | 'all')}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">所有优先级</option>
              <option value="high">高优先级</option>
              <option value="medium">中优先级</option>
              <option value="low">低优先级</option>
            </select>

            {/* Sort */}
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="score">按评分排序</option>
              <option value="addedAt">按添加时间</option>
              <option value="readTime">按阅读时间</option>
              <option value="priority">按优先级</option>
            </select>
          </div>

          {/* View Mode Toggle */}
          <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
            {(['grid', 'list', 'compact'] as ViewMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                  viewMode === mode
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                {mode === 'grid' && '▦'}
                {mode === 'list' && '☰'}
                {mode === 'compact' && '≡'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Content Grid */}
      <div className="max-w-7xl mx-auto px-4 pb-12">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-20">
            <div className="text-6xl mb-4">📭</div>
            <h3 className="text-lg font-medium text-gray-900">收件箱为空</h3>
            <p className="text-gray-500 mt-2">
              {searchQuery
                ? '没有找到匹配的文章，试试其他搜索词'
                : '还没有文章，点击上方"添加文章"开始'}
            </p>
          </div>
        ) : (
          <div className={`
            ${viewMode === 'grid' ? 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4' : ''}
            ${viewMode === 'list' ? 'space-y-4' : ''}
            ${viewMode === 'compact' ? 'space-y-2' : ''}
          `}>
            {items.map((item) => (
              <InboxItemCard
                key={item.id}
                item={item}
                onStatusChange={handleStatusChange}
                variant={viewMode === 'compact' ? 'compact' : viewMode === 'list' ? 'list' : 'default'}
              />
            ))}
          </div>
        )}
      </div>

      {/* Quick Stats Footer */}
      {stats && (
        <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 px-4 py-3">
          <div className="max-w-7xl mx-auto flex items-center justify-between text-sm">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <span className="text-gray-500">按优先级:</span>
                <span className="text-red-600 font-medium">{stats.byPriority.high} 高</span>
                <span className="text-yellow-600 font-medium">{stats.byPriority.medium} 中</span>
                <span className="text-gray-500 font-medium">{stats.byPriority.low} 低</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-gray-500">按类型:</span>
                <span className="font-medium">{stats.byContentType.article} 文章</span>
                <span className="font-medium">{stats.byContentType.newsletter} Newsletter</span>
                <span className="font-medium">{stats.byContentType.paper} 论文</span>
              </div>
            </div>
            <div className="text-gray-500">
              平均阅读时间: <span className="font-medium text-gray-900">{stats.averageReadTime}分钟</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
