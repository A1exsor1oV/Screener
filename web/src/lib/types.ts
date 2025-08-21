export type Quote = { ticker: string; bid: number; ask: number; last: number; time: number }
export type SymbolRow = { ticker: string; board: string; lot: number; currency: string }
// web/src/lib/types.ts
export type ScreenerRow = {
  'Акция': string
  'Фьючерс': string
  'Дата див. отсечки'?: string | null
  'Размер див.(₽)'?: number | null
  'Див.(%)'?: number | null
  'Цена акции'?: number | null
  'Цена фьючерса'?: number | null
  'ГО(%)'?: number | null
  'Спред Входа(%)'?: number | null
  'Спред Выхода(%)'?: number | null
  'Справ. Стоимость'?: number | null
  'Дельта(%)'?: number | null
  'Всего(%)'?: number | null
  'Дней до отсечки'?: number | null
  'Дней до эксп.'?: number | null
  'Доход к отсечке(%)'?: number | null
  'Доход к эксп.(%)'?: number | null
}


