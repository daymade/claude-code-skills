import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getQueue, getQueueStatus, getQueueTasks, addTasks, startQueue, pauseQueue, resumeQueue, stopQueue } from '@/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { ArrowLeft, Play, Pause, Square, Plus, CheckCircle, XCircle, Clock } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getStatusColor, cn } from '@/lib/utils'

export default function QueueDetail() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const [newUrl, setNewUrl] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)

  const { data: queue } = useQuery({
    queryKey: ['queue', id],
    queryFn: () => getQueue(id!),
  })

  const { data: status } = useQuery({
    queryKey: ['queue-status', id],
    queryFn: () => getQueueStatus(id!),
    refetchInterval: 2000, // 每2秒刷新状态
  })

  const { data: tasks } = useQuery({
    queryKey: ['queue-tasks', id],
    queryFn: () => getQueueTasks(id!),
    refetchInterval: 2000,
  })

  const addTasksMutation = useMutation({
    mutationFn: (urls: string[]) => addTasks(id!, urls.map(url => ({ task_type: 'scrape', target: url, priority: 5 }))),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue', id] })
      queryClient.invalidateQueries({ queryKey: ['queue-tasks', id] })
      setShowAddModal(false)
      setNewUrl('')
    },
  })

  const startMutation = useMutation({
    mutationFn: () => startQueue(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['queue', id] }),
  })

  const pauseMutation = useMutation({
    mutationFn: () => pauseQueue(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['queue', id] }),
  })

  const resumeMutation = useMutation({
    mutationFn: () => resumeQueue(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['queue', id] }),
  })

  const stopMutation = useMutation({
    mutationFn: () => stopQueue(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['queue', id] }),
  })

  const queueData = queue?.data
  const statusData = status?.data
  const progress = statusData?.progress?.percentage || 0

  return (
    <div className="space-y-6">
      {/* Back */}
      <Link
        to="/queues"
        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="h-4 w-4" />
        返回队列列表
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold">{queueData?.name}</h1>
            <span
              className={cn(
                'rounded-full px-2 py-0.5 text-xs text-white',
                getStatusColor(queueData?.status)
              )}
            >
              {queueData?.status}
            </span>
          </div>
          <p className="mt-2 text-muted-foreground">ID: {queueData?.id}</p>
        </div>

        <div className="flex items-center gap-2">
          {queueData?.status === 'idle' && (
            <button
              onClick={() => startMutation.mutate()}
              className="flex items-center gap-2 rounded-lg bg-green-500 px-4 py-2 text-white hover:bg-green-600"
            >
              <Play className="h-4 w-4" />
              启动
            </button>
          )}
          {queueData?.status === 'running' && (
            <>
              <button
                onClick={() => pauseMutation.mutate()}
                className="flex items-center gap-2 rounded-lg bg-yellow-500 px-4 py-2 text-white hover:bg-yellow-600"
              >
                <Pause className="h-4 w-4" />
                暂停
              </button>
              <button
                onClick={() => stopMutation.mutate()}
                className="flex items-center gap-2 rounded-lg bg-red-500 px-4 py-2 text-white hover:bg-red-600"
              >
                <Square className="h-4 w-4" />
                停止
              </button>
            </>
          )}
          {queueData?.status === 'paused' && (
            <>
              <button
                onClick={() => resumeMutation.mutate()}
                className="flex items-center gap-2 rounded-lg bg-green-500 px-4 py-2 text-white hover:bg-green-600"
              >
                <Play className="h-4 w-4" />
                恢复
              </button>
              <button
                onClick={() => stopMutation.mutate()}
                className="flex items-center gap-2 rounded-lg bg-red-500 px-4 py-2 text-white hover:bg-red-600"
              >
                <Square className="h-4 w-4" />
                停止
              </button>
            </>
          )}
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" />
            添加任务
          </button>
        </div>
      </div>

      {/* Progress */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-between text-sm">
            <span>任务进度</span>
            <span className="font-medium">{progress}%</span>
          </div>
          <div className="mt-3 h-4 rounded-full bg-secondary">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="mt-4 flex items-center gap-8">
            <div className="flex items-center gap-2">
              <div className="h-3 w-3 rounded-full bg-gray-400" />
              <span className="text-sm">总任务: {statusData?.total_tasks || 0}</span>
            </div>
            <div className="flex items-center gap-2">
              <CheckCircle className="h-4 w-4 text-green-500" />
              <span className="text-sm">已完成: {statusData?.completed_tasks || 0}</span>
            </div>
            <div className="flex items-center gap-2">
              <XCircle className="h-4 w-4 text-red-500" />
              <span className="text-sm">失败: {statusData?.failed_tasks || 0}</span>
            </div>
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-blue-500" />
              <span className="text-sm">剩余: {statusData?.progress?.remaining || 0}</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tasks */}
      <Card>
        <CardHeader>
          <CardTitle>任务列表</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {tasks?.data?.slice(0, 20).map((task: any) => (
              <div
                key={task.id}
                className="flex items-center justify-between rounded-lg border p-3"
              >
                <div className="flex-1 min-w-0">
                  <p className="truncate text-sm font-medium">{task.target}</p>
                  <p className="text-xs text-muted-foreground">
                    {task.task_type} · 重试 {task.retry_count}/{task.max_retries}
                  </p>
                </div>
                <span
                  className={cn(
                    'ml-4 rounded-full px-2 py-0.5 text-xs text-white',
                    getStatusColor(task.status)
                  )}
                >
                  {task.status}
                </span>
              </div>
            ))}
            {tasks?.data?.length === 0 && (
              <p className="text-center text-muted-foreground py-8">暂无任务</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Add Tasks Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <Card className="w-full max-w-lg">
            <CardHeader>
              <CardTitle>添加任务</CardTitle>
            </CardHeader>
            <CardContent>
              <textarea
                placeholder="输入文章 URL，每行一个..."
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                rows={8}
                className="w-full rounded-lg border bg-background px-3 py-2 outline-none focus:ring-2 focus:ring-primary"
              />
              <div className="mt-4 flex justify-end gap-2">
                <button
                  onClick={() => setShowAddModal(false)}
                  className="rounded-lg px-4 py-2 hover:bg-accent"
                >
                  取消
                </button>
                <button
                  onClick={() => addTasksMutation.mutate(newUrl.split('\n').filter(Boolean))}
                  disabled={!newUrl.trim() || addTasksMutation.isPending}
                  className="rounded-lg bg-primary px-4 py-2 text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  添加
                </button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
