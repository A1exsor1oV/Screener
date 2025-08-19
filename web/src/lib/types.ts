export type Quote = { ticker: string; bid: number; ask: number; last: number; time: number }
export type SymbolRow = { ticker: string; board: string; lot: number; currency: string }
export type ScreenerRow = {
  // Обязательные
  Акция: string;                 // ticker акции
  Фьючерс: string;               // код фьючерса
  'Дата див. отсечки': string | Date; // ISO или Date

  // Остальные
  'Размер див.(₽)'?: number | null;     // рубли
  'Див.(%)'?: number | null;            // проценты (например 8.5 => 8.5%)
  'Цена акции'?: number | null;         // ₽
  'Цена фьючерса'?: number | null;      // ₽
  'ГО(%)'?: number | null;              // проценты
  'Спред Входа(%)'?: number | null;     // проценты
  'Спред Выхода(%)'?: number | null;    // проценты
  'Справ. Стоимость'?: number | null;   // ₽ (fair price)
  'Дельта(%)'?: number | null;          // проценты
  'Всего(%)'?: number | null;           // проценты (итог)
  'Дней до отсечки'?: number | null;    // integer
  'Дней до эксп.'?: number | null;      // integer
  'Доход к отсечке(%)'?: number | null; // проценты
  'Доход к эксп.(%)'?: number | null;   // проценты
};
