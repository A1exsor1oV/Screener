# backend/app/quik_ingest.py
import json
import socket
import threading
import time
from datetime import datetime
from typing import Dict, Any

from .settings import settings

# In‑memory кэши (потом можно заменить на Redis/БД)
QUOTES: Dict[str, float] = {}           # "TQBR:SBER" -> 123.45
FUTS: Dict[str, float] = {}             # "SPBFUT:SRU5" -> цена контракта (в пунктах)
META: Dict[str, Dict[str, Any]] = {}    # "SRU5" -> {lot_size, go_contract, days_to_mat_date}
DIVS: Dict[str, Dict[str, Any]] = {}    # "SBER" -> {ex_date, amount, utv}

def start_quik_listener(host: str | None = None, port: int | None = None) -> None:
    """
    Фоновый TCP-клиент к QLua (stream_quotes.lua). Получает JSON-массив строками \n.
    Каждая запись может быть классом SPBFUT (фьючерс) или TQBR (акция).
    """
    host = host or settings.TCP_HOST
    port = port or settings.TCP_PORT

    def loop():
        while True:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((host, port))
                    buf = b""
                    while True:
                        chunk = s.recv(65536)
                        if not chunk:
                            break
                        buf += chunk
                        # читаем по строкам (одна JSON-строка = один батч)
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            if not line:
                                continue
                            arr = json.loads(line.decode("utf-8"))
                            now = datetime.utcnow()
                            for rec in arr:
                                board = rec.get("class")
                                sec = rec.get("sec")
                                last = float(rec.get("last") or 0)
                                key = f"{board}:{sec}"

                                if board == "SPBFUT":
                                    # цена контракта
                                    FUTS[key] = last
                                    # метаданные контракта (если пришли)
                                    ls = rec.get("lot_size")
                                    go = rec.get("go_contract")
                                    d2m = rec.get("days_to_mat_date")
                                    if ls is not None or go is not None or d2m is not None:
                                        prev = META.get(sec, {})
                                        META[sec] = {
                                            "lot_size": ls if ls is not None else prev.get("lot_size"),
                                            "go_contract": go if go is not None else prev.get("go_contract"),
                                            "days_to_mat_date": d2m if d2m is not None else prev.get("days_to_mat_date"),
                                        }
                                else:
                                    # акция (спот)
                                    QUOTES[key] = last

                                # дивиденды прокидывает и для акций, и для фьючей (name=базовый тикер акции)
                                name = rec.get("name")
                                if name:
                                    DIVS[name] = {
                                        "ex_date": rec.get("ddiv"),
                                        "amount": rec.get("divr"),
                                        "utv": rec.get("utv"),
                                    }
            except Exception:
                # простой backoff и переподключение
                time.sleep(2)
                continue

    t = threading.Thread(target=loop, daemon=True)
    t.start()
