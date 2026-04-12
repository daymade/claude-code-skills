'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import DOMPurify from 'dompurify';
import {
  TextSelectionManager,
  AnnotationStore,
  Annotation,
  ReadingProgressTracker,
} from '@/lib/annotation-engine';
import { Article } from '@/types/supabase';

interface ReaderProps {
  article: Article;
  userId: string;
  onExit?: () => void;
}

type Theme = 'light' | 'sepia' | 'dark';
type FontSize = 'small' | 'medium' | 'large' | 'xlarge';

const themeConfig = {
  light: {
    bg: 'bg-white',
    text: 'text-gray-900',
    highlight: {
      yellow: 'bg-yellow-200',
      green: 'bg-green-200',
      blue: 'bg-blue-200',
      pink: 'bg-pink-200',
      purple: 'bg-purple-200',
    },
  },
  sepia: {
    bg: 'bg-[#f4ecd8]',
    text: 'text-[#5b4636]',
    highlight: {
      yellow: 'bg-[#e8d4a8]',
      green: 'bg-[#c8d4a8]',
      blue: 'bg-[#a8c4d4]',
      pink: 'bg-[#d4a8c8]',
      purple: 'bg-[#c8a8d4]',
    },
  },
  dark: {
    bg: 'bg-gray-900',
    text: 'text-gray-100',
    highlight: {
      yellow: 'bg-yellow-900/50',
      green: 'bg-green-900/50',
      blue: 'bg-blue-900/50',
      pink: 'bg-pink-900/50',
      purple: 'bg-purple-900/50',
    },
  },
};

const fontSizeConfig = {
  small: 'text-base leading-relaxed',
  medium: 'text-lg leading-relaxed',
  large: 'text-xl leading-loose',
  xlarge: 'text-2xl leading-loose',
};

