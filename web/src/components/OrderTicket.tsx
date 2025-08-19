import * as React from 'react'
import axios from 'axios'

export function OrderTicket() {
  const [ticker, setTicker] = React.useState('SBER')
  const [side, setSide] = React.useState<'buy'|'sell'>('buy')
  const [qty, setQty] = React.useState(1)
  const [price, setPrice] = React.useState<string>('')  // пусто → market
  const [log, setLog] = React.useState<string>('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const payload = { account: 'demo', ticker, side, type: price ? 'limit' : 'market', qty, price: price ? Number(price) : undefined }
    const { data } = await axios.post('http://localhost:8000/orders', payload)
    setLog(JSON.stringify(data, null, 2))
  }

  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-2 sm:grid-cols-4 bg-neutral-900/60 rounded-2xl p-3">
      <input value={ticker} onChange={e=>setTicker(e.target.value.toUpperCase())} placeholder="Тикер" className="px-3 py-2 rounded-md bg-neutral-800" />
      <select value={side} onChange={e=>setSide(e.target.value as any)} className="px-3 py-2 rounded-md bg-neutral-800">
        <option value="buy">Buy</option>
        <option value="sell">Sell</option>
      </select>
      <input type="number" min={1} value={qty} onChange={e=>setQty(Number(e.target.value))} placeholder="Qty" className="px-3 py-2 rounded-md bg-neutral-800" />
      <input value={price} onChange={e=>setPrice(e.target.value)} placeholder="Limit price (опц.)" className="px-3 py-2 rounded-md bg-neutral-800" />
      <button className="col-span-2 sm:col-span-1 px-3 py-2 rounded-md bg-green-600 hover:bg-green-500 font-semibold">Отправить</button>
      <pre className="col-span-2 sm:col-span-3 text-xs bg-neutral-950 p-2 rounded-md overflow-auto max-h-40">{log}</pre>
    </form>
  )
}
