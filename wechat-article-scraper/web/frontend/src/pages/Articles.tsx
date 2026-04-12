import { useState, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { getArticles, batchExportArticles } from '@/api'
import { formatDate, getWciLevel, formatNumber, calculateReadingTime } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/Card'
import { Link } from 'react-router-dom'
import { ExternalLink, Search, Filter, Clock, Download, CheckSquare, Square } from 'lucide-react'

// Estimated row height for virtual scrolling
const ESTIMATED_ROW_HEIGHT = 80

export default function Articles() {
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedAuthor, setSelectedAuthor] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('')
  const [selectedArticles, setSelectedArticles] = useState<Set<string>>(new Set())
  const [isExporting, setIsExporting] = useState(false)
  const [showExportMenu, setShowExportMenu] = useState(false)
  const parentRef = useRef<HTMLDivElement>(null)

  const { data: articles, isLoading } = useQuery({
    queryKey: ['articles', { author: selectedAuthor, category: selectedCategory }],
    queryFn: () => getArticles({ author: selectedAuthor, category: selectedCategory, limit: 1000 }),
  })

  const filteredArticles = articles?.data?.filter((article: any) =>
    article.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    article.author.toLowerCase().includes(searchTerm.toLowerCase())
  ) || []

  // Virtual list setup
  const virtualizer = useVirtualizer({
    count: filteredArticles.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ESTIMATED_ROW_HEIGHT,
    overscan: 5, // Render 5 extra items for smoother scrolling
  })

  const virtualItems = virtualizer.getVirtualItems()

  // Toggle article selection
  const toggleSelection = (id: string) => {
    const newSet = new Set(selectedArticles)
    if (newSet.has(id)) {
      newSet.delete(id)
    } else {
      newSet.add(id)
    }
    setSelectedArticles(newSet)
  }

  // Toggle select all
  const toggleSelectAll = () => {
    if (selectedArticles.size === filteredArticles.length && filteredArticles.length > 0) {
      setSelectedArticles(new Set())
    } else {
      setSelectedArticles(new Set(filteredArticles.map((a: any) => String(a.id))))
    }
  }

  // Handle batch export
  const handleBatchExport = async (format: string) => {
    if (selectedArticles.size === 0) {
      alert('请先选择要导出的文章')
      return
    }

    setIsExporting(true)
    setShowExportMenu(false)

    try {
      const result = await batchExportArticles({
        article_ids: Array.from(selectedArticles),
        format: format as any,
        include_meta: true
      })

      if (result?.isFile && result?.blob) {
        const url = window.URL.createObjectURL(result.blob)
        const link = document.createElement('a')
        link.href = url
        link.download = result.filename
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        window.URL.revokeObjectURL(url)
        setSelectedArticles(new Set()) // Clear selection after export
      } else {
        alert('导出失败: ' + (result?.detail || '未知错误'))
      }
    } catch (error) {
      console.error('Export failed:', error)
      alert('导出失败，请检查后端服务是否正常运行')
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">文章列表</h1>
        <p className="mt-2 text-muted-foreground">
          共 {filteredArticles.length} 篇文章
        </p>
      </div>

      {/* Filters and Actions */}
      <div className="flex gap-4 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
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

        {/* Batch Export Controls */}
        {selectedArticles.size > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">
              已选择 {selectedArticles.size} 篇
            </span>
            <button
              onClick={toggleSelectAll}
              className="flex items-center gap-2 rounded-lg border px-4 py-2 hover:bg-accent"
            >
              {selectedArticles.size === filteredArticles.length ? (
                <CheckSquare className="h-4 w-4" />
              ) : (
                <Square className="h-4 w-4" />
              )}
              全选
            </button>
            <div className="relative">
              <button
                onClick={() => setShowExportMenu(!showExportMenu)}
                disabled={isExporting}
                className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                <Download className="h-4 w-4" />
                {isExporting ? '导出中...' : '批量导出'}
              </button>

              {showExportMenu && (
                <div className="absolute right-0 z-50 mt-1 w-40 rounded-md border bg-white py-1 shadow-lg">
                  <button
                    onClick={() => handleBatchExport('markdown')}
                    className="block w-full px-4 py-2 text-left text-sm hover:bg-gray-100"
                  >
                    Markdown (ZIP)
                  </button>
                  <button
                    onClick={() => handleBatchExport('html')}
                    className="block w-full px-4 py-2 text-left text-sm hover:bg-gray-100"
                  >
                    HTML (ZIP)
                  </button>
                  <button
                    onClick={() => handleBatchExport('json')}
                    className="block w-full px-4 py-2 text-left text-sm hover:bg-gray-100"
                  >
                    JSON
                  </button>
                  <button
                    onClick={() => handleBatchExport('excel')}
                    className="block w-full px-4 py-2 text-left text-sm hover:bg-gray-100"
                  >
                    Excel (.xlsx)
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Articles List with Virtual Scrolling */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-8 text-center text-muted-foreground">加载中...</div>
          ) : filteredArticles.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">暂无文章</div>
          ) : (
            <div
              ref={parentRef}
              className="h-[600px] overflow-auto"
              style={{ contain: 'strict' }}
            >
              <div
                style={{
                  height: `${virtualizer.getTotalSize()}px`,
                  width: '100%',
                  position: 'relative',
                }}
              >
                {virtualItems.map((virtualItem) => {
                  const article = filteredArticles[virtualItem.index]
                  const wciInfo = getWciLevel(article.wci_score)

                  return (
                    <div
                      key={article.id}
                      style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        height: `${virtualItem.size}px`,
                        transform: `translateY(${virtualItem.start}px)`,
                      }}
                      className="flex items-center justify-between p-4 border-b hover:bg-accent/50 transition-colors"
                      onClick={() => toggleSelection(String(article.id))}
                    >
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        <div onClick={(e) => e.stopPropagation()}>
                          {selectedArticles.has(String(article.id)) ? (
                            <CheckSquare className="h-5 w-5 text-primary" />
                          ) : (
                            <Square className="h-5 w-5 text-muted-foreground" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <Link
                            to={`/articles/${article.id}`}
                            className="font-medium hover:text-primary line-clamp-1"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {article.title}
                          </Link>
                        <div className="mt-1 flex items-center gap-4 text-sm text-muted-foreground flex-wrap">
                          <span>{article.author}</span>
                          <span>{formatDate(article.publish_time)}</span>
                          <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {calculateReadingTime(article.content)}
                          </span>
                          {article.category && (
                            <span className="rounded-full bg-secondary px-2 py-0.5 text-xs">
                              {article.category}
                            </span>
                          )}
                        </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 ml-4 shrink-0" onClick={(e) => e.stopPropagation()}>
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
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
