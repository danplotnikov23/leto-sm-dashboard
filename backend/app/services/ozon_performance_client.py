from datetime import UTC, datetime, timedelta
from io import BytesIO
from zipfile import ZipFile

import httpx

from app.core.config import Settings
from app.services.http_retry import request_with_retry
from app.services.ozon_errors import OzonApiError, OzonConfigurationError


class OzonPerformanceClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._access_token: str | None = None
        self._expires_at: datetime | None = None
        self._timeout_seconds = max(settings.request_timeout_seconds, 60)
        self._retry_count = max(settings.request_retry_count, 4)

    async def _get_access_token(
        self,
        timeout_seconds: float | None = None,
        retry_count: int | None = None,
    ) -> str:
        if not self._settings.performance_credentials_configured:
            raise OzonConfigurationError(
                "Ozon Performance API credentials are not configured"
            )

        if self._access_token and self._expires_at and self._expires_at > datetime.now(UTC):
            return self._access_token

        payload = {
            "client_id": self._settings.ozon_performance_client_id,
            "client_secret": self._settings.ozon_performance_client_secret,
            "grant_type": "client_credentials",
        }

        try:
            async with httpx.AsyncClient(
                timeout=timeout_seconds or self._timeout_seconds
            ) as client:
                response = await request_with_retry(
                    lambda: client.post(
                        f"{self._settings.ozon_performance_base_url}/api/client/token",
                        json=payload,
                    ),
                    self._retry_count if retry_count is None else retry_count,
                    retry_delay_seconds=2,
                )
        except httpx.RequestError as exc:
            reason = str(exc) or exc.__class__.__name__
            raise OzonApiError(
                f"Ozon Performance API token request failed: {reason}"
            ) from exc

        if response.status_code >= 400:
            raise OzonApiError(response.text, response.status_code)

        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("access_token"), str):
            raise OzonApiError("Ozon Performance API token response is invalid")

        expires_in = data.get("expires_in")
        ttl = int(expires_in) if isinstance(expires_in, int | str) else 1800
        self._access_token = data["access_token"]
        self._expires_at = datetime.now(UTC) + timedelta(seconds=max(ttl - 60, 60))
        return self._access_token

    async def request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await request_with_retry(
                    lambda: client.request(
                        method,
                        f"{self._settings.ozon_performance_base_url}{path}",
                        json=payload,
                        headers=headers,
                    ),
                    self._retry_count,
                    retry_delay_seconds=2,
                )
        except httpx.RequestError as exc:
            reason = str(exc) or exc.__class__.__name__
            raise OzonApiError(f"Ozon Performance API request failed: {reason}") from exc

        if response.status_code >= 400:
            raise OzonApiError(response.text, response.status_code)

        data = response.json()
        if not isinstance(data, dict):
            raise OzonApiError("Ozon Performance API returned non-object response")

        return data

    async def download_report(self, uuid: str) -> str:
        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await request_with_retry(
                    lambda: client.get(
                        f"{self._settings.ozon_performance_base_url}/api/client/statistics/report",
                        params={"UUID": uuid},
                        headers=headers,
                    ),
                    self._retry_count,
                    retry_delay_seconds=2,
                )
        except httpx.RequestError as exc:
            reason = str(exc) or exc.__class__.__name__
            raise OzonApiError(
                f"Ozon Performance API report download failed: {reason}"
            ) from exc

        if response.status_code >= 400:
            raise OzonApiError(response.text, response.status_code)

        return _decode_report_content(response.content)

    async def get_campaign_expense_csv(self, date_from: str, date_to: str) -> str:
        """Total ad spend per campaign for a date range.

        Unlike /api/client/statistics (which needs a list of campaign IDs and
        an async report-generation-and-poll cycle per 10 campaigns), this
        endpoint answers synchronously for the whole account in one call -
        the right fit for an unattended daily total, not per-SKU detail.
        """

        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await request_with_retry(
                    lambda: client.get(
                        f"{self._settings.ozon_performance_base_url}/api/client/statistics/expense",
                        params={"dateFrom": date_from, "dateTo": date_to},
                        headers=headers,
                    ),
                    self._retry_count,
                    retry_delay_seconds=2,
                )
        except httpx.RequestError as exc:
            reason = str(exc) or exc.__class__.__name__
            raise OzonApiError(
                f"Ozon Performance API expense request failed: {reason}"
            ) from exc

        if response.status_code >= 400:
            raise OzonApiError(response.text, response.status_code)

        return _decode_text(response.content)

    async def check_connection(self) -> None:
        await self._get_access_token(
            timeout_seconds=self._settings.health_timeout_seconds,
            retry_count=0,
        )


def _decode_report_content(content: bytes) -> str:
    if content.startswith(b"PK"):
        parts: list[str] = []
        with ZipFile(BytesIO(content)) as archive:
            for name in archive.namelist():
                if name.endswith("/"):
                    continue

                parts.append(_decode_text(archive.read(name)))

        return "\n".join(parts)

    return _decode_text(content)


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue

    return content.decode("utf-8-sig", errors="replace")
