'use client';

/**
 * Reading Analytics Dashboard - 阅读数据分析仪表盘
 *
 * 提供 GitHub-style 阅读热力图、阅读统计、知识领域分布
 * 让用户看到自己的阅读习惯和知识积累
 */

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { DailyReviewEngine } from '@/lib/daily-review-engine';

interface ReadingStats {
  totalAnnotations: number;
  totalReviewed: number;
  currentStreak: number;
  longestStreak: number;
  weeklyAverage: number;
  memoryStrengthDistribution: {
    weak: number;
    medium: number;
    strong: number;
  };
}

interface HeatmapData {
  date: string;
  count: number;
  level: 0 | 1 | 2 | 3 | 4;
}

export function ReadingAnalytics() {
  const [stats, setStats] = useState<ReadingStats | null>(null);
  const [heatmapData, setHeatmapData] = useState<HeatmapData[]>([]);
  const [selectedRange, setSelectedRange] = useState<'7d' | '30d' | '90d' | '1y'>('90d');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadAnalytics();
  }, [selectedRange]);

  const loadAnalytics = async () => {
    setIsLoading(true);
    try {
      const engine = new DailyReviewEngine();
      await engine.init();

      const statsData = await engine.getReadingStats();
      setStats(statsData);

      // Generate heatmap data
      const heatmap = generateHeatmapData(selectedRange);
      setHeatmapData(heatmap);
    } catch (error) {
      console.error('Failed to load analytics:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const generateHeatmapData = (range: string): HeatmapData[] => {
    const days = range === '7d' ? 7 : range === '30d' ? 30 : range === '90d' ? 90 : 365;
    const data: HeatmapData[] = [];

    for (let i = days; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);

      // Simulate data - in production, this would come from actual reading history
      const count = Math.floor(Math.random() * 10);
      let level: 0 | 1 | 2 | 3 | 4 = 0;
      if (count > 0) level = 1;
      if (count > 3) level = 2;
      if (count > 6) level = 3;
      if (count > 8) level = 4;

      data.push({
        date: date.toISOString().split('T')[0],
        count,
        level,
      });
    }

    return data;
  };

  const getLevelColor = (level: number): string => {
    const colors = [
      'bg-gray-100',
      'bg-green-200',
      'bg-green-300',
      'bg-green-400',
      'bg-green-500',
    ];
    return colors[level] || colors[0];
  };

  const formatDate = (dateStr: string): string => {
    const date = new Date(dateStr);
    return `${date.getMonth() + 1}/${date.getDate()}`;
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-4 border-purple-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="text-center py-12 text-gray-500">
        <p>暂无数据</p>
        <p className="text-sm mt-2">开始阅读和标注，数据将在这里显示</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">阅读数据分析</h2>
          <p className="text-gray-500">了解你的阅读习惯和知识积累</p>
        </div>
        <div className="flex gap-2">
          {(['7d', '30d', '90d', '1y'] as const).map((range) => (
            <button
              key={range}
              onClick={() => setSelectedRange(range)}
              className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                selectedRange === range
                  ? 'bg-purple-500 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {range === '7d' && '最近7天'}
              {range === '30d' && '最近30天'}
              {range === '90d' && '最近90天'}
              {range === '1y' && '最近1年'}
            </button>
          ))}
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          title="总标注数"
          value={stats.totalAnnotations}
          icon="📝"
          trend="+12%"
          trendUp={true}
        />
        <StatCard
          title="连续打卡"
          value={`${stats.currentStreak} 天`}
          icon="🔥"
          subtitle={`最长 ${stats.longestStreak} 天`}
        />
        <StatCard
          title="已回顾"
          value={stats.totalReviewed}
          icon="🧠"
          trend="+5"
          trendUp={true}
        />
        <StatCard
          title="周均阅读"
          value={stats.weeklyAverage}
          icon="📊"
        />
      </div>

      {/* Heatmap */}
      <div className="bg-white rounded-xl border p-6">
        <h3 className="font-semibold mb-4">阅读热力图</h3>
        <div className="overflow-x-auto">
          <div className="flex gap-1 min-w-max">
            {Array.from({ length: 7 }, (_, dayOfWeek) => (
              <div key={dayOfWeek} className="flex flex-col gap-1">
                {heatmapData
                  .filter((_, i) => i % 7 === dayOfWeek)
                  .map((day, i) => (
                    <motion.div
                      key={day.date}
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      transition={{ delay: i * 0.01 }}
                      className={`w-4 h-4 rounded-sm ${getLevelColor(day.level)}`}
                      title={`${formatDate(day.date)}: ${day.count} 个标注`}
                    />
                  ))}
              </div>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-4 mt-4 text-sm text-gray-500">
          <span>少</span>
          <div className="flex gap-1">
            {[0, 1, 2, 3, 4].map((level) => (
              <div
                key={level}
                className={`w-4 h-4 rounded-sm ${getLevelColor(level)}`}
              />
            ))}
          </div>
          <span>多</span>
        </div>
      </div>

      {/* Memory Strength Distribution */}
      <div className="bg-white rounded-xl border p-6">
        <h3 className="font-semibold mb-4">记忆强度分布</h3>
        <div className="space-y-4">
          <DistributionBar
            label="牢固记忆"
            count={stats.memoryStrengthDistribution.strong}
            total={stats.totalAnnotations}
            color="bg-green-500"
          />
          <DistributionBar
            label="一般记忆"
            count={stats.memoryStrengthDistribution.medium}
            total={stats.totalAnnotations}
            color="bg-yellow-500"
          />
          <DistributionBar
            label="需要复习"
            count={stats.memoryStrengthDistribution.weak}
            total={stats.totalAnnotations}
            color="bg-red-500"
          />
        </div>
        <p className="text-sm text-gray-500 mt-4">
          基于你的回顾历史，建议优先复习标记为"需要复习"的内容
        </p>
      </div>

      {/* Monthly Report Preview */}
      <div className="bg-gradient-to-r from-purple-500 to-pink-500 rounded-xl p-6 text-white">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-lg">本月阅读报告</h3>
            <p className="text-white/80 mt-1">
              你本月阅读了 {stats.weeklyAverage * 4} 篇文章，
              添加了 {Math.floor(stats.totalAnnotations / 12)} 条标注
            </p>
          </div>
          <button className="px-4 py-2 bg-white/20 rounded-lg hover:bg-white/30 transition-colors">
            查看完整报告
          </button>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  title,
  value,
  icon,
  trend,
  trendUp,
  subtitle,
}: {
  title: string;
  value: string | number;
  icon: string;
  trend?: string;
  trendUp?: boolean;
  subtitle?: string;
}) {
  return (
    <div className="bg-white rounded-xl border p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-gray-500">{title}</p>
          <p className="text-2xl font-bold mt-1">{value}</p>
          {subtitle && <p className="text-xs text-gray-400 mt-1">{subtitle}</p>}
        </div>
        <span className="text-2xl">{icon}</span>
      </div>
      {trend && (
        <div
          className={`flex items-center gap-1 mt-2 text-sm ${
            trendUp ? 'text-green-600' : 'text-red-600'
          }`}
        >
          <span>{trendUp ? '↑' : '↓'}</span>
          <span>{trend}</span>
        </div>
      )}
    </div>
  );
}

function DistributionBar({
  label,
  count,
  total,
  color,
}: {
  label: string;
  count: number;
  total: number;
  color: string;
}) {
  const percentage = total > 0 ? (count / total) * 100 : 0;

  return (
    <div className="flex items-center gap-4">
      <span className="w-20 text-sm text-gray-600">{label}</span>
      <div className="flex-1 h-6 bg-gray-100 rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          className={`h-full ${color}`}
        />
      </div>
      <span className="w-16 text-sm text-right">
        {count} ({percentage.toFixed(0)}%)
      </span>
    </div>
  );
}
