from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    RISK_FREE: float = 0.12 # годовая ставка r
    TCP_HOST: str = "127.0.0.1" # где QLua шлёт данные
    TCP_PORT: int = 40100
    FUTURES_POOL_PATH: str = "data/futures_pool.txt"


    settings = Settings()