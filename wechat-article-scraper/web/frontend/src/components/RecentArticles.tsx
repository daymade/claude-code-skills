import { useQuery } from '@tanstack/react-query'
import { getArticles } from '@/api'
import { formatDate, getWciLevel, formatNumber } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Link } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'

export default function RecentArticles() {
  const { data: articles, isLoading } = useQuery({
    queryKey: ['articles', { limit: 5 }],
    queryFn: () => getArticles({ limit: 5 }),
  })

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>最近文章</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-muted-foreground">加载中...</div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>最近文章</CardTitle>
        <Link
          to="/articles"
          className="text-sm text-primary hover:underline"
        >
          查看全部 →
        </Link>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {articles?.data?.map((article) => {
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
                  <div className="mt-1 flex items-center gap-4 text-sm text-muted-foreground">
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
                      {article.wci_score} {wciInfo.label}
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
      </CardContent>
    </Card>
  )
}
