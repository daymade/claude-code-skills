import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getArticles } from '@/api'
import { formatDate, getWciLevel, formatNumber } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Link } from 'react-router-dom'
import { ExternalLink, Search, Filter } from 'lucide-react'

export default function Articles() {
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedAuthor, setSelectedAuthor] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('')

  const { data: articles, isLoading } = useQuery({
    queryKey: ['articles', { author: selectedAuthor, category: selectedCategory }],
    queryFn: () => getArticles({ author: selectedAuthor, category: selectedCategory, limit: 100 }),
  })

  const filteredArticles = articles?.data?.filter((article: any) =>
    article.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    article.author.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">文章列表</h1>
        <p className="mt-2 text-muted-foreground">浏览和管理已抓取的文章</p>
      </div>

      {/* Filters */}
      <div className="flex gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="搜索标题或作者..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full rounded-lg border bg-background px-9 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <button className="flex items-center gap-2 rounded-lg border px-4 py-2 hover:bg-accent">
          <Filter className="h-4 w-4" />
          筛选
        </button>
      </div>

      {/* Articles List */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-8 text-center text-muted-foreground">加载中...</div>
          ) : filteredArticles?.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">暂无文章</div>
          ) : (
            <div className="divide-y">
              {filteredArticles?.map((article: any) => {
                const wciInfo = getWciLevel(article.wci_score)
                return (
                  <div
                    key={article.id}
                    className="flex items-center justify-between p-4 hover:bg-accent/50 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <Link
                        to={`/articles/${article.id}`}
                        className="font-medium hover:text-primary line-clamp-1"
                      >
                        {article.title}
                      </Link>
                      <div className="mt-1 flex items-center gap-4 text-sm text-muted-foreground">
                        <span>{article.author}</span>
                        <span>{formatDate(article.publish_time)}</span>
                        {article.category && (
                          <span className="rounded-full bg-secondary px-2 py-0.5 text-xs">
                            {article.category}
                          </span>
                        )}
                        <span className="text-xs">{article.strategy}</span>
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
    </div>
  )
}
