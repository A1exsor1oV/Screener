/*import { createColumnHelper, type ColumnDef } from '@tanstack/react-table'
import type { ScreenerRow } from './types'

// форматтеры
const fmtRub = (v?: number | null) => (v !== null && v !== undefined ? v.toFixed(2) : '—')
const fmtPct = (v?: number | null) => (v !== null && v !== undefined ? `${v.toFixed(2)}%` : '—')
const fmtInt = (v?: number | null) => (v !== null && v !== undefined ? Math.trunc(v).toString() : '—')
const fmtDate = (d: string | Date | undefined) => {
  if (!d) return '—'
  const date = typeof d === 'string' ? new Date(d) : d
  return isNaN(date.getTime()) ? '—' : date.toLocaleDateString()
}

const h = createColumnHelper<ScreenerRow>()

export const screenerColumns: ColumnDef<ScreenerRow, unknown>[] = [
  h.accessor('Акция', { id: 'Акция', header: () => 'Акция', cell: i => <span className="font-medium">{i.getValue()}</span> }),
  h.accessor('Фьючерс', { id: 'Фьючерс', header: () => 'Фьючерс', cell: i => i.getValue() ?? '—' }),
  h.accessor('Дата див. отсечки', { id: 'Дата див. отсечки', header: () => 'Дата див. отсечки', cell: i => fmtDate(i.getValue()) }),
  h.accessor('Размер див.(₽)', { id: 'Размер див.(₽)', header: () => 'Размер див.(₽)', cell: i => fmtRub(i.getValue()) }),
  h.accessor('Див.(%)', { id: 'Див.(%)', header: () => 'Див.(%)', cell: i => fmtPct(i.getValue()) }),
  h.accessor('Цена акции', { id: 'Цена акции', header: () => 'Цена акции', cell: i => fmtRub(i.getValue()) }),
  h.accessor('Цена фьючерса', { id: 'Цена фьючерса', header: () => 'Цена фьючерса', cell: i => fmtRub(i.getValue()) }),
  h.accessor('ГО(%)', { id: 'ГО(%)', header: () => 'ГО(%)', cell: i => fmtPct(i.getValue()) }),
  h.accessor('Спред Входа(%)', { id: 'Спред Входа(%)', header: () => 'Спред Входа(%)', cell: i => fmtPct(i.getValue()) }),
  h.accessor('Спред Выхода(%)', { id: 'Спред Выхода(%)', header: () => 'Спред Выхода(%)', cell: i => fmtPct(i.getValue()) }),
  h.accessor('Справ. Стоимость', { id: 'Справ. Стоимость', header: () => 'Справ. Стоимость', cell: i => fmtRub(i.getValue()) }),
  h.accessor('Дельта(%)', { id: 'Дельта(%)', header: () => 'Дельта(%)', cell: i => fmtPct(i.getValue()) }),
  h.accessor('Всего(%)', { id: 'Всего(%)', header: () => 'Всего(%)', cell: i => fmtPct(i.getValue()) }),
  h.accessor('Дней до отсечки', { id: 'Дней до отсечки', header: () => 'Дней до отсечки', cell: i => fmtInt(i.getValue()) }),
  h.accessor('Дней до эксп.', { id: 'Дней до эксп.', header: () => 'Дней до эксп.', cell: i => fmtInt(i.getValue()) }),
  h.accessor('Доход к отсечке(%)', { id: 'Доход к отсечке(%)', header: () => 'Доход к отсечке(%)', cell: i => fmtPct(i.getValue()) }),
  h.accessor('Доход к эксп.(%)', { id: 'Доход к эксп.(%)', header: () => 'Доход к эксп.(%)', cell: i => fmtPct(i.getValue()) }),
]
*/
// web/src/lib/columns.tsx
import type { ColumnDef } from '@tanstack/react-table'
import type { ScreenerRow } from './types'

