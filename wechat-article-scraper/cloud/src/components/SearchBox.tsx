'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import DOMPurify from 'dompurify';

interface SearchSuggestion {
  suggestion: string;
  type: 'tag' | 'author' | 'recent';
  count?: number;
}

interface SearchBoxProps {
  onSearch?: (query: string, results: SearchResult[]) => void;
  onResultClick?: (result: SearchResult) => void;
  placeholder?: string;
  autoFocus?: boolean;
  showInlineResults?: boolean;
}

interface SearchResult {
  id: string;
  title: string;
  content: string;
  author: string;
  url: string;
  tags: string[];
  summary?: string;
  rank: number;
  matchType: 'keyword' | 'semantic' | 'hybrid';
  highlightedTitle: string;
  highlightedContent: string;
  createdAt: string;
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

export function SearchBox({
  onSearch,
  onResultClick,
  placeholder = '搜索文章、作者、标签...',
  autoFocus = false,
  showInlineResults = true,
}: SearchBoxProps) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch suggestions
  const fetchSuggestions = useCallback(async (prefix: string) => {
    if (prefix.length < 2) {
      setSuggestions([]);
      return;
    }

    try {
      const response = await fetch(`/api/search?suggestions&q=${encodeURIComponent(prefix)}&limit=10`);
      if (response.ok) {
        const data = await response.json();
        setSuggestions(data.suggestions || []);
      }
    } catch (error) {
      console.error('Failed to fetch suggestions:', error);
    }
  }, []);

