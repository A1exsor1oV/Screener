from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from datetime import date, datetime, timedelta

from .models import ScreenRow, FuturesPool
from .calc import fair_value, carry_cost
from .quik_ingest import QUOTES, FUTS, META, DIVS, start_quik_listener
from .settings import settings

app = FastAPI(title="QUIK Screener API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Загрузка пула фьючерсов из txt

def load_futures_pool(path: str) -> List[str]:
    items = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"): continue
                items.append(s)
    except FileNotFoundError:
        pass
    return items

FUTURES_POOL = load_futures_pool(settings.FUTURES_POOL_PATH)

@app.on_event("startup")
async def boot():
    start_quik_listener()

@app.get("/config/futures", response_model=FuturesPool)
def get_pool():
    return FuturesPool(items=FUTURES_POOL)

@app.post("/config/futures", response_model=FuturesPool)
def set_pool(body: FuturesPool):
    global FUTURES_POOL
    FUTURES_POOL = [x.strip() for x in body.items if x.strip()]
    with open(settings.FUTURES_POOL_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(FUTURES_POOL) + "\n")
    return FuturesPool(items=FUTURES_POOL)

@app.get("/screen", response_model=List[ScreenRow])
def screen(tickers: List[str] = Query(default=["SBER","YNDX"])):
    rows: List[ScreenRow] = []
    today = date.today()

    # Подберём все фьючерсы из пула, относящиеся к тикерам (по префиксу совпадения)
    # Пример: для SBER ищем SECID, начинающиеся с "SR"/"SBRF" — но точнее нам шлёт QLua.
    # Здесь берём любые, что есть в кэше FUTS и входят в FUTURES_POOL.

    for spot in tickers:
        # Ищем спот-цену
        S = QUOTES.get(f"TQBR:{spot}") or 0.0

        # Ищем фьючерс(ы) из пула, которые есть в кеше
        matched_keys = [k for k in FUTS.keys() if k.startswith("SPBFUT:") and k.split(":",1)[1] in FUTURES_POOL]
        # эвристика: берём ближайший по DAYS_TO_MAT_DATE
        best = None
        best_days = 10**9
        for key in matched_keys:
            sec = key.split(":",1)[1]
            m = META.get(sec) or {}
            d2m = m.get("days_to_mat_date")
            if d2m is None:
                continue
            if d2m < best_days:
                best_days = d2m
                best = sec

        if not best and matched_keys:
            best = matched_keys[0].split(":",1)[1]

        if not best:
            # Нет фьючерса в пуле/кэше, пропускаем строку
            continue

        F_contract = FUTS.get(f"SPBFUT:{best}") or 0.0
        meta = META.get(best) or {}
        lot = meta.get("lot_size") or 1
        go_contract = meta.get("go_contract")
        days_exp = meta.get("days_to_mat_date")

        F = F_contract / lot if lot else F_contract
        go_per_share = (go_contract / lot) if (go_contract and lot) else None

        # дивиденды по базовому споту
        d = DIVS.get(spot, {})
        ex_str = d.get("ex_date")
        ex_date = None
        if ex_str:
            # формат "DD.MM.YYYY"
            ex_date = datetime.strptime(ex_str, "%d.%m.%Y").date()
        amount = d.get("amount")

        days_cut = (ex_date - today).days if ex_date else None

        fair = None
        delta = None
        spread_out = None
        if days_exp is not None:
            fair = fair_value(S, settings.RISK_FREE, days_exp, amount, days_cut)
            delta = F - fair
            spread_out = delta

        spread_in = F - S if F and S else None
        total_cap = (S + (go_per_share or 0)) if S else None

        inc_cut = None
        if days_cut is not None:
            inc_cut = (amount or 0) - carry_cost(S, settings.RISK_FREE, max(0, days_cut))

        inc_exp = None
        if days_exp is not None:
            inc_exp = (F - S) - carry_cost(S, settings.RISK_FREE, max(0, days_exp)) + ((amount or 0) if (days_cut is not None and days_cut <= days_exp) else 0)

        rows.append(ScreenRow(
            aktsiya=spot, fyuchers=best,
            div_ex_date=ex_date, div_amount=amount,
            has_div_before_exp=(days_cut is not None and days_exp is not None and days_cut <= days_exp),
            spot=S, fut=F, go_per_share=go_per_share,
            spread_in=spread_in, spread_out=spread_out, fair=fair, delta=delta,
            total_capital=total_cap,
            days_to_ex_date=(max(0, days_cut) if days_cut is not None else None),
            days_to_exp=(max(0, days_exp) if days_exp is not None else None),
            income_to_ex=inc_cut, income_to_exp=inc_exp
        ))

    return rows