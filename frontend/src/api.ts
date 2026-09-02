import type {
  CompetitorImportResponse,
  DashboardResponse,
  OzonCategoryTreeCheckResponse,
  OzonPerformanceTokenCheckResponse,
  OzonProductListResponse,
  OzonSellerAnalyticsAccessCheckResponse,
  OzonSellerAnalyticsImportResponse,
  OzonSellerAnalyticsPlanResponse,
  OzonSellerAnalyticsStatusResponse,
  OzonStatusResponse,
  PriceImportVersion,
  ProductAnalysis,
  ShortlistItem,
  ShortlistResponse,
  ShortlistStockRefreshResponse,
  ShortlistUpdatePayload,
  StockApplyResult,
  StockSnapshot,
  OzonOrdersResponse,
  PurchasePriceApplyResult,
  PurchasePriceSnapshot,
  UnitkaAssumptions,
  UnitkaImportResult,
  UnitkaItem,
  UnitkaRow,
} from "./types";

export const API_URL = import.meta.env.VITE_API_URL ?? "/api";
const AUTH_STORAGE_KEY = "leto_sm_auth";

/** Basic-auth токен, сохранённый после успешного входа (см. LoginGate в main.tsx). */
export function getStoredAuthToken(): string | null {
  try {
    return sessionStorage.getItem(AUTH_STORAGE_KEY);
  } catch {
    return null; // приватный режим браузера может блокировать sessionStorage
  }
}

export function storeAuthToken(token: string): void {
  try {
    sessionStorage.setItem(AUTH_STORAGE_KEY, token);
  } catch {
    // тихо игнорируем — платформа просто будет спрашивать пароль каждый раз
  }
}

export function clearStoredAuthToken(): void {
  try {
    sessionStorage.removeItem(AUTH_STORAGE_KEY);
  } catch {
    // см. storeAuthToken
  }
}

/** Обёртка над fetch — добавляет пароль (если есть) ко всем запросам к API платформы.
 * При 401 сбрасывает сохранённый токен и перезагружает страницу — LoginGate спросит
 * пароль заново (например, если его сменили на бэкенде). */
async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = getStoredAuthToken();
  const headers = new Headers(init.headers);
  if (token) {
    headers.set("Authorization", `Basic ${token}`);
  }
  const response = await fetch(input, { ...init, headers });
  if (response.status === 401 && token) {
    clearStoredAuthToken();
    window.location.reload();
  }
  return response;
}

async function apiErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail?.trim() || fallback;
  } catch {
    return fallback;
  }
}

export async function fetchDashboard(): Promise<DashboardResponse> {
  const response = await apiFetch(`${API_URL}/dashboard`);
  if (!response.ok) {
    throw new Error("Не удалось загрузить dashboard");
  }
  return response.json() as Promise<DashboardResponse>;
}

export async function fetchShortlist(): Promise<ShortlistResponse> {
  const response = await apiFetch(`${API_URL}/shortlist`);
  if (!response.ok) {
    throw new Error("Не удалось загрузить отбор");
  }
  return response.json() as Promise<ShortlistResponse>;
}

export async function fetchStockStatus(): Promise<StockSnapshot> {
  const response = await apiFetch(`${API_URL}/stock/status`);
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Не удалось загрузить остатки"));
  }
  return response.json() as Promise<StockSnapshot>;
}

export async function refreshStockStatus(): Promise<StockSnapshot> {
  const response = await apiFetch(`${API_URL}/stock/refresh`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Не удалось обновить остатки"));
  }
  return response.json() as Promise<StockSnapshot>;
}

export async function applyStockToOzon(): Promise<StockApplyResult> {
  const response = await apiFetch(`${API_URL}/stock/apply`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Не удалось применить остатки на Ozon"));
  }
  return response.json() as Promise<StockApplyResult>;
}

export async function refreshShortlistStocks(): Promise<ShortlistStockRefreshResponse> {
  const response = await apiFetch(`${API_URL}/shortlist/refresh-stocks`, { method: "POST" });
  if (!response.ok) {
    throw new Error("Не удалось обновить остатки отбора");
  }
  return response.json() as Promise<ShortlistStockRefreshResponse>;
}

export async function uploadShortlistFile(file: File): Promise<ShortlistResponse> {
  const form = new FormData();
  form.append("file", file);
  const response = await apiFetch(`${API_URL}/imports/shortlist`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw new Error("Не удалось загрузить файл отбора");
  }
  return response.json() as Promise<ShortlistResponse>;
}

