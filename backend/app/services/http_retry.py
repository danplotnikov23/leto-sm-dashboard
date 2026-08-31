from collections.abc import Awaitable, Callable
import asyncio

import httpx


async def request_with_retry(
    request_factory: Callable[[], Awaitable[httpx.Response]],
    retry_count: int,
    retry_delay_seconds: float = 1.0,
) -> httpx.Response:
    last_error: httpx.RequestError | None = None

    attempts = max(retry_count, 0) + 1
    for attempt in range(attempts):
        try:
            return await request_factory()
        except httpx.RequestError as exc:
            last_error = exc
            if attempt < attempts - 1:
                await asyncio.sleep(retry_delay_seconds * (attempt + 1))

    if last_error is None:
        raise RuntimeError("HTTP request retry failed without captured error")

    raise last_error
