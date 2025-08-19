# -*- coding: utf-8 -*-
# FastAPI + MOEX ISS provider (real data, futures on RFUD)
import os, json, asyncio, time
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

SYMBOLS_FILE = os.path.join(os.path.dirname(__file__), "symbols.json")

app = FastAPI(title="Screener API", version="0.7.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ------------------------------- конфигурация --------------------------------
HTTP_TIMEOUT = 12.0
REFRESH_SEC = 5.0
DIV_REFRESH_SEC = 3600.0
PREFER_YEAR_DEC = 2025
TRY_YEARS_AHEAD = 1
MONTHS_ORDER = [12, 9, 6, 3]      # приоритет серий
FUT_BOARD = "RFUD"                # доска срочного рынка

# Акция -> root на FORTS
FUT_ROOT: Dict[str, str] = {
    "SBER": "SBRF",
    "GAZP": "GAZR",
    "LKOH": "LKOH",
    "MOEX": "MOEX",
    "PLZL": "PLZL",
    "X5":   "FIVE",
    # при необходимости дополняй: "PHOR":"PHOR", "TATN":"TATN", ...
}

# ------------------------------- тикеры --------------------------------------
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
    "shares": {},
    "futs": {},
    "divs": {},
    "map_ui_code": {},
    "map_fut_secid": {},
    "debug_fut": {},
}

# ------------------------------- ISS helpers ---------------------------------
def _now_ts() -> float: return time.time()

async def _get(client: httpx.AsyncClient, url: str) -> dict:
    r = await client.get(url, timeout=HTTP_TIMEOUT, headers={"User-Agent": "screener/0.7"})
    r.raise_for_status()
    return r.json()

def _mm_yy(mm: int, year: int) -> str: return f"{mm:02d}.{str(year)[-2:]}"
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

# --- utils
def _is_future_date(iso: str) -> bool:
    try:
        d = datetime.fromisoformat(str(iso)).date()
        return d >= datetime.now(timezone.utc).date()
    except Exception:
        return False

# --- берём цену с фолбэками, пробуем с RFUD и без
async def _md_price_any(client: httpx.AsyncClient, secid: str) -> Optional[float]:
    # 1) с RFUD
    url1 = (
        "https://iss.moex.com/iss/engines/futures/markets/forts/boards/RFUD/"
        f"securities/{secid}.json?iss.meta=off&marketdata.columns=LAST,LCURRENTPRICE,BID,ASK"
    )
    # 2) без boards (иногда marketdata тут)
    url2 = (
        "https://iss.moex.com/iss/engines/futures/markets/forts/"
        f"securities/{secid}.json?iss.meta=off&marketdata.columns=LAST,LCURRENTPRICE,BID,ASK"
    )
    for url in (url1, url2):
        try:
            js = await _get(client, url)
            md = js.get("marketdata", {}).get("data", [])
            if not md or not md[0]:
                continue
            last, lcur, bid, ask = md[0][0], md[0][1], md[0][2], md[0][3]
            if last is not None:
                return float(last)
            if lcur is not None:
                return float(lcur)
            if bid is not None and ask is not None:
                return (float(bid) + float(ask)) / 2.0
        except Exception:
            continue
    return None

async def _sec_exp_any(client: httpx.AsyncClient, secid: str) -> Optional[str]:
    url1 = (
        "https://iss.moex.com/iss/engines/futures/markets/forts/boards/RFUD/"
        f"securities/{secid}.json?iss.meta=off&securities.columns=SECID,EXPIRATION"
    )
    url2 = (
        "https://iss.moex.com/iss/engines/futures/markets/forts/"
        f"securities/{secid}.json?iss.meta=off&securities.columns=SECID,EXPIRATION"
    )
    for url in (url1, url2):
        try:
            js = await _get(client, url)
            cols = js.get("securities", {}).get("columns", [])
            data = js.get("securities", {}).get("data", [])
            if cols and data:
                c = {n: i for i, n in enumerate(cols)}
                if data and data[0]:
                    return data[0][c["EXPIRATION"]]
        except Exception:
            continue
    return None

# --- список серий через query=<root>
async def _list_series_by_query(client: httpx.AsyncClient, root: str) -> list[dict]:
    url = (
        "https://iss.moex.com/iss/engines/futures/markets/forts/"
        "securities.json?iss.meta=off&limit=5000&securities.columns=SECID,EXPIRATION&query="
        + root
    )
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
            exp = row[c["EXPIRATION"]]
            if not isinstance(secid, str):
                continue
            # отбираем только наши root-ы и будущие серии
            if not secid.startswith(root):
                continue
            if not exp or not _is_future_date(exp):
                continue
            out.append({"secid": secid, "exp": exp})
        # ближайшие вперёд
        out.sort(key=lambda x: x["exp"])
        return out
    except Exception:
        return []
    
