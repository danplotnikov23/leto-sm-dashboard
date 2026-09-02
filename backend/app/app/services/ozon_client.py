from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from pydantic import BaseModel

from app.core.config import Settings


@dataclass(frozen=True)
class OzonCredentials:
    client_id: str
    api_key: str


class OzonIntegrationStatus(BaseModel):
    configured: bool
    base_url: str
    client_id_masked: str | None
    account_label: str
    target_store_name: str
    usage_mode: str
    data_scope_warning: str
    message: str


class OzonSellerClient:
    """Thin async client shell; secrets are injected, never stored in code."""

    def __init__(
        self,
        credentials: OzonCredentials,
        base_url: str = "https://api-seller.ozon.ru",
        timeout: float = 20.0,
    ) -> None:
        self.credentials = credentials
        self.base_url = base_url
        self.timeout = timeout

    async def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        headers = {
            "Client-Id": self.credentials.client_id,
            "Api-Key": self.credentials.api_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post(path, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                msg = "Ozon API вернул неожиданный формат ответа."
                raise ValueError(msg)
            return result

    async def get_description_category_tree(self, language: str = "RU") -> dict[str, object]:
        return await self.post("/v1/description-category/tree", {"language": language})

    async def get_product_prices(
        self,
        offer_ids: list[str],
        limit: int = 100,
        last_id: str = "",
    ) -> dict[str, object]:
        return await self.post(
            "/v5/product/info/prices",
            {
                "filter": {"offer_id": offer_ids},
                "limit": limit,
                "last_id": last_id,
            },
        )

    async def list_products(
        self,
        limit: int = 10,
        visibility: str = "ALL",
        last_id: str = "",
    ) -> dict[str, object]:
        return await self.post(
            "/v3/product/list",
            {
                "filter": {"visibility": visibility},
                "limit": min(max(limit, 1), 1000),
                "last_id": last_id,
            },
        )

    async def get_stocks_by_offer_ids(self, offer_ids: list[str]) -> dict[str, object]:
        """Остатки по offer_id (до 1000 за вызов, вызывающий код режет на чанки)."""
        return await self.post("/v3/product/info/list", {"offer_id": offer_ids})

    async def set_stocks(self, updates: list[dict[str, object]]) -> dict[str, object]:
        """updates: [{"offer_id": ..., "stock": int, "warehouse_id": int}, ...]."""
        return await self.post("/v2/products/stocks", {"stocks": updates})

    async def list_orders(
        self,
        since: datetime,
        to: datetime,
        status: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, object]:
        """FBS posting list (orders)."""
        payload: dict[str, object] = {
            "dir": "DESC",
            "filter": {
                "since": since.isoformat(),
                "to": to.isoformat(),
            },
            "limit": min(max(limit, 1), 1000),
            "offset": offset,
            "with": {
                "analytics_data": True,
                "financial_data": True,
            },
        }
        if status:
            payload["filter"]["status"] = status
        return await self.post("/v3/posting/fbs/list", payload)
        """updates: [{"offer_id": ..., "stock": int, "warehouse_id": int}, ...]."""
        return await self.post("/v2/products/stocks", {"stocks": updates})


class OzonClientFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def status(self) -> OzonIntegrationStatus:
        configured = self._has_credentials()
        return OzonIntegrationStatus(
            configured=configured,
            base_url=self.settings.ozon_api_base_url,
            client_id_masked=self._mask(self.settings.ozon_client_id),
            account_label=self.settings.ozon_account_label,
            target_store_name=self.settings.target_store_name,
            usage_mode=self.settings.ozon_account_usage_mode,
            data_scope_warning=self._data_scope_warning(),
            message="Ozon API настроен." if configured else "Нет OZON_CLIENT_ID или OZON_API_KEY.",
        )

    def create(self) -> OzonSellerClient:
        if not self._has_credentials():
            msg = "Ozon API не настроен: добавьте OZON_CLIENT_ID и OZON_API_KEY в backend/.env."
            raise RuntimeError(msg)
        return OzonSellerClient(
            credentials=OzonCredentials(
                client_id=self.settings.ozon_client_id or "",
                api_key=self.settings.ozon_api_key or "",
            ),
            base_url=self.settings.ozon_api_base_url,
            timeout=self.settings.ozon_request_timeout,
        )

    def _has_credentials(self) -> bool:
        return bool(self.settings.ozon_client_id and self.settings.ozon_api_key)

    def _mask(self, value: str | None) -> str | None:
        if not value:
            return None
        if len(value) <= 4:
            return "****"
        return f"{value[:2]}***{value[-2:]}"

    def _data_scope_warning(self) -> str:
        if self.settings.ozon_account_usage_mode == "target_store":
            return "Данные относятся к целевому кабинету магазина."
        return (
            f"Данные Ozon берутся из кабинета {self.settings.ozon_account_label} "
            f"и используются как временная аналитика для {self.settings.target_store_name}."
        )


class OzonPerformanceTokenCheck(BaseModel):
    ok: bool
    expires_in_seconds: int | None
    token_type: str | None
    message: str


class OzonPerformanceClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        base_url: str = "https://api-performance.ozon.ru",
        timeout: float = 20.0,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._access_token: str | None = None
        self._expires_at: datetime | None = None

    async def get_access_token(self) -> tuple[str, dict[str, object]]:
        if self._access_token and self._expires_at and self._expires_at > datetime.now(UTC):
            return self._access_token, {}

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post("/api/client/token", json=payload)
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or not isinstance(result.get("access_token"), str):
                msg = "Ozon Performance API вернул неожиданный формат токена."
                raise ValueError(msg)

        expires_in = _int_or_none(result.get("expires_in")) or 1800
        self._access_token = result["access_token"]
        self._expires_at = datetime.now(UTC) + timedelta(seconds=max(expires_in - 60, 60))
        return self._access_token, result

    async def request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        token, _ = await self.get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.request(method, path, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                msg = "Ozon Performance API вернул неожиданный формат ответа."
                raise ValueError(msg)
            return result

    async def check_token(self) -> OzonPerformanceTokenCheck:
        _, payload = await self.get_access_token()
        expires_in = _int_or_none(payload.get("expires_in"))
        token_type = payload.get("token_type")
        return OzonPerformanceTokenCheck(
            ok=True,
            expires_in_seconds=expires_in,
            token_type=str(token_type) if token_type else None,
            message="Performance API токен получен.",
        )


class OzonPerformanceClientFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def status(self) -> OzonIntegrationStatus:
        configured = self._has_credentials()
        return OzonIntegrationStatus(
            configured=configured,
            base_url=self.settings.ozon_performance_base_url,
            client_id_masked=self._mask(self.settings.ozon_performance_client_id),
            account_label=self.settings.ozon_account_label,
            target_store_name=self.settings.target_store_name,
            usage_mode=self.settings.ozon_account_usage_mode,
            data_scope_warning=self._data_scope_warning(),
            message="Ozon Performance API настроен."
            if configured
            else "Нет OZON_PERFORMANCE_CLIENT_ID или OZON_PERFORMANCE_CLIENT_SECRET.",
        )

    def create(self) -> OzonPerformanceClient:
        if not self._has_credentials():
            msg = (
                "Ozon Performance API не настроен: добавьте OZON_PERFORMANCE_CLIENT_ID "
                "и OZON_PERFORMANCE_CLIENT_SECRET в backend/.env."
            )
            raise RuntimeError(msg)
        return OzonPerformanceClient(
            client_id=self.settings.ozon_performance_client_id or "",
            client_secret=self.settings.ozon_performance_client_secret or "",
            base_url=self.settings.ozon_performance_base_url,
            timeout=self.settings.ozon_request_timeout,
        )

    def _has_credentials(self) -> bool:
        return bool(
            self.settings.ozon_performance_client_id
            and self.settings.ozon_performance_client_secret
        )

    def _mask(self, value: str | None) -> str | None:
        if not value:
            return None
        if len(value) <= 8:
            return "****"
        return f"{value[:4]}***{value[-4:]}"

    def _data_scope_warning(self) -> str:
        if self.settings.ozon_account_usage_mode == "target_store":
            return "Рекламная аналитика относится к целевому кабинету магазина."
        return (
            f"Рекламная аналитика берется из кабинета {self.settings.ozon_account_label} "
            f"и используется как временный ориентир для {self.settings.target_store_name}."
        )


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
