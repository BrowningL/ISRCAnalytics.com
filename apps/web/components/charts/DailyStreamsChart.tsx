import { useQuery } from '@tanstack/react-query'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js'
import { api } from '@/lib/api'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
)

interface DailyStreamsChartProps {
  days: string
}

export function DailyStreamsChart({ days }: DailyStreamsChartProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['daily-streams', days],
    queryFn: () => api.getTotalDailyStreams(days),
  })

  if (isLoading) return <div>Loading chart...</div>
  if (error) return <div>Error loading chart</div>
  if (!data) return null

  const chartData = {
    labels: data.labels,
    datasets: [
      {
        label: 'Streams Δ (sum)',
        data: data.values,
        borderColor: 'rgb(59, 130, 246)',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        tension: 0.3,
        fill: true,
      },
    ],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        callbacks: {
          label: (context: any) => {
            return ` ${context.parsed.y.toLocaleString()} streams`
          },
        },
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: {
          callback: function(value: any) {
            return value.toLocaleString()
          },
        },
      },
    },
  }

  return (
    <div style={{ height: '300px' }}>
      <Line data={chartData} options={options} />
    </div>
  )
}