export function Reader({ article, userId, onExit }: ReaderProps) {
  const [theme, setTheme] = useState<Theme>('light');
  const [fontSize, setFontSize] = useState<FontSize>('medium');
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [selectedText, setSelectedText] = useState('');
  const [showToolbar, setShowToolbar] = useState(false);
  const [toolbarPosition, setToolbarPosition] = useState({ x: 0, y: 0 });
  const [showAnnotationPanel, setShowAnnotationPanel] = useState(false);
  const [activeAnnotation, setActiveAnnotation] = useState<Annotation | null>(null);
  const [comment, setComment] = useState('');
  const [readingProgress, setReadingProgress] = useState(0);
  const [timeSpent, setTimeSpent] = useState(0);
  const [showStats, setShowStats] = useState(false);

  const contentRef = useRef<HTMLDivElement>(null);
  const selectionManager = useRef<TextSelectionManager | null>(null);
  const annotationStore = useRef<AnnotationStore | null>(null);
  const progressTracker = useRef<ReadingProgressTracker | null>(null);

  // Sanitize HTML content
  const sanitizedContent = DOMPurify.sanitize(article.content || '', {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote', 'img', 'a', 'div', 'span'],
    ALLOWED_ATTR: ['src', 'alt', 'href', 'title', 'class', 'id'],
  });

  // Initialize
  useEffect(() => {
    annotationStore.current = new AnnotationStore();
    annotationStore.current.init().then(() => {
      loadAnnotations();
    });

    progressTracker.current = new ReadingProgressTracker(
      article.id,
      userId,
      (progress) => setReadingProgress(progress)
    );

    const timer = setInterval(() => {
      if (progressTracker.current) {
        setTimeSpent(progressTracker.current.getTimeSpent());
      }
    }, 1000);

    return () => clearInterval(timer);
  }, [article.id, userId]);

  // Setup text selection
  useEffect(() => {
    selectionManager.current = new TextSelectionManager((range) => {
      if (range) {
        const text = range.toString().trim();
        if (text.length > 0) {
          setSelectedText(text);
          const rect = range.getBoundingClientRect();
          setToolbarPosition({
            x: rect.left + rect.width / 2,
            y: rect.top - 50,
          });
          setShowToolbar(true);
        }
      } else {
        setShowToolbar(false);
      }
    });

    return () => selectionManager.current?.destroy();
  }, []);

  const loadAnnotations = async () => {
    if (!annotationStore.current) return;
    const loaded = await annotationStore.current.getAnnotationsByArticle(article.id);
    setAnnotations(loaded);
    applyAnnotationsToDOM(loaded);
  };

  const applyAnnotationsToDOM = (annos: Annotation[]) => {
    // Clear existing highlights
    document.querySelectorAll('.annotation-highlight').forEach((el) => {
      const parent = el.parentNode;
      if (parent) {
        parent.replaceChild(document.createTextNode(el.textContent || ''), el);
        parent.normalize();
      }
    });

    // Apply new highlights
    annos.forEach((anno) => {
      highlightText(anno.quote, anno.color, anno.id);
    });
  };

  const highlightText = (text: string, color: string, id: string) => {
    if (!contentRef.current) return;

    const walker = document.createTreeWalker(
      contentRef.current,
      NodeFilter.SHOW_TEXT,
      null,
      false
    );

    const textNodes: Text[] = [];
    let node;
    while ((node = walker.nextNode())) {
      if (node.textContent?.includes(text)) {
        textNodes.push(node as Text);
      }
    }

    textNodes.forEach((textNode) => {
      const span = document.createElement('span');
      span.className = `annotation-highlight ${themeConfig[theme].highlight[color as keyof typeof themeConfig.light.highlight]}`;
      span.dataset.annotationId = id;
      span.style.cursor = 'pointer';
      span.onclick = () => handleHighlightClick(id);

      const parent = textNode.parentNode;
      if (parent) {
        const content = textNode.textContent || '';
        const index = content.indexOf(text);
        if (index >= 0) {
          const before = document.createTextNode(content.substring(0, index));
          const after = document.createTextNode(content.substring(index + text.length));
          span.textContent = text;

          parent.insertBefore(before, textNode);
          parent.insertBefore(span, textNode);
          parent.insertBefore(after, textNode);
          parent.removeChild(textNode);
        }
      }
    });
  };

  const handleHighlightClick = async (id: string) => {
    if (!annotationStore.current) return;
    const anno = annotations.find((a) => a.id === id);
    if (anno) {
      setActiveAnnotation(anno);
      setComment(anno.comment || '');
      setShowAnnotationPanel(true);
    }
  };

  const createAnnotation = async (color: Annotation['color']) => {
    if (!selectionManager.current || !annotationStore.current) return;

    const anno = selectionManager.current.createAnnotationFromSelection(
      article.id,
      userId,
      color,
      comment,
      []
    );

    if (anno) {
      await annotationStore.current.saveAnnotation(anno);
      setAnnotations([...annotations, anno]);
      applyAnnotationsToDOM([...annotations, anno]);
      setShowToolbar(false);
      setComment('');

      window.getSelection()?.removeAllRanges();
    }
  };

  const updateAnnotation = async () => {
    if (!activeAnnotation || !annotationStore.current) return;

    const updated = { ...activeAnnotation, comment, updatedAt: new Date().toISOString() };
    await annotationStore.current.saveAnnotation(updated);
    setAnnotations(annotations.map((a) => (a.id === updated.id ? updated : a)));
    setShowAnnotationPanel(false);
    setActiveAnnotation(null);
    setComment('');
  };

  const deleteAnnotation = async () => {
    if (!activeAnnotation || !annotationStore.current) return;

    await annotationStore.current.deleteAnnotation(activeAnnotation.id);
    setAnnotations(annotations.filter((a) => a.id !== activeAnnotation.id));
    applyAnnotationsToDOM(annotations.filter((a) => a.id !== activeAnnotation.id));
    setShowAnnotationPanel(false);
    setActiveAnnotation(null);
  };

  const exportAnnotations = async () => {
    if (!annotationStore.current) return;

    const data = await annotationStore.current.exportForReadwise();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `annotations-${article.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className={`min-h-screen ${themeConfig[theme].bg} ${themeConfig[theme].text} transition-colors duration-300`}>
      {/* Top Bar */}
      <header className="sticky top-0 z-50 backdrop-blur-md bg-opacity-90 border-b border-gray-200/20">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between">
          <button
            onClick={onExit}
            className="p-2 rounded-lg hover:bg-gray-200/20 transition-colors"
          >
            ← 返回
          </button>

          <div className="flex items-center gap-4">
            <div className="hidden sm:flex items-center gap-2 text-sm opacity-60">
              <span>{readingProgress}%</span>
              <div className="w-20 h-1 bg-gray-300 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 transition-all duration-300"
                  style={{ width: `${readingProgress}%` }}
                />
              </div>
            </div>

            <button
              onClick={() => setShowStats(!showStats)}
              className="p-2 rounded-lg hover:bg-gray-200/20 transition-colors text-sm"
            >
              ⏱ {formatTime(timeSpent)}
            </button>

            <button
              onClick={() => setShowAnnotationPanel(!showAnnotationPanel)}
              className="p-2 rounded-lg hover:bg-gray-200/20 transition-colors relative"
            >
              📝
              {annotations.length > 0 && (
                <span className="absolute -top-1 -right-1 w-5 h-5 bg-blue-500 text-white text-xs rounded-full flex items-center justify-center">
                  {annotations.length}
                </span>
              )}
            </button>

            <div className="flex items-center gap-2">
              <select
                value={theme}
                onChange={(e) => setTheme(e.target.value as Theme)}
                className="px-2 py-1 rounded bg-gray-200/20 text-sm"
              >
                <option value="light">☀️ 白天</option>
                <option value="sepia">📜 护眼</option>
                <option value="dark">🌙 夜间</option>
              </select>

              <select
                value={fontSize}
                onChange={(e) => setFontSize(e.target.value as FontSize)}
                className="px-2 py-1 rounded bg-gray-200/20 text-sm"
              >
                <option value="small">小</option>
                <option value="medium">中</option>
                <option value="large">大</option>
                <option value="xlarge">特大</option>
              </select>
            </div>
          </div>
        </div>
      </header>

      {/* Reading Stats Panel */}
      <AnimatePresence>
        {showStats && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-16 left-1/2 -translate-x-1/2 z-40 bg-white dark:bg-gray-800 rounded-xl shadow-lg p-4 min-w-[300px]"
          >
            <h3 className="font-semibold mb-3">阅读统计</h3>
            {progressTracker.current && (
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="opacity-60">阅读进度</span>
                  <span>{readingProgress}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="opacity-60">阅读时长</span>
                  <span>{formatTime(timeSpent)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="opacity-60">标注数量</span>
                  <span>{annotations.length}</span>
                </div>
                {(() => {
                  const summary = progressTracker.current!.generateSessionSummary();
                  return (
                    <>
                      <div className="flex justify-between">
                        <span className="opacity-60">文章字数</span>
                        <span>{summary.articleWordCount.toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="opacity-60">阅读速度</span>
                        <span>{summary.wordsPerMinute} 字/分</span>
                      </div>
                    </>
                  );
                })()}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Selection Toolbar */}
      <AnimatePresence>
        {showToolbar && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            style={{
              position: 'fixed',
              left: toolbarPosition.x,
              top: toolbarPosition.y,
              transform: 'translateX(-50%)',
              zIndex: 100,
            }}
            className="bg-gray-900 text-white rounded-lg shadow-xl p-2 flex items-center gap-1"
          >
            {(['yellow', 'green', 'blue', 'pink', 'purple'] as const).map((color) => (
              <button
                key={color}
                onClick={() => createAnnotation(color)}
                className={`w-8 h-8 rounded-full ${themeConfig.light.highlight[color]} hover:scale-110 transition-transform`}
                title={`高亮 - ${color}`}
              />
            ))}
            <div className="w-px h-6 bg-gray-700 mx-1" />
            <button
              onClick={() => setShowAnnotationPanel(true)}
              className="px-3 py-1 text-sm hover:bg-gray-700 rounded"
            >
              批注
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main Content */}
      <main className="max-w-3xl mx-auto px-4 py-8">
        <header className="mb-8">
          <h1 className={`font-bold mb-4 ${fontSize === 'xlarge' ? 'text-3xl' : 'text-2xl'}`}>
            {article.title}
          </h1>
          <div className="flex items-center gap-4 text-sm opacity-60">
            <span>{article.author}</span>
            <span>·</span>
            <span>{new Date(article.publish_time || article.created_at).toLocaleDateString('zh-CN')}</span>
            {article.read_count && (
              <>
                <span>·</span>
                <span>👁 {article.read_count.toLocaleString()}</span>
              </>
            )}
          </div>
        </header>

        <article
          ref={contentRef}
          className={`prose prose-lg max-w-none ${fontSizeConfig[fontSize]} ${
            theme === 'dark' ? 'prose-invert' : ''
          }`}
          dangerouslySetInnerHTML={{ __html: sanitizedContent }}
        />
      </main>

      {/* Annotation Panel */}
      <AnimatePresence>
        {showAnnotationPanel && (
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            className="fixed right-0 top-0 bottom-0 w-80 bg-white dark:bg-gray-800 shadow-xl z-50 overflow-y-auto"
          >
            <div className="p-4 border-b flex items-center justify-between">
              <h2 className="font-semibold">标注 ({annotations.length})</h2>
              <div className="flex gap-2">
                <button
                  onClick={exportAnnotations}
                  className="text-sm text-blue-500 hover:underline"
                >
                  导出
                </button>
                <button
                  onClick={() => setShowAnnotationPanel(false)}
                  className="text-2xl leading-none"
                >
                  ×
                </button>
              </div>
            </div>

            <div className="p-4 space-y-4">
              {activeAnnotation ? (
                <div className="space-y-4">
                  <div
                    className={`p-3 rounded ${themeConfig[theme].highlight[activeAnnotation.color]} text-sm`}
                  >
                    {activeAnnotation.quote}
                  </div>
                  <textarea
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="添加批注..."
                    className="w-full p-3 border rounded-lg resize-none h-32 dark:bg-gray-700 dark:border-gray-600"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={updateAnnotation}
                      className="flex-1 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600"
                    >
                      保存
                    </button>
                    <button
                      onClick={deleteAnnotation}
                      className="px-4 py-2 text-red-500 hover:bg-red-50 rounded-lg"
                    >
                      删除
                    </button>
                    <button
                      onClick={() => {
                        setActiveAnnotation(null);
                        setComment('');
                      }}
                      className="px-4 py-2 text-gray-500 hover:bg-gray-100 rounded-lg"
                    >
                      取消
                    </button>
                  </div>
                </div>
              ) : (
                annotations.map((anno) => (
                  <div
                    key={anno.id}
                    onClick={() => {
                      setActiveAnnotation(anno);
                      setComment(anno.comment || '');
                    }}
                    className="p-3 border rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                  >
                    <div
                      className={`text-sm mb-2 ${themeConfig[theme].highlight[anno.color]} px-2 py-1 rounded`}
                    >
                      {anno.quote.substring(0, 100)}
                      {anno.quote.length > 100 && '...'}
                    </div>
                    {anno.comment && (
                      <p className="text-sm opacity-70">{anno.comment}</p>
                    )}
                    <div className="text-xs opacity-40 mt-2">
                      {new Date(anno.createdAt).toLocaleString('zh-CN')}
                    </div>
                  </div>
                ))
              )}

              {annotations.length === 0 && !activeAnnotation && (
                <div className="text-center py-8 opacity-50">
                  <p>暂无标注</p>
                  <p className="text-sm mt-2">选中文字添加高亮和批注</p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
