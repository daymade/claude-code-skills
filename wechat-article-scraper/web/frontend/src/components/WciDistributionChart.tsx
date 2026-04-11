import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'

interface WciData {
  level: string
  count: number
}

interface WciDistributionChartProps {
  data: WciData[]
}

const COLORS = {
  '爆款(800+)': '#ef4444',
  '热门(500-799)': '#f97316',
  '良好(300-499)': '#3b82f6',
  '普通(<300)': '#6b7280',
  '未知': '#9ca3af',
}

export default function WciDistributionChart({ data }: WciDistributionChartProps) {
  const chartData = data.map((item) => ({
    name: item.level,
    value: item.count,
  }))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">WCI 传播指数分布</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) =>
                  `${name}: ${(percent * 100).toFixed(0)}%`
                }
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
              >
                {chartData.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={
                      COLORS[entry.name as keyof typeof COLORS] || '#8884d8'
                    }
                  />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}
