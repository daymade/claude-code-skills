/**
 * Serendipity Explorer - 随机漫步发现
 *
 * 让用户重新发现过往的内容
 * 类似 Obsidian 的图谱漫游，但更简单直接
 */

import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AnnotationStore, Annotation } from '@/lib/annotation-engine';

interface SerendipityItem {
  annotation: Annotation;
  relatedAnnotations: Annotation[];
  connectionReason: string;
}

export function SerendipityExplorer() {
  const [item, setItem] = useState<SerendipityItem | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [history, setHistory] = useState<string[]>([]);

  const discoverNew = useCallback(async () => {
    setIsLoading(true);
    try {
      const store = new AnnotationStore();
      await store.init();

      // Get all annotations
      const allAnnotations = await store.getAllAnnotations();

      if (allAnnotations.length === 0) {
        setItem(null);
        return;
      }

      // Filter out recently shown
      const candidates = allAnnotations.filter(
        (a) => !history.includes(a.id)
      );

      const pool = candidates.length > 0 ? candidates : allAnnotations;

      // Pick random annotation
      const randomAnnotation = pool[Math.floor(Math.random() * pool.length)];

      // Find related annotations by tag similarity
      const related = allAnnotations
        .filter(
          (a) =>
            a.id !== randomAnnotation.id &&
            a.articleId === randomAnnotation.articleId
        )
        .slice(0, 2);

      setItem({
        annotation: randomAnnotation,
        relatedAnnotations: related,
        connectionReason: '来自同一篇文章',
      });

      // Add to history
      setHistory((prev) => [...prev.slice(-9), randomAnnotation.id]);
    } catch (error) {
      console.error('Failed to discover:', error);
    } finally {
      setIsLoading(false);
    }
  }, [history]);

  useEffect(() => {
    discoverNew();
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-4 border-purple-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!item) {
    return (
      <div className="text-center py-16">
        <div className="text-6xl mb-4">🔮</div>
        <h3 className="text-xl font-semibold">暂无内容可发现</h3>
        <p className="text-gray-500 mt-2">添加更多标注后，这里会显示随机发现</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold">✨ 随机发现</h2>
          <p className="text-sm text-gray-500">重新发现过去的想法</p>
        </div>
        <button
          onClick={discoverNew}
          disabled={isLoading}
          className="px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 disabled:opacity-50"
        >
          🎲 下一个
        </button>
      </div>

      {/* Main Card */}
      <AnimatePresence mode="wait">
        <motion.div
          key={item.annotation.id}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          className="bg-white rounded-2xl shadow-xl border overflow-hidden"
        >
          {/* Article Header */}
          <div className="bg-gradient-to-r from-purple-500 to-pink-500 p-4 text-white">
            <h3 className="font-semibold">{item.annotation.articleTitle}</h3>
            <p className="text-sm text-white/80">
              {new Date(item.annotation.createdAt).toLocaleDateString('zh-CN')}
            </p>
          </div>

          {/* Content */}
          <div className="p-6">
            <blockquote className="text-lg leading-relaxed text-gray-800 border-l-4 border-purple-500 pl-4 mb-4">
              "{item.annotation.quote}"
            </blockquote>

            {item.annotation.comment && (
              <div className="bg-gray-50 rounded-lg p-4 mb-4">
                <p className="text-sm text-gray-600">
                  <span className="font-medium">当时的想法：</span>
                  {item.annotation.comment}
                </p>
              </div>
            )}

            {/* Tags */}
            {item.annotation.tags && item.annotation.tags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {item.annotation.tags.map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-1 bg-purple-100 text-purple-700 text-xs rounded-full"
                  >
                    #{tag}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Related Section */}
          {item.relatedAnnotations.length > 0 && (
            <div className="border-t p-4">
              <p className="text-sm text-gray-500 mb-3">{item.connectionReason}</p>
              <div className="space-y-3">
                {item.relatedAnnotations.map((related) => (
                  <div
                    key={related.id}
                    className="p-3 bg-gray-50 rounded-lg text-sm"
                  >
                    <p className="line-clamp-2">"{related.quote}"</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="border-t p-4 flex gap-3">
            <button className="flex-1 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600">
              重新阅读文章
            </button>
            <button className="flex-1 py-2 border border-gray-300 rounded-lg hover:bg-gray-50">
              添加到回顾
            </button>
          </div>
        </motion.div>
      </AnimatePresence>

      {/* History Dots */}
      {history.length > 1 && (
        <div className="flex justify-center gap-2 mt-6">
          {history.slice(-5).map((id, i) => (
            <div
              key={id}
              className={`w-2 h-2 rounded-full ${
                i === history.slice(-5).length - 1
                  ? 'bg-purple-500'
                  : 'bg-gray-300'
              }`}
            />
          ))}
        </div>
      )}

      {/* Tip */}
      <p className="text-center text-sm text-gray-400 mt-6">
        💡 随机发现帮助你重新连接过去的想法
      </p>
    </div>
  );
}
