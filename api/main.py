# -*- coding: utf-8 -*-
# FastAPI + MOEX ISS provider (real data, robust futures resolver + history fallback)
import os, json, asyncio, time
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

SYMBOLS_FILE = os.path.join(os.path.dirname(__file__), "symbols.json")

app = FastAPI(title="Screener API", version="0.8.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ------------------------------- конфигурация --------------------------------
HTTP_TIMEOUT = 12.0
REFRESH_SEC = 5.0
DIV_REFRESH_SEC = 3600.0
PREFER_YEAR_DEC = 2025        # целевой год (12.25)
TRY_YEARS_AHEAD = 1
MONTHS_ORDER = [12, 9, 6, 3]  # приоритет серий
FUT_BOARD = "RFUD"            # базовая доска срочного рынка

# Акция -> root на FORTS
FUT_ROOT: Dict[str, str] = {
    "SBER": "SBRF",
    "GAZP": "GAZR",
    "LKOH": "LKOH",
    "MOEX": "MOEX",
    "PLZL": "PLZL",
    "X5":   "FIVE",
    # добавляй по мере необходимости
}

# ------------------------------- загрузка тикеров -----------------------------
def load_symbols() -> list[str]:
    try:
        with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [str(x).upper() for x in data if x]
    except Exception:
        return ["SBER", "GAZP", "LKOH", "MOEX", "PLZL", "X5"]

SYMBOLS = load_symbols()

# ------------------------------- модели --------------------------------------
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

# ------------------------------- кэш -----------------------------------------
CACHE: Dict[str, dict] = {
    "shares": {},          # { 'SBER': {'last': 317.62, 'ts': ...}, ... }
    "futs": {},            # { 'SBRF-12.25': {'last': 319.1, 'exp': '2025-12-19', 'ts': ...}, ... }
    "divs": {},            # { 'SBER': {'ex_date': '2025-10-01', 'value': 18.7, 'ts': ...}, ... }
    "map_ui_code": {},     # { 'SBER': 'SBER-12.25', ... }
    "map_fut_secid": {},   # { 'SBER': 'SBRF-12.25', ... }  # (или буквенный форм-фактор)
    "debug_fut": {},       # отладка по поиску серий/цен
}

# ------------------------------- ISS helpers ---------------------------------
def _now_ts() -> float:
    return time.time()

async def _get(client: httpx.AsyncClient, url: str) -> dict:
    r = await client.get(url, timeout=HTTP_TIMEOUT, headers={"User-Agent": "screener/0.8"})
    r.raise_for_status()
    return r.json()

# ------------------------------- утилиты --------------------------------------
def _is_future_date(iso: str) -> bool:
    try:
        d = datetime.fromisoformat(str(iso)).date()
        return d >= datetime.now(timezone.utc).date()
    except Exception:
        return False

def _mm_yy(mm: int, year: int) -> str:
    return f"{mm:02d}.{str(year)[-2:]}"

LETTER_FOR_MONTH = {3: "H", 6: "M", 9: "U", 12: "Z"}

# ------------------------------- акции ---------------------------------------
async def fetch_share_last(client: httpx.AsyncClient, secid: str) -> Optional[float]:
    url = (
        "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/"
        f"securities/{secid}.json?iss.meta=off&marketdata.columns=LAST"
    )
    try:
        js = await _get(client, url)
        data = js.get("marketdata", {}).get("data", [])
        if data and data[0] and data[0][0] is not None:
            return float(data[0][0])
    except Exception:
        pass
    return None

# ------------------------------- дивиденды -----------------------------------
async def fetch_dividend_info(client: httpx.AsyncClient, secid: str) -> dict:
    url = f"https://iss.moex.com/iss/securities/{secid}/dividends.json?iss.meta=off"
    out = {"ex_date": None, "value": None}
    try:
        js = await _get(client, url)
        cols = js.get("dividends", {}).get("columns", [])
        data = js.get("dividends", {}).get("data", [])
        if not (cols and data):
            return out
        col = {name: i for i, name in enumerate(cols)}
        today = datetime.now(timezone.utc).date()
        future = []
        for row in data:
            exd = row[col.get("registry_close_date")] or row[col.get("close_date")] or row[col.get("date")]
            val = row[col.get("value")]
            if not exd:
                continue
            try:
                d = datetime.fromisoformat(str(exd)).date()
            except Exception:
                continue
            if d >= today:
                future.append((d, val))
        if future:
            future.sort(key=lambda x: x[0])
            d, v = future[0]
            out = {"ex_date": d.isoformat(), "value": float(v) if v is not None else None}
    except Exception:
        pass
    return out

# ------------------------------- MARKETDATA (цены фьючерса) ------------------
async def _marketdata_row(client: httpx.AsyncClient, url: str):
    try:
        js = await _get(client, url)
        cols = js.get("marketdata", {}).get("columns", [])
        data = js.get("marketdata", {}).get("data", [])
        if not cols or not data:
            return None
        return {"cols": cols, "row": data[0]}
    except Exception:
        return None

def _pick_price_from_row(row: dict):
    cols = {n: i for i, n in enumerate(row["cols"])}
    r = row["row"]
    def val(name: str):
        i = cols.get(name)
        if i is None: return None
        v = r[i]
        return float(v) if v is not None else None
    # приоритеты
    for name in ("LAST", "LCURRENTPRICE"):
        p = val(name)
        if p is not None: return p
    bid, ask = val("BID"), val("ASK")
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    for name in ("MARKETPRICE", "MARKETPRICETODAY"):
        p = val(name)
        if p is not None: return p
    return None

async def _md_price_any(client: httpx.AsyncClient, secid: str, dbg_list: list) -> Optional[float]:
    urls = [
        f"https://iss.moex.com/iss/engines/futures/markets/forts/boards/{FUT_BOARD}/securities/{secid}.json?iss.meta=off&marketdata.columns=LAST,LCURRENTPRICE,BID,ASK,MARKETPRICE,MARKETPRICETODAY",
        f"https://iss.moex.com/iss/engines/futures/markets/forts/securities/{secid}.json?iss.meta=off&marketdata.columns=LAST,LCURRENTPRICE,BID,ASK,MARKETPRICE,MARKETPRICETODAY",
    ]
    for u in urls:
        row = await _marketdata_row(client, u)
        price = _pick_price_from_row(row) if row else None
        dbg_list.append({"secid": secid, "where": "marketdata", "url": u, "price": price, "cols": row["cols"] if row else None})
        if price is not None:
            return price
    return None

# ------------------------------- EXPIRATION ----------------------------------
async def _sec_exp_any(client: httpx.AsyncClient, secid: str) -> Optional[str]:
    urls = [
        f"https://iss.moex.com/iss/engines/futures/markets/forts/boards/{FUT_BOARD}/securities/{secid}.json?iss.meta=off&securities.columns=SECID,EXPIRATION",
        f"https://iss.moex.com/iss/engines/futures/markets/forts/securities/{secid}.json?iss.meta=off&securities.columns=SECID,EXPIRATION",
    ]
    for u in urls:
        try:
            js = await _get(client, u)
            cols = js.get("securities", {}).get("columns", [])
            data = js.get("securities", {}).get("data", [])
            if cols and data:
                c = {n: i for i, n in enumerate(cols)}
                return data[0][c["EXPIRATION"]]
        except Exception:
            pass
    return None

# ------------------------------- HISTORY fallback ----------------------------
async def _history_close_any(client: httpx.AsyncClient, secid: str, days_back: int = 5):
    base = datetime.now(timezone.utc).date()
    for d in range(days_back + 1):
        day = base if d == 0 else (base.fromordinal(base.toordinal() - d))
        day_iso = day.isoformat()
        urls = [
            f"https://iss.moex.com/iss/history/engines/futures/markets/forts/boards/{FUT_BOARD}/securities/{secid}.json?iss.meta=off&date={day_iso}&history.columns=SECID,LEGALCLOSEPRICE,CLOSE",
            f"https://iss.moex.com/iss/history/engines/futures/markets/forts/securities/{secid}.json?iss.meta=off&date={day_iso}&history.columns=SECID,LEGALCLOSEPRICE,CLOSE",
        ]
        for u in urls:
            try:
                js = await _get(client, u)
                cols = js.get("history", {}).get("columns", [])
                data = js.get("history", {}).get("data", [])
                if cols and data:
                    c = {n: i for i, n in enumerate(cols)}
                    for row in reversed(data):
                        lc_i = c.get("LEGALCLOSEPRICE"); cl_i = c.get("CLOSE")
                        lc = row[lc_i] if lc_i is not None else None
                        cl = row[cl_i] if cl_i is not None else None
                        price = lc or cl
                        if price is not None:
                            return float(price), {"where": "history", "url": u, "date": day_iso}
            except Exception:
                continue
    return None, None

# ------------------------------- список серий --------------------------------
async def _list_series_by_query(client: httpx.AsyncClient, root: str) -> list[dict]:
    url = ("https://iss.moex.com/iss/engines/futures/markets/forts/"
           "securities.json?iss.meta=off&limit=5000&securities.columns=SECID,EXPIRATION&query=" + root)
    try:
        js = await _get(client, url)
        cols = js.get("securities", {}).get("columns", [])
        data = js.get("securities", {}).get("data", [])
        if not cols or not data:
            return []
        c = {n: i for i, n in enumerate(cols)}
        out = []
        for row in data:
            secid = row[c["SECID"]]
            exp   = row[c["EXPIRATION"]]
            if not isinstance(secid, str) or not secid.startswith(root):
                continue
            if not exp or not _is_future_date(exp):
                continue
            out.append({"secid": secid, "exp": exp})
        out.sort(key=lambda x: x["exp"])
        return out
    except Exception:
        return []

# ------------------------------- резолвер серии -------------------------------
async def resolve_series_for_share(client: httpx.AsyncClient, share: str, prefer_year: int = PREFER_YEAR_DEC) -> dict:
    root = FUT_ROOT.get(share)
    dbg: list[dict] = []
    if not root:
        return {"secid": None, "ui_code": f"{share}-", "exp": None, "last": None, "tried": dbg}

    # (A) реальные серии из списка
    series = await _list_series_by_query(client, root)
    chosen = None
    if series:
        # приоритет — декабрь prefer_year, иначе ближайшая квартальная
        want = f"-12.{str(prefer_year)[-2:]}"
        chosen = next((s for s in series if isinstance(s["secid"], str) and s["secid"].endswith(want)), None)
        if not chosen:
            def mm_from_secid(sec: str) -> int:
                if "-" in sec:
                    try: return int(sec.split("-")[1].split(".")[0])
                    except: return 0
                return 0
            q = [s for s in series if mm_from_secid(str(s["secid"])) in (3,6,9,12)]
            chosen = q[0] if q else series[0]

    # (B) если через список не нашли — брутфорс по шаблонам (dash → letter), 2 года
    if not chosen:
        for year in (prefer_year, prefer_year + TRY_YEARS_AHEAD):
            y1 = str(year)[-1]
            for mm in MONTHS_ORDER:
                secid = f"{root}-{_mm_yy(mm, year)}"
                price = await _md_price_any(client, secid, dbg)
                if price is not None:
                    exp = await _sec_exp_any(client, secid)
                    return {"secid": secid, "ui_code": f"{share}-{_mm_yy(mm, year)}", "exp": exp, "last": price, "tried": dbg}
            for mm in MONTHS_ORDER:
                letter = LETTER_FOR_MONTH[mm]
                secid  = f"{root}{letter}{y1}"
                price  = await _md_price_any(client, secid, dbg)
                if price is not None:
                    exp = await _sec_exp_any(client, secid)
                    return {"secid": secid, "ui_code": f"{share}-{_mm_yy(mm, year)}", "exp": exp, "last": price, "tried": dbg}
        return {"secid": None, "ui_code": f"{share}-", "exp": None, "last": None, "tried": dbg}

    # (C) выбрана реальная серия → цена (marketdata) с фолбэком в history
    secid = chosen["secid"]
    exp   = chosen["exp"]
    price = await _md_price_any(client, secid, dbg)
    if price is None:
        hprice, hdbg = await _history_close_any(client, secid, days_back=5)
        if hprice is not None:
            price = hprice
            dbg.append({"secid": secid, **(hdbg or {}), "price": price})

    # UI‑код
    if isinstance(secid, str) and "-" in secid:
        mm_yy = secid.split("-")[1]
    else:
        try:
            dt = datetime.fromisoformat(str(exp))
            mm_yy = _mm_yy(dt.month, dt.year)
        except Exception:
            mm_yy = "??.??"

    return {"secid": secid, "ui_code": f"{share}-{mm_yy}", "exp": exp, "last": price, "tried": dbg}

# ------------------------------- refresh cache --------------------------------
async def refresh_cache():
    async with httpx.AsyncClient() as client:
        # акции
        for secid in SYMBOLS:
            last = await fetch_share_last(client, secid)
            if last is not None:
                CACHE["shares"][secid] = {"last": last, "ts": _now_ts()}

        # дивиденды
        now = _now_ts()
        for secid in SYMBOLS:
            div_rec = CACHE["divs"].get(secid)
            if not div_rec or now - div_rec.get("ts", 0) > DIV_REFRESH_SEC:
                info = await fetch_dividend_info(client, secid)
                info["ts"] = now
                CACHE["divs"][secid] = info

        # фьючерсы
        for share in SYMBOLS:
            picked = await resolve_series_for_share(client, share, prefer_year=PREFER_YEAR_DEC)
            CACHE["debug_fut"][share] = picked.get("tried", [])
            secid = picked["secid"]
            ui_code = picked["ui_code"]
            exp = picked["exp"]
            last_direct = picked.get("last")

            CACHE["map_ui_code"][share] = ui_code
            if secid:
                CACHE["futs"][secid] = {
                    "last": last_direct,
                    "exp": exp,
                    "ts": _now_ts(),
                }
                CACHE["map_fut_secid"][share] = secid
            else:
                CACHE["map_fut_secid"][share] = None

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

# ------------------------------- сборка строки --------------------------------
def build_row(share: str) -> ScreenerRow:
    spot = (CACHE["shares"].get(share) or {}).get("last")
    ui_code = CACHE["map_ui_code"].get(share) or f"{share}-"
    fut_secid = CACHE["map_fut_secid"].get(share)
    fut_last = CACHE["futs"].get(fut_secid, {}).get("last") if fut_secid else None

    # дивиденды
    div = CACHE["divs"].get(share, {})
    ex = div.get("ex_date")
    div_val = div.get("value")

    # метрики
    div_pct = round((div_val / spot * 100), 2) if (div_val and spot) else None
    delta_pct = round(((fut_last - spot) / spot * 100), 2) if (spot and fut_last) else None
    total_pct = (
        round((div_pct or 0) + (delta_pct or 0), 2)
        if (div_pct is not None or delta_pct is not None)
        else None
    )

    # дни до дат
    days_to_ex = None
    exp_iso = CACHE["futs"].get(fut_secid, {}).get("exp") if fut_secid else None
    try:
        if exp_iso:
            d = datetime.fromisoformat(str(exp_iso)).replace(tzinfo=timezone.utc).date()
            days_to_ex = (d - datetime.now(timezone.utc).date()).days
    except Exception:
        pass
    days_to_cut = None
    try:
        if ex:
            d = datetime.fromisoformat(str(ex)).replace(tzinfo=timezone.utc).date()
            days_to_cut = (d - datetime.now(timezone.utc).date()).days
    except Exception:
        pass

    return ScreenerRow(
        Акция=share,
        Фьючерс=ui_code,                     # <АКЦИЯ>-MM.YY
        Дата_див_отсечки=ex,
        Размер_див_руб=div_val,
        Див_pct=div_pct,
        Цена_акции=round(spot, 2) if spot is not None else None,
        Цена_фьючерса=round(fut_last, 2) if fut_last is not None else None,
        ГО_pct=None,                         # добавим позже (secparams)
        Спред_Входа_pct=None,
        Спред_Выхода_pct=None,
        Справ_Стоимость=None,
        Дельта_pct=delta_pct,
        Всего_pct=total_pct,
        Дней_до_отсечки=days_to_cut,
        Дней_до_эксп=days_to_ex,
        Доход_к_отсечке_pct=div_pct,
        Доход_к_эксп_pct=total_pct,
    )

# ------------------------------- REST / WS ------------------------------------
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

# ------------------------------- DEBUG ----------------------------------------
@app.get("/debug/futures")
def debug_futures():
    return CACHE.get("debug_fut", {})

@app.get("/debug/peek/{secid}")
async def debug_peek(secid: str):
    async with httpx.AsyncClient() as client:
        dbg: List[dict] = []
        price = await _md_price_any(client, secid, dbg)
        exp = await _sec_exp_any(client, secid)
        hclose, hdbg = await _history_close_any(client, secid, days_back=5)
        return {
            "secid": secid,
            "exp": exp,
            "marketdata_attempts": dbg,
            "history": {"close": hclose, "meta": hdbg},
            "picked_price": price or hclose,
        }
