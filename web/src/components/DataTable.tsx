import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  type ColumnDef,
  type VisibilityState,
  type OnChangeFn,
} from '@tanstack/react-table'

/**
 * Generic data table component for the screener.
 *
 * Renders a dynamic table based off the provided column definitions
 * and data array. Also supports toggling column visibility and ordering.
 */
export interface TableProps<TData> {
  /** Column definitions describing how to access and render each field. */
  columns: ColumnDef<TData, any>[]
  /** Array of data rows to render in the table. */
  data: TData[]
  /** Optional visibility state keyed by column ID. */
  columnVisibility?: VisibilityState
  /** Callback fired when the visibility state changes. */
  onColumnVisibilityChange?: OnChangeFn<VisibilityState>
  /** Optional ordering of column IDs to control ordering. */
  columnOrder?: string[]
  /** Callback fired when column order changes. */
  onColumnOrderChange?: OnChangeFn<string[]>
}

export default function DataTable<TData>({
  columns,
  data,
  columnVisibility,
  onColumnVisibilityChange,
  columnOrder,
  onColumnOrderChange,
}: TableProps<TData>) {
  // Initialise the TanStack table with core row model and current state.
  const table = useReactTable({
    data,
    columns,
    state: {
      columnVisibility,
      columnOrder,
    },
    onColumnVisibilityChange,
    onColumnOrderChange,
    getCoreRowModel: getCoreRowModel(),
  })

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-neutral-700">
        <thead className="bg-neutral-900">
          {table.getHeaderGroups().map(headerGroup => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map(header => (
                <th
                  key={header.id}
                  colSpan={header.colSpan}
                  className="px-4 py-2 text-left text-xs font-medium text-neutral-300 uppercase tracking-wider"
                >
                  {header.isPlaceholder
                    ? null
                    : flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody className="bg-neutral-800 divide-y divide-neutral-700">
          {table.getRowModel().rows.map(row => (
            <tr key={row.id} className="hover:bg-neutral-700">
              {row.getVisibleCells().map(cell => (
                <td
                  key={cell.id}
                  className="px-4 py-2 whitespace-nowrap text-sm text-neutral-100"
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
