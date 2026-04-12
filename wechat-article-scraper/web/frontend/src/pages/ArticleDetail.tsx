import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getArticle, getArticleSummary, generateArticleSummary, createHighlight, getHighlights,
  getReadingProgress, saveReadingProgress, exportArticle
} from '@/api'
import HighlightToolbar from '@/components/HighlightToolbar'
import EdgeTTSPlayer from '@/components/EdgeTTSPlayer'
import { formatDate, getWciLevel, formatNumber, calculateReadingTime, getWordCount } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { ArrowLeft, ExternalLink, FileText, BarChart3, Sparkles, Headphones, Clock, BookOpen, Download } from 'lucide-react'
import { Link } from 'react-router-dom'
import SummaryCard from '@/components/SummaryCard'
import ImmersiveReader from '@/components/ImmersiveReader'

type TabType = 'content' | 'summary' | 'metadata'

interface Highlight {
  id: number
  content: string
  note?: string
  position?: string
}

// Component to render HTML content with highlights
function HTMLContent({ html, highlights }: { html: string; highlights: Highlight[] }) {
  // Process HTML to add highlight spans
  let processedHtml = html

  if (highlights && highlights.length > 0) {
    // Sort by length (longest first) to avoid partial matches
    const sortedHighlights = [...highlights].sort((a, b) => b.content.length - a.content.length)

    sortedHighlights.forEach((highlight) => {
      const colorMap: Record<string, string> = {
        yellow: '#fef08a',
        green: '#bbf7d0',
        blue: '#bfdbfe',
        pink: '#fbcfe8',
        purple: '#e9d5ff',
      }

      let color = colorMap.yellow
      try {
        const pos = JSON.parse(highlight.position || '{}')
        color = colorMap[pos.color] || color
      } catch {
        // use default
      }

      // Replace text with highlighted span (simple string replacement)
      const highlightSpan = `<span style="background-color: ${color}; padding: 2px 4px; border-radius: 4px;" title="${highlight.note || '高亮'}">${highlight.content}</span>`
      processedHtml = processedHtml.replace(highlight.content, highlightSpan)
    })
  }

  return (
    <div
      className="whitespace-pre-wrap"
      dangerouslySetInnerHTML={{ __html: processedHtml }}
    />
  )
}

// Component to render content with highlights
function HighlightedContent({ content, highlights }: { content: string; highlights: Highlight[] }) {
  if (!highlights || highlights.length === 0) {
    return <div className="whitespace-pre-wrap">{content}</div>
  }

  // Simple approach: split content by highlight texts and render with spans
  let parts: Array<{ text: string; isHighlight: boolean; highlight?: Highlight }> = []
  let remainingContent = content

  // Sort highlights by length (longest first) to avoid partial matches
  const sortedHighlights = [...highlights].sort((a, b) => b.content.length - a.content.length)

  // Track which positions are already highlighted to avoid overlap
  const highlightedRanges: Array<{ start: number; end: number }> = []

  sortedHighlights.forEach((highlight) => {
    const index = remainingContent.indexOf(highlight.content)
    if (index !== -1) {
      // Check for overlap
      const isOverlapping = highlightedRanges.some(
        (range) => (index >= range.start && index < range.end) || (index + highlight.content.length > range.start && index + highlight.content.length <= range.end)
      )

      if (!isOverlapping) {
        // Parse position for color
        let color = '#fef08a' // default yellow
        try {
          const pos = JSON.parse(highlight.position || '{}')
          const colorMap: Record<string, string> = {
            yellow: '#fef08a',
            green: '#bbf7d0',
            blue: '#bfdbfe',
            pink: '#fbcfe8',
            purple: '#e9d5ff',
          }
          if (pos.color && colorMap[pos.color]) {
            color = colorMap[pos.color]
          }
        } catch {
          // use default color
        }

        // Add range to tracked ranges
        highlightedRanges.push({ start: index, end: index + highlight.content.length })

        parts.push({
          text: highlight.content,
          isHighlight: true,
          highlight: { ...highlight, position: JSON.stringify({ color }) },
        })
      }
    }
  })

  // If no highlights found, return plain content
  if (parts.length === 0) {
    return <div className="whitespace-pre-wrap">{content}</div>
  }

  // Reconstruct content with highlights
  const result: Array<JSX.Element | string> = []
  let lastIndex = 0
  let partIndex = 0

  sortedHighlights.forEach((highlight, idx) => {
    const index = content.indexOf(highlight.content, lastIndex)
    if (index !== -1) {
      // Add text before highlight
      if (index > lastIndex) {
        result.push(content.substring(lastIndex, index))
      }

      // Parse color
      let color = '#fef08a'
      try {
        const pos = JSON.parse(highlight.position || '{}')
        const colorMap: Record<string, string> = {
          yellow: '#fef08a',
          green: '#bbf7d0',
          blue: '#bfdbfe',
          pink: '#fbcfe8',
          purple: '#e9d5ff',
        }
        color = colorMap[pos.color] || color
      } catch {
        // use default
      }

      // Add highlighted text
      result.push(
        <span
          key={`highlight-${highlight.id || idx}`}
          className="rounded px-1 cursor-pointer hover:ring-2 hover:ring-offset-1 transition-all"
          style={{
            backgroundColor: color,
          }}
          title={highlight.note || '高亮'}
        >
          {highlight.content}
        </span>
      )

      lastIndex = index + highlight.content.length
    }
  })

  // Add remaining text
  if (lastIndex < content.length) {
    result.push(content.substring(lastIndex))
  }

  return <div className="whitespace-pre-wrap">{result}</div>
}

