'use client';

/**
 * Daily Review Component - 每日回顾界面
 *
 * 核心交互：展示待回顾内容 -> 用户反馈 -> 算法优化
 * 学习 Readwise 的卡片式回顾，但更加简洁
 */

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { DailyReviewEngine, ReviewItem } from '@/lib/daily-review-engine';

export function DailyReview() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isComplete, setIsComplete] = useState(false);
  const [stats, setStats] = useState({ remembered: 0, fuzzy: 0, forgotten: 0 });

  const engine = new DailyReviewEngine();

  useEffect(() => {
    loadReviewItems();
  }, []);

  const loadReviewItems = async () => {
    setIsLoading(true);
    try {
      await engine.init();
      const reviewItems = await engine.generateTodayReview();
      setItems(reviewItems);
    } catch (error) {
      console.error('Failed to load review items:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleFeedback = async (feedback: 'remembered' | 'fuzzy' | 'forgotten') => {
    const currentItem = items[currentIndex];
    if (!currentItem) return;

    // Submit feedback
    await engine.submitFeedback(currentItem.id, feedback);

    // Update stats
    setStats((prev) => ({
      ...prev,
      [feedback]: prev[feedback] + 1,
    }));

    // Move to next
    if (currentIndex < items.length - 1) {
      setCurrentIndex((prev) => prev + 1);
    } else {
      setIsComplete(true);
    }
  };

  const handleSkip = () => {
    if (currentIndex < items.length - 1) {
      setCurrentIndex((prev) => prev + 1);
    } else {
      setIsComplete(true);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="w-8 h-8 border-4 border-purple-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="text-center py-16">
        <div className="text-6xl mb-4">🎉</div>
        <h3 className="text-xl font-semibold">今日无回顾内容</h3>
        <p className="text-gray-500 mt-2">去阅读并添加一些标注吧！</p>
      </div>
    );
  }

  if (isComplete) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="text-center py-16"
      >
        <div className="text-6xl mb-4">✨</div>
        <h3 className="text-xl font-semibold">今日回顾完成！</h3>
        <p className="text-gray-500 mt-2">
          已回顾 {items.length} 条内容
        </p>
        <div className="flex justify-center gap-6 mt-6">
          <StatBadge label="记得" value={stats.remembered} color="green" />
          <StatBadge label="模糊" value={stats.fuzzy} color="yellow" />
          <StatBadge label="忘记" value={stats.forgotten} color="red" />
        </div>
        <button
          onClick={() => {
            setIsComplete(false);
            setCurrentIndex(0);
            setStats({ remembered: 0, fuzzy: 0, forgotten: 0 });
          }}
          className="mt-8 px-6 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600"
        >
          再来一轮
        </button>
      </motion.div>
    );
  }

  const currentItem = items[currentIndex];
  const progress = ((currentIndex + 1) / items.length) * 100;

  return (
    <div className="max-w-2xl mx-auto py-8">
      {/* Progress */}
      <div className="mb-8">
        <div className="flex justify-between text-sm text-gray-500 mb-2">
          <span>今日回顾</span>
          <span>
            {currentIndex + 1} / {items.length}
          </span>
        </div>
        <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-purple-500"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Card */}
      <AnimatePresence mode="wait">
        <motion.div
          key={currentItem.id}
          initial={{ opacity: 0, x: 50 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -50 }}
          className="bg-white rounded-2xl shadow-xl border p-8"
        >
          {/* Source */}
          <div className="flex items-center gap-2 text-sm text-gray-500 mb-6">
            <span>📰</span>
            <span>{currentItem.source.articleTitle}</span>
            {currentItem.source.articleAuthor && (
              <>
                <span>·</span>
                <span>{currentItem.source.articleAuthor}</span>
              </>
            )}
          </div>

          {/* Content */}
          <blockquote className="text-xl leading-relaxed text-gray-800 mb-6 border-l-4 border-purple-500 pl-4">
            "{currentItem.content}"
          </blockquote>

          {/* Context/Comment */}
          {currentItem.context && (
            <div className="bg-gray-50 rounded-lg p-4 mb-6">
              <p className="text-sm text-gray-600">
                <span className="font-medium">你的批注：</span>
                {currentItem.context}
              </p>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3">
            <button
              onClick={() => handleFeedback('remembered')}
              className="flex-1 py-3 bg-green-500 text-white rounded-xl font-medium hover:bg-green-600 transition-colors"
            >
              ✓ 记得
            </button>
            <button
              onClick={() => handleFeedback('fuzzy')}
              className="flex-1 py-3 bg-yellow-500 text-white rounded-xl font-medium hover:bg-yellow-600 transition-colors"
            >
              ~ 模糊
            </button>
            <button
              onClick={() => handleFeedback('forgotten')}
              className="flex-1 py-3 bg-red-500 text-white rounded-xl font-medium hover:bg-red-600 transition-colors"
            >
              ✕ 忘记
            </button>
          </div>

          {/* Skip */}
          <button
            onClick={handleSkip}
            className="w-full mt-3 py-2 text-gray-400 hover:text-gray-600 text-sm"
          >
            跳过此项
          </button>
        </motion.div>
      </AnimatePresence>

      {/* Tips */}
      <p className="text-center text-sm text-gray-400 mt-6">
        💡 诚实反馈帮助算法优化回顾频率
      </p>
    </div>
  );
}

function StatBadge({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: 'green' | 'yellow' | 'red';
}) {
  const colorClasses = {
    green: 'bg-green-100 text-green-700',
    yellow: 'bg-yellow-100 text-yellow-700',
    red: 'bg-red-100 text-red-700',
  };

  return (
    <div className={`px-4 py-2 rounded-lg ${colorClasses[color]}`}>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-sm">{label}</div>
    </div>
  );
}
