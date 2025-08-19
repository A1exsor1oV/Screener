import * as React from 'react'
import {
  useReactTable, getCoreRowModel, flexRender,
  type ColumnDef, type VisibilityState, type OnChangeFn, type Updater
} from '@tanstack/react-table'

type TableProps<TData> = {
  columns: ColumnDef<TData, unknown>[]
  data: TData[]
  columnVisibility?: VisibilityState
  onColumnVisibilityChange?: OnChangeFn<VisibilityState>
  columnOrder?: string[]
  onColumnOrderChange?: OnChangeFn<string[]>
}

export default function DataTable<TData>({
  columns, data, columnVisibility, onColumnVisibilityChange,
  columnOrder, onColumnOrderChange
}: TableProps<TData>) {
  const table = useReactTable<TData>({
    data,
    columns,
    state: { columnVisibility, columnOrder },
    onColumnVisibilityChange,
    onColumnOrderChange,
    getCoreRowModel: getCoreRowModel(),
  })

  return (
    <div className="w-full overflow-x-auto">
      <table className="min-w-full border-separate border-spacing-y-1">
        <thead className="sticky top-0 z-10 bg-neutral-900/80 backdrop-blur">
          {table.getHeaderGroups().map(hg => (
            <tr key={hg.id}>
              {hg.headers.map(h => (
                <th key={h.id} className="text-left text-sm font-semibold px-3 py-2">
                  {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map(r => (
            <tr key={r.id} className="bg-neutral-900/40 hover:bg-neutral-800/50">
              {r.getVisibleCells().map(c => (
                <td key={c.id} className="px-3 py-2 text-sm whitespace-nowrap">
                  {flexRender(c.column.columnDef.cell, c.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
