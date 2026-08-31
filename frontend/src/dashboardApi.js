import { API_BASE } from "./marketplaceToolsApi";

const DASHBOARD_REQUEST_TIMEOUT_MS = 25_000;

export async function getMarketplaceSalesDashboard(
  period,
  { forceRefresh = false, signal } = {}
) {
  const params = new URLSearchParams({
    period,
    force_refresh: String(forceRefresh),
  });
  const controller = new AbortController();
  let timedOut = false;
  const abortFromParent = () => controller.abort();

  if (signal?.aborted) {
    controller.abort();
  } else {
    signal?.addEventListener("abort", abortFromParent, { once: true });
  }

  const timeoutId = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, DASHBOARD_REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(
      `${API_BASE}/api/dashboard/marketplace-sales?${params.toString()}`,
      { signal: controller.signal }
    );
    const payload = await response.json().catch(() => null);

    if (!response.ok) {
      const detail =
        typeof payload?.detail === "string"
          ? payload.detail
          : "Не удалось загрузить продажи маркетплейсов";
      throw new Error(detail);
    }

    return payload;
  } catch (error) {
    if (timedOut) {
      throw new Error(
        "Площадки отвечают слишком долго. Обнови данные ещё раз: готовый отчёт будет взят из кэша.",
        { cause: error }
      );
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
    signal?.removeEventListener("abort", abortFromParent);
  }
}
