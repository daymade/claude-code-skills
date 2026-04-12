'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { MobileLayout } from '@/components/MobileLayout';
import { ArticleCard } from '@/components/ArticleCard';
import { usePWA, useNetworkStatus } from '@/hooks/usePWA';
import { Article } from '@/types/supabase';

export default function HomePage() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const { status, install, requestPushPermission } = usePWA();
  const { isOnline } = useNetworkStatus();

  useEffect(() => {
    fetchArticles();
  }, []);

  const fetchArticles = async () => {
    try {
      // This would fetch from your actual API
      // For now using mock data
      const mockArticles: Article[] = [
        {
          id: '1',
          workspace_id: 'default',
          url: 'https://example.com/1',
          title: '人工智能在内容创作领域的应用与发展趋势',
          content: '随着大语言模型技术的快速发展，AI在内容创作领域展现出了巨大的潜力...',
          author: '科技前沿',
          publish_time: '2025-04-11T10:00:00Z',
          read_count: 15234,
          like_count: 892,
          tags: ['AI', '内容创作'],
          metadata: {},
          created_by: null,
          created_at: '2025-04-11T10:00:00Z',
          updated_at: '2025-04-11T10:00:00Z',
        },
        {
          id: '2',
          workspace_id: 'default',
          url: 'https://example.com/2',
          title: '2025年微信公众号运营策略全解析',
          content: '在算法不断迭代的今天，如何让你的公众号内容获得更多曝光...',
          author: '运营课堂',
          publish_time: '2025-04-10T08:30:00Z',
          read_count: 8932,
          like_count: 567,
          tags: ['运营', '公众号'],
          metadata: {},
          created_by: null,
          created_at: '2025-04-10T08:30:00Z',
          updated_at: '2025-04-10T08:30:00Z',
        },
        {
          id: '3',
          workspace_id: 'default',
          url: 'https://example.com/3',
          title: '从零开始搭建个人知识管理系统',
          content: '信息爆炸时代，如何有效管理知识成为了一项重要技能...',
          author: '效率工具',
          publish_time: '2025-04-09T14:20:00Z',
          read_count: 5671,
          like_count: 423,
          tags: ['知识管理', '效率'],
          metadata: {},
          created_by: null,
          created_at: '2025-04-09T14:20:00Z',
          updated_at: '2025-04-09T14:20:00Z',
        },
      ];
      setArticles(mockArticles);
    } catch (error) {
      console.error('Failed to fetch articles:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleInstall = async () => {
    const result = await install();
    if (!result.success) {
      alert('安装失败，请重试');
    }
  };

  return (
    <MobileLayout>
      {/* Offline Banner */}
      {!isOnline && (
        <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg flex items-center gap-2 text-yellow-800 text-sm">
          <span className="text-lg">📡</span>
          <span>离线模式 - 部分功能可能不可用</span>
        </div>
      )}

      {/* Install Banner (mobile only) */}
      {status.canInstall && !status.isStandalone && (
        <div className="mb-4 p-4 bg-gradient-to-r from-blue-500 to-purple-600 rounded-xl text-white">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="font-semibold">添加到主屏幕</h2>
              <p className="text-sm text-blue-100 mt-1">像原生App一样使用，支持离线访问</p>
            </div>
            <button
              onClick={handleInstall}
              className="px-4 py-2 bg-white text-blue-600 rounded-lg font-medium text-sm hover:bg-blue-50 transition-colors"
            >
              安装
            </button>
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div className="grid grid-cols-4 gap-3 mb-6">
        <QuickAction
          href="/scrape"
          icon="🔗"
          label="抓取文章"
          color="bg-blue-500"
        />
        <QuickAction
          href="/search"
          icon="🔍"
          label="智能搜索"
          color="bg-purple-500"
        />
        <QuickAction
          href="/agent"
          icon="🤖"
          label="AI助手"
          color="bg-green-500"
        />
        <QuickAction
          href="/kg"
          icon="🕸️"
          label="知识图谱"
          color="bg-orange-500"
        />
      </div>

      {/* Stats Summary */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <StatCard value="1,234" label="已抓取" trend="+12%" />
        <StatCard value="89" label="本周新增" trend="+5%" />
        <StatCard value="45.2K" label="总阅读" trend="+23%" />
      </div>

      {/* Featured Article */}
      <section className="mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-3">精选文章</h2>
        {articles[0] && <ArticleCard article={articles[0]} variant="featured" />}
      </section>

      {/* Recent Articles */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900">最近更新</h2>
          <Link href="/articles" className="text-sm text-blue-600 hover:text-blue-700">
            查看全部 →
          </Link>
        </div>
        <div className="space-y-3">
          {isLoading ? (
            <LoadingSkeleton />
          ) : (
            articles.slice(1).map((article) => (
              <ArticleCard key={article.id} article={article} variant="compact" />
            ))
          )}
        </div>
      </section>

      {/* PWA Settings (mobile only) */}
      <section className="mt-8 pt-6 border-t border-gray-200 md:hidden">
        <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">
          应用设置
        </h3>
        <div className="space-y-2">
          {!status.pushEnabled && (
            <button
              onClick={() => requestPushPermission()}
              className="w-full flex items-center justify-between p-3 bg-white rounded-lg border border-gray-200 text-left"
            >
              <div className="flex items-center gap-3">
                <span className="text-xl">🔔</span>
                <div>
                  <div className="font-medium text-gray-900">启用推送通知</div>
                  <div className="text-sm text-gray-500">新文章抓取完成时提醒</div>
                </div>
              </div>
              <span className="text-gray-400">→</span>
            </button>
          )}
          <div className="flex items-center justify-between p-3 bg-white rounded-lg border border-gray-200">
            <div className="flex items-center gap-3">
              <span className="text-xl">💾</span>
              <div>
                <div className="font-medium text-gray-900">离线缓存</div>
                <div className="text-sm text-gray-500">
                  {status.swRegistered ? '已启用' : '未启用'}
                </div>
              </div>
            </div>
            <span className={`w-2 h-2 rounded-full ${status.swRegistered ? 'bg-green-500' : 'bg-gray-300'}`} />
          </div>
        </div>
      </section>
    </MobileLayout>
  );
}

function QuickAction({ href, icon, label, color }: { href: string; icon: string; label: string; color: string }) {
  return (
    <Link
      href={href}
      className="flex flex-col items-center gap-1.5"
    >
      <div className={`w-14 h-14 ${color} rounded-2xl flex items-center justify-center text-2xl shadow-lg active:scale-95 transition-transform`}>
        {icon}
      </div>
      <span className="text-xs text-gray-600 font-medium">{label}</span>
    </Link>
  );
}

function StatCard({ value, label, trend }: { value: string; label: string; trend: string }) {
  return (
    <div className="bg-white rounded-xl p-3 border border-gray-200">
      <div className="text-xl font-bold text-gray-900">{value}</div>
      <div className="text-xs text-gray-500 mt-0.5">{label}</div>
      <div className="text-xs text-green-600 mt-1 font-medium">{trend}</div>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <>
      {[1, 2, 3].map((i) => (
        <div key={i} className="bg-white rounded-lg p-3 border border-gray-200 animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
          <div className="h-3 bg-gray-200 rounded w-1/2" />
        </div>
      ))}
    </>
  );
}
