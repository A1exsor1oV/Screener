# -*- coding: utf-8 -*-
# FastAPI + MOEX ISS provider (real data, futures on RFUD)
import os
import json
import time
import asyncio
from datetime import datetime, timezone, date
from typing import Optional, Dict, List, Any
from QuikPy import QuikPy
from concurrent.futures import ThreadPoolExecutor
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
# Path to JSON list of share tickers.  This file should reside alongside
# this module and contain an array of SECIDs (e.g. ["SBER", "GAZP", ...]).
SYMBOLS_FILE = os.path.join(os.path.dirname(__file__), "symbols.json")

# Network timeout for MOEX ISS requests (seconds)
HTTP_TIMEOUT: float = float(os.getenv("HTTP_TIMEOUT", "10"))

# How often the cache is refreshed (seconds) for spot and futures quotes
REFRESH_SEC: float = float(os.getenv("REFRESH_SEC", "5"))

# How often dividend information is refreshed (seconds)
DIV_REFRESH_SEC: float = float(os.getenv("DIV_REFRESH_SEC", "3600"))

# The December contract year for futures.  Defaults to the current year or
# the value specified in the ``YEAR_DEC`` environment variable.
_current_year = datetime.now(timezone.utc).year
YEAR_DEC: int = int(os.getenv("YEAR_DEC", str(_current_year)))

# Futures code letters for quarterly expiries: March=H, June=M, September=U,
# December=Z.  We focus on the December series.  See MOEX documentation.
MONTH_LETTER: str = "Z"

# Last digit of the futures year, used when constructing letter codes
YEAR_LAST_DIGIT: str = str(YEAR_DEC)[-1]

# Boards used for spot and futures quotes.  These values rarely change, but
# if MOEX introduces new boards they can be overridden via environment.
FUT_BOARD: str = os.getenv("FUT_BOARD", "RFUD")
SPOT_BOARD: str = os.getenv("SPOT_BOARD", "TQBR")

# Mapping from share SECID to futures root.  When adding a new share to
# ``symbols.json`` you may need to add an entry here if the root differs
# from the share code.  See MOEX futures ticker rules for details.
FUT_ROOT: Dict[str, str] = {
    "SBER": "SBRF",
    "GAZP": "GAZR",
    "LKOH": "LKOH",
    "MOEX": "MOEX",
    "PLZL": "PLZL",
    "X5":   "FIVE",
    # extend as necessary
}

# Переключатель источника данных
USE_QUIK = os.getenv("USE_QUIK", "1").strip().lower() in ("1","true","yes","y")
  # 1 = включён по умолчанию

# классы QUIK
QUIK_SPOT_CLASS: str = os.getenv("QUIK_SPOT_CLASS", "TQBR")
QUIK_FUT_CLASS: str = os.getenv("QUIK_FUT_CLASS", "SPBFUT")

# Пул потоков, чтобы не блокировать event‑loop FastAPI
EXECUTOR = ThreadPoolExecutor(max_workers=4)

# -----------------------------------------------------------------------------
# Data model
# -----------------------------------------------------------------------------
class ScreenerRow(BaseModel):
    """One row of screener data.  Field names use snake_case Russian names
    matching the original implementation to simplify front‑end mapping."""
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

