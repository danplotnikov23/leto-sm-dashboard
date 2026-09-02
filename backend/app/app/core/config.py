from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Лето СМ Платформа"
    target_store_name: str = "Лето стройматериалы"
    database_url: str = Field(default="sqlite:///./leto_bi.db")
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:18174",
            "http://127.0.0.1:18174",
        ],
    )
    default_vat_rate: float = 0.22
    profit_tax_rate: float = 0.20
    ozon_account_label: str = "Аллея мебели"
    ozon_account_usage_mode: str = "benchmark_account"
    ozon_client_id: str | None = None
    ozon_api_key: str | None = None
    ozon_api_base_url: str = "https://api-seller.ozon.ru"
    ozon_performance_client_id: str | None = None
    ozon_performance_client_secret: str | None = None
    ozon_performance_base_url: str = "https://api-performance.ozon.ru"
    ozon_seller_web_base_url: str = "https://seller.ozon.ru"
    ozon_seller_web_cookie: str | None = None
    ozon_request_timeout: float = 20.0

    # Собственный кабинет Ozon (Лето СМ / ассортимент Центр СМ) — НАМЕРЕННО отдельные
    # переменные от ozon_client_id/ozon_api_key выше. Те принадлежат бенчмарк-аккаунту
    # "Аллея мебели" (см. ozon_account_usage_mode) и используются только для сравнения
    # конкурентов в Каталоге поставщиков. Путать эти два аккаунта нельзя — это разные
    # магазины Ozon с разными данными о реальных продажах.
    own_ozon_account_label: str = "Лето СМ (Центр СМ)"
    own_ozon_client_id: str | None = None
    own_ozon_api_key: str | None = None

    # Мониторинг остатков (перенесено из projects/stock-monitor) — сверка остатков на Ozon
    # с остатками у поставщика tdcsm.ru.
    tdcsm_api_base_url: str = "https://tdcsm.ru"
    stock_threshold: int = 10
    stock_warehouse_id: str = "1020005026094810"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
