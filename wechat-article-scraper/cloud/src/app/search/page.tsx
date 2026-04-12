'use client';

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import DOMPurify from 'dompurify';

interface SearchResult {
  id: string;
  title: string;
  content: string;
  author: string;
  url: string;
  tags: string[];
  summary?: string;
  keywords: string[];
  rank: number;
  matchType: 'keyword' | 'semantic' | 'hybrid';
  highlightedTitle: string;
  highlightedContent: string;
  createdAt: string;
}

interface FilterState {
  matchTypes: ('keyword' | 'semantic' | 'hybrid')[];
  tags: string[];
  author?: string;
  dateRange?: 'day' | 'week' | 'month' | 'year' | 'all';
}

/**
 * Render text with <mark> tags as React elements
 * Parses HTML and safely renders only allowed elements
 */
function HighlightedText({ html }: { html: string }) {
  // Sanitize first
  const sanitized = DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['mark'],
    ALLOWED_ATTR: [],
  });

  // Parse and render
  const parser = new DOMParser();
  const doc = parser.parseFromString(sanitized, 'text/html');
  const elements: React.ReactNode[] = [];

  doc.body.childNodes.forEach((node, index) => {
    if (node.nodeName === 'MARK') {
      elements.push(
        <mark key={index} className="bg-yellow-200 text-yellow-900">
          {node.textContent}
        </mark>
      );
    } else {
      elements.push(<span key={index}>{node.textContent}</span>);
    }
  });

  return <>{elements}</>;
}

