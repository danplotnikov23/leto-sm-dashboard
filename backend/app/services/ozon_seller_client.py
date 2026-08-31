import asyncio
from datetime import date, datetime

import httpx

from app.core.config import Settings
from app.schemas.ozon import OzonPromotionInfo
from app.services.http_retry import request_with_retry
from app.services.ozon_errors import OzonApiError, OzonConfigurationError


class OzonSellerClient:
    _rate_limit_lock = asyncio.Lock()
    _last_request_at = 0.0
    _min_request_interval_seconds = 1.1
    _rate_limit_retry_count = 12

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def request(
        self,
        path: str,
        payload: dict[str, object] | None = None,
        timeout_seconds: float | None = None,
        retry_count: int | None = None,
        method: str = "POST",
    ) -> dict[str, object]:
        if not self._settings.seller_credentials_configured:
            raise OzonConfigurationError("Ozon Seller API credentials are not configured")

        headers = {
            "Client-Id": self._settings.ozon_seller_client_id or "",
            "Api-Key": self._settings.ozon_seller_api_key or "",
            "Content-Type": "application/json",
        }

        url = f"{self._settings.ozon_seller_base_url}{path}"
        retries = self._settings.request_retry_count if retry_count is None else retry_count
        max_attempts = max(retries, self._rate_limit_retry_count) + 1
        response: httpx.Response | None = None

        try:
            async with httpx.AsyncClient(
                timeout=timeout_seconds or self._settings.request_timeout_seconds
            ) as client:
                for attempt in range(max_attempts):
                    await self._wait_for_rate_slot()
                    response = await request_with_retry(
                        lambda: client.request(
                            method,
                            url,
                            json=payload if method.upper() != "GET" else None,
                            headers=headers,
                        ),
                        retries,
                    )
                    if not _is_seller_rate_limit_response(response):
                        break

                    if attempt == max_attempts - 1:
                        break

                    await asyncio.sleep(_seller_rate_limit_wait_seconds(response, attempt))
        except httpx.RequestError as exc:
            reason = str(exc) or exc.__class__.__name__
            raise OzonApiError(f"Ozon Seller API request failed: {reason}") from exc

        if response is None:
            raise OzonApiError("Ozon Seller API request failed without response")

        if response.status_code >= 400:
            raise OzonApiError(response.text, response.status_code)

        data = response.json()
        if not isinstance(data, dict):
            raise OzonApiError("Ozon Seller API returned non-object response")

        return data

    async def _wait_for_rate_slot(self) -> None:
        async with self._rate_limit_lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            wait_seconds = (
                self._last_request_at + self._min_request_interval_seconds - now
            )
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)

            self.__class__._last_request_at = loop.time()

    async def check_connection(self) -> None:
        await self.request(
            "/v3/product/list",
            {"filter": {"visibility": "ALL"}, "limit": 1, "last_id": ""},
            timeout_seconds=self._settings.health_timeout_seconds,
            retry_count=0,
        )

    async def get_products_by_sku(
        self,
        skus: list[str],
    ) -> dict[str, dict[str, object]]:
        products_by_sku: dict[str, dict[str, object]] = {}
        normalized_skus = list(
            dict.fromkeys(sku.strip() for sku in skus if sku.strip())
        )

        for chunk in _chunked(normalized_skus, 100):
            products_by_sku.update(
                await self._get_products_by_sku_resilient(chunk)
            )

        return products_by_sku

    async def _get_products_by_sku_resilient(
        self,
        skus: list[str],
    ) -> dict[str, dict[str, object]]:
        if not skus:
            return {}

        try:
            data = await self.request("/v3/product/info/list", {"sku": skus})
        except OzonApiError:
            if len(skus) == 1:
                return {}

            middle = len(skus) // 2
            left = await self._get_products_by_sku_resilient(skus[:middle])
            right = await self._get_products_by_sku_resilient(skus[middle:])
            return {**left, **right}

        items = data.get("items", [])
        if not isinstance(items, list):
            return {}

        products_by_sku: dict[str, dict[str, object]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue

            sku = _extract_sku(item)
            if sku is not None:
                products_by_sku[sku] = item

        return products_by_sku

    async def get_products_by_offer_id(
        self,
        offer_ids: list[str],
    ) -> dict[str, dict[str, object]]:
        products_by_offer_id: dict[str, dict[str, object]] = {}

        for chunk in _chunked(offer_ids, 1000):
            data = await self.request("/v3/product/info/list", {"offer_id": chunk})
            items = data.get("items", [])
            if not isinstance(items, list):
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue

                offer_id = _optional_text(item.get("offer_id"))
                if offer_id is None:
                    continue

                products_by_offer_id[offer_id] = item

        return products_by_offer_id

    async def get_product_attributes_by_offer_id(
        self,
        offer_ids: list[str],
    ) -> dict[str, dict[str, object]]:
        products_by_offer_id: dict[str, dict[str, object]] = {}

        for chunk in _chunked(offer_ids, 1000):
            data = await self.request(
                "/v4/product/info/attributes",
                {
                    "filter": {"offer_id": chunk, "visibility": "ALL"},
                    "limit": len(chunk),
                    "last_id": "",
                },
            )
            items = data.get("result", [])
            if not isinstance(items, list):
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue

                offer_id = _optional_text(item.get("offer_id"))
                if offer_id is None:
                    continue

                products_by_offer_id[offer_id] = item

        return products_by_offer_id

    async def get_product_prices_by_offer_id(
        self,
        offer_ids: list[str],
    ) -> dict[str, dict[str, object]]:
        products_by_offer_id: dict[str, dict[str, object]] = {}

        for chunk in _chunked(offer_ids, 1000):
            data = await self.request(
                "/v5/product/info/prices",
                {
                    "filter": {"offer_id": chunk, "visibility": "ALL"},
                    "limit": len(chunk),
                    "cursor": "",
                },
            )
            items = data.get("items", [])
            if not isinstance(items, list):
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue

                offer_id = _optional_text(item.get("offer_id"))
                if offer_id is None:
                    continue

                products_by_offer_id[offer_id] = item

        return products_by_offer_id

    async def get_products_by_product_id(
        self,
        product_ids: list[str],
    ) -> dict[str, dict[str, object]]:
        products_by_product_id: dict[str, dict[str, object]] = {}

        for chunk in _chunked(product_ids, 1000):
            data = await self.request("/v3/product/info/list", {"product_id": chunk})
            items = data.get("items", [])
            if not isinstance(items, list):
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue

                product_id = _optional_text(item.get("id") or item.get("product_id"))
                if product_id is None:
                    continue

                products_by_product_id[product_id] = item

        return products_by_product_id

    async def list_products(
        self,
        limit: int = 100,
        visibility: str = "ALL",
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        last_id = ""
        page_limit = min(max(limit, 1), 1000)

        while len(rows) < limit:
            data = await self.request(
                "/v3/product/list",
                {
                    "filter": {"visibility": visibility},
                    "limit": min(page_limit, limit - len(rows)),
                    "last_id": last_id,
                },
            )
            result = data.get("result")
            if not isinstance(result, dict):
                break

            items = result.get("items")
            if not isinstance(items, list) or not items:
                break

            rows.extend(item for item in items if isinstance(item, dict))
            next_last_id = _optional_text(result.get("last_id"))
            if not next_last_id or next_last_id == last_id:
                break

            last_id = next_last_id

        product_ids = [
            product_id
            for item in rows
            if (product_id := _optional_text(item.get("product_id") or item.get("id")))
        ]
        if not product_ids:
            return rows[:limit]

        detailed = await self.get_products_by_product_id(product_ids[:limit])
        return [
            detailed.get(product_id, item)
            for item in rows[:limit]
            if (product_id := _optional_text(item.get("product_id") or item.get("id")))
        ]

    async def get_analytics_sales_by_sku(
        self,
        date_from: str,
        date_to: str,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        limit = 1000
        offset = 0

        while True:
            data = await self.request(
                "/v1/analytics/data",
                {
                    "date_from": date_from,
                    "date_to": date_to,
                    "metrics": ["ordered_units", "revenue"],
                    "dimension": ["sku"],
                    "filters": [],
                    "sort": [{"key": "ordered_units", "order": "DESC"}],
                    "limit": limit,
                    "offset": offset,
                },
            )
            result = data.get("result")
            if not isinstance(result, dict):
                break

            page_rows = result.get("data")
            if not isinstance(page_rows, list) or not page_rows:
                break

            rows.extend(row for row in page_rows if isinstance(row, dict))
            if len(page_rows) < limit:
                break

            offset += limit

        return rows

    async def get_analytics_sales_with_cancellations_by_sku(
        self,
        date_from: str,
        date_to: str,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        limit = 1000
        offset = 0

        while True:
            data = await self.request(
                "/v1/analytics/data",
                {
                    "date_from": date_from,
                    "date_to": date_to,
                    "metrics": ["ordered_units", "revenue", "cancellations"],
                    "dimension": ["sku"],
                    "filters": [],
                    "sort": [{"key": "ordered_units", "order": "DESC"}],
                    "limit": limit,
                    "offset": offset,
                },
            )
            result = data.get("result")
            if not isinstance(result, dict):
                break

            page_rows = result.get("data")
            if not isinstance(page_rows, list) or not page_rows:
                break

            rows.extend(row for row in page_rows if isinstance(row, dict))
            if len(page_rows) < limit:
                break

            offset += limit

        return rows

    async def get_analytics_sales_by_day(
        self,
        date_from: str,
        date_to: str,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        limit = 1000
        offset = 0

        while True:
            data = await self.request(
                "/v1/analytics/data",
                {
                    "date_from": date_from,
                    "date_to": date_to,
                    "metrics": ["ordered_units", "revenue"],
                    "dimension": ["day"],
                    "filters": [],
                    "sort": [{"key": "revenue", "order": "DESC"}],
                    "limit": limit,
                    "offset": offset,
                },
            )
            result = data.get("result")
            if not isinstance(result, dict):
                break

            page_rows = result.get("data")
            if not isinstance(page_rows, list) or not page_rows:
                break

            rows.extend(row for row in page_rows if isinstance(row, dict))
            if len(page_rows) < limit:
                break

            offset += limit

        return rows

    async def get_analytics_sales_by_sku_day(
        self,
        date_from: str,
        date_to: str,
        sku: str,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        limit = 1000
        offset = 0

        while True:
            data = await self.request(
                "/v1/analytics/data",
                {
                    "date_from": date_from,
                    "date_to": date_to,
                    "metrics": ["ordered_units", "revenue"],
                    "dimension": ["sku", "day"],
                    "filters": [{"key": "sku", "op": "EQ", "value": sku}],
                    "sort": [{"key": "revenue", "order": "DESC"}],
                    "limit": limit,
                    "offset": offset,
                },
            )
            result = data.get("result")
            if not isinstance(result, dict):
                break

            page_rows = result.get("data")
            if not isinstance(page_rows, list) or not page_rows:
                break

            rows.extend(row for row in page_rows if isinstance(row, dict))
            if len(page_rows) < limit:
                break

            offset += limit

        return rows

    async def get_fbs_posting(self, posting_number: str) -> dict[str, object]:
        data = await self.request(
            "/v3/posting/fbs/get",
            {
                "posting_number": posting_number,
                "with": {
                    "analytics_data": True,
                    "financial_data": True,
                },
            },
        )
        result = data.get("result")
        if not isinstance(result, dict):
            raise OzonApiError("Ozon Seller API returned no order data")
        return result

    async def list_fbs_postings(
        self,
        since_iso: str,
        to_iso: str,
    ) -> list[dict[str, object]]:
        postings: list[dict[str, object]] = []
        offset = 0
        page_limit = 1000

        while True:
            data = await self.request(
                "/v3/posting/fbs/list",
                {
                    "dir": "DESC",
                    "filter": {"since": since_iso, "to": to_iso},
                    "limit": page_limit,
                    "offset": offset,
                    "with": {"analytics_data": False, "financial_data": False},
                },
            )
            result = data.get("result", {})
            if not isinstance(result, dict):
                break

            page = result.get("postings", [])
            if isinstance(page, list):
                postings.extend(item for item in page if isinstance(item, dict))

            if not result.get("has_next") or not page:
                break
            offset += page_limit

        return postings

    async def get_promotions_by_product_id(
        self,
        date_from: str,
        date_to: str,
        product_ids: list[str],
    ) -> dict[str, list[OzonPromotionInfo]]:
        requested_ids = {str(product_id) for product_id in product_ids if product_id}
        if not requested_ids:
            return {}

        actions = await self.get_actions_for_period(date_from, date_to)
        promotions_by_product_id: dict[str, list[OzonPromotionInfo]] = {}

        for action in actions:
            action_id = _optional_text(action.get("id") or action.get("action_id"))
            if action_id is None:
                continue

            for product in await self.get_action_products(action_id):
                product_id = _optional_text(
                    product.get("id")
                    or product.get("product_id")
                    or product.get("productId")
                )
                if product_id is None or product_id not in requested_ids:
                    continue

                promotion = _build_promotion_info(action, product, product_id)
                promotions_by_product_id.setdefault(product_id, []).append(promotion)

        return promotions_by_product_id

    async def get_stocks(self, limit: int = 1000) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        last_id = ""
        page_limit = 1000

        while len(rows) < limit:
            data = await self.request(
                "/v4/product/info/stocks",
                {
                    "filter": {"visibility": "ALL"},
                    "limit": min(page_limit, limit - len(rows)),
                    "last_id": last_id,
                },
            )

            items = data.get("items")
            if not isinstance(items, list) or not items:
                break

            for item in items:
                if not isinstance(item, dict):
                    continue
                offer_id = _optional_text(item.get("offer_id"))
                stocks = item.get("stocks")
                if not isinstance(stocks, list):
                    continue
                for stock in stocks:
                    if not isinstance(stock, dict):
                        continue
                    rows.append({
                        "sku": stock.get("sku"),
                        "offer_id": offer_id,
                        "type": stock.get("type"),
                        "present": stock.get("present"),
                        "reserved": stock.get("reserved"),
                        "shipped": stock.get("shipped"),
                    })

            if len(items) < page_limit:
                break

            last_id = _optional_text(data.get("last_id")) or ""

        return rows[:limit]
        rows: list[dict[str, object]] = []
        offset = 0
        page_limit = 1000

        while len(rows) < limit:
            data = await self.request(
                "/v4/product/info/stocks",
                {
                    "filter": {"visibility": "ALL"},
                    "limit": min(page_limit, limit - len(rows)),
                    "offset": offset,
                },
            )
            result = data.get("result")
            if not isinstance(result, dict):
                break

            items = result.get("items")
            if not isinstance(items, list) or not items:
                break

            rows.extend(item for item in items if isinstance(item, dict))
            if len(items) < page_limit:
                break
            offset += page_limit

        return rows[:limit]

    async def get_actions_for_period(
        self,
        date_from: str,
        date_to: str,
    ) -> list[dict[str, object]]:
        data = await self._request_actions()
        raw_actions = data.get("result") or data.get("actions") or data.get("items") or []
        if isinstance(raw_actions, dict):
            raw_actions = raw_actions.get("actions") or raw_actions.get("items") or []
        if not isinstance(raw_actions, list):
            return []

        return [
            action
            for action in raw_actions
            if isinstance(action, dict)
            and _action_overlaps_period(action, date_from, date_to)
        ]

    async def _request_actions(self) -> dict[str, object]:
        try:
            return await self.request("/v1/actions", method="GET")
        except OzonApiError as exc:
            if exc.status_code not in {404, 405}:
                raise

        return await self.request("/v1/actions", {}, method="POST")

    async def get_action_products(self, action_id: str) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        limit = 1000
        offset = 0

        while True:
            data = await self.request(
                "/v1/actions/products",
                {"action_id": int(action_id) if action_id.isdigit() else action_id, "limit": limit, "offset": offset},
            )
            raw_items = data.get("result") or data.get("products") or data.get("items") or []
            if isinstance(raw_items, dict):
                raw_items = raw_items.get("products") or raw_items.get("items") or []
            if not isinstance(raw_items, list) or not raw_items:
                break

            rows.extend(item for item in raw_items if isinstance(item, dict))
            if len(raw_items) < limit:
                break

            offset += limit

        return rows


def _chunked(values: list[str], chunk_size: int) -> list[list[str]]:
    return [values[index : index + chunk_size] for index in range(0, len(values), chunk_size)]


def _is_seller_rate_limit_response(response: httpx.Response) -> bool:
    if response.status_code == 429:
        return True

    try:
        data = response.json()
    except ValueError:
        return "rate limit" in response.text.lower()

    if not isinstance(data, dict):
        return False

    message = str(data.get("message", "")).lower()
    code = data.get("code")
    return code == 8 or "rate limit" in message or "max rate per sec" in message


def _seller_rate_limit_wait_seconds(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        try:
            return max(float(retry_after), 1.0)
        except ValueError:
            pass

    return min(3.0 * (attempt + 1), 30.0)


def _extract_sku(item: dict[str, object]) -> str | None:
    sku = item.get("sku")
    if sku is not None:
        return str(sku)

    sources = item.get("sources")
    if not isinstance(sources, list):
        return None

    for source in sources:
        if not isinstance(source, dict):
            continue

        source_sku = source.get("sku")
        if source_sku is not None:
            return str(source_sku)

    return None


def _action_overlaps_period(
    action: dict[str, object],
    date_from: str,
    date_to: str,
) -> bool:
    period_start = _parse_date(date_from)
    period_end = _parse_date(date_to)
    if period_start is None or period_end is None:
        return True

    action_start = _parse_date(
        action.get("date_start")
        or action.get("dateStart")
        or action.get("start_date")
        or action.get("startDate")
        or action.get("from")
    )
    action_end = _parse_date(
        action.get("date_end")
        or action.get("dateEnd")
        or action.get("end_date")
        or action.get("endDate")
        or action.get("to")
    )

    if action_start is not None and action_start > period_end:
        return False
    if action_end is not None and action_end < period_start:
        return False
    return True


def _build_promotion_info(
    action: dict[str, object],
    product: dict[str, object],
    product_id: str,
) -> OzonPromotionInfo:
    price = _parse_optional_float(
        product.get("price")
        or product.get("current_price")
        or product.get("currentPrice")
    )
    action_price = _parse_optional_float(
        product.get("action_price")
        or product.get("actionPrice")
        or product.get("discount_price")
        or product.get("discountPrice")
    )
    max_action_price = _parse_optional_float(
        product.get("max_action_price")
        or product.get("maxActionPrice")
        or product.get("max_price")
        or product.get("maxPrice")
    )
    discount_percent = _parse_optional_float(
        product.get("discount")
        or product.get("discount_percent")
        or product.get("discountPercent")
    )
    if discount_percent is None:
        compared_price = action_price or max_action_price
        if price is not None and compared_price is not None and price > 0:
            discount_percent = max(0.0, (1 - compared_price / price) * 100)

    return OzonPromotionInfo(
        action_id=str(action.get("id") or action.get("action_id") or ""),
        title=_optional_text(
            action.get("title")
            or action.get("name")
            or action.get("action_name")
        ),
        date_start=_optional_text(
            action.get("date_start")
            or action.get("dateStart")
            or action.get("start_date")
            or action.get("startDate")
        ),
        date_end=_optional_text(
            action.get("date_end")
            or action.get("dateEnd")
            or action.get("end_date")
            or action.get("endDate")
        ),
        product_id=product_id,
        price_with_vat=price,
        action_price_with_vat=action_price,
        max_action_price_with_vat=max_action_price,
        discount_percent=discount_percent,
    )


def _parse_date(value: object) -> date | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    for candidate in (text[:10], text):
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _parse_optional_float(value: object) -> float | None:
    if value is None:
        return None

    normalized = (
        str(value)
        .replace("\u00a0", "")
        .replace(" ", "")
        .replace("₽", "")
        .replace("%", "")
        .replace(",", ".")
        .strip()
    )
    if not normalized:
        return None

    try:
        return float(normalized)
    except ValueError:
        return None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None
