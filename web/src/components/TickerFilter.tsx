import * as React from 'react'

type Props = {
  allTickers: string[]
  selected: Set<string>
  setSelected: (next: Set<string>) => void
}

export function TickerFilter({ allTickers, selected, setSelected }: Props) {
  const [open, setOpen] = React.useState(false)

  function toggle(t: string) {
    const next = new Set(selected)
    next.has(t) ? next.delete(t) : next.add(t)
    setSelected(next) // разрешаем пустой набор — таблица покажет все (см. фильтр выше)
  }

  function selectAll() {
    setSelected(new Set(allTickers))
  }

  function clearAll() {
    setSelected(new Set()) // ← теперь реально «очистить» (и таблица покажет все)
  }

  return (
    <div className="relative">
      <button onClick={() => setOpen(v => !v)} className="px-3 py-2 rounded-md bg-neutral-800 hover:bg-neutral-700 text-sm">
        Акции
      </button>
      {open && (
        <div className="absolute z-30 mt-2 w-56 rounded-lg border border-neutral-800 bg-neutral-900 p-2 shadow-lg">
          <div className="flex justify-between mb-2 gap-2">
            <button onClick={selectAll} className="text-xs px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700">Выбрать все</button>
            <button onClick={clearAll} className="text-xs px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700">Сбросить</button>
          </div>
          <div className="max-h-72 overflow-auto space-y-1 pr-1">
            {allTickers.map(t => (
              <label key={t} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={selected.has(t)} onChange={() => toggle(t)} />
                <span>{t}</span>
              </label>
            ))}
          </div>
          <div className="text-right mt-2">
            <button onClick={() => setOpen(false)} className="text-sm opacity-70 hover:opacity-100">Закрыть</button>
          </div>
        </div>
      )}
    </div>
  )
}
