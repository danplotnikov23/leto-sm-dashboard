import re
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.domain.models import CompetitorOffer, DataSource

OzonSellerPeriod = Literal["weekly", "monthly"]
OzonSellerStock = Literal["any_stock", "with_stock", "without_stock"]


class OzonSellerAnalyticsStatus(BaseModel):
    configured: bool
    source: str = "ozon_seller_web"
    stability: str = "experimental"
    base_url: str
    cookie_configured: bool
    cookie_masked: str | None
    report_workflow: list[str]
    json_data_endpoint: str
    message: str
    warning: str


class OzonSellerAnalyticsAccessCheck(BaseModel):
    ok: bool
    configured: bool
    source: str = "ozon_seller_web"
    status_code: int | None = None
    offers_seen: int = 0
    message: str
    warning: str


class OzonBestsellersRequest(BaseModel):
    search: str | None = Field(
        default=None,
        description="Поисковый запрос из раздела 'Товары на Ozon', например 'гвозди'.",
    )
    categories: list[str] = Field(default_factory=list)
    period: OzonSellerPeriod = "weekly"
    stock: OzonSellerStock = "any_stock"
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    sort_key: str = "GmvSum_desc"


class OzonBestsellersImportRequest(BaseModel):
    searches: list[str] = Field(default_factory=list)
    period: OzonSellerPeriod = "weekly"
    stock: OzonSellerStock = "any_stock"
    limit_per_search: int = Field(default=50, ge=1, le=100)
    max_pages_per_search: int = Field(default=1, ge=1, le=10)
    sort_key: str = "GmvSum_desc"


