// API client for wechat-article-scraper

const API_BASE = '/api'

export async function getStatistics() {
  const response = await fetch(`${API_BASE}/statistics`)
  return response.json()
}

export async function getArticles(params?: { author?: string; category?: string; limit?: number }) {
  const query = new URLSearchParams(params as Record<string, string>).toString()
  const response = await fetch(`${API_BASE}/articles?${query}`)
  return response.json()
}

export async function getArticle(id: string) {
  const response = await fetch(`${API_BASE}/articles/${id}`)
  return response.json()
}

export async function getQueues() {
  const response = await fetch(`${API_BASE}/queues`)
  return response.json()
}

export async function getQueue(id: string) {
  const response = await fetch(`${API_BASE}/queues/${id}`)
  return response.json()
}

export async function searchArticles(keyword: string) {
  const response = await fetch(`${API_BASE}/articles/search?keyword=${encodeURIComponent(keyword)}`)
  return response.json()
}

// Sogou WeChat Search API
export interface SogouSearchParams {
  keyword: string
  search_type?: 'articles' | 'accounts'
  num_results?: number
  time_filter?: 'day' | 'week' | 'month' | 'year' | null
  resolve_urls?: boolean
}

export async function sogouSearch(params: SogouSearchParams) {
  const query = new URLSearchParams({
    keyword: params.keyword,
    search_type: params.search_type || 'articles',
    num_results: String(params.num_results || 10),
    ...(params.time_filter ? { time_filter: params.time_filter } : {}),
    resolve_urls: String(params.resolve_urls || false)
  }).toString()

  const response = await fetch(`${API_BASE}/search/sogou?${query}`)
  return response.json()
}

// Article Summary API
export async function getArticleSummary(articleId: string) {
  const response = await fetch(`${API_BASE}/articles/${articleId}/summary`)
  return response.json()
}

export async function generateArticleSummary(articleId: string) {
  const response = await fetch(`${API_BASE}/articles/${articleId}/summarize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  return response.json()
}

// Queue API
export async function createQueue(name: string, config?: Record<string, unknown>) {
  const response = await fetch(`${API_BASE}/queues`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, ...config })
  })
  return response.json()
}

export async function getQueueStatus(id: string) {
  const response = await fetch(`${API_BASE}/queues/${id}/status`)
  return response.json()
}

export async function getQueueTasks(id: string, status?: string) {
  const query = status ? `?status=${status}` : ''
  const response = await fetch(`${API_BASE}/queues/${id}/tasks${query}`)
  return response.json()
}

export async function addTasks(id: string, tasks: any[]) {
  const response = await fetch(`${API_BASE}/queues/${id}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tasks })
  })
  return response.json()
}

export async function startQueue(id: string) {
  const response = await fetch(`${API_BASE}/queues/${id}/start`, { method: 'POST' })
  return response.json()
}

export async function pauseQueue(id: string) {
  const response = await fetch(`${API_BASE}/queues/${id}/pause`, { method: 'POST' })
  return response.json()
}

export async function resumeQueue(id: string) {
  const response = await fetch(`${API_BASE}/queues/${id}/resume`, { method: 'POST' })
  return response.json()
}

export async function stopQueue(id: string) {
  const response = await fetch(`${API_BASE}/queues/${id}/stop`, { method: 'POST' })
  return response.json()
}

// Highlights API
export async function getHighlights(params?: { article_id?: string; color?: string; limit?: number }) {
  const query = new URLSearchParams(params as Record<string, string>).toString()
  const response = await fetch(`${API_BASE}/highlights?${query}`)
  return response.json()
}

export async function createHighlight(data: { article_id: string; content: string; note?: string; position?: string }) {
  const response = await fetch(`${API_BASE}/highlights`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  })
  return response.json()
}

export async function deleteHighlight(id: number) {
  const response = await fetch(`${API_BASE}/highlights/${id}`, { method: 'DELETE' })
  return response.json()
}

export async function getHighlightStatistics() {
  const response = await fetch(`${API_BASE}/highlights/stats`)
  return response.json()
}

// Daily Review API
export async function getDueReviews(limit?: number) {
  const query = limit ? `?limit=${limit}` : ''
  const response = await fetch(`${API_BASE}/reviews/due${query}`)
  return response.json()
}

// Dashboard API
export async function getDashboardOverview() {
  const response = await fetch(`${API_BASE}/dashboard/overview`)
  return response.json()
}

export async function getDashboardReading() {
  const response = await fetch(`${API_BASE}/dashboard/reading`)
  return response.json()
}

export async function getDashboardAuthors() {
  const response = await fetch(`${API_BASE}/dashboard/authors`)
  return response.json()
}

export async function getFullDashboard() {
  const response = await fetch(`${API_BASE}/dashboard`)
  return response.json()
}

