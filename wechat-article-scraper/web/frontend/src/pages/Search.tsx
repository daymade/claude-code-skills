import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { searchArticles } from '@/api'
import { formatDate, getWciLevel } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Link } from 'react-router-dom'
import { Search as SearchIcon, ExternalLink } from 'lucide-react'

export default function Search() {
  const [keyword, setKeyword] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  const { data: results, isLoading } = useQuery({
    queryKey: ['search', searchQuery],
    queryFn: () => searchArticles(searchQuery),
    enabled: searchQuery.length > 0,
  })

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setSearchQuery(keyword)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">全文搜索</h1>
        <p className="mt-2 text-muted-foreground">搜索文章标题和内容</p>
      </div>

      {/* Search Form */}
      <form onSubmit={handleSearch} className="flex gap-4">
        <div className="relative flex-1">
          <SearchIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="输入关键词..."
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            className="w-full rounded-lg border bg-background px-9 py-3 text-base outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <button
          type="submit"
          disabled={isLoading || !keyword.trim()}
          className="rounded-lg bg-primary px-6 py-3 text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {isLoading ? '搜索中...' : '搜索'}
        </button>
      </form>

      {/* Results */}
      {searchQuery && (
        <Card>
          <CardHeader>
            <CardTitle>
              搜索结果: "{searchQuery}"
              {results?.data && (
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  ({results.data.length} 条)
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="py-12 text-center text-muted-foreground">搜索中...</div>
            ) : results?.data?.length === 0 ? (
              <div className="py-12 text-center text-muted-foreground">未找到相关文章</div>
            ) : (
              <div className="space-y-4">
                {results?.data?.map((article: any) => {
                  const wciInfo = getWciLevel(article.wci_score)
                  return (
                    <div
                      key={article.id}
                      className="flex items-start justify-between rounded-lg border p-4 hover:bg-accent/50 transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <Link
                          to={`/articles/${article.id}`}
                          className="font-medium hover:text-primary line-clamp-1"
                        >
                          {article.title}
                        </Link>
                        <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                          {article.content?.substring(0, 200)}...
                        </p>
                        <div className="mt-2 flex items-center gap-4 text-sm text-muted-foreground">
                          <span>{article.author}</span>
                          <span>{formatDate(article.publish_time)}</span>
                          {article.category && (
                            <span className="rounded-full bg-secondary px-2 py-0.5 text-xs">
                              {article.category}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-4 ml-4">
                        {article.wci_score && (
                          <span
                            className={`rounded-full px-2 py-1 text-xs text-white ${wciInfo.color}`}
                          >
                            {article.wci_score}
                          </span>
                        )}
                        <a
                          href={article.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-muted-foreground hover:text-primary"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
