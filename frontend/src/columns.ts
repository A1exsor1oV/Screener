import type { ColumnKey } from "./types";

export const DEFAULT_COLUMNS: ColumnKey[] = [
  "aktsiya","fyuchers","div_ex_date","div_amount","has_div_before_exp",
  "spot","fut","go_per_share","spread_in","spread_out","fair","delta",
  "total_capital","days_to_ex_date","days_to_exp","income_to_ex","income_to_exp"
];

export const COLUMN_LABELS: Record<ColumnKey,string> = {
  aktsiya:"АКЦИЯ", fyuchers:"ФЬЮЧЕРС",
  div_ex_date:"ДАТА ДИВ. ОТСЕЧКИ", div_amount:"РАЗМЕР ДИВ.(₽)",
  has_div_before_exp:"ДИВ.(%)", spot:"ЦЕНА АКЦИИ", fut:"ЦЕНА ФЬЮЧЕРСА",
  go_per_share:"ГО(%)", spread_in:"СПРЕД ВХОДА(%)", spread_out:"СПРЕД ВЫХОДА(%)",
  fair:"СПРАВ. СТОИМОСТЬ", delta:"ДЕЛЬТА(%)", total_capital:"ВСЕГО(%)",
  days_to_ex_date:"ДНЕЙ ДО ОТСЕЧКИ", days_to_exp:"ДНЕЙ ДО ЭКСП.",
  income_to_ex:"ДОХОД К ОТСЕЧКЕ(%)", income_to_exp:"ДОХОД К ЭКСП.(%)"
};
