from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List


class QuoteIn(BaseModel):
    board: str
    ticker: str
    last: float
    ts: datetime
    # расширение от QLua (необязательно для всех записей)
    name: Optional[str] = None # базовый спот (например SBER)
    ddiv: Optional[str] = None # "18.07.2025"
    divr: Optional[float] = None # 34.84
    utv: Optional[int] = None # 0/1/2
    lot_size: Optional[int] = None
    go_contract: Optional[float] = None
    days_to_mat_date: Optional[int] = None


class ScreenRow(BaseModel):
    aktsiya: str
    fyuchers: str
    div_ex_date: Optional[date]
    div_amount: Optional[float]
    has_div_before_exp: bool
    spot: float
    fut: float
    go_per_share: Optional[float]
    spread_in: Optional[float]
    spread_out: Optional[float]
    fair: Optional[float]
    delta: Optional[float]
    total_capital: Optional[float]
    days_to_ex_date: Optional[int]
    days_to_exp: Optional[int]
    income_to_ex: Optional[float]
    income_to_exp: Optional[float]


class FuturesPool(BaseModel):
    items: List[str]