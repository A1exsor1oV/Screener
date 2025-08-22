from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from datetime import date, datetime

from .models import ScreenRow, FuturesPool
from .calc import fair_value, carry_cost
from .quik_ingest import QUOTES, FUTS, META, DIVS, FUT_NAME, start_quik_listener
from .settings import settings

app = FastAPI(title="QUIK Screener API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Алиасы тикеров спота (что приходит с фронта -> как называется в QUIK/таблице)
ALIASES = {
    "YNDX": "YDEX",
    # добавляй при необходимости
}

# ---- загрузка/сохранение пула фьючерсов из txt ----
def load_futures_pool(path: str) -> List[str]:
    items: List[str] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                items.append(s)
    except FileNotFoundError:
        pass
    return items

FUTURES_POOL = load_futures_pool(settings.FUTURES_POOL_PATH)

@app.on_event("startup")
async def boot():
    # важно: слушатель стартанёт ровно один раз благодаря защите внутри
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

# ---- основной эндпоинт скринера ----
@app.get("/screen", response_model=List[ScreenRow])
def screen(tickers: List[str] = Query(default=["SBER", "YNDX"])):
    rows: List[ScreenRow] = []
    today = date.today()

    for spot in tickers:
        spot_alias = ALIASES.get(spot, spot)

        # Цена акции
        S = QUOTES.get(f"TQBR:{spot_alias}") or 0.0

        # Подбор фьючерса: только из пула и с тем же базовым активом
        candidates: List[str] = []
        for key in list(FUTS.keys()):
            if not key.startswith("SPBFUT:"):
                continue
            sec = key.split(":", 1)[1]
            if sec not in FUTURES_POOL:
                continue
            if FUT_NAME.get(sec) != spot_alias:
                continue
            candidates.append(sec)

        # выбрать ближайший по DAYS_TO_MAT_DATE
        best, best_days = None, 10**9
        for sec in candidates:
            d2m = (META.get(sec) or {}).get("days_to_mat_date")
            if d2m is not None and d2m < best_days:
                best, best_days = sec, d2m

        if not best and candidates:
            best = candidates[0]
        if not best:
            # нет подходящей серии — пропускаем бумагу
            continue

        # Цена фьючерса: нормализуем до цены за 1 акцию
        F_contract = FUTS.get(f"SPBFUT:{best}") or 0.0
        meta = META.get(best) or {}
        lot = meta.get("lot_size") or 1
        go_contract = meta.get("go_contract")
        days_exp = meta.get("days_to_mat_date")
        F = F_contract / lot if lot else F_contract
        go_per_share = (go_contract / lot) if (go_contract and lot) else None

        # Дивиденды по базовой акции
        d = DIVS.get(spot_alias, {})
        ex_str = d.get("ex_date")
        ex_date = None
        if ex_str:
            try:
                ex_date = datetime.strptime(ex_str, "%d.%m.%Y").date()
            except Exception:
                ex_date = None
        amount_raw = d.get("amount")
        try:
            amount = float(amount_raw) if amount_raw is not None else None
        except Exception:
            amount = None

        days_cut = (ex_date - today).days if ex_date else None

        # Расчёты
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
            inc_exp = (F - S) - carry_cost(S, settings.RISK_FREE, max(0, days_exp)) + (
                (amount or 0) if (days_cut is not None and days_cut <= days_exp) else 0
            )

        rows.append(ScreenRow(
            aktsiya=spot,                 # показываем оригинальный тикер с фронта
            fyuchers=best,
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
