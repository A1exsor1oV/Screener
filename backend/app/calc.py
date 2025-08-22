from datetime import date
from typing import Optional


def fair_value(S: float, r: float, days_to_exp: int, div_amount: Optional[float], days_to_cut: Optional[int]) -> float:
    T = max(0, days_to_exp) / 365
    pv_div = 0.0
    if div_amount and days_to_cut is not None and days_to_cut <= days_to_exp:
        pv_div = div_amount * (1 - r * max(0, days_to_exp - days_to_cut) / 365)
    return S * (1 + r * T) - pv_div


def carry_cost(S: float, r: float, days: int) -> float:
    return S * r * max(0, days) / 365