export async function submitReview(reviewId: string, feedback: 'remembered' | 'fuzzy' | 'forgotten') {
  const response = await fetch(`${API_BASE}/reviews/${reviewId}/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ feedback })
  })
  return response.json()
}

export async function skipReview(reviewId: string) {
  // Skip is treated as 'fuzzy' in the spaced repetition algorithm
  return submitReview(reviewId, 'fuzzy')
}

export async function getReviewStatistics() {
  const response = await fetch(`${API_BASE}/reviews/stats`)
  return response.json()
}

export async function importGenericURL(url: string, title?: string, category?: string) {
  const response = await fetch(`${API_BASE}/articles/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, title, category })
  })
  return response.json()
}

// Download article images for offline storage
export async function downloadArticleImages(articleId: string) {
  const response = await fetch(`${API_BASE}/articles/${articleId}/download-images`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  return response.json()
}

// Reading Progress API
export async function getReadingProgress(articleId: string) {
  const response = await fetch(`${API_BASE}/articles/${articleId}/progress`)
  return response.json()
}

export async function saveReadingProgress(
  articleId: string,
  progress: {
    progress_percent: number
    last_position?: number
    read_time_seconds?: number
    is_finished?: boolean
  }
) {
  const response = await fetch(`${API_BASE}/articles/${articleId}/progress`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(progress)
  })
  return response.json()
}

export async function getInProgressArticles(limit?: number) {
  const query = limit ? `?limit=${limit}` : ''
  const response = await fetch(`${API_BASE}/reading/in-progress${query}`)
  return response.json()
}

export async function getFinishedArticles(limit?: number) {
  const query = limit ? `?limit=${limit}` : ''
  const response = await fetch(`${API_BASE}/reading/finished${query}`)
  return response.json()
}

export async function getReadingStatistics() {
  const response = await fetch(`${API_BASE}/reading/statistics`)
  return response.json()
}

// History Crawl API
export interface HistoryCrawlParams {
  biz: string
  appmsg_token: string
  cookie?: string
  nickname?: string
  max_articles?: number
}

export async function getHistoryCrawlTasks(limit?: number) {
  const query = limit ? `?limit=${limit}` : ''
  const response = await fetch(`${API_BASE}/history-crawl${query}`)
  return response.json()
}

export async function getHistoryCrawlStatus(taskId: string) {
  const response = await fetch(`${API_BASE}/history-crawl/${taskId}`)
  return response.json()
}

export async function startHistoryCrawl(params: HistoryCrawlParams) {
  const response = await fetch(`${API_BASE}/history-crawl`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params)
  })
  return response.json()
}

export async function testHistoryParams(params: { biz: string; appmsg_token: string; cookie?: string }) {
  const response = await fetch(`${API_BASE}/history-crawl/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params)
  })
  return response.json()
}

// Export API
export type ExportFormat = 'markdown' | 'html' | 'json' | 'pdf' | 'excel' | 'xlsx' | 'md'

export interface ExportOptions {
  format: ExportFormat
  include_images?: boolean
  include_meta?: boolean
}

export async function exportArticle(articleId: string, options: ExportOptions) {
  const query = new URLSearchParams({
    format: options.format,
    include_images: String(options.include_images ?? true),
    include_meta: String(options.include_meta ?? true)
  }).toString()

  const response = await fetch(`${API_BASE}/articles/${articleId}/export?${query}`)

  // Check if response is a file download (PDF, Excel)
  const contentType = response.headers.get('content-type')
  if (contentType?.includes('application/pdf') ||
      contentType?.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') ||
      contentType?.includes('application/zip')) {
    // Return blob for file download
    const blob = await response.blob()
    const contentDisposition = response.headers.get('content-disposition')
    const filename = contentDisposition?.match(/filename="?([^"]+)"?/)?.[1] || `export.${options.format}`
    return { blob, filename, isFile: true }
  }

  // Return JSON for text formats
  return response.json()
}

export interface BatchExportOptions {
  article_ids: string[]
  format: Exclude<ExportFormat, 'pdf'>
  include_meta?: boolean
}

export async function batchExportArticles(options: BatchExportOptions) {
  const response = await fetch(`${API_BASE}/articles/export/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      article_ids: options.article_ids.map(id => parseInt(id)),
      format: options.format,
      include_meta: options.include_meta ?? true
    })
  })

  // Check if response is a file download
  const contentType = response.headers.get('content-type')
  if (contentType?.includes('application/') && !contentType?.includes('application/json')) {
    const blob = await response.blob()
    const contentDisposition = response.headers.get('content-disposition')
    const filename = contentDisposition?.match(/filename="?([^"]+)"?/)?.[1] || `export.${options.format}`
    return { blob, filename, isFile: true }
  }

  return response.json()
}

export async function getExportFormats() {
  const response = await fetch(`${API_BASE}/export/formats`)
  return response.json()
}
