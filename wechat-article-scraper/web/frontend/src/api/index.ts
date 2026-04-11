import axios from 'axios'
import type { Article, Queue, Task, QueueStatus, Statistics, ApiResponse } from '@/types'

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Articles
export const getArticles = async (params?: { author?: string; category?: string; limit?: number; offset?: number }) => {
  const { data } = await api.get<ApiResponse<Article[]>>('/articles', { params })
  return data
}

export const getArticle = async (id: number) => {
  const { data } = await api.get<ApiResponse<Article>>(`/articles/${id}`)
  return data
}

export const searchArticles = async (keyword: string, limit: number = 20) => {
  const { data } = await api.get<ApiResponse<Article[]>>('/articles/search', { params: { keyword, limit } })
  return data
}

// Statistics
export const getStatistics = async () => {
  const { data } = await api.get<ApiResponse<Statistics>>('/statistics')
  return data
}

// Queues
export const getQueues = async () => {
  const { data } = await api.get<ApiResponse<Queue[]>>('/queues')
  return data
}

export const getQueue = async (id: string) => {
  const { data } = await api.get<ApiResponse<Queue>>(`/queues/${id}`)
  return data
}

export const getQueueStatus = async (id: string) => {
  const { data } = await api.get<ApiResponse<QueueStatus>>(`/queues/${id}/status`)
  return data
}

export const getQueueTasks = async (id: string, status?: string) => {
  const { data } = await api.get<ApiResponse<Task[]>>(`/queues/${id}/tasks`, { params: { status } })
  return data
}

export const createQueue = async (name: string, config: any) => {
  const { data } = await api.post<ApiResponse<Queue>>('/queues', { name, config })
  return data
}

export const addTasks = async (queueId: string, tasks: any[]) => {
  const { data } = await api.post<ApiResponse<{ count: number }>>(`/queues/${queueId}/tasks`, { tasks })
  return data
}

export const startQueue = async (id: string) => {
  const { data } = await api.post<ApiResponse<any>>(`/queues/${id}/start`)
  return data
}

export const pauseQueue = async (id: string) => {
  const { data } = await api.post<ApiResponse<any>>(`/queues/${id}/pause`)
  return data
}

export const resumeQueue = async (id: string) => {
  const { data } = await api.post<ApiResponse<any>>(`/queues/${id}/resume`)
  return data
}

export const stopQueue = async (id: string) => {
  const { data } = await api.post<ApiResponse<any>>(`/queues/${id}/stop`)
  return data
}

// Scrape
export const scrapeArticle = async (url: string, options?: any) => {
  const { data } = await api.post<ApiResponse<any>>('/scrape', { url, ...options })
  return data
}

export default api