  // Debounced suggestions
  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    debounceRef.current = setTimeout(() => {
      if (query.length >= 2) {
        fetchSuggestions(query);
      } else {
        setSuggestions([]);
      }
    }, 150);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [query, fetchSuggestions]);

  // Handle search
  const performSearch = useCallback(async (searchQuery: string) => {
    if (searchQuery.length < 2) return;

    setLoading(true);
    setShowSuggestions(false);

    try {
      const response = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: searchQuery,
          limit: 20,
          semantic: true,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setResults(data.results || []);
        onSearch?.(searchQuery, data.results || []);
      }
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setLoading(false);
    }
  }, [onSearch]);

  // Handle key navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    const totalItems = suggestions.length + (query.length >= 2 ? 1 : 0);

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex((prev) =>
          prev < totalItems - 1 ? prev + 1 : prev
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex((prev) => (prev > -1 ? prev - 1 : -1));
        break;
      case 'Enter':
        e.preventDefault();
        if (selectedIndex >= 0 && selectedIndex < suggestions.length) {
          const suggestion = suggestions[selectedIndex];
          setQuery(suggestion.suggestion);
          performSearch(suggestion.suggestion);
        } else {
          performSearch(query);
        }
        break;
      case 'Escape':
        setShowSuggestions(false);
        setSelectedIndex(-1);
        inputRef.current?.blur();
        break;
    }
  };

  // Get suggestion icon
  const getSuggestionIcon = (type: SearchSuggestion['type']) => {
    switch (type) {
      case 'tag':
        return '🏷️';
      case 'author':
        return '✍️';
      case 'recent':
        return '🕐';
      default:
        return '🔍';
    }
  };

  return (
    <div className="relative w-full max-w-3xl mx-auto">
      {/* Search Input */}
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setShowSuggestions(true);
            setSelectedIndex(-1);
          }}
          onFocus={() => setShowSuggestions(true)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          autoFocus={autoFocus}
          className="w-full px-5 py-4 pl-12 pr-20 text-lg bg-white border border-gray-200 rounded-2xl shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
        />
        <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-xl">
          🔍
        </span>

        {/* Clear/Search Button */}
        <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2">
          {query && (
            <button
              onClick={() => {
                setQuery('');
                setResults([]);
                inputRef.current?.focus();
              }}
              className="p-1 text-gray-400 hover:text-gray-600 rounded-full hover:bg-gray-100"
            >
              ✕
            </button>
          )}
          <button
            onClick={() => performSearch(query)}
            disabled={loading || query.length < 2}
            className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? '搜索中...' : '搜索'}
          </button>
        </div>
      </div>

      {/* Suggestions Dropdown */}
      {showSuggestions && suggestions.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-2 bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden z-50">
          {query.length >= 2 && (
            <button
              onClick={() => performSearch(query)}
              className={`w-full px-4 py-3 text-left flex items-center gap-3 hover:bg-gray-50 transition-colors ${
                selectedIndex === 0 ? 'bg-blue-50' : ''
              }`}
            >
              <span>🔍</span>
              <span className="flex-1">搜索 &quot;{query}&quot;</span>
            </button>
          )}

          {suggestions.map((suggestion, index) => {
            const actualIndex = query.length >= 2 ? index + 1 : index;
            return (
              <button
                key={`${suggestion.type}-${suggestion.suggestion}`}
                onClick={() => {
                  setQuery(suggestion.suggestion);
                  performSearch(suggestion.suggestion);
                }}
                className={`w-full px-4 py-3 text-left flex items-center gap-3 hover:bg-gray-50 transition-colors ${
                  selectedIndex === actualIndex ? 'bg-blue-50' : ''
                }`}
              >
                <span>{getSuggestionIcon(suggestion.type)}</span>
                <span className="flex-1">{suggestion.suggestion}</span>
                <span className="text-xs text-gray-400">
                  {suggestion.type === 'tag' && '标签'}
                  {suggestion.type === 'author' && '作者'}
                  {suggestion.type === 'recent' && '最近'}
                </span>
                {suggestion.count && (
                  <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                    {suggestion.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Inline Results */}
      {showInlineResults && results.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-2 bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden z-40 max-h-96 overflow-y-auto">
          <div className="p-3 bg-gray-50 border-b border-gray-200 text-sm text-gray-600 flex items-center justify-between">
            <span>找到 {results.length} 个结果</span>
            <span className="text-xs">按回车查看全部</span>
          </div>

          {results.slice(0, 5).map((result) => (
            <div
              key={result.id}
              onClick={() => {
                onResultClick?.(result);
                router.push(`/articles/${result.id}`);
              }}
              className="px-4 py-3 border-b border-gray-100 last:border-0 hover:bg-gray-50 cursor-pointer transition-colors"
            >
              <div className="flex items-start gap-3">
                <span className="text-2xl">📄</span>
                <div className="flex-1 min-w-0">
                  <h4 className="font-medium text-gray-900 line-clamp-1">
                    <HighlightedText html={result.highlightedTitle || result.title} />
                  </h4>
                  <p className="text-sm text-gray-600 mt-1 line-clamp-2">
                    <HighlightedText html={result.highlightedContent} />
                  </p>
                  <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                    <span>{result.author || '未知作者'}</span>
                    <span>·</span>
                    <span
                      className={`px-1.5 py-0.5 rounded ${
                        result.matchType === 'keyword'
                          ? 'bg-blue-100 text-blue-700'
                          : result.matchType === 'semantic'
                          ? 'bg-purple-100 text-purple-700'
                          : 'bg-green-100 text-green-700'
                      }`}
                    >
                      {result.matchType === 'keyword'
                        ? '关键词'
                        : result.matchType === 'semantic'
                        ? '语义'
                        : '混合'}
                    </span>
                    {result.tags.slice(0, 3).map((tag) => (
                      <span key={tag} className="text-blue-600">
                        #{tag}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ))}

          {results.length > 5 && (
            <button
              onClick={() => router.push(`/search?q=${encodeURIComponent(query)}`)}
              className="w-full py-3 text-center text-blue-600 hover:bg-blue-50 text-sm font-medium"
            >
              查看全部 {results.length} 个结果 →
            </button>
          )}
        </div>
      )}

      {/* Click outside to close */}
      {showSuggestions && (suggestions.length > 0 || results.length > 0) && (
        <div
          className="fixed inset-0 z-30"
          onClick={() => setShowSuggestions(false)}
        />
      )}
    </div>
  );
}
