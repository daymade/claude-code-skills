'use client';

import Link from 'next/link';
import { useState } from 'react';
import { InboxItem, InboxStatus, ContentPriority } from '@/lib/inbox-engine';

interface InboxItemCardProps {
  item: InboxItem;
  onStatusChange?: (id: string, status: InboxStatus) => void;
  onPriorityChange?: (id: string, priority: ContentPriority) => void;
  variant?: 'default' | 'compact' | 'list';
}

const statusConfig: Record<InboxStatus, { label: string; color: string; icon: string }> = {
  inbox: { label: '收件箱', color: 'bg-blue-100 text-blue-700', icon: '📥' },
  reading: { label: '阅读中', color: 'bg-yellow-100 text-yellow-700', icon: '📖' },
  later: { label: '稍后读', color: 'bg-gray-100 text-gray-700', icon: '⏰' },
  archived: { label: '已归档', color: 'bg-green-100 text-green-700', icon: '✓' },
  favorite: { label: '收藏', color: 'bg-red-100 text-red-700', icon: '⭐' },
};

const priorityConfig: Record<ContentPriority, { label: string; color: string }> = {
  high: { label: '高优先级', color: 'text-red-600' },
  medium: { label: '中优先级', color: 'text-yellow-600' },
  low: { label: '低优先级', color: 'text-gray-500' },
};

const complexityConfig = {
  easy: { label: '简单', color: 'text-green-600', icon: '🟢' },
  medium: { label: '中等', color: 'text-yellow-600', icon: '🟡' },
  hard: { label: '困难', color: 'text-red-600', icon: '🔴' },
};

const contentTypeConfig: Record<string, { label: string; icon: string }> = {
  article: { label: '文章', icon: '📄' },
  newsletter: { label: 'Newsletter', icon: '📧' },
  paper: { label: '论文', icon: '📑' },
  'tweet-thread': { label: '推文串', icon: '🐦' },
  'video-transcript': { label: '视频字幕', icon: '🎬' },
};

