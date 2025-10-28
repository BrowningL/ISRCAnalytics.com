import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface TopTracksTableProps {
  date: string
}

export function TopTracksTable({ date }: TopTracksTableProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['top-deltas', date],
    queryFn: () => api.getTopDeltas(date, 100),
    enabled: !!date,
  })

  if (isLoading) return <div>Loading tracks...</div>
  if (error) return <div>Error loading tracks</div>
  if (!data?.rows) return <div>No data available for this date</div>

  return (
    <div className="relative overflow-x-auto max-h-[500px] overflow-y-auto">
      <Table>
        <TableHeader className="sticky top-0 bg-white dark:bg-gray-900">
          <TableRow>
            <TableHead className="w-12">#</TableHead>
            <TableHead>ISRC</TableHead>
            <TableHead>Title</TableHead>
            <TableHead>Artist</TableHead>
            <TableHead className="text-right">Δ</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.rows.map((track, index) => (
            <TableRow key={`${track.isrc}-${index}`}>
              <TableCell className="font-medium">{index + 1}</TableCell>
              <TableCell className="font-mono text-xs">{track.isrc}</TableCell>
              <TableCell>{track.title}</TableCell>
              <TableCell>{track.artist}</TableCell>
              <TableCell className="text-right font-semibold">
                {track.delta.toLocaleString()}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
