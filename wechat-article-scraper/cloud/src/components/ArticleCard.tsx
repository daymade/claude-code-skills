'use client';

import Link from 'next/link';
import { Article } from '@/types/supabase';

interface ArticleCardProps {
  article: Article;
  variant?: 'default' | 'compact' | 'featured';
}

export function ArticleCard({ article, variant = 'default' }: ArticleCardProps) {
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

  const formatNumber = (num: number) => {
    if (num >= 10000) return `${(num / 10000).toFixed(1)}w`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}k`;
    return num.toString();
  };

  if (variant === 'compact') {
    return (
      <Link
        href={`/articles/${article.id}`}
        className="block bg-white rounded-lg shadow-sm border border-gray-200 p-3 active:scale-[0.98] transition-transform"
      >
        <div className="flex gap-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-medium text-gray-900 line-clamp-2 leading-snug">
              {article.title}
            </h3>
            <div className="flex items-center gap-2 mt-1.5 text-xs text-gray-500">
              <span className="truncate">{article.author || '未知作者'}</span>
              <span>·</span>
              <span>{formatDate(article.publish_time || article.created_at)}</span>
            </div>
          </div>
          {(article.read_count || 0) > 0 && (
            <div className="flex flex-col items-end text-xs text-gray-400">
              <span className="flex items-center gap-0.5">
                👁 {formatNumber(article.read_count || 0)}
              </span>
              {(article.like_count || 0) > 0 && (
                <span className="flex items-center gap-0.5 mt-0.5">
                  👍 {formatNumber(article.like_count || 0)}
                </span>
              )}
            </div>
          )}
        </div>
      </Link>
    );
  }

  if (variant === 'featured') {
    return (
      <Link
        href={`/articles/${article.id}`}
        className="block bg-white rounded-xl shadow-md overflow-hidden active:scale-[0.98] transition-transform"
      >
        <div className="aspect-video bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
          <span className="text-4xl">📰</span>
        </div>
        <div className="p-4">
          <h3 className="text-lg font-semibold text-gray-900 line-clamp-2">
            {article.title}
          </h3>
          <p className="text-sm text-gray-600 mt-2 line-clamp-2">
            {(article.content || '').substring(0, 100)}...
          </p>
          <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100">
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <span className="font-medium text-blue-600">{article.author || '未知作者'}</span>
              <span>·</span>
              <span>{formatDate(article.publish_time || article.created_at)}</span>
            </div>
            <div className="flex items-center gap-3 text-sm text-gray-400">
              <span className="flex items-center gap-1">
                👁 {formatNumber(article.read_count || 0)}
              </span>
              <span className="flex items-center gap-1">
                👍 {formatNumber(article.like_count || 0)}
              </span>
            </div>
          </div>
        </div>
      </Link>
    );
  }

  return (
    <Link
      href={`/articles/${article.id}`}
      className="block bg-white rounded-lg shadow-sm border border-gray-200 p-4 active:scale-[0.98] transition-transform"
    >
      <h3 className="text-base font-medium text-gray-900 line-clamp-2 leading-snug">
        {article.title}
      </h3>
      <p className="text-sm text-gray-600 mt-2 line-clamp-2">
        {(article.content || '').substring(0, 120)}...
      </p>
      <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="font-medium text-blue-600">{article.author || '未知作者'}</span>
          <span>·</span>
          <span>{formatDate(article.publish_time || article.created_at)}</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-400">
          <span className="flex items-center gap-0.5">
            👁 {formatNumber(article.read_count || 0)}
          </span>
          <span className="flex items-center gap-0.5">
            👍 {formatNumber(article.like_count || 0)}
          </span>
        </div>
      </div>
    </Link>
  );
}