class OzonSellerAnalyticsClient:
    """Client for Ozon Seller web analytics.

    This is not the public Seller API. It mirrors endpoints used by the Seller
    cabinet, so callers must treat it as an experimental source and keep
    credentials outside code.
    """

    data_endpoint = "/api/site/seller-analytics/what_to_sell/data/v3"
    widget_endpoint = "/api/site/seller-analytics/what_to_sell/data/widget_v2"
    categories_endpoint = "/api/site/seller-analytics/what_to_sell/get_categories"
    platform_data_endpoint = "/api/site/seller-analytics/what_to_sell/get_platform_data"
    report_create_endpoint = "/api/v1/report/what_to_sell"
    report_status_endpoint = "/api/v1/report/status/{code}"
    report_download_endpoint = "/api/v1/report/download/{code}"
    report_list_endpoint = "/api/v1/report/list"

    def __init__(
        self,
        base_url: str = "https://seller.ozon.ru",
        session_cookie: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session_cookie = session_cookie
        self.timeout = timeout

    def build_bestsellers_payload(self, request: OzonBestsellersRequest) -> dict[str, object]:
        filters: dict[str, object] = {
            "stock": request.stock,
            "period": request.period,
        }
        if request.search:
            key = "sku" if request.search.isdigit() else "name"
            filters[key] = request.search.strip()
        if request.categories:
            filters["categories"] = request.categories

        return {
            "limit": str(request.limit),
            "offset": str(request.offset),
            "filter": filters,
            "sort": {"key": request.sort_key},
        }

    def build_report_payload(self, request: OzonBestsellersRequest) -> dict[str, object]:
        payload = self.build_bestsellers_payload(request)
        return {
            "filter": payload["filter"],
            "sort": payload["sort"],
        }

    async def fetch_bestsellers(self, request: OzonBestsellersRequest) -> dict[str, object]:
        return await self._post_json(
            self.data_endpoint,
            self.build_bestsellers_payload(request),
        )

    async def check_access(self) -> OzonSellerAnalyticsAccessCheck:
        payload = await self.fetch_bestsellers(
            OzonBestsellersRequest(search="гвозди", limit=1, offset=0)
        )
        offers = parse_bestsellers_offers(payload)
        return OzonSellerAnalyticsAccessCheck(
            ok=True,
            configured=True,
            offers_seen=len(offers),
            message=(
                "Ozon Seller web-доступ работает. Можно запускать автосбор конкурентов."
            ),
            warning=OzonSellerAnalyticsFactory.web_api_warning(),
        )

    async def fetch_bestsellers_offers(
        self,
        request: OzonBestsellersImportRequest,
    ) -> list[CompetitorOffer]:
        offers: list[CompetitorOffer] = []
        for search in request.searches:
            for page in range(request.max_pages_per_search):
                page_request = OzonBestsellersRequest(
                    search=search,
                    period=request.period,
                    stock=request.stock,
                    limit=request.limit_per_search,
                    offset=page * request.limit_per_search,
                    sort_key=request.sort_key,
                )
                payload = await self.fetch_bestsellers(page_request)
                offers.extend(parse_bestsellers_offers(payload))
                if not _has_next_page(payload):
                    break
        return offers

    async def create_bestsellers_report(self, request: OzonBestsellersRequest) -> dict[str, object]:
        return await self._post_json(
            self.report_create_endpoint,
            self.build_report_payload(request),
        )

    async def get_report_status(self, code: str) -> dict[str, object]:
        path = self.report_status_endpoint.format(code=code)
        return await self._get_json(path)

    async def download_report(self, code: str) -> bytes:
        path = self.report_download_endpoint.format(code=code)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.get(path, headers=self._headers())
            response.raise_for_status()
            return response.content

    async def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post(path, json=payload, headers=self._headers())
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                msg = "Ozon Seller Analytics вернул неожиданный формат ответа."
                raise ValueError(msg)
            return result

    async def _get_json(self, path: str) -> dict[str, object]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.get(path, headers=self._headers())
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                msg = "Ozon Seller Analytics вернул неожиданный формат ответа."
                raise ValueError(msg)
            return result

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.session_cookie:
            headers["Cookie"] = self.session_cookie
        return headers


def parse_bestsellers_offers(payload: dict[str, object]) -> list[CompetitorOffer]:
    rows = _extract_items(payload)
    offers: list[CompetitorOffer] = []
    for row in rows:
        title = _first_text(row, ("title", "name", "itemName", "productName"))
        price = _first_money(
            row,
            (
                "minSellerPrice",
                "minPrice",
                "lowestPrice",
                "avgPrice",
                "avgGmv",
                "avgPurchasePrice",
            ),
        )
        if not title or price is None:
            continue
        sku = _first_text(row, ("sku", "ozonSku", "productId", "id", "variantId"))
        avg_purchase_price = _first_money(row, ("avgPrice", "avgGmv", "avgPurchasePrice"))
        offers.append(
            CompetitorOffer(
                sku=sku,
                title=title,
                price_vat_included=price,
                url=_first_url(row) or _ozon_product_url(sku),
                match_type="analog",
                orders_count=_first_int(row, ("soldCount", "orderedCount", "ordersCount")),
                avg_purchase_price=avg_purchase_price,
                buyout_rate=_first_percent(row, ("redemptionRate", "nullableRedemptionRate")),
                is_promo=bool(row.get("isPromo") or row.get("hasPromo")),
                source=DataSource.API,
            )
        )
    return offers


def _extract_items(payload: dict[str, object]) -> list[dict[str, object]]:
    for key in ("items", "result", "products", "rows"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _extract_items(value)
            if nested:
                return nested
    return []


def _has_next_page(payload: dict[str, object]) -> bool:
    value = payload.get("hasNext")
    return bool(value)


def _first_text(row: dict[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "none":
            return text
    return None


def _first_url(row: dict[str, object]) -> str | None:
    for key in ("url", "link", "productUrl", "itemUrl"):
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text.startswith("http://") or text.startswith("https://"):
            return text
    return None


def _ozon_product_url(sku: str | None) -> str | None:
    if not sku:
        return None
    if not sku.isdigit():
        return None
    return f"https://www.ozon.ru/product/{sku}/"


def _first_money(row: dict[str, object], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        parsed = _money(row.get(key))
        if parsed is not None:
            return parsed
    return None


def _first_int(row: dict[str, object], keys: tuple[str, ...]) -> int | None:
    parsed = _first_money(row, keys)
    return int(parsed) if parsed is not None else None


def _first_percent(row: dict[str, object], keys: tuple[str, ...]) -> float | None:
    parsed = _first_money(row, keys)
    if parsed is None:
        return None
    return parsed / 100 if parsed > 1 else parsed


def _money(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, dict):
        if "units" in value:
            units = _money(value.get("units")) or 0.0
            nanos = _money(value.get("nanos")) or 0.0
            return units + nanos / 1_000_000_000
        for key in ("amount", "value", "price"):
            parsed = _money(value.get(key))
            if parsed is not None:
                return parsed
    text = str(value).replace("\xa0", " ").replace(",", ".")
    match = re.search(r"-?\d+(?:\s\d{3})*(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0).replace(" ", ""))


class OzonSellerAnalyticsFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def status(self) -> OzonSellerAnalyticsStatus:
        configured = bool(self.settings.ozon_seller_web_cookie)
        return OzonSellerAnalyticsStatus(
            configured=configured,
            base_url=self.settings.ozon_seller_web_base_url,
            cookie_configured=configured,
            cookie_masked=self._mask(self.settings.ozon_seller_web_cookie),
            report_workflow=[
                OzonSellerAnalyticsClient.report_create_endpoint,
                OzonSellerAnalyticsClient.report_status_endpoint,
                OzonSellerAnalyticsClient.report_download_endpoint,
            ],
            json_data_endpoint=OzonSellerAnalyticsClient.data_endpoint,
            message=(
                "Ozon Seller web-аналитика настроена."
                if configured
                else "Нет OZON_SELLER_WEB_COOKIE. Прямой web-сбор выключен."
            ),
            warning=self.web_api_warning(),
        )

    def create(self) -> OzonSellerAnalyticsClient:
        if not self.settings.ozon_seller_web_cookie:
            msg = "Ozon Seller web-сбор не настроен: нет OZON_SELLER_WEB_COOKIE."
            raise RuntimeError(msg)
        return OzonSellerAnalyticsClient(
            base_url=self.settings.ozon_seller_web_base_url,
            session_cookie=self.settings.ozon_seller_web_cookie,
            timeout=self.settings.ozon_request_timeout,
        )

    def create_planner(self) -> OzonSellerAnalyticsClient:
        return OzonSellerAnalyticsClient(
            base_url=self.settings.ozon_seller_web_base_url,
            timeout=self.settings.ozon_request_timeout,
        )

    def _mask(self, value: str | None) -> str | None:
        if not value:
            return None
        if len(value) <= 12:
            return "****"
        return f"{value[:4]}***{value[-4:]}"

    @staticmethod
    def web_api_warning() -> str:
        return (
            "Это внутренний web-API кабинета Ozon Seller, не публичный Seller API. "
            "Использовать как экспериментальный источник и держать XLSX-импорт fallback."
        )