// форматтеры
const fmtRub = (v?: number | null) => (v !== null && v !== undefined ? v.toFixed(2) : '—')
const fmtPct = (v?: number | null) => (v !== null && v !== undefined ? `${v.toFixed(2)}%` : '—')
const fmtInt = (v?: number | null) => (v !== null && v !== undefined ? Math.trunc(v).toString() : '—')
const fmtDate = (d?: string | Date | null) => {
  if (!d) return '—'
  const date = typeof d === 'string' ? new Date(d) : d
  return isNaN(date.getTime()) ? '—' : date.toLocaleDateString()
}

export const screenerColumns: ColumnDef<ScreenerRow>[] = [
  {
    accessorKey: 'Акция',
    id: 'Акция',
    header: () => 'Акция',
    cell: i => <span className="font-medium">{i.getValue<string>()}</span>,
  },
  {
    accessorKey: 'Фьючерс',
    id: 'Фьючерс',
    header: () => 'Фьючерс',
    cell: i => i.getValue<string>() ?? '—',
  },
  {
    accessorKey: 'Дата див. отсечки',
    id: 'Дата див. отсечки',
    header: () => 'Дата див. отсечки',
    cell: i => fmtDate(i.getValue<string | null | undefined>()),
  },
  {
    accessorKey: 'Размер див.(₽)',
    id: 'Размер див.(₽)',
    header: () => 'Размер див.(₽)',
    cell: i => fmtRub(i.getValue<number | null | undefined>()),
  },
  {
    accessorKey: 'Див.(%)',
    id: 'Див.(%)',
    header: () => 'Див.(%)',
    cell: i => fmtPct(i.getValue<number | null | undefined>()),
  },
  {
    accessorKey: 'Цена акции',
    id: 'Цена акции',
    header: () => 'Цена акции',
    cell: i => fmtRub(i.getValue<number | null | undefined>()),
  },
  {
    accessorKey: 'Цена фьючерса',
    id: 'Цена фьючерса',
    header: () => 'Цена фьючерса',
    cell: i => fmtRub(i.getValue<number | null | undefined>()),
  },
  {
    accessorKey: 'ГО(%)',
    id: 'ГО(%)',
    header: () => 'ГО(%)',
    cell: i => fmtPct(i.getValue<number | null | undefined>()),
  },
  {
    accessorKey: 'Спред Входа(%)',
    id: 'Спред Входа(%)',
    header: () => 'Спред Входа(%)',
    cell: i => fmtPct(i.getValue<number | null | undefined>()),
  },
  {
    accessorKey: 'Спред Выхода(%)',
    id: 'Спред Выхода(%)',
    header: () => 'Спред Выхода(%)',
    cell: i => fmtPct(i.getValue<number | null | undefined>()),
  },
  {
    accessorKey: 'Справ. Стоимость',
    id: 'Справ. Стоимость',
    header: () => 'Справ. Стоимость',
    cell: i => fmtRub(i.getValue<number | null | undefined>()),
  },
  {
    accessorKey: 'Дельта(%)',
    id: 'Дельта(%)',
    header: () => 'Дельта(%)',
    cell: i => fmtPct(i.getValue<number | null | undefined>()),
  },
  {
    accessorKey: 'Всего(%)',
    id: 'Всего(%)',
    header: () => 'Всего(%)',
    cell: i => fmtPct(i.getValue<number | null | undefined>()),
  },
  {
    accessorKey: 'Дней до отсечки',
    id: 'Дней до отсечки',
    header: () => 'Дней до отсечки',
    cell: i => fmtInt(i.getValue<number | null | undefined>()),
  },
  {
    accessorKey: 'Дней до эксп.',
    id: 'Дней до эксп.',
    header: () => 'Дней до эксп.',
    cell: i => fmtInt(i.getValue<number | null | undefined>()),
  },
  {
    accessorKey: 'Доход к отсечке(%)',
    id: 'Доход к отсечке(%)',
    header: () => 'Доход к отсечке(%)',
    cell: i => fmtPct(i.getValue<number | null | undefined>()),
  },
  {
    accessorKey: 'Доход к эксп.(%)',
    id: 'Доход к эксп.(%)',
    header: () => 'Доход к эксп.(%)',
    cell: i => fmtPct(i.getValue<number | null | undefined>()),
  },
]

