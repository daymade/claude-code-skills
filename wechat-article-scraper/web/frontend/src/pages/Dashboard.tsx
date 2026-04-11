import { useQuery } from '@tanstack/react-query'
import { FileText, Users, BarChart3, Activity } from 'lucide-react'
import { getStatistics } from '@/api'
import { formatNumber } from '@/lib/utils'
import StatCard from '@/components/StatCard'
import CategoryChart from '@/components/CategoryChart'
import WciDistributionChart from '@/components/WciDistributionChart'
import RecentArticles from '@/components/RecentArticles'

export default function Dashboard() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['statistics'],
    queryFn: getStatistics,
  })

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="text-lg text-muted-foreground">加载中...</div>
      </div>
    )
  }

  const statsData = stats?.data

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">仪表板</h1>
        <p className="mt-2 text-muted-foreground">
          微信文章抓取系统概览
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="总文章数"
          value={formatNumber(statsData?.total_articles)}
          icon={FileText}
          description="已抓取的文章总数"
        />
        <StatCard
          title="作者数"
          value={statsData?.top_authors?.length || 0}
          icon={Users}
          description="不同作者数量"
        />
        <StatCard
          title="分类数"
          value={statsData?.category_distribution?.length || 0}
          icon={BarChart3}
          description="文章分类数量"
        />
        <StatCard
          title="系统状态"
          value="运行中"
          icon={Activity}
          description="最后更新: 刚刚"
        />
      </div>

      {/* Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        <CategoryChart data={statsData?.category_distribution || []} />
        <WciDistributionChart data={statsData?.wci_distribution || []} />
      </div>

      {/* Recent Articles */}
      <RecentArticles />
    </div>
  )
}
