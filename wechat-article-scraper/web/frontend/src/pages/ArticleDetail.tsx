import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getArticle } from '@/api'
import { formatDate, getWciLevel, formatNumber } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { ArrowLeft, ExternalLink } from 'lucide-react'
import { Link } from 'react-router-dom'

export default function ArticleDetail() {
  const { id } = useParams<{ id: string }>()

  const { data: article, isLoading } = useQuery({
    queryKey: ['article', id],
    queryFn: () => getArticle(parseInt(id!)),
  })

  if (isLoading) {
    return <div className="text-center py-12">加载中...</div>
  }

  if (!article?.data) {
    return <div className="text-center py-12">文章不存在</div>
  }

  const data = article.data
  const wciInfo = getWciLevel(data.wci_score)
  const engagement = data.engagement || {}

  return (
    <div className="space-y-6">
      {/* Back button */}
      <Link
        to="/articles"
        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="h-4 w-4" />
        返回文章列表
      </Link>

      {/* Title */}
      <div>
        <h1 className="text-2xl font-bold">{data.title}</h1>
        <div className="mt-2 flex items-center gap-4 text-muted-foreground">
          <span>{data.author}</span>
          <span>{formatDate(data.publish_time)}</span>
          <a
            href={data.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 hover:text-primary"
          >
            <ExternalLink className="h-4 w-4" />
            原文链接
          </a>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">WCI 传播指数</CardTitle>
          </CardHeader>
          <CardContent>
            {data.wci_score ? (
              <div className="flex items-center gap-2">
                <span className="text-2xl font-bold">{data.wci_score}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs text-white ${wciInfo.color}`}>
                  {wciInfo.label}
                </span>
              </div>
            ) : (
              <span className="text-muted-foreground">-</span>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">阅读量</CardTitle>
          </CardHeader>
          <CardContent>
            <span className="text-2xl font-bold">{formatNumber(engagement.readCount)}</span>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">点赞数</CardTitle>
          </CardHeader>
          <CardContent>
            <span className="text-2xl font-bold">{formatNumber(engagement.likeCount)}</span>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">在看数</CardTitle>
          </CardHeader>
          <CardContent>
            <span className="text-2xl font-bold">{formatNumber(engagement.watchCount)}</span>
          </CardContent>
        </Card>
      </div>

      {/* Content */}
      <Card>
        <CardHeader>
          <CardTitle>文章内容</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="prose max-w-none">
            {data.content ? (
              <div className="whitespace-pre-wrap">{data.content}</div>
            ) : (
              <p className="text-muted-foreground">暂无内容</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Metadata */}
      <Card>
        <CardHeader>
          <CardTitle>元数据</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-4">
            <div>
              <dt className="text-sm text-muted-foreground">分类</dt>
              <dd>{data.category || '-'}</dd>
            </div>
            <div>
              <dt className="text-sm text-muted-foreground">抓取策略</dt>
              <dd>{data.strategy}</dd>
            </div>
            <div>
              <dt className="text-sm text-muted-foreground">内容状态</dt>
              <dd>{data.content_status}</dd>
            </div>
            <div>
              <dt className="text-sm text-muted-foreground">抓取时间</dt>
              <dd>{formatDate(data.created_at)}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>
    </div>
  )
}
