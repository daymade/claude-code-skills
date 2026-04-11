import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getQueues, createQueue, startQueue, pauseQueue, stopQueue } from '@/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Link } from 'react-router-dom'
import { Play, Pause, Square, Plus, List, Trash2 } from 'lucide-react'
import { getStatusColor, cn } from '@/lib/utils'

export default function Queues() {
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newQueueName, setNewQueueName] = useState('')
  const queryClient = useQueryClient()

  const { data: queues, isLoading } = useQuery({
    queryKey: ['queues'],
    queryFn: getQueues,
  })

  const createMutation = useMutation({
    mutationFn: (name: string) => createQueue(name, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queues'] })
      setShowCreateModal(false)
      setNewQueueName('')
    },
  })

  const startMutation = useMutation({
    mutationFn: startQueue,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['queues'] }),
  })

  const pauseMutation = useMutation({
    mutationFn: pauseQueue,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['queues'] }),
  })

  const stopMutation = useMutation({
    mutationFn: stopQueue,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['queues'] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">任务队列</h1>
          <p className="mt-2 text-muted-foreground">管理批量抓取任务</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-primary-foreground hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          新建队列
        </button>
      </div>

      {/* Queues List */}
      {isLoading ? (
        <div className="text-center py-12">加载中...</div>
      ) : queues?.data?.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <List className="mx-auto h-12 w-12 text-muted-foreground" />
            <p className="mt-4 text-muted-foreground">暂无任务队列</p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="mt-4 text-primary hover:underline"
            >
              创建第一个队列
            </button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {queues?.data?.map((queue: any) => {
            const progress = queue.total_tasks > 0
              ? Math.round((queue.completed_tasks / queue.total_tasks) * 100)
              : 0

            return (
              <Card key={queue.id}>
                <CardContent className="p-6">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3">
                        <h3 className="text-lg font-semibold">
                          <Link to={`/queues/${queue.id}`} className="hover:text-primary">
                            {queue.name}
                          </Link>
                        </h3>
                        <span
                          className={cn(
                            'rounded-full px-2 py-0.5 text-xs text-white',
                            getStatusColor(queue.status)
                          )}
                        >
                          {queue.status}
                        </span>
                      </div>

                      <div className="mt-4 flex items-center gap-8 text-sm text-muted-foreground">
                        <span>总任务: {queue.total_tasks}</span>
                        <span>已完成: {queue.completed_tasks}</span>
                        <span>失败: {queue.failed_tasks}</span>
                        <span>进度: {progress}%</span>
                      </div>

                      {/* Progress bar */}
                      <div className="mt-3 h-2 rounded-full bg-secondary">
                        <div
                          className="h-full rounded-full bg-primary transition-all"
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="ml-6 flex items-center gap-2">
                      {queue.status === 'idle' && (
                        <button
                          onClick={() => startMutation.mutate(queue.id)}
                          className="rounded-lg p-2 hover:bg-accent"
                          title="启动"
                        >
                          <Play className="h-5 w-5 text-green-500" />
                        </button>
                      )}
                      {queue.status === 'running' && (
                        <>
                          <button
                            onClick={() => pauseMutation.mutate(queue.id)}
                            className="rounded-lg p-2 hover:bg-accent"
                            title="暂停"
                          >
                            <Pause className="h-5 w-5 text-yellow-500" />
                          </button>
                          <button
                            onClick={() => stopMutation.mutate(queue.id)}
                            className="rounded-lg p-2 hover:bg-accent"
                            title="停止"
                          >
                            <Square className="h-5 w-5 text-red-500" />
                          </button>
                        </>
                      )}
                      {queue.status === 'paused' && (
                        <>
                          <button
                            onClick={() => startMutation.mutate(queue.id)}
                            className="rounded-lg p-2 hover:bg-accent"
                            title="恢复"
                          >
                            <Play className="h-5 w-5 text-green-500" />
                          </button>
                          <button
                            onClick={() => stopMutation.mutate(queue.id)}
                            className="rounded-lg p-2 hover:bg-accent"
                            title="停止"
                          >
                            <Square className="h-5 w-5 text-red-500" />
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle>新建队列</CardTitle>
            </CardHeader>
            <CardContent>
              <input
                type="text"
                placeholder="队列名称"
                value={newQueueName}
                onChange={(e) => setNewQueueName(e.target.value)}
                className="w-full rounded-lg border bg-background px-3 py-2 outline-none focus:ring-2 focus:ring-primary"
              />
              <div className="mt-4 flex justify-end gap-2">
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="rounded-lg px-4 py-2 hover:bg-accent"
                >
                  取消
                </button>
                <button
                  onClick={() => createMutation.mutate(newQueueName)}
                  disabled={!newQueueName || createMutation.isPending}
                  className="rounded-lg bg-primary px-4 py-2 text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  创建
                </button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
