# Скринер (QUIK + FastAPI + React)


- QLua читает `quik/Data250818.lua` и пул фьючерсов из `data/futures_pool.txt`, шлёт JSON в `backend` по TCP.
- Backend агрегирует и считает колонки, фронт рисует таблицу. Интервалы: 3 сек / 10 мин (пуллинг).


## Запуск
1) **QUIK**: скопируй `quik/stream_quotes.lua` и `quik/Data250818.lua` в каталог скриптов, подправь путь к `futures_pool.txt` в `stream_quotes.lua`.
2) **Backend**:
```bash
cd backend
pip install -r requirements.txt
python run.py