export default function SearchPage() {
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get('q') || '';

  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [filters, setFilters] = useState<FilterState>({
    matchTypes: ['keyword', 'semantic', 'hybrid'],
    tags: [],
    dateRange: 'all',
  });
  const [showFilters, setShowFilters] = useState(false);

  const performSearch = useCallback(async (searchQuery: string, pageNum: number = 0) => {
    if (!searchQuery || searchQuery.length < 2) return;

    setLoading(true);

    try {
      const response = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: searchQuery,
          limit: 20,
          offset: pageNum * 20,
          semantic: filters.matchTypes.includes('semantic'),
          filters: {
            tags: filters.tags.length > 0 ? filters.tags : undefined,
            dateRange: filters.dateRange !== 'all' ? filters.dateRange : undefined,
          },
        }),
      });

      if (response.ok) {
        const data = await response.json();
        if (pageNum === 0) {
          setResults(data.results || []);
        } else {
          setResults((prev) => [...prev, ...(data.results || [])]);
        }
        setTotal(data.total || 0);
        setHasMore(data.hasMore || false);
      }
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  // Search when query changes
  useEffect(() => {
    if (initialQuery) {
      performSearch(initialQuery, 0);
    }
  }, [initialQuery, performSearch]);

  // Handle search submit
  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(0);
    performSearch(query, 0);
    // Update URL
    window.history.pushState({}, '', `/search?q=${encodeURIComponent(query)}`);
  };

  // Load more
  const loadMore = () => {
    const nextPage = page + 1;
    setPage(nextPage);
    performSearch(query, nextPage);
  };

  // Format date
  const formatDate = (date: string) => {
    return new Date(date).toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  // Get match type badge
  const getMatchBadge = (type: SearchResult['matchType']) => {
    const config = {
      keyword: { label: '关键词匹配', class: 'bg-blue-100 text-blue-700' },
      semantic: { label: '语义匹配', class: 'bg-purple-100 text-purple-700' },
      hybrid: { label: '混合匹配', class: 'bg-green-100 text-green-700' },
    };
    const { label, class: className } = config[type];
    return <span className={`px-2 py-0.5 rounded-full text-xs ${className}`}>{label}</span>;
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-6">
          <div className="flex items-center gap-4 mb-4">
            <Link href="/" className="text-gray-500 hover:text-gray-900">
              ← 返回
            </Link>
            <h1 className="text-xl font-semibold">搜索结果</h1>
          </div>

          {/* Search Form */}
          <form onSubmit={handleSearch} className="relative">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索文章、作者、标签..."
              className="w-full px-5 py-3 pl-12 pr-24 text-lg bg-gray-100 border-0 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition-all"
            />
            <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-xl">🔍</span>
            <button
              type="submit"
              disabled={loading || query.length < 2}
              className="absolute right-3 top-1/2 -translate-y-1/2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? '搜索中...' : '搜索'}
            </button>
          </form>

          {/* Filter Bar */}
          <div className="flex items-center justify-between mt-4">
            <div className="flex items-center gap-4">
              <span className="text-sm text-gray-600">
                找到 <span className="font-semibold text-gray-900">{total}</span> 个结果
              </span>
              {query && (
                <span className="text-sm text-gray-500">
                  搜索: &quot;{query}&quot;
                </span>
              )}
            </div>
            <button
              onClick={() => setShowFilters(!showFilters)}
              className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
            >
              <span>筛选</span>
              <span>{showFilters ? '▲' : '▼'}</span>
            </button>
          </div>

          {/* Filters Panel */}
          {showFilters && (
            <div className="mt-4 p-4 bg-gray-50 rounded-xl">
              <div className="space-y-4">
                {/* Match Type Filter */}
                <div>
                  <span className="text-sm font-medium text-gray-700">匹配类型:</span>
                  <div className="flex gap-2 mt-2">
                    {(['keyword', 'semantic', 'hybrid'] as const).map((type) => (
                      <button
                        key={type}
                        onClick={() => {
                          setFilters((prev) => ({
                            ...prev,
                            matchTypes: prev.matchTypes.includes(type)
                              ? prev.matchTypes.filter((t) => t !== type)
                              : [...prev.matchTypes, type],
                          }));
                        }}
                        className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                          filters.matchTypes.includes(type)
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-white text-gray-600 border border-gray-200'
                        }`}
                      >
                        {type === 'keyword' && '关键词'}
                        {type === 'semantic' && '语义'}
                        {type === 'hybrid' && '混合'}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Date Range Filter */}
                <div>
                  <span className="text-sm font-medium text-gray-700">时间范围:</span>
                  <div className="flex gap-2 mt-2">
                    {([
                      { value: 'all', label: '全部' },
                      { value: 'day', label: '今天' },
                      { value: 'week', label: '本周' },
                      { value: 'month', label: '本月' },
                      { value: 'year', label: '今年' },
                    ] as const).map(({ value, label }) => (
                      <button
                        key={value}
                        onClick={() => setFilters((prev) => ({ ...prev, dateRange: value }))}
                        className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                          filters.dateRange === value
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-white text-gray-600 border border-gray-200'
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Results */}
      <div className="max-w-5xl mx-auto px-4 py-8">
        {results.length === 0 && !loading && query.length >= 2 && (
          <div className="text-center py-20">
            <div className="text-6xl mb-4">🔍</div>
            <h2 className="text-lg font-medium text-gray-900">未找到结果</h2>
            <p className="text-gray-500 mt-2">尝试使用不同的关键词或检查拼写</p>
          </div>
        )}

        <div className="space-y-4">
          {results.map((result) => (
            <Link
              key={result.id}
              href={`/articles/${result.id}`}
              className="block bg-white rounded-xl p-6 border border-gray-200 hover:shadow-md hover:border-blue-300 transition-all"
            >
              <div className="flex items-start gap-4">
                <div className="flex-1 min-w-0">
                  {/* Title */}
                  <h2 className="text-lg font-semibold text-gray-900 mb-2">
                    <HighlightedText html={result.highlightedTitle || result.title} />
                  </h2>

                  {/* Meta */}
                  <div className="flex items-center gap-3 text-sm text-gray-500 mb-3">
                    <span className="font-medium text-blue-600">{result.author || '未知作者'}</span>
                    <span>·</span>
                    <span>{formatDate(result.createdAt)}</span>
                    <span>·</span>
                    {getMatchBadge(result.matchType)}
                  </div>

                  {/* Summary */}
                  {result.summary && (
                    <p className="text-sm text-gray-600 mb-3 line-clamp-2">{result.summary}</p>
                  )}

                  {/* Highlighted Content */}
                  <p className="text-sm text-gray-700 line-clamp-3">
                    <HighlightedText html={result.highlightedContent} />
                  </p>

                  {/* Tags */}
                  {result.tags.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-4">
                      {result.tags.map((tag) => (
                        <span
                          key={tag}
                          className="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded-full hover:bg-blue-100 hover:text-blue-600 transition-colors"
                        >
                          #{tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </Link>
          ))}
        </div>

        {/* Load More */}
        {hasMore && (
          <div className="text-center mt-8">
            <button
              onClick={loadMore}
              disabled={loading}
              className="px-6 py-3 bg-white border border-gray-200 text-gray-700 rounded-xl hover:bg-gray-50 disabled:opacity-50 transition-colors"
            >
              {loading ? '加载中...' : '加载更多'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