export function InboxItemCard({
  item,
  onStatusChange,
  onPriorityChange,
  variant = 'default',
}: InboxItemCardProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const formatDate = (date: string) => {
    const d = new Date(date);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) return '今天';
    if (days === 1) return '昨天';
    if (days < 7) return `${days}天前`;
    if (days < 30) return `${Math.floor(days / 7)}周前`;
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  };

  const handleStatusChange = (newStatus: InboxStatus) => {
    onStatusChange?.(item.id, newStatus);
    setIsMenuOpen(false);
  };

  if (variant === 'compact') {
    return (
      <div className="flex items-center gap-3 p-3 bg-white rounded-lg border border-gray-200 hover:border-blue-300 transition-colors">
        <button
          onClick={() => handleStatusChange(item.status === 'archived' ? 'inbox' : 'archived')}
          className={`flex-shrink-0 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors ${
            item.status === 'archived'
              ? 'bg-green-500 border-green-500 text-white'
              : 'border-gray-300 hover:border-blue-400'
          }`}
        >
          {item.status === 'archived' && '✓'}
        </button>

        <Link
          href={`/articles/${item.articleId}`}
          className="flex-1 min-w-0 hover:text-blue-600 transition-colors"
        >
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-900 line-clamp-1">
              {item.summary || '未命名文章'}
            </span>
            <span className={`text-xs px-1.5 py-0.5 rounded ${priorityConfig[item.priority].color} bg-opacity-10`}>
              {priorityConfig[item.priority].label}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
            <span>{contentTypeConfig[item.contentType]?.icon || '📄'}</span>
            <span>{item.estimatedReadTime}分钟</span>
            <span>·</span>
            <span>{formatDate(item.addedAt)}</span>
          </div>
        </Link>

        <div className="flex items-center gap-1">
          {item.suggestedTags.slice(0, 2).map((tag) => (
            <span
              key={tag}
              className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full"
            >
              {tag}
            </span>
          ))}
        </div>
      </div>
    );
  }

  if (variant === 'list') {
    return (
      <div className="flex items-center gap-4 p-4 bg-white rounded-lg border border-gray-200 hover:shadow-md transition-shadow">
        <button
          onClick={() => handleStatusChange(item.status === 'archived' ? 'inbox' : 'archived')}
          className={`flex-shrink-0 w-6 h-6 rounded-full border-2 flex items-center justify-center transition-colors ${
            item.status === 'archived'
              ? 'bg-green-500 border-green-500 text-white'
              : 'border-gray-300 hover:border-blue-400'
          }`}
        >
          {item.status === 'archived' && '✓'}
        </button>

        <Link
          href={`/articles/${item.articleId}`}
          className="flex-1 min-w-0"
        >
          <div className="flex items-center gap-3">
            <span className="text-base font-medium text-gray-900 hover:text-blue-600 transition-colors">
              {item.summary || '未命名文章'}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${statusConfig[item.status].color}`}>
              {statusConfig[item.status].icon} {statusConfig[item.status].label}
            </span>
          </div>
          <div className="flex items-center gap-4 mt-2 text-sm text-gray-500">
            <span className="flex items-center gap-1">
              {contentTypeConfig[item.contentType]?.icon}
              {contentTypeConfig[item.contentType]?.label}
            </span>
            <span className="flex items-center gap-1">
              {complexityConfig[item.complexity].icon}
              {complexityConfig[item.complexity].label}
            </span>
            <span>预计{item.estimatedReadTime}分钟</span>
            <span>评分 {item.score}/100</span>
            <span>添加于 {formatDate(item.addedAt)}</span>
          </div>
        </Link>

        <div className="flex items-center gap-2">
          {item.suggestedTags.slice(0, 3).map((tag) => (
            <span
              key={tag}
              className="text-xs px-2 py-1 bg-blue-50 text-blue-600 rounded-full"
            >
              {tag}
            </span>
          ))}

          <div className="relative">
            <button
              onClick={() => setIsMenuOpen(!isMenuOpen)}
              className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100"
            >
              ⋯
            </button>

            {isMenuOpen && (
              <div className="absolute right-0 top-full mt-1 w-40 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-10">
                {(['inbox', 'reading', 'later', 'favorite', 'archived'] as InboxStatus[]).map((s) => (
                  <button
                    key={s}
                    onClick={() => handleStatusChange(s)}
                    className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-50 flex items-center gap-2 ${
                      item.status === s ? 'text-blue-600 bg-blue-50' : 'text-gray-700'
                    }`}
                  >
                    <span>{statusConfig[s].icon}</span>
                    <span>{statusConfig[s].label}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden hover:shadow-md transition-shadow">
      <div className="p-4">
        <div className="flex items-start gap-3">
          <button
            onClick={() => handleStatusChange(item.status === 'archived' ? 'inbox' : 'archived')}
            className={`flex-shrink-0 w-6 h-6 rounded-full border-2 flex items-center justify-center transition-colors mt-0.5 ${
              item.status === 'archived'
                ? 'bg-green-500 border-green-500 text-white'
                : 'border-gray-300 hover:border-blue-400'
            }`}
          >
            {item.status === 'archived' && '✓'}
          </button>

          <div className="flex-1 min-w-0">
            <Link
              href={`/articles/${item.articleId}`}
              className="block group"
            >
              <h3 className="text-lg font-semibold text-gray-900 group-hover:text-blue-600 transition-colors line-clamp-2">
                {item.summary || '未命名文章'}
              </h3>
            </Link>

            {item.summary && (
              <p className="text-sm text-gray-600 mt-2 line-clamp-2">
                {item.summary}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-2 mt-3">
              <span className={`text-xs px-2 py-1 rounded-full ${statusConfig[item.status].color}`}>
                {statusConfig[item.status].icon} {statusConfig[item.status].label}
              </span>
              <span className={`text-xs px-2 py-1 rounded-full ${priorityConfig[item.priority].color} bg-opacity-10 bg-current`}>
                {priorityConfig[item.priority].label}
              </span>
              <span className="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded-full">
                {contentTypeConfig[item.contentType]?.icon} {contentTypeConfig[item.contentType]?.label}
              </span>
              <span className="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded-full">
                {complexityConfig[item.complexity].icon} {complexityConfig[item.complexity].label}
              </span>
            </div>

            <div className="flex items-center gap-4 mt-3 text-sm text-gray-500">
              <span>⏱️ {item.estimatedReadTime}分钟</span>
              <span>📊 评分 {item.score}/100</span>
              {item.suggestedFolder && (
                <span>📁 {item.suggestedFolder}</span>
              )}
              <span>📅 {formatDate(item.addedAt)}</span>
            </div>

            {item.keyTopics.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-3">
                {item.keyTopics.map((topic) => (
                  <span
                    key={topic}
                    className="text-xs px-2 py-1 bg-purple-50 text-purple-600 rounded"
                  >
                    {topic}
                  </span>
                ))}
              </div>
            )}

            {item.suggestedTags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {item.suggestedTags.map((tag) => (
                  <span
                    key={tag}
                    className="text-xs px-2 py-1 bg-blue-50 text-blue-600 rounded-full"
                  >
                    #{tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="px-4 py-3 bg-gray-50 border-t border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {(['inbox', 'reading', 'later', 'favorite'] as InboxStatus[]).map((s) => (
            <button
              key={s}
              onClick={() => handleStatusChange(s)}
              className={`text-xs px-3 py-1.5 rounded-lg transition-colors flex items-center gap-1 ${
                item.status === s
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-white text-gray-600 hover:bg-gray-100 border border-gray-200'
              }`}
            >
              <span>{statusConfig[s].icon}</span>
              <span>{statusConfig[s].label}</span>
            </button>
          ))}
        </div>

        <Link
          href={`/articles/${item.articleId}`}
          className="text-sm text-blue-600 hover:text-blue-700 font-medium"
        >
          开始阅读 →
        </Link>
      </div>
    </div>
  );
}
