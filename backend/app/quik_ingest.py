import json
import socket
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional

from .settings import settings

# In‑memory кэши (можно заменить на Redis/БД)
QUOTES: Dict[str, float] = {}            # "TQBR:SBER" -> 123.45
FUTS: Dict[str, float] = {}              # "SPBFUT:SRU5" -> цена контракта (в пунктах)
META: Dict[str, Dict[str, Any]] = {}     # "SRU5" -> {lot_size, go_contract, days_to_mat_date}
DIVS: Dict[str, Dict[str, Any]] = {}     # "SBER" -> {ex_date, amount, utv}
FUT_NAME: Dict[str, str] = {}            # "SRU5" -> "SBER" (базовый актив фьючерса)

# ---- защита от повторного старта (uvicorn --reload, повторные старты приложения) ----
_listener_thread: Optional[threading.Thread] = None
_listener_lock = threading.Lock()

def _loop(host: str, port: int):
    """Бесконечное переподключение к TCP и разбор JSON-строк."""
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
                    # читаем батчи по \n
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if not line:
                            continue
                        try:
                            arr = json.loads(line.decode("utf-8"))
                        except Exception:
                            continue

                        now = datetime.utcnow()  # пока не используем, но пригодится
                        for rec in arr:
                            board = rec.get("class")
                            sec = rec.get("sec")
                            if not board or not sec:
                                continue

                            last = float(rec.get("last") or 0)
                            key = f"{board}:{sec}"

                            if board == "SPBFUT":
                                FUTS[key] = last
                                # связь фьючерса с базовым активом (имя шлёт QLua)
                                base_name = rec.get("name")
                                if base_name:
                                    FUT_NAME[sec] = base_name

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

                            # дивиденды (по имени базовой акции)
                            name = rec.get("name")
                            if name:
                                DIVS[name] = {
                                    "ex_date": rec.get("ddiv"),   # "DD.MM.YYYY" или None
                                    "amount": rec.get("divr"),    # float/str/None
                                    "utv": rec.get("utv"),        # 0/1/2
                                }
        except Exception:
            # переподключение с бэкофом
            time.sleep(2)
            continue

def start_quik_listener(host: str | None = None, port: int | None = None) -> None:
    """
    Стартуем единственный поток‑слушатель. Повторные вызовы — no‑op,
    если поток уже жив.
    """
    global _listener_thread
    host = host or settings.TCP_HOST
    port = port or settings.TCP_PORT

    with _listener_lock:
        if _listener_thread and _listener_thread.is_alive():
            # уже запущен
            return
        # создаём новый поток и запоминаем ссылку
        _listener_thread = threading.Thread(
            target=_loop, args=(host, port), name="QUIK-TCP-Listener", daemon=True
        )
        _listener_thread.start()
