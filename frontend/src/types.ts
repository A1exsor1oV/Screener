export type ScreenRow = {
aktsiya: string;
fyuchers: string;
div_ex_date?: string | null;
div_amount?: number | null;
has_div_before_exp: boolean;
spot: number;
fut: number;
go_per_share?: number | null;
spread_in?: number | null;
spread_out?: number | null;
fair?: number | null;
delta?: number | null;
total_capital?: number | null;
days_to_ex_date?: number | null;
days_to_exp?: number | null;
income_to_ex?: number | null;
income_to_exp?: number | null;
};


export type ColumnKey =
| "aktsiya" | "fyuchers" | "div_ex_date" | "div_amount" | "has_div_before_exp"
| "spot" | "fut" | "go_per_share" | "spread_in" | "spread_out" | "fair" | "delta"
| "total_capital" | "days_to_ex_date" | "days_to_exp" | "income_to_ex" | "income_to_exp";