# ------------------------------- фьючерсы (RFUD) ------------------------------
async def _md_price(client: httpx.AsyncClient, secid: str) -> Optional[float]:
    # цена с fallback: LAST → LCURRENTPRICE → mid(BID,ASK)
    url = (
        "https://iss.moex.com/iss/engines/futures/markets/forts/boards/"
        f"{FUT_BOARD}/securities/{secid}.json"
        "?iss.meta=off&marketdata.columns=LAST,LCURRENTPRICE,BID,ASK"
    )
    try:
        js = await _get(client, url)
        md = js.get("marketdata", {}).get("data", [])
        if not md or not md[0]:
            return None
        last, lcur, bid, ask = md[0][0], md[0][1], md[0][2], md[0][3]
        if last is not None:
            return float(last)
        if lcur is not None:
            return float(lcur)
        if bid is not None and ask is not None:
            return (float(bid) + float(ask)) / 2.0
    except Exception:
        pass
    return None

async def _sec_exp(client: httpx.AsyncClient, secid: str) -> Optional[str]:
    url = (
        "https://iss.moex.com/iss/engines/futures/markets/forts/boards/"
        f"{FUT_BOARD}/securities/{secid}.json?iss.meta=off&securities.columns=SECID,EXPIRATION"
    )
    try:
        js = await _get(client, url)
        cols = js.get("securities", {}).get("columns", [])
        data = js.get("securities", {}).get("data", [])
        if cols and data:
            c = {n: i for i, n in enumerate(cols)}
            if data and data[0]:
                return data[0][c["EXPIRATION"]]
    except Exception:
        pass
    return None

async def resolve_series_for_share(
    client: httpx.AsyncClient,
    share: str,
    prefer_year: int = PREFER_YEAR_DEC
) -> dict:
    root = FUT_ROOT.get(share)
    dbg: list[dict] = []
    if not root:
        return {"secid": None, "ui_code": f"{share}-", "exp": None, "last": None, "tried": dbg}

    # 1) получаем реальные серии из списка по query=root
    series = await _list_series_by_query(client, root)
    # приоритет: декабрь prefer_year, иначе квартальные 12/9/6/3 ближайшие
    chosen = None
    if series:
        # exact декабрь prefer_year
        want_dec_suffix = f"-12.{str(prefer_year)[-2:]}"
        chosen = next((s for s in series if s["secid"].endswith(want_dec_suffix)), None)
        if not chosen:
            # ближайшая квартальная вперёд
            def mm_of(s): 
                try:
                    # SECID может быть ROOT-12.25 или ROOTZ5; если с дефисом — возьмём месяц из него
                    part = s["secid"].split("-")[1] if "-" in s["secid"] else ""
                    return int(part.split(".")[0]) if part else 0
                except Exception:
                    return 0
            q = [s for s in series if mm_of(s) in (3, 6, 9, 12)]
            chosen = q[0] if q else series[0]

    # 2) если через список не нашли — брутфорс по нашим шаблонам (как раньше)
    if not chosen:
        months = [12, 9, 6, 3]
        for year in (prefer_year, prefer_year + 1):
            for mm in months:
                secid = f"{root}-{_mm_yy(mm, year)}"
                price = await _md_price_any(client, secid)
                dbg.append({"secid": secid, "fmt": "dash", "last": price})
                if price is not None:
                    exp = await _sec_exp_any(client, secid)
                    ui = f"{share}-{_mm_yy(mm, year)}"
                    return {"secid": secid, "ui_code": ui, "exp": exp, "last": price, "tried": dbg}
            # буквенный
            y1 = str(year)[-1]
            for mm in months:
                letter = LETTER_FOR_MONTH[mm]
                secid = f"{root}{letter}{y1}"
                price = await _md_price_any(client, secid)
                dbg.append({"secid": secid, "fmt": "letter", "last": price})
                if price is not None:
                    exp = await _sec_exp_any(client, secid)
                    ui = f"{share}-{_mm_yy(mm, year)}"
                    return {"secid": secid, "ui_code": ui, "exp": exp, "last": price, "tried": dbg}

        return {"secid": None, "ui_code": f"{share}-", "exp": None, "last": None, "tried": dbg}

    # 3) для найденной серии — цена и UI‑код
    secid = chosen["secid"]
    exp = chosen["exp"]
    price = await _md_price_any(client, secid)
    dbg.append({"secid": secid, "fmt": "query", "last": price})
    # ui: если в secid есть дефис — используем MM.YY из него; иначе из даты EXPIRATION
    if "-" in secid:
        mm_yy = secid.split("-")[1]
    else:
        try:
            dt = datetime.fromisoformat(str(exp))
            mm_yy = _mm_yy(dt.month, dt.year)
        except Exception:
            mm_yy = "??.??"
    ui = f"{share}-{mm_yy}"
    return {"secid": secid, "ui_code": ui, "exp": exp, "last": price, "tried": dbg}

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

@app.get("/debug/futures")
def debug_futures():
    return CACHE.get("debug_fut", {})
