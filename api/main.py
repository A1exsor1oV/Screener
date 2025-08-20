# -*- coding: utf-8 -*-
# FastAPI + MOEX ISS (реальные данные, стакан и ГО)
import os, json, time, asyncio
from datetime import datetime, timezone, date
from typing import Optional, Dict, List

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# -------------------------------------------------
# Конфиг
# -------------------------------------------------
SYMBOLS_FILE = os.path.join(os.path.dirname(__file__), "symbols.json")

HTTP_TIMEOUT = 10.0
REFRESH_SEC = 5.0
DIV_REFRESH_SEC = 3600.0

YEAR_DEC = 2025           # декабрьская серия для UI ***-12.25
MONTH_LETTER = "Z"        # декабрь = Z
YEAR_LAST_DIGIT = "5"     # 2025 -> '5' для буквенного кода (ISS)
FUT_BOARD = "RFUD"        # срочный рынок, основной борд
SPOT_BOARD = "TQBR"       # акции T+

# акция -> рут фьючерса
FUT_ROOT: Dict[str, str] = {
    "SBER": "SBRF",
    "GAZP": "GAZR",
    "LKOH": "LKOH",
    "MOEX": "MOEX",
    "PLZL": "PLZL",
    "X5":   "FIVE",
    # добавляй по мере необходимости
}

# -------------------------------------------------
# Pydantic модель строки
# -------------------------------------------------
class ScreenerRow(BaseModel):
    Акция: str
    Фьючерс: str
    Дата_див_отсечки: Optional[str] = None
    Размер_див_руб: Optional[float] = None
    Див_pct: Optional[float] = None
    Цена_акции: Optional[float] = None
    Цена_фьючерса: Optional[float] = None
    ГО_pct: Optional[float] = None
    Спред_Входа_pct: Optional[float] = None
    Спред_Выхода_pct: Optional[float] = None
    Справ_Стоимость: Optional[float] = None
    Дельта_pct: Optional[float] = None
    Всего_pct: Optional[float] = None
    Дней_до_отсечки: Optional[int] = None
    Дней_до_эксп: Optional[int] = None
    Доход_к_отсечке_pct: Optional[float] = None
    Доход_к_эксп_pct: Optional[float] = None

