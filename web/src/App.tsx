import * as React from 'react'
import DataTable from './components/DataTable'
import { screenerColumns } from './lib/columns'
import type { ScreenerRow } from './lib/types'
import { Header } from './components/Header'
import { OrderTicket } from './components/OrderTicket'
import { ColumnControls } from './components/ColumnControls'
import { TickerFilter } from './components/TickerFilter'

export default function App() {
  const [wire, setWire] = React.useState<ScreenerRow[]>([])
  const [symbols, setSymbols] = React.useState<string[]>([])

  // состояние таблицы
  const allColumnIds = React.useMemo(() => screenerColumns.map(c => (c.id ?? (c as any).accessorKey) as string), [])
  const [columnVisibility, setColumnVisibility] = React.useState<Record<string, boolean>>(
    Object.fromEntries(allColumnIds.map(id => [id, true]))
  )
  const [columnOrder, setColumnOrder] = React.useState<string[]>(allColumnIds)

  // фильтр тикеров
  const [selectedTickers, setSelectedTickers] = React.useState<Set<string>>(new Set())

  // WS данные
  // тип «как пришло с бэка»
type RowWire = {
  Акция: string; Фьючерс: string;
  Дата_див_отсечки?: string; Размер_див_руб?: number;
  Див_pct?: number; Цена_акции?: number; Цена_фьючерса?: number; ГО_pct?: number;
  Спред_Входа_pct?: number; Спред_Выхода_pct?: number; Справ_Стоимость?: number;
  Дельта_pct?: number; Всего_pct?: number; Дней_до_отсечки?: number; Дней_до_эксп?: number;
  Доход_к_отсечке_pct?: number; Доход_к_эксп_pct?: number;
}

// конвертация «бэкенд → UI»
const toUi = (r: RowWire) => ({
  'Акция': r.Акция,
  'Фьючерс': r.Фьючерс,
  'Дата див. отсечки': r.Дата_див_отсечки,
  'Размер див.(₽)': r.Размер_див_руб,
  'Див.(%)': r.Див_pct,
  'Цена акции': r.Цена_акции,
  'Цена фьючерса': r.Цена_фьючерса,
  'ГО(%)': r.ГО_pct,
  'Спред Входа(%)': r.Спред_Входа_pct,
  'Спред Выхода(%)': r.Спред_Выхода_pct,
  'Справ. Стоимость': r.Справ_Стоимость,
  'Дельта(%)': r.Дельта_pct,
  'Всего(%)': r.Всего_pct,
  'Дней до отсечки': r.Дней_до_отсечки,
  'Дней до эксп.': r.Дней_до_эксп,
  'Доход к отсечке(%)': r.Доход_к_отсечке_pct,
  'Доход к эксп.(%)': r.Доход_к_эксп_pct,
} as const)

React.useEffect(() => {
  const ws = new WebSocket('ws://localhost:8000/ws/screener')
  ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data)
    if (msg.type === 'screener') {
      const rows = (msg.data as RowWire[]).map(toUi)
      setWire(rows as any) // если тип придирается — оставь as any
    }
  }
  return () => ws.close()
}, [])


  // список акций от бэка
  React.useEffect(() => {
    fetch('http://localhost:8000/symbols')
      .then(r => r.json())
      .then((arr: string[]) => {
        setSymbols(arr)
        setSelectedTickers(new Set(arr)) // по умолчанию показываем все
      })
      .catch(() => {})
  }, [])

  // применяем фильтр тикеров
  const data = React.useMemo(() => {
    if (selectedTickers.size === 0) return []
    return wire.filter(r => selectedTickers.has(r['Акция']))
  }, [wire, selectedTickers])

  return (
    <div className="min-h-dvh grid grid-rows-[auto_1fr]">
      <Header />
      <main className="container mx-auto py-4 space-y-4 px-4">
        <OrderTicket />

        <section className="bg-neutral-900/60 rounded-2xl p-3">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-base font-semibold">Котировки (демо)</h2>
            <div className="flex items-center gap-2">
              <ColumnControls
                allColumnIds={allColumnIds}
                lockedColumnIds={['Акция', 'Фьючерс', 'Дата див. отсечки']} // нельзя скрывать/таскать
                visible={columnVisibility}
                setVisible={setColumnVisibility}
                order={columnOrder}
                setOrder={setColumnOrder}
              />
              <TickerFilter
                allTickers={symbols}
                selected={selectedTickers}
                setSelected={setSelectedTickers}
              />
              <span className="text-xs opacity-60 hidden sm:inline">обновление по WS</span>
            </div>
          </div>

          <DataTable
            columns={screenerColumns}
            data={data}
            columnVisibility={columnVisibility}
            onColumnVisibilityChange={(updater) =>
              setColumnVisibility(prev => typeof updater === 'function' ? (updater as any)(prev) : updater)
            }
            columnOrder={columnOrder}
            onColumnOrderChange={(updater) =>
              setColumnOrder(prev => typeof updater === 'function' ? (updater as any)(prev) : updater)
            }
          />
        </section>
      </main>
    </div>
  )
}