# -----------------------------------------------------------------------------
# FastAPI application
# -----------------------------------------------------------------------------
app = FastAPI(title="Screener API", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------
def _now_ts() -> float:
    return time.time()


def ui_fut_code(share: str) -> str:
    """Return the user‑friendly futures code for a share.

    The UI code uses a human friendly format like ``SBER-12.25`` instead of
    the MOEX SECID (e.g. ``SBRFZ5``).  The month and year suffix are derived
    from ``YEAR_DEC``.
    """
    return f"{share}-12.{str(YEAR_DEC)[-2:]}"


def letter_fut_code(share: str) -> Optional[str]:
    """Construct the standard letter code for a share's December futures.

    For example, ``SBER`` maps to ``SBRFZ5`` when ``MONTH_LETTER`` is ``Z``
    and ``YEAR_LAST_DIGIT`` is ``5``.  Returns ``None`` if the share is not
    configured in ``FUT_ROOT``.
    """
    root = FUT_ROOT.get(share.upper())
    if not root:
        return None
    return f"{root}{MONTH_LETTER}{YEAR_LAST_DIGIT}"


def load_symbols() -> List[str]:
    """Load the list of share SECIDs from ``symbols.json``.

    Falls back to a built‑in list if the file cannot be read.
    """
    try:
        with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [str(x).upper() for x in data if x]
    except Exception:
        # default list mirrors the repository version
        return ["SBER", "GAZP", "LKOH", "MOEX", "PLZL", "X5"]


SYMBOLS: List[str] = load_symbols()

# When true, the application will not attempt to contact MOEX.  Instead it
# populates the cache with fabricated data suitable for development and
# demonstration.  Set the environment variable ``OFFLINE`` to any
# truthy value to enable.
OFFLINE: bool = bool(os.getenv("OFFLINE"))


def _num(x: Any) -> Optional[float]:
    """Convert a value to a float if possible, otherwise return ``None``."""
    try:
        return float(x) if x is not None else None
    except Exception:
        return None

# NEW: безопасное получение параметра из QUIK
def quik_param(qp: QuikPy, class_code: str, sec_code: str, param: str) -> Optional[float]:
    try:
        r = qp.getParamEx2(class_code, sec_code, param)  # {"data":{"param_value": "...", "result": "1", ...}}
        data = (r or {}).get("data") or {}
        if data.get("result") != "1":
            return None
        v = data.get("param_value")
        return float(v) if (v is not None and v != "") else None
    except Exception:
        return None

# Строковый параметр (например, даты)
def quik_param_str(qp: QuikPy, class_code: str, sec_code: str, param: str) -> Optional[str]:
    try:
        r = qp.getParam_ex2(class_code, sec_code, param)
        data = (r or {}).get("data") or {}
        if data.get("result") != "1":
            return None
        v = data.get("param_value")
        return str(v) if v not in (None, "") else None
    except Exception:
        return None

# Вычисление SECID фьючерса в QUIK (формат 'SBRF-12.25')
def quik_fut_code_for_share(share: str, year_dec: int = YEAR_DEC) -> Optional[str]:
    return letter_fut_code(share)

# -----------------------------------------------------------------------------
# Cache structure
# -----------------------------------------------------------------------------
#
# The cache holds four sections:
#  * 'spot': mapping SECID -> {last, bid, offer, ts}
#  * 'fut':  mapping SECID -> {last, bid, offer, exp, im, minstep, stepprice,
#                               lotvolume, ts}
#  * 'divs': mapping SECID -> {ex_date, value, ts}
#  * 'map':  mapping share -> {secid (fut), ui (display string)}
#
# The 'map' section ensures that ``build_row`` always has something to use
# for the futures UI code even if we cannot fetch live data.

CACHE: Dict[str, Dict[str, Any]] = {
    "spot": {},
    "fut": {},
    "divs": {},
    "map": {},
}


# -----------------------------------------------------------------------------
# MOEX ISS requests
# -----------------------------------------------------------------------------
async def iss_get(client: httpx.AsyncClient, url: str) -> dict:
    """Fetch JSON from a MOEX ISS endpoint.  Raises on non‐200 responses."""
    r = await client.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


async def fetch_spot_quote(client: httpx.AsyncClient, secid: str) -> Optional[dict]:
    """Fetch the latest spot quote (last, bid, offer) for a given share SECID.

    Returns ``None`` if the data is unavailable.
    """
    url = (
        f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/{SPOT_BOARD}/"
        f"securities/{secid}.json?iss.meta=off&marketdata.columns=LAST,BID,OFFER"
    )
    try:
        js = await iss_get(client, url)
        cols = js.get("marketdata", {}).get("columns", [])
        data = js.get("marketdata", {}).get("data", [])
        if not (cols and data and data[0]):
            return None
        c = {n: i for i, n in enumerate(cols)}
        return {
            "last": _num(data[0][c.get("LAST")]),
            "bid":  _num(data[0][c.get("BID")]),
            "offer": _num(data[0][c.get("OFFER")]),
        }
    except Exception:
        return None


async def fetch_dividend_info(client: httpx.AsyncClient, secid: str) -> dict:
    """Fetch upcoming dividend information for a share.

    Returns a dict with ``ex_date`` and ``value`` keys; either may be ``None``
    if no future dividend is scheduled.
    """
    url = f"https://iss.moex.com/iss/securities/{secid}/dividends.json?iss.meta=off"
    out = {"ex_date": None, "value": None}
    try:
        js = await iss_get(client, url)
        cols = js.get("dividends", {}).get("columns", [])
        data = js.get("dividends", {}).get("data", [])
        if not (cols and data):
            return out
        c = {n: i for i, n in enumerate(cols)}
        today = datetime.now(timezone.utc).date()
        future = []
        for row in data:
            # the API uses different field names for dates; pick the first non‐None
            exd = row[c.get("registry_close_date")] or row[c.get("close_date")] or row[c.get("date")]
            val = row[c.get("value")]
            if not exd:
                continue
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


async def fetch_fut_md_and_params(client: httpx.AsyncClient, secid: str) -> Optional[dict]:
    """Fetch futures market data and security parameters for a given SECID.

    This implementation combines multiple ISS endpoints: market data, security
    parameters, orderbook fallback and recent trades.  It returns a dict
    containing ``last``, ``bid``, ``offer``, ``exp``, ``im``, ``minstep``,
    ``stepprice`` and ``lotvolume``.  If all quotes are missing it returns
    ``None``.
    """
    result = {
        "last": None,
        "bid": None,
        "offer": None,
        "exp": None,
        "im": None,
        "minstep": None,
        "stepprice": None,
        "lotvolume": None,
    }
    # (A) batch marketdata – sometimes the only place with L1 quotes
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
                if row[c.get("SECID")] != secid:
                    continue
                result["last"]  = _num(row[c.get("LAST")])
                result["bid"]   = _num(row[c.get("BID")])
                result["offer"] = _num(row[c.get("OFFER")])
                break
    except Exception:
        pass
    # (B) security parameters: INITIALMARGIN, MINSTEP, STEPPRICE, LOTVOLUME, EXPIRATION
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
    # (C) fallback to orderbook if bid/offer missing
    if result["bid"] is None or result["offer"] is None:
        ob_url = (
            f"https://iss.moex.com/iss/engines/futures/markets/forts/securities/{secid}/orderbook.json?iss.meta=off&depth=1"
        )
        try:
            js = await iss_get(client, ob_url)
            bids = js.get("bids", {}).get("data", [])
            offers = js.get("offers", {}).get("data", [])
            if bids and bids[0]:
                result["bid"] = _num(bids[0][0])
            if offers and offers[0]:
                result["offer"] = _num(offers[0][0])
        except Exception:
            pass
    # (D) fallback to recent trades if last missing
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
    if result["last"] is None and result["bid"] is None and result["offer"] is None:
        # If there is absolutely no price information, signal failure
        return None
    return result


async def find_fut_secid_on_board(client: httpx.AsyncClient, share: str, year_dec: int = YEAR_DEC) -> Optional[dict]:
    root = FUT_ROOT.get(share.upper())
    if not root:
        return None
    url = (
        f"https://iss.moex.com/iss/engines/futures/markets/forts/boards/{FUT_BOARD}/securities.json"
        f"?iss.meta=off&limit=5000&securities.columns=SECID,EXPIRATION&query={root}"
    )
    try:
        js = await iss_get(client, url)
        cols = js.get("securities", {}).get("columns", [])
        data = js.get("securities", {}).get("data", [])
        if not cols or not data:
            return None
        c = {n: i for i, n in enumerate(cols)}
        rows: List[dict] = []
        for row in data:
            secid = row[c.get("SECID")]
            exp   = row[c.get("EXPIRATION")]
            if not isinstance(secid, str):
                continue
            if not secid.startswith(root):
                continue
            rows.append({"secid": secid, "exp": exp})
        if not rows:
            return None
        # Prefer the December contract of the target year
        target_suffix = f"-12.{str(year_dec)[-2:]}"
        best = next((r for r in rows if r["secid"].endswith(target_suffix)), None)
        if not best:
            # Choose the earliest contract expiring after today
            def exp_date(r: dict) -> date:
                try:
                    return datetime.fromisoformat(str(r["exp"])).date()
                except Exception:
                    return date.max
            today = datetime.now(timezone.utc).date()
            # filter to those not expired
            valid = [r for r in rows if exp_date(r) >= today]
            valid.sort(key=lambda r: exp_date(r))
            best = valid[0] if valid else rows[0]
        return best
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Cache refresh
# -----------------------------------------------------------------------------
async def _refresh_spot(client: httpx.AsyncClient, now: float) -> None:
    """Fetch spot quotes concurrently and update the cache."""
    tasks = [fetch_spot_quote(client, secid) for secid in SYMBOLS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for secid, q in zip(SYMBOLS, results):
        if isinstance(q, Exception):
            continue
        if q:
            CACHE["spot"][secid] = {**q, "ts": now}


async def _refresh_dividends(client: httpx.AsyncClient, now: float) -> None:
    """Fetch dividend info concurrently and update the cache."""
    tasks = []
    for secid in SYMBOLS:
        rec = CACHE["divs"].get(secid)
        if not rec or (now - rec.get("ts", 0) > DIV_REFRESH_SEC):
            tasks.append((secid, fetch_dividend_info(client, secid)))
    # gather tasks
    coros = [t[1] for t in tasks]
    results = await asyncio.gather(*coros, return_exceptions=True)
    for (secid, _), info in zip(tasks, results):
        if isinstance(info, Exception):
            continue
        info = info or {"ex_date": None, "value": None}
        info["ts"] = now
        CACHE["divs"][secid] = info


async def _refresh_futures(client: httpx.AsyncClient, now: float) -> None:
    """Fetch futures contracts concurrently and update the cache.

    For each share we first try to locate the December contract via the
    securities list; failing that we fall back to the letter code.  Even
    when we cannot fetch quotes we still register the mapping so that
    ``build_row`` produces a sensible UI code.
    """
    async def process_share(share: str) -> None:
        try:
            # Attempt to locate a contract via the securities list
            found = await find_fut_secid_on_board(client, share, year_dec=YEAR_DEC)
        except Exception:
            found = None
        fut_secid: Optional[str] = None
        if found:
            fut_secid = found.get("secid")
        # Fall back to letter code if necessary
        if not fut_secid:
            fut_secid = letter_fut_code(share)
        # Always set up the mapping for UI; use letter code for display
        CACHE["map"].setdefault(share, {"secid": fut_secid, "ui": ui_fut_code(share)})
        if not fut_secid:
            return
        # Fetch market data & parameters
        try:
            mdp = await fetch_fut_md_and_params(client, fut_secid)
        except Exception:
            mdp = None
        if mdp:
            CACHE["fut"][fut_secid] = {**mdp, "ts": now}
            CACHE["map"][share] = {"secid": fut_secid, "ui": ui_fut_code(share)}
    # launch tasks
    tasks = [process_share(s) for s in SYMBOLS]
    await asyncio.gather(*tasks)


async def refresh_cache() -> None:
    if USE_QUIK:
        # запускаем блокирующий QUIK‑сбор в отдельном потоке
        await asyncio.get_running_loop().run_in_executor(EXECUTOR, refresh_cache_quik_blocking)
        return
    """Refresh the entire cache: spot, dividends and futures."""
    now = _now_ts()
    # ensure sections exist
    CACHE.setdefault("spot", {})
    CACHE.setdefault("fut", {})
    CACHE.setdefault("divs", {})
    CACHE.setdefault("map", {})
    # When OFFLINE is set, populate the cache with deterministic dummy data
    # and skip network calls.  This is useful when developing in an environment
    # that cannot reach the MOEX ISS endpoints.
    if OFFLINE:
        for share in SYMBOLS:
            base = float(abs(hash(share)) % 1000) / 10.0 + 100.0
            CACHE["spot"][share] = {"last": base, "bid": base - 0.5, "offer": base + 0.5, "ts": now}
            fut_code = letter_fut_code(share) or f"{share}{MONTH_LETTER}{YEAR_LAST_DIGIT}"
            CACHE["map"][share] = {"secid": fut_code, "ui": ui_fut_code(share)}
            fut_last = base + 5.0
            CACHE["fut"][fut_code] = {
                "last": fut_last,
                "bid": fut_last - 0.5,
                "offer": fut_last + 0.5,
                "exp": f"{YEAR_DEC}-12-15",
                "im": 10000.0,
                "minstep": 1.0,
                "stepprice": 0.1,
                "lotvolume": 1,
                "ts": now,
            }
            CACHE["divs"][share] = {"ex_date": None, "value": None, "ts": now}
        return
    # Disable environment proxy settings to avoid requiring the optional
    # socksio package (see https://www.python-httpx.org/advanced/#environment-proxies).
    async with httpx.AsyncClient(
        headers={"User-Agent": "screener/0.4"}, trust_env=False
    ) as client:
        # refresh concurrently
        await asyncio.gather(
            _refresh_spot(client, now),
            _refresh_dividends(client, now),
            _refresh_futures(client, now),
        )

# Refresh из QUIK
def _refresh_spot_quik(qp: QuikPy, now: float) -> None:
    for secid in SYMBOLS:
        last  = quik_param(qp, QUIK_SPOT_CLASS, secid, "LAST")
        bid   = quik_param(qp, QUIK_SPOT_CLASS, secid, "BID")
        offer = quik_param(qp, QUIK_SPOT_CLASS, secid, "OFFER")
        if any(v is not None for v in (last, bid, offer)):
            CACHE["spot"][secid] = {"last": last, "bid": bid, "offer": offer, "ts": now}

def _refresh_futures_quik(qp: QuikPy, now: float) -> None:
    for share in SYMBOLS:
        fut_code = quik_fut_code_for_share(share)  # например, 'SBRF-12.25'
        ui_code  = ui_fut_code(share)

        CACHE["map"].setdefault(share, {"secid": fut_code, "ui": ui_code})
        if not fut_code:
            continue

        last   = quik_param(qp, QUIK_FUT_CLASS, fut_code, "LAST")
        bid    = quik_param(qp, QUIK_FUT_CLASS, fut_code, "BID")
        offer  = quik_param(qp, QUIK_FUT_CLASS, fut_code, "OFFER")

        # Параметры для ГО%: INITIAL_MARGIN, MINSTEP, STEPPRICE, LOTSIZE (имена могут отличаться у брокеров —
        # если что‑то None, просто пропускаем расчёт ГО)
        im         = quik_param(qp, QUIK_FUT_CLASS, fut_code, "INITIAL_MARGIN")
        minstep    = quik_param(qp, QUIK_FUT_CLASS, fut_code, "MINSTEP")
        stepprice  = quik_param(qp, QUIK_FUT_CLASS, fut_code, "STEPPRICE")
        lotvolume  = quik_param(qp, QUIK_FUT_CLASS, fut_code, "LOTSIZE")  # иногда LOTSIZE/LOT_SIZE

        # Дата экспирации (строкой). В QUIK часто 'MAT_DATE' (ддммГГГГ) и/или 'DAYS_TO_MAT_DATE'
        mat_date_raw = quik_param_str(qp, QUIK_FUT_CLASS, fut_code, "MAT_DATE")
        exp_iso = None
        if mat_date_raw and len(mat_date_raw) == 8 and mat_date_raw.isdigit():
            # формат QUIK: ДДММГГГГ → ISO: ГГГГ-ММ-ДД
            d = mat_date_raw
            exp_iso = f"{d[4:]}-{d[2:4]}-{d[0:2]}"

        if any(v is not None for v in (last, bid, offer, im, minstep, stepprice, lotvolume, exp_iso)):
            CACHE["fut"][fut_code] = {
                "last": last,
                "bid": bid,
                "offer": offer,
                "exp": exp_iso,
                "im": im,
                "minstep": minstep,
                "stepprice": stepprice,
                "lotvolume": lotvolume,
                "ts": now,
            }
            CACHE["map"][share] = {"secid": fut_code, "ui": ui_code}

def refresh_cache_quik_blocking() -> None:
    now = _now_ts()
    # обнуляем разделы, чтобы избежать "старого" мусора
    CACHE.setdefault("spot", {})
    CACHE.setdefault("fut", {})
    CACHE.setdefault("divs", {})
    CACHE.setdefault("map", {})

    with QuikPy() as qp:
        _refresh_spot_quik(qp, now)
        _refresh_futures_quik(qp, now)
        # Дивиденды из QUIK не тянем — оставляем None
        for secid in SYMBOLS:
            rec = CACHE["divs"].get(secid) or {}
            if not rec:
                CACHE["divs"][secid] = {"ex_date": None, "value": None, "ts": now}

# -----------------------------------------------------------------------------
# Row computations
# -----------------------------------------------------------------------------
def build_row(share: str) -> ScreenerRow:
    """Assemble a ``ScreenerRow`` from cached spot, futures and dividend data."""
    # spot quote
    s = CACHE["spot"].get(share, {})
    s_last, s_bid, s_offer = s.get("last"), s.get("bid"), s.get("offer")
    # futures mapping & quote
    m = CACHE["map"].get(share, {})
    fut_secid = m.get("secid")
    ui_code   = m.get("ui") or ui_fut_code(share)
    f = CACHE["fut"].get(fut_secid or "", {})
    f_last, f_bid, f_offer = f.get("last"), f.get("bid"), f.get("offer")
    im, minstep, stepprice = f.get("im"), f.get("minstep"), f.get("stepprice")
    exp = f.get("exp")
    # dividends
    d = CACHE["divs"].get(share, {})
    ex_date, div_val = d.get("ex_date"), d.get("value")
    # ГО calculation: initial margin to contract value
    go_pct: Optional[float] = None
    multiplier: Optional[float] = None
    if minstep and stepprice and minstep != 0:
        multiplier = stepprice / minstep
    if im and f_last and multiplier:
        try:
            go_pct = round(im / (f_last * multiplier) * 100, 4)
        except ZeroDivisionError:
            go_pct = None
    # Spreads (enter and exit)
    spread_in_pct: Optional[float] = None
    if f_offer and s_bid:
        spread_in_pct = round((f_offer - s_bid) / s_bid * 100, 4)
    spread_out_pct: Optional[float] = None
    if s_offer and f_bid:
        spread_out_pct = round((s_offer - f_bid) / s_offer * 100, 4)
    # Delta (futures minus spot)
    delta_pct: Optional[float] = None
    if (f_last is not None) and (s_last is not None) and s_last != 0:
        delta_pct = round((f_last - s_last) / s_last * 100, 4)
    # Dividend yield
    div_pct: Optional[float] = None
    if (div_val is not None) and (s_last is not None) and s_last != 0:
        div_pct = round((div_val / s_last) * 100, 4)
    # Total return: sum of delta and dividend
    total_pct: Optional[float] = None
    if div_pct is not None or delta_pct is not None:
        total_pct = round((div_pct or 0.0) + (delta_pct or 0.0), 4)
    # Fair value (Справ. Стоимость) – simple theoretical value: spot + dividend
    fair_value: Optional[float] = None
    if (s_last is not None) and (div_val is not None):
        fair_value = round(s_last + div_val, 4)
    # Days differences
    def days_to(iso: Optional[str]) -> Optional[int]:
        if not iso:
            return None
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
        Справ_Стоимость=fair_value,
        Дельта_pct=delta_pct,
        Всего_pct=total_pct,
        Дней_до_отсечки=days_to(ex_date),
        Дней_до_эксп=days_to(exp),
        Доход_к_отсечке_pct=div_pct,
        Доход_к_эксп_pct=total_pct,
    )


# -----------------------------------------------------------------------------
# FastAPI endpoints
# -----------------------------------------------------------------------------
@app.on_event("startup")
async def _startup() -> None:
    """Kick off the background refresh loop on startup."""
    # Perform an initial refresh synchronously to populate the cache
    await refresh_cache()
    async def worker() -> None:
        while True:
            try:
                await refresh_cache()
            except Exception:
                # suppress exceptions – they'll be logged by httpx but should not
                # crash the background task
                pass
            await asyncio.sleep(REFRESH_SEC)
    asyncio.create_task(worker())


@app.get("/screener", response_model=List[ScreenerRow])
def get_screener() -> List[ScreenerRow]:
    """Return the current screener rows for all configured symbols."""
    return [build_row(s) for s in SYMBOLS]


@app.websocket("/ws/screener")
async def ws_screener(ws: WebSocket) -> None:
    """Push screener rows to the client once per second over WebSocket."""
    await ws.accept()
    try:
        while True:
            rows = [build_row(s) for s in SYMBOLS]
            await ws.send_json({"type": "screener", "data": [r.model_dump() for r in rows]})
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass


@app.get("/symbols", response_model=List[str])
def get_symbols() -> List[str]:
    """Return the configured list of share SECIDs."""
    return SYMBOLS


# Debug endpoints for inspecting the cache
@app.get("/debug/peek/{secid}")
def debug_peek(secid: str) -> Dict[str, Any]:
    """Return raw cached futures data for a given futures SECID."""
    return CACHE["fut"].get(secid.upper(), {})


@app.get("/debug/peek_fut/{share}")
async def debug_peek_fut(share: str) -> Dict[str, Any]:
    """Find and fetch futures data for a share without touching the cache."""
    share = share.upper()
    async with httpx.AsyncClient(headers={"User-Agent": "screener/debug"}, trust_env=False) as client:
        found = await find_fut_secid_on_board(client, share, year_dec=YEAR_DEC)
        info = None
        if found:
            try:
                info = await fetch_fut_md_and_params(client, found["secid"])
            except Exception:
                info = None
        return {"share": share, "found": found, "info": info}

from QuikPy import QuikPy

@app.get("/debug/quik/{secid}")
def debug_quik(secid: str) -> dict:
    """Прямой запрос к терминалу QUIK через QuikPy"""
    with QuikPy(callbacks=False) as qp:
        info = qp.getParam_ex2("TQBR", secid.upper(), "LAST")
    return info

@app.get("/debug/quik_cache/{share}")
def debug_quik_cache(share: str) -> dict:
    share = share.upper()
    m = CACHE["map"].get(share) or {}
    fut = CACHE["fut"].get((m.get("secid") or "").upper(), {})
    spot = CACHE["spot"].get(share, {})
    return {
        "share": share,
        "mapped_fut": m,
        "spot": spot,
        "fut": fut,
    }