# -------------------------------------------------
# FastAPI
# -------------------------------------------------
app = FastAPI(title="Screener API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# -------------------------------------------------
# Утилиты
# -------------------------------------------------
def _now_ts() -> float: return time.time()

def ui_fut_code(share: str) -> str:
    return f"{share}-12.{str(YEAR_DEC)[-2:]}"  # SBER-12.25

def letter_fut_code(share: str) -> Optional[str]:
    root = FUT_ROOT.get(share)
    if not root: return None
    return f"{root}{MONTH_LETTER}{YEAR_LAST_DIGIT}"  # SBRFZ5

def load_symbols() -> List[str]:
    try:
        with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [str(x).upper() for x in data if x]
    except Exception:
        return ["SBER", "GAZP", "LKOH", "MOEX", "PLZL", "X5"]

SYMBOLS = load_symbols()

# -------------------------------------------------
# Кэш
# -------------------------------------------------
CACHE: Dict[str, dict] = {
    "spot": {},   # 'SBER': {'last':..., 'bid':..., 'offer':..., 'ts':...}
    "fut": {},    # 'SBRFZ5': {'last':..., 'bid':..., 'offer':..., 'im':..., 'minstep':..., 'stepprice':..., 'lotvolume':..., 'exp':..., 'ts':...}
    "divs": {},   # 'SBER': {'ex_date':..., 'value':..., 'ts':...}
}

# -------------------------------------------------
# Запросы ISS
# Документация примеров колонок marketdata/securities: https://moexalgo.github.io/des/realtime/
# -------------------------------------------------
async def iss_get(client: httpx.AsyncClient, url: str) -> dict:
    r = await client.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()

async def fetch_spot_quote(client: httpx.AsyncClient, secid: str) -> Optional[dict]:
    url = (
        f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/{SPOT_BOARD}/"
        f"securities/{secid}.json?iss.meta=off&marketdata.columns=LAST,BID,OFFER"
    )
    try:
        js = await iss_get(client, url)
        cols = js.get("marketdata", {}).get("columns", [])
        data = js.get("marketdata", {}).get("data", [])
        if not (cols and data and data[0]): return None
        c = {n: i for i, n in enumerate(cols)}
        return {
            "last": _num(data[0][c.get("LAST")]),
            "bid":  _num(data[0][c.get("BID")]),
            "offer":_num(data[0][c.get("OFFER")]),
        }
    except Exception:
        return None

async def fetch_future_quote_and_params(client: httpx.AsyncClient, fut_secid: str) -> Optional[dict]:
    # тянем одним запросом marketdata + securities (RFUD)
    url = (
        f"https://iss.moex.com/iss/engines/futures/markets/forts/boards/{FUT_BOARD}/"
        f"securities/{fut_secid}.json?iss.meta=off&marketdata.columns=LAST,BID,OFFER"
        f"&securities.columns=SECID,EXPIRATION,INITIALMARGIN,MINSTEP,STEPPRICE,LOTVOLUME"
    )
    try:
        js = await iss_get(client, url)

        # marketdata
        md_cols = js.get("marketdata", {}).get("columns", [])
        md_data = js.get("marketdata", {}).get("data", [])
        md = None
        if md_cols and md_data and md_data[0]:
            mc = {n: i for i, n in enumerate(md_cols)}
            md = {
                "last":  _num(md_data[0][mc.get("LAST")]),
                "bid":   _num(md_data[0][mc.get("BID")]),
                "offer": _num(md_data[0][mc.get("OFFER")]),
            }

        # securities (INITIALMARGIN, MINSTEP, STEPPRICE, LOTVOLUME, EXPIRATION)
        sc_cols = js.get("securities", {}).get("columns", [])
        sc_data = js.get("securities", {}).get("data", [])
        sc = None
        if sc_cols and sc_data and sc_data[0]:
            sc_map = {n: i for i, n in enumerate(sc_cols)}
            row = sc_data[0]
            sc = {
                "exp": row[sc_map.get("EXPIRATION")],
                "im": _num(row[sc_map.get("INITIALMARGIN")]),
                "minstep": _num(row[sc_map.get("MINSTEP")]),
                "stepprice": _num(row[sc_map.get("STEPPRICE")]),
                "lotvolume": _num(row[sc_map.get("LOTVOLUME")]),
            }

        if not md: md = {}
        if not sc: sc = {}
        return {**md, **sc}
    except Exception:
        return None

async def fetch_dividend_info(client: httpx.AsyncClient, secid: str) -> dict:
    # Берём ближайшую будущую ex-date из справочника дивидендов
    url = f"https://iss.moex.com/iss/securities/{secid}/dividends.json?iss.meta=off"
    out = {"ex_date": None, "value": None}
    try:
        js = await iss_get(client, url)
        cols = js.get("dividends", {}).get("columns", [])
        data = js.get("dividends", {}).get("data", [])
        if not (cols and data): return out
        c = {n: i for i, n in enumerate(cols)}
        today = datetime.now(timezone.utc).date()
        future = []
        for row in data:
            # варианты полей в разных записях
            exd = row[c.get("registry_close_date")] or row[c.get("close_date")] or row[c.get("date")]
            val = row[c.get("value")]
            if not exd: continue
            try:
                d = datetime.fromisoformat(str(exd)).date()
            except Exception:
                continue
            if d >= today:
                future.append((d, _num(val)))
        if future:
            future.sort(key=lambda x: x[0])
            d, v = future[0]
            out = {"ex_date": d.isoformat(), "value": v}
    except Exception:
        pass
    return out

def _num(x):
    try:
        return float(x) if x is not None else None
    except Exception:
        return None

# --- найти действующую серию фьючерса на RFUD через табличный список
async def find_fut_secid_on_board(client: httpx.AsyncClient, share: str, year_dec: int = 2025) -> Optional[dict]:
    root = FUT_ROOT.get(share)
    if not root:
        return None
    url = (
        f"https://iss.moex.com/iss/engines/futures/markets/forts/boards/{FUT_BOARD}/securities.json"
        f"?iss.meta=off&limit=5000&securities.columns=SECID,SHORTNAME,EXPIRATION&query={root}"
    )
    js = await iss_get(client, url)
    cols = js.get("securities", {}).get("columns", [])
    data = js.get("securities", {}).get("data", [])
    if not cols or not data:
        return None
    c = {n: i for i, n in enumerate(cols)}
    rows = []
    for row in data:
        secid = row[c["SECID"]]
        exp   = row[c["EXPIRATION"]]
        if not isinstance(secid, str):
            continue
        if not secid.startswith(root):
            continue
        rows.append({"secid": secid, "exp": exp})

    if not rows:
        return None

    # приоритет SBER-12.25 (декабрь целевого года)
    target_suffix = f"-12.{str(year_dec)[-2:]}"
    best = next((r for r in rows if r["secid"].endswith(target_suffix)), None)
    if not best:
        # ближайшая «квартальная» вперёд по дате EXPIRATION
        def exp_date(r):
            try: return datetime.fromisoformat(str(r["exp"])).date()
            except: return date.max
        rows.sort(key=exp_date)
        best = rows[0]
    return best  # {'secid': 'SBRF-12.25', 'exp': '2025-12-XX'}

async def fetch_fut_md_and_params(
    client: httpx.AsyncClient, secid: str
) -> Optional[dict]:
    result = {"last": None, "bid": None, "offer": None, "exp": None,
              "im": None, "minstep": None, "stepprice": None, "lotvolume": None}

    # (A) batch marketdata (часто это единственное место, где есть L1)
    md_url = (
        f"https://iss.moex.com/iss/engines/futures/markets/forts/boards/{FUT_BOARD}/"
        f"securities.json?iss.meta=off&securities={secid}&marketdata.columns=SECID,LAST,BID,OFFER"
    )
    try:
        js = await iss_get(client, md_url)
        cols = js.get("marketdata", {}).get("columns", [])
        data = js.get("marketdata", {}).get("data", [])
        if cols and data:
            c = {n: i for i, n in enumerate(cols)}
            for row in data:
                if row[c["SECID"]] != secid:
                    continue
                result["last"]  = _num(row[c.get("LAST")])
                result["bid"]   = _num(row[c.get("BID")])
                # OFFER в marketdata именно OFFER (не ASK)
                result["offer"] = _num(row[c.get("OFFER")])
                break
    except Exception:
        pass

    # (B) параметры из securities (INITIALMARGIN, MINSTEP, STEPPRICE, LOTVOLUME, EXPIRATION)
    sec_url = (
        f"https://iss.moex.com/iss/engines/futures/markets/forts/boards/{FUT_BOARD}/"
        f"securities/{secid}.json?iss.meta=off&securities.columns=SECID,EXPIRATION,INITIALMARGIN,MINSTEP,STEPPRICE,LOTVOLUME"
    )
    try:
        js = await iss_get(client, sec_url)
        cols = js.get("securities", {}).get("columns", [])
        data = js.get("securities", {}).get("data", [])
        if cols and data and data[0]:
            c = {n: i for i, n in enumerate(cols)}
            row = data[0]
            result["exp"]       = row[c.get("EXPIRATION")]
            result["im"]        = _num(row[c.get("INITIALMARGIN")])
            result["minstep"]   = _num(row[c.get("MINSTEP")])
            result["stepprice"] = _num(row[c.get("STEPPRICE")])
            result["lotvolume"] = _num(row[c.get("LOTVOLUME")])
    except Exception:
        pass

    # (C) если bid/offer пустые — возьмём лучшую пару из orderbook (стакан)
    if result["bid"] is None or result["offer"] is None:
        ob_url = (
            f"https://iss.moex.com/iss/engines/futures/markets/forts/securities/{secid}/orderbook.json?iss.meta=off&depth=1"
        )
        try:
            js = await iss_get(client, ob_url)
            bids = js.get("bids", {}).get("data", [])
            offers = js.get("offers", {}).get("data", [])
            if bids and bids[0]:
                # таблица: [PRICE, ...]
                result["bid"] = _num(bids[0][0])
            if offers and offers[0]:
                result["offer"] = _num(offers[0][0])
        except Exception:
            pass

    # (D) если last пустой — возьмём последнюю сделку
    if result["last"] is None:
        tr_url = (
            f"https://iss.moex.com/iss/engines/futures/markets/forts/securities/{secid}/trades.json?iss.meta=off&limit=1&sort_time=desc"
        )
        try:
            js = await iss_get(client, tr_url)
            cols = js.get("trades", {}).get("columns", [])
            data = js.get("trades", {}).get("data", [])
            if cols and data and data[0]:
                c = {n: i for i, n in enumerate(cols)}
                price = _num(data[0][c.get("PRICE")])
                if price is not None:
                    result["last"] = price
        except Exception:
            pass

    # если вообще ничего — вернём None
    if result["last"] is None and result["bid"] is None and result["offer"] is None:
        return None
    return result

# -------------------------------------------------
# Обновление кэша
# -------------------------------------------------
async def refresh_cache():
    global CACHE
    # гарантируем, что разделы есть и это dict
    if not isinstance(CACHE, dict):
        CACHE = {}
    CACHE.setdefault("spot", {})
    CACHE.setdefault("fut", {})
    CACHE.setdefault("divs", {})
    CACHE.setdefault("map", {})
    async with httpx.AsyncClient(headers={"User-Agent": "screener/0.3"}) as client:
        now = _now_ts()

        # Акции: LAST + BID/OFFER
        for secid in SYMBOLS:
            q = await fetch_spot_quote(client, secid)
            if q:
                CACHE["spot"][secid] = {**q, "ts": now}

        # Дивиденды (редко)
        for secid in SYMBOLS:
            rec = CACHE["divs"].get(secid)
            if not rec or (now - rec.get("ts", 0) > DIV_REFRESH_SEC):
                info = await fetch_dividend_info(client, secid)
                info["ts"] = now
                CACHE["divs"][secid] = info

        # Фьючерсы: по каждому шеру — целевая серия (буквенный код)
        for share in SYMBOLS:
            try:
                found = await find_fut_secid_on_board(client, share, year_dec=YEAR_DEC)
                if not found:
                    continue
                fut_secid = found["secid"]
                mdp = await fetch_fut_md_and_params(client, fut_secid)
                if not mdp:
                    continue
                CACHE["fut"][fut_secid] = {**mdp, "ts": now}
                # положим ещё «карту соответствия» для удобства при сборке строк
                CACHE["map"][share] = {"secid": fut_secid, "ui": ui_fut_code(share)}
            except Exception:
                continue

# -------------------------------------------------
# Вычисления по строке
# -------------------------------------------------
def days_diff(to_iso: Optional[str]) -> Optional[int]:
    if not to_iso: return None
    try:
        d = datetime.fromisoformat(str(to_iso)).date()
        return (d - datetime.now(timezone.utc).date()).days
    except Exception:
        return None

def build_row(share: str) -> ScreenerRow:
    # spot
    s = CACHE["spot"].get(share, {})
    s_last, s_bid, s_offer = s.get("last"), s.get("bid"), s.get("offer")

    # fut
    m = CACHE["map"].get(share, {})
    fut_secid = (m or {}).get("secid")
    ui_code   = (m or {}).get("ui") or f"{share}-12.{str(YEAR_DEC)[-2:]}"
    f = CACHE["fut"].get(fut_secid or "", {})
    f_last, f_bid, f_offer = f.get("last"), f.get("bid"), f.get("offer")
    im, minstep, stepprice = f.get("im"), f.get("minstep"), f.get("stepprice")
    exp = f.get("exp")

    # Дивиденды
    d = CACHE["divs"].get(share, {})
    ex_date, div_val = d.get("ex_date"), d.get("value")

    # ГО: через мультипликатор
    go_pct = None
    multiplier = None
    if minstep and stepprice and minstep != 0:
        multiplier = stepprice / minstep
    if im and f_last and multiplier:
        try:
            go_pct = round(im / (f_last * multiplier) * 100, 4)
        except ZeroDivisionError:
            go_pct = None

    # Спреды
    spread_in_pct = None
    if f_offer and s_bid:
        spread_in_pct = round((f_offer - s_bid) / s_bid * 100, 4)

    spread_out_pct = None
    if s_offer and f_bid:
        spread_out_pct = round((s_offer - f_bid) / s_offer * 100, 4)

    # Дельта/итого
    delta_pct = round((f_last - s_last) / s_last * 100, 4) if (f_last and s_last) else None
    div_pct = round((div_val / s_last) * 100, 4) if (div_val and s_last) else None
    total_pct = None
    if div_pct is not None or delta_pct is not None:
        total_pct = round((div_pct or 0.0) + (delta_pct or 0.0), 4)

    # дни
    def days_to(iso: Optional[str]) -> Optional[int]:
        if not iso: return None
        try:
            return (datetime.fromisoformat(str(iso)).date() - datetime.now(timezone.utc).date()).days
        except Exception:
            return None

    return ScreenerRow(
        Акция=share,
        Фьючерс=ui_code,
        Дата_див_отсечки=ex_date,
        Размер_див_руб=div_val,
        Див_pct=div_pct,
        Цена_акции=round(s_last, 4) if s_last is not None else None,
        Цена_фьючерса=round(f_last, 4) if f_last is not None else None,
        ГО_pct=go_pct,
        Спред_Входа_pct=spread_in_pct,
        Спред_Выхода_pct=spread_out_pct,
        Справ_Стоимость=None,
        Дельта_pct=delta_pct,
        Всего_pct=total_pct,
        Дней_до_отсечки=days_to(ex_date),
        Дней_до_эксп=days_to(exp),
        Доход_к_отсечке_pct=div_pct,
        Доход_к_эксп_pct=total_pct,
    )

# -------------------------------------------------
# FastAPI endpoints
# -------------------------------------------------
@app.on_event("startup")
async def _startup():
    await refresh_cache()
    async def worker():
        while True:
            try:
                await refresh_cache()
            except Exception:
                pass
            await asyncio.sleep(REFRESH_SEC)
    asyncio.create_task(worker())

@app.get("/screener")
def get_screener():
    return [build_row(s) for s in SYMBOLS]

@app.websocket("/ws/screener")
async def ws_screener(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            rows = [build_row(s) for s in SYMBOLS]
            await ws.send_json({"type": "screener", "data": [r.model_dump() for r in rows]})
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass

@app.get("/symbols")
def get_symbols():
    return SYMBOLS

# отладка: посмотреть, что в кэше по фьючу
@app.get("/debug/peek/{secid}")
def debug_peek(secid: str):
    return CACHE["fut"].get(secid.upper(), {})

@app.get("/debug/peek_fut/{share}")
async def debug_peek_fut(share: str):
    async with httpx.AsyncClient() as client:
        found = await find_fut_secid_on_board(client, share.upper(), year_dec=YEAR_DEC)
        info = None
        if found:
            info = await fetch_fut_md_and_params(client, found["secid"])
        return {"share": share.upper(), "found": found, "info": info}