export async function addShortlistItem(
  productId: string,
  payload: ShortlistUpdatePayload,
): Promise<ShortlistItem> {
  const response = await apiFetch(`${API_URL}/shortlist/products/${productId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Не удалось добавить товар в отбор"));
  }
  return response.json() as Promise<ShortlistItem>;
}

export async function updateShortlistItem(
  productId: string,
  payload: ShortlistUpdatePayload,
): Promise<ShortlistItem> {
  const response = await apiFetch(`${API_URL}/shortlist/products/${productId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Не удалось обновить отбор");
  }
  return response.json() as Promise<ShortlistItem>;
}

export async function deleteShortlistItem(productId: string): Promise<void> {
  const response = await apiFetch(`${API_URL}/shortlist/products/${productId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error("Не удалось удалить товар из отбора");
  }
}

export async function fetchImports(): Promise<PriceImportVersion[]> {
  const response = await apiFetch(`${API_URL}/imports`);
  if (!response.ok) {
    throw new Error("Не удалось загрузить версии прайсов");
  }
  return response.json() as Promise<PriceImportVersion[]>;
}

export async function uploadPrice(
  file: File,
  supplierName?: string,
): Promise<PriceImportVersion> {
  const form = new FormData();
  form.append("file", file);
  if (supplierName?.trim()) form.append("supplier_name", supplierName.trim());
  const response = await apiFetch(`${API_URL}/imports/prices`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw new Error("Не удалось импортировать прайс");
  }
  return response.json() as Promise<PriceImportVersion>;
}

export async function uploadCompetitors(file: File): Promise<CompetitorImportResponse> {
  const form = new FormData();
  form.append("file", file);
  const response = await apiFetch(`${API_URL}/imports/competitors`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw new Error("Не удалось импортировать конкурентов");
  }
  return response.json() as Promise<CompetitorImportResponse>;
}

export async function saveManualCompetitor(
  productId: string,
  payload: {
    price_vat_included: number;
    url: string;
    title?: string;
    match_type: "exact" | "analog" | "reference";
  },
): Promise<ProductAnalysis> {
  const response = await apiFetch(`${API_URL}/products/${productId}/competitor`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Не удалось сохранить конкурента");
  }
  return response.json() as Promise<ProductAnalysis>;
}

export async function fetchOzonOrders(days: number): Promise<OzonOrdersResponse> {
  const response = await apiFetch(`${API_URL}/ozon/orders?days=${days}`);
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Не удалось загрузить заказы Ozon"));
  }
  return response.json() as Promise<OzonOrdersResponse>;
}
export async function fetchOzonStatus(): Promise<OzonStatusResponse> {
  const response = await apiFetch(`${API_URL}/ozon/status`);
  if (!response.ok) {
    throw new Error("Не удалось проверить Seller API");
  }
  return response.json() as Promise<OzonStatusResponse>;
}

export async function fetchOzonPerformanceStatus(): Promise<OzonStatusResponse> {
  const response = await apiFetch(`${API_URL}/ozon/performance/status`);
  if (!response.ok) {
    throw new Error("Не удалось проверить Performance API");
  }
  return response.json() as Promise<OzonStatusResponse>;
}

export async function checkOzonCategoryTree(): Promise<OzonCategoryTreeCheckResponse> {
  const response = await apiFetch(`${API_URL}/ozon/check-category-tree`, { method: "POST" });
  if (!response.ok) {
    throw new Error("Ozon не вернул дерево категорий");
  }
  return response.json() as Promise<OzonCategoryTreeCheckResponse>;
}

export async function fetchOzonProducts(): Promise<OzonProductListResponse> {
  const response = await apiFetch(`${API_URL}/ozon/products?limit=5`);
  if (!response.ok) {
    throw new Error("Ozon не вернул товары");
  }
  return response.json() as Promise<OzonProductListResponse>;
}

export async function checkOzonPerformanceToken(): Promise<OzonPerformanceTokenCheckResponse> {
  const response = await apiFetch(`${API_URL}/ozon/performance/check-token`, { method: "POST" });
  if (!response.ok) {
    throw new Error("Performance API не выдал токен");
  }
  return response.json() as Promise<OzonPerformanceTokenCheckResponse>;
}

export async function fetchOzonSellerAnalyticsStatus(): Promise<OzonSellerAnalyticsStatusResponse> {
  const response = await apiFetch(`${API_URL}/ozon/seller-analytics/status`);
  if (!response.ok) {
    throw new Error("Не удалось проверить Ozon Seller Analytics");
  }
  return response.json() as Promise<OzonSellerAnalyticsStatusResponse>;
}

export async function checkOzonSellerAnalyticsAccess(): Promise<OzonSellerAnalyticsAccessCheckResponse> {
  const response = await apiFetch(`${API_URL}/ozon/seller-analytics/check-access`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response, "Не удалось проверить доступ к Ozon Seller"));
  }
  return response.json() as Promise<OzonSellerAnalyticsAccessCheckResponse>;
}

export async function buildOzonBestsellersPlan(
  search: string,
): Promise<OzonSellerAnalyticsPlanResponse> {
  const response = await apiFetch(`${API_URL}/ozon/seller-analytics/bestsellers-plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      search,
      limit: 50,
      offset: 0,
      period: "weekly",
      stock: "any_stock",
      sort_key: "GmvSum_desc",
    }),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response, "Не удалось построить план автосбора конкурентов"));
  }
  return response.json() as Promise<OzonSellerAnalyticsPlanResponse>;
}

