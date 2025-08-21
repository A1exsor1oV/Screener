import type { ColumnDef } from '@tanstack/react-table'
import type { ScreenerRow } from './types'

/**
 * Column definitions for the screener table.
 *
 * Each column specifies its accessor key (matching a ScreenerRow property), an identifier,
 * a header renderer and a cell renderer. Formatting helpers are defined at the top
 * to avoid duplicating logic in every cell definition.
 */
const fmtRub = (v?: number | null) =>
  v !== null && v !== undefined ? v.toFixed(2) : '—'
const fmtPct = (v?: number | null) =>
  v !== null && v !== undefined ? `${v.toFixed(2)}%` : '—'
const fmtInt = (v?: number | null) =>
  v !== null && v !== undefined ? Math.trunc(v).toString() : '—'
const fmtDate = (d?: string | Date | null) => {
  if (!d) return '—'
  const date = typeof d === 'string' ? new Date(d) : d
  return isNaN(date.getTime()) ? '—' : date.toLocaleDateString()
}

export const screenerColumns: ColumnDef<ScreenerRow, any>[] = [
  {
    accessorKey: 'Акция',
    id: 'Акция',
    header: () => 'Акция',
    // Return the ticker symbol or a dash if missing.
    cell: i => i.getValue<string | undefined>() ?? '—',
  },
  {
    accessorKey: 'Фьючерс',
    id: 'Фьючерс',
    header: () => 'Фьючерс',
    cell: i => i.getValue<string | undefined>() ?? '—',
  },
  {
    accessorKey: 'Дата див. отсечки',
    id: 'Дата див. отсечки',
    header: () => 'Дата див. отсечки',
    cell: i => fmtDate(i.getValue<string | Date | undefined>()),
  },
  {
    accessorKey: 'Размер див.(₽)',
    id: 'Размер див.(₽)',
    header: () => 'Размер див.(₽)',
    cell: i => fmtRub(i.getValue<number | null>()),
  },
  {
    accessorKey: 'Див.(%)',
    id: 'Див.(%)',
    header: () => 'Див.(%)',
    cell: i => fmtPct(i.getValue<number | null>()),
  },
  {
    accessorKey: 'Цена акции',
    id: 'Цена акции',
    header: () => 'Цена акции',
    cell: i => fmtRub(i.getValue<number | null>()),
  },
  {
    accessorKey: 'Цена фьючерса',
    id: 'Цена фьючерса',
    header: () => 'Цена фьючерса',
    cell: i => fmtRub(i.getValue<number | null>()),
  },
  {
    accessorKey: 'ГО(%)',
    id: 'ГО(%)',
    header: () => 'ГО(%)',
    cell: i => fmtPct(i.getValue<number | null>()),
  },
  {
    accessorKey: 'Спред Входа(%)',
    id: 'Спред Входа(%)',
    header: () => 'Спред Входа(%)',
    cell: i => fmtPct(i.getValue<number | null>()),
  },
  {
    accessorKey: 'Спред Выхода(%)',
    id: 'Спред Выхода(%)',
    header: () => 'Спред Выхода(%)',
    cell: i => fmtPct(i.getValue<number | null>()),
  },
  {
    accessorKey: 'Справ. Стоимость',
    id: 'Справ. Стоимость',
    header: () => 'Справ. Стоимость',
    cell: i => fmtRub(i.getValue<number | null>()),
  },
  {
    accessorKey: 'Дельта(%)',
    id: 'Дельта(%)',
    header: () => 'Дельта(%)',
    cell: i => fmtPct(i.getValue<number | null>()),
  },
  {
    accessorKey: 'Всего(%)',
    id: 'Всего(%)',
    header: () => 'Всего(%)',
    cell: i => fmtPct(i.getValue<number | null>()),
  },
  {
    accessorKey: 'Дней до отсечки',
    id: 'Дней до отсечки',
    header: () => 'Дней до отсечки',
    cell: i => fmtInt(i.getValue<number | null>()),
  },
  {
    accessorKey: 'Дней до эксп.',
    id: 'Дней до эксп.',
    header: () => 'Дней до эксп.',
    cell: i => fmtInt(i.getValue<number | null>()),
  },
  {
    accessorKey: 'Доход к отсечке(%)',
    id: 'Доход к отсечке(%)',
    header: () => 'Доход к отсечке(%)',
    cell: i => fmtPct(i.getValue<number | null>()),
  },
  {
    accessorKey: 'Доход к эксп.(%)',
    id: 'Доход к эксп.(%)',
    header: () => 'Доход к эксп.(%)',
    cell: i => fmtPct(i.getValue<number | null>()),
  },
]