export default function ArticleDetail() {
  const { id } = useParams<{ id: string }>()
  const [activeTab, setActiveTab] = useState<TabType>('content')
  const [showImmersiveReader, setShowImmersiveReader] = useState(false)
  const [readingProgress, setReadingProgress] = useState(0)
  const queryClient = useQueryClient()

  // Highlight state
  const [showToolbar, setShowToolbar] = useState(false)
  const [selectedText, setSelectedText] = useState('')
  const [selectionPosition, setSelectionPosition] = useState<{ x: number; y: number } | null>(null)

  // Export state
  const [isExporting, setIsExporting] = useState(false)
  const [showExportMenu, setShowExportMenu] = useState(false)

  const { data: article, isLoading } = useQuery({
    queryKey: ['article', id],
    queryFn: () => getArticle(id!),
  })

  // Fetch highlights for this article
  const { data: highlightsData } = useQuery({
    queryKey: ['highlights', id],
    queryFn: () => getHighlights({ article_id: id }),
    enabled: !!id,
  })
  const highlights = highlightsData?.data || []

  // Fetch reading progress
  const { data: progressData } = useQuery({
    queryKey: ['reading-progress', id],
    queryFn: () => getReadingProgress(id!),
    enabled: !!id,
  })

  // Save reading progress mutation
  const saveProgress = useMutation({
    mutationFn: (progress: { progress_percent: number; last_position?: number }) =>
      saveReadingProgress(id!, { ...progress, read_time_seconds: 0 }),
  })

  // Track scroll progress
  useEffect(() => {
    if (activeTab !== 'content') return

    const handleScroll = () => {
      const scrollTop = window.scrollY
      const docHeight = document.documentElement.scrollHeight - window.innerHeight
      const progress = docHeight > 0 ? Math.round((scrollTop / docHeight) * 100) : 0
      setReadingProgress(Math.min(100, progress))

      // Debounce save progress
      const timeoutId = setTimeout(() => {
        saveProgress.mutate({ progress_percent: progress, last_position: scrollTop })
      }, 1000)

      return () => clearTimeout(timeoutId)
    }

    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [activeTab, id])

  // Handle text selection
  const handleTextSelection = () => {
    const selection = window.getSelection()
    if (selection && selection.toString().trim().length > 0) {
      const text = selection.toString()
      const range = selection.getRangeAt(0)
      const rect = range.getBoundingClientRect()

      setSelectedText(text)
      setSelectionPosition({
        x: rect.left + rect.width / 2,
        y: rect.top + window.scrollY
      })
      setShowToolbar(true)
    } else {
      setShowToolbar(false)
    }
  }

  // Handle highlight creation
  const handleHighlight = async (color: string, note?: string) => {
    if (!id || !selectedText) return

    try {
      await createHighlight({
        article_id: id,
        content: selectedText,
        note: note || '',
        position: JSON.stringify({ color, timestamp: Date.now() })
      })

      // Refresh highlights
      queryClient.invalidateQueries({ queryKey: ['highlights', id] })

      // Clear selection
      window.getSelection()?.removeAllRanges()
      setShowToolbar(false)
      setSelectedText('')
    } catch (error) {
      console.error('Failed to create highlight:', error)
    }
  }

  // Handle toolbar close
  const handleToolbarClose = () => {
    setShowToolbar(false)
    window.getSelection()?.removeAllRanges()
  }

  // Handle export
  const handleExport = async (format: string) => {
    if (!id) return

    setIsExporting(true)
    setShowExportMenu(false)

    try {
      const result = await exportArticle(id, {
        format: format as any,
        include_images: true,
        include_meta: true
      })

      // Check if result is a file download
      if (result?.isFile && result?.blob) {
        // Download file
        const url = window.URL.createObjectURL(result.blob)
        const link = document.createElement('a')
        link.href = url
        link.download = result.filename
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        window.URL.revokeObjectURL(url)
      } else if (result?.success && result?.data?.content) {
        // Download text content
        const blob = new Blob([result.data.content], { type: result.data.media_type })
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = result.data.filename
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        window.URL.revokeObjectURL(url)
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

  // Add selection listener
  useEffect(() => {
    const handleSelectionChange = () => {
      const selection = window.getSelection()
      if (selection && selection.toString().trim().length > 0) {
        handleTextSelection()
      }
    }

    document.addEventListener('selectionchange', handleSelectionChange)
    return () => {
      document.removeEventListener('selectionchange', handleSelectionChange)
    }
  }, [])

  const { data: summary, isLoading: isSummaryLoading } = useQuery({
    queryKey: ['article-summary', id],
    queryFn: () => getArticleSummary(id!),
    enabled: activeTab === 'summary',
  })

  const generateSummary = useMutation({
    mutationFn: () => generateArticleSummary(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['article-summary', id] })
    },
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
        <div className="mt-2 flex items-center gap-4 text-muted-foreground flex-wrap">
          <span>{data.author}</span>
          <span>{formatDate(data.publish_time)}</span>
          <span className="flex items-center gap-1">
            <Clock className="h-4 w-4" />
            {calculateReadingTime(data.content)}
          </span>
          <span className="flex items-center gap-1">
            <BookOpen className="h-4 w-4" />
            {formatNumber(getWordCount(data.content))} 字
          </span>
          <span className="flex items-center gap-1">
            <BookOpen className="h-4 w-4" />
            {formatNumber(getWordCount(data.content))} 字
          </span>
          <a
            href={data.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 hover:text-primary"
          >
            <ExternalLink className="h-4 w-4" />
            原文链接
          </a>

          {/* Export Dropdown */}
          <div className="relative">
            <button
              onClick={() => setShowExportMenu(!showExportMenu)}
              disabled={isExporting}
              className="flex items-center gap-1 hover:text-primary disabled:opacity-50"
            >
              <Download className="h-4 w-4" />
              {isExporting ? '导出中...' : '导出'}
            </button>

            {showExportMenu && (
              <div className="absolute right-0 z-50 mt-1 w-40 rounded-md border bg-white py-1 shadow-lg">
                <button
                  onClick={() => handleExport('markdown')}
                  className="block w-full px-4 py-2 text-left text-sm hover:bg-gray-100"
                >
                  Markdown (.md)
                </button>
                <button
                  onClick={() => handleExport('html')}
                  className="block w-full px-4 py-2 text-left text-sm hover:bg-gray-100"
                >
                  HTML (.html)
                </button>
                <button
                  onClick={() => handleExport('json')}
                  className="block w-full px-4 py-2 text-left text-sm hover:bg-gray-100"
                >
                  JSON (.json)
                </button>
                <button
                  onClick={() => handleExport('pdf')}
                  className="block w-full px-4 py-2 text-left text-sm hover:bg-gray-100"
                >
                  PDF (.pdf)
                </button>
                <button
                  onClick={() => handleExport('excel')}
                  className="block w-full px-4 py-2 text-left text-sm hover:bg-gray-100"
                >
                  Excel (.xlsx)
                </button>
              </div>
            )}
          </div>
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

        {/* Reading Progress */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">阅读进度</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold">{readingProgress}%</span>
              {progressData?.data?.progress_percent > 0 && readingProgress === 0 && (
                <span className="text-xs text-muted-foreground">
                  (上次 {progressData.data.progress_percent}%)
                </span>
              )}
            </div>
            <div className="mt-2 h-1.5 w-full rounded-full bg-gray-100">
              <div
                className="h-full rounded-full bg-primary transition-all duration-300"
                style={{ width: `${Math.max(readingProgress, progressData?.data?.progress_percent || 0)}%` }}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <div className="border-b">
        <div className="flex gap-4">
          <button
            onClick={() => setActiveTab('content')}
            className={`flex items-center gap-2 pb-2 text-sm font-medium ${
              activeTab === 'content'
                ? 'border-b-2 border-blue-500 text-blue-600'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <FileText className="h-4 w-4" />
            文章内容
          </button>
          <button
            onClick={() => setActiveTab('summary')}
            className={`flex items-center gap-2 pb-2 text-sm font-medium ${
              activeTab === 'summary'
                ? 'border-b-2 border-blue-500 text-blue-600'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Sparkles className="h-4 w-4" />
            AI摘要
          </button>
          <button
            onClick={() => setActiveTab('metadata')}
            className={`flex items-center gap-2 pb-2 text-sm font-medium ${
              activeTab === 'metadata'
                ? 'border-b-2 border-blue-500 text-blue-600'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <BarChart3 className="h-4 w-4" />
            元数据
          </button>
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'content' && (
        <div className="space-y-4">
          {/* TTS Player */}
          {data.content && (
            <EdgeTTSPlayer text={data.content} />
          )}

          {/* Immersive Reader Button */}
          {data.content && (
            <div className="flex justify-end">
              <button
                onClick={() => setShowImmersiveReader(true)}
                className="flex items-center gap-2 rounded-lg bg-primary/10 px-4 py-2 text-sm font-medium text-primary hover:bg-primary/20 transition-colors"
              >
                <BookOpen className="h-4 w-4" />
                沉浸式阅读
              </button>
            </div>
          )}

          <Card>
            <CardContent className="pt-6">
              <div
                className="prose max-w-none"
                onMouseUp={handleTextSelection}
              >
                {/* Priority: html_content > content */}
                {data.html_content ? (
                  <HTMLContent
                    html={data.html_content}
                    highlights={highlights}
                  />
                ) : data.content ? (
                  <HighlightedContent
                    content={data.content}
                    highlights={highlights}
                  />
                ) : (
                  <p className="text-muted-foreground">暂无内容</p>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Highlight Toolbar */}
      {showToolbar && (
        <HighlightToolbar
          selectedText={selectedText}
          onHighlight={handleHighlight}
          onClose={handleToolbarClose}
        />
      )}

      {activeTab === 'summary' && (
        <SummaryCard
          articleId={id!}
          summary={summary?.data}
          isLoading={isSummaryLoading || generateSummary.isPending}
          onGenerate={() => generateSummary.mutate()}
          onRefresh={() => generateSummary.mutate()}
        />
      )}

      {activeTab === 'metadata' && (
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
      )}

      {/* Immersive Reader */}
      {showImmersiveReader && data && (
        <ImmersiveReader
          title={data.title}
          author={data.author}
          content={data.content}
          publishTime={data.publish_time}
          url={data.url}
          onClose={() => setShowImmersiveReader(false)}
        />
      )}
    </div>
  )
}