export async function importOzonBestsellers(
  searches: string[],
): Promise<OzonSellerAnalyticsImportResponse> {
  const response = await apiFetch(`${API_URL}/ozon/seller-analytics/import-bestsellers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      searches,
      limit_per_search: 50,
      max_pages_per_search: 1,
      period: "weekly",
      stock: "any_stock",
      sort_key: "GmvSum_desc",
    }),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response, "Не удалось запустить автосбор конкурентов"));
  }
  return response.json() as Promise<OzonSellerAnalyticsImportResponse>;
}

export function unitEconomicsExportUrl(): string {
  return `${API_URL}/exports/unit-economics.xlsx`;
}

export function shortlistExportUrl(): string {
  return `${API_URL}/exports/shortlist.xlsx`;
}

export function shortlistFileExportUrl(): string {
  return `${API_URL}/exports/shortlist.json`;
}

async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") return payload.detail;
  } catch {
    return fallback;
  }
  return fallback;
}

export async function fetchUnitkaRows(): Promise<UnitkaItem[]> {
  const response = await apiFetch(`${API_URL}/unitka/rows`);
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Не удалось загрузить юнитку"));
  }
  return response.json() as Promise<UnitkaItem[]>;
}

export async function createUnitkaRow(row: Partial<UnitkaRow>): Promise<UnitkaItem> {
  const response = await apiFetch(`${API_URL}/unitka/rows`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(row),
  });
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Не удалось добавить строку"));
  }
  return response.json() as Promise<UnitkaItem>;
}

export async function updateUnitkaRow(id: string, row: UnitkaRow): Promise<UnitkaItem> {
  const response = await apiFetch(`${API_URL}/unitka/rows/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(row),
  });
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Не удалось сохранить изменения"));
  }
  return response.json() as Promise<UnitkaItem>;
}

export async function deleteUnitkaRow(id: string): Promise<void> {
  const response = await apiFetch(`${API_URL}/unitka/rows/${id}`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Не удалось удалить строку"));
  }
}

export async function importUnitkaFile(file: File): Promise<UnitkaImportResult> {
  const form = new FormData();
  form.append("file", file);
  const response = await apiFetch(`${API_URL}/unitka/import`, { method: "POST", body: form });
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Не удалось импортировать юнитку"));
  }
  return response.json() as Promise<UnitkaImportResult>;
}

export async function fetchUnitkaAssumptions(): Promise<UnitkaAssumptions> {
  const response = await apiFetch(`${API_URL}/unitka/assumptions`);
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Не удалось загрузить допущения юнитки"));
  }
  return response.json() as Promise<UnitkaAssumptions>;
}

export async function updateUnitkaAssumptions(
  assumptions: UnitkaAssumptions,
): Promise<UnitkaAssumptions> {
  const response = await apiFetch(`${API_URL}/unitka/assumptions`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(assumptions),
  });
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Не удалось сохранить допущения юнитки"));
  }
  return response.json() as Promise<UnitkaAssumptions>;
}

export async function refreshPurchasePrices(): Promise<PurchasePriceSnapshot> {
  const response = await apiFetch(`${API_URL}/purchase-prices/refresh`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Не удалось сверить закупочные цены"));
  }
  return response.json() as Promise<PurchasePriceSnapshot>;
}

export async function applyPurchasePrices(): Promise<PurchasePriceApplyResult> {
  const response = await apiFetch(`${API_URL}/purchase-prices/apply`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Не удалось применить закупочные цены"));
  }
  return response.json() as Promise<PurchasePriceApplyResult>;
}
