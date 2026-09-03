import {
  Fragment,
  type CSSProperties,
  type Dispatch,
  type FormEvent,
  type ReactNode,
} from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowDownUp,
  Boxes,
  Calculator,
  CircleHelp,
  Download,
  FileSpreadsheet,
  LayoutDashboard,
  Maximize2,
  Minimize2,
  Moon,
  PlugZap,
  RefreshCw,
  Search,
  ShoppingCart,
  Sun,
} from "lucide-react";
import {
  addShortlistItem,
  applyStockToOzon,
  buildOzonBestsellersPlan,
  checkOzonCategoryTree,
  checkOzonPerformanceToken,
  checkOzonSellerAnalyticsAccess,
  createUnitkaRow,
  deleteShortlistItem,
  deleteUnitkaRow,
  applyPurchasePrices,
  fetchDashboard,
  fetchImports,
  fetchOzonOrders,
  fetchOzonPerformanceStatus,
  fetchOzonProducts,
  fetchOzonSellerAnalyticsStatus,
  fetchOzonStatus,
  fetchShortlist,
  fetchStockStatus,
  fetchUnitkaRows,
  fetchUnitkaAssumptions,
  getStoredAuthToken,
  importOzonBestsellers,
  importUnitkaFile,
  API_URL,
  refreshShortlistStocks,
  refreshPurchasePrices,
  refreshStockStatus,
  saveManualCompetitor,
  shortlistFileExportUrl,
  shortlistExportUrl,
  storeAuthToken,
  unitEconomicsExportUrl,
  updateShortlistItem,
  updateUnitkaAssumptions,
  updateUnitkaRow,
  uploadCompetitors,
  uploadPrice,
  uploadShortlistFile,
} from "./api";
import type {
  DashboardKpi,
  OzonCategoryTreeCheckResponse,
  OzonPerformanceTokenCheckResponse,
  OzonProductListResponse,
  OzonSellerAnalyticsAccessCheckResponse,
  OzonSellerAnalyticsPlanResponse,
  OzonSellerAnalyticsStatusResponse,
  OzonStatusResponse,
  OzonOrdersResponse,
  PriceImportVersion,
  ProductAnalysis,
  Recommendation,
  ShortlistItem,
  ShortlistUpdatePayload,
  StockSnapshot,
  StockStatus,
  PurchasePriceSnapshot,
  UnitkaAssumptions,
  UnitkaItem,
  UnitkaRow,
} from "./types";
import "./styles.css";
import { useEffect, useMemo, useRef, useState } from "react";

const statusOptions: Array<Recommendation | "Все"> = [
  "Все",
  "Заводить",
  "Заводить осторожно",
  "Только при повышении цены",
  "Только без акции",
  "Не заводить",
  "Нужна ручная проверка",
];

const tablePageSize = 200;

type SortKey =
  | "article"
  | "title"
  | "category"
  | "purchase"
  | "stock"
  | "listPrice"
  | "competitor"
  | "orders"
  | "profit"
  | "margin"
  | "recommended";
type SortDirection = "asc" | "desc";
type ProfitFilter = "Все" | "В плюс" | "В минус";
type StockFilter = "Все" | "В наличии" | "Нет в наличии" | "Не указан";
type ReadinessFilter = "Все" | "Готов к запуску" | "Нужны данные" | "Стоп";
type MatchType = "exact" | "analog" | "reference";
type ActiveTab = "catalog" | "shortlist";
type CompetitorDraft = {
  price: string;
  url: string;
  title: string;
  matchType: MatchType;
};

type Section = "home" | "unitka" | "purchase-prices" | "orders" | "stock" | "catalog";

// "catalog" (Каталог поставщиков) скрыт из меню по просьбе — сейчас работаем
// только с ассортиментом Центр СМ, инструмент подбора новых поставщиков пока
// не нужен. Код и страница никуда не делись (SupplierCatalogPage ниже), их
// легко вернуть в список — просто добавить строку обратно.
const sectionNavItems: { key: Section; label: string; icon: typeof LayoutDashboard }[] = [
  { key: "home", label: "Главная", icon: LayoutDashboard },
  { key: "unitka", label: "Юнитка", icon: Calculator },
  { key: "purchase-prices", label: "Закупочные цены", icon: RefreshCw },
  { key: "orders", label: "Заказы", icon: ShoppingCart },
  { key: "stock", label: "Остатки", icon: Boxes },
];

function ComingSoonPanel({ title, description }: { title: string; description: string }) {
  return (
    <div className="comingSoon">
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
  );
}

const stockStatusMeta: Record<StockStatus, { label: string; className: string }> = {
  critical: { label: "Ноль у поставщика", className: "stockBadge stockBadge-critical" },
  low: { label: "Мало у поставщика", className: "stockBadge stockBadge-low" },
  mismatch: { label: "На Ozon больше, чем у поставщика", className: "stockBadge stockBadge-mismatch" },
  restock: { label: "У поставщика снова есть", className: "stockBadge stockBadge-restock" },
  unknown: { label: "Не найден у поставщика", className: "stockBadge stockBadge-unknown" },
  ok: { label: "Ок", className: "stockBadge stockBadge-ok" },
};

function StockMonitorPage() {
  const [snapshot, setSnapshot] = useState<StockSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    fetchStockStatus()
      .then(setSnapshot)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  async function handleRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      setSnapshot(await refreshStockStatus());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }

  async function handleApply() {
    if (!snapshot || snapshot.diff_count === 0) return;
    if (
      !window.confirm(
        `Проставить на Ozon остаток поставщика по ${snapshot.diff_count} SKU? ` +
          "Это изменит реальные остатки в живом кабинете Ozon."
      )
    ) {
      return;
    }
    setApplying(true);
    setError(null);
    setNotice(null);
    try {
      const result = await applyStockToOzon();
      setNotice(result.message);
      if (result.ok) await handleRefresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setApplying(false);
    }
  }

  const flaggedRows = snapshot?.rows.filter((r) => r.status !== "ok") ?? [];

  return (
    <div>
      <header className="pageHeader">
        <div>
          <h2>Остатки</h2>
        </div>
        <div className="actions">
          <button
            className="uploadButton"
            type="button"
            onClick={() => void handleRefresh()}
            disabled={refreshing}
          >
            <RefreshCw size={16} />
            {refreshing ? "Обновляю…" : "Обновить сейчас"}
          </button>
        </div>
      </header>

      {error && <div className="alert">{error}</div>}
      {notice && <div className="alert alert-notice">{notice}</div>}

      {loading ? (
        <p className="eyebrow">Загрузка…</p>
      ) : !snapshot || snapshot.total === 0 ? (
        <div className="comingSoon">
          <p className="eyebrow">Нет данных</p>
          <h2>Ещё не проверяли</h2>
          <p>Нажмите «Обновить сейчас» — платформа сверит Ozon и tdcsm.ru прямо сейчас.</p>
        </div>
      ) : (
        <>
          <div className="kpis">
            <div className="coverageItem">
              <span>Всего SKU</span>
              <strong>{snapshot.total}</strong>
            </div>
            <div className="coverageItem">
              <span>🔴 Ноль у поставщика</span>
              <strong>{snapshot.counts.critical}</strong>
            </div>
            <div className="coverageItem">
              <span>🟡 Мало у поставщика</span>
              <strong>{snapshot.counts.low}</strong>
            </div>
            <div className="coverageItem">
              <span>⚠️ Расхождение с Ozon</span>
              <strong>{snapshot.counts.mismatch}</strong>
            </div>
            <div className="coverageItem">
              <span>🟢 Надо проставить остаток</span>
              <strong>{snapshot.counts.restock}</strong>
            </div>
          </div>

          <div className="importHeader" style={{ margin: "16px 0" }}>
            <span>
              Проверено: {snapshot.checked_at ? new Date(snapshot.checked_at).toLocaleString("ru-RU") : "—"}
              {" · "}Расхождений: {snapshot.diff_count}
            </span>
            <button
              className="uploadButton"
              type="button"
              onClick={() => void handleApply()}
              disabled={applying || snapshot.diff_count === 0}
              title={
                snapshot.diff_count === 0
                  ? "Расхождений нет"
                  : "Проставить на Ozon остаток поставщика по всем расхождениям"
              }
            >
              {applying ? "Применяю…" : `Применить остатки на Ozon (${snapshot.diff_count})`}
            </button>
          </div>

          {flaggedRows.length === 0 ? (
            <p className="noIssues">Расхождений нет — все остатки в норме.</p>
          ) : (
            <div className="issueList" style={{ maxHeight: "none" }}>
              {flaggedRows.map((row) => (
                <div key={row.offer_id} className="issue">
                  <span className={stockStatusMeta[row.status].className}>
                    {stockStatusMeta[row.status].label}
                  </span>
                  <strong>
                    {row.offer_id} — {row.name}
                  </strong>
                  <span>
                    Ozon: {row.ozon_stock} / Поставщик: {row.supplier_stock ?? "—"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function zeroFilledDaily(
  daily: { date: string; orders: number; revenue: number; qty: number }[],
  days: number,
): { date: string; orders: number; revenue: number; qty: number }[] {
  const byDate = new Map(daily.map((d) => [d.date, d]));
  const result: { date: string; orders: number; revenue: number; qty: number }[] = [];
  const today = new Date();
  for (let i = days - 1; i >= 0; i -= 1) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().slice(0, 10);
    result.push(byDate.get(dateStr) ?? { date: dateStr, orders: 0, revenue: 0, qty: 0 });
  }
  return result;
}

function formatDateShort(dateStr: string): string {
  return new Date(`${dateStr}T00:00:00`).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
  });
}

function formatDateLong(dateStr: string): string {
  return new Date(`${dateStr}T00:00:00`).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function formatRevenueScale(value: number): string {
  if (value === 0) return "0";
  if (value < 1_000) return `${value} ₽`;
  return `${Math.round(value / 1_000)} тыс.`;
}

function revenueScale(maxRevenue: number): { max: number; ticks: number[] } {
  const minimum = Math.max(maxRevenue, 5_000);
  const desiredStep = minimum / 6;
  const step = [1_000, 2_000, 5_000, 10_000, 20_000, 50_000, 100_000].find(
    (candidate) => candidate >= desiredStep,
  ) ?? 100_000;
  const max = Math.ceil(minimum / step) * step;
  const ticks = Array.from({ length: max / step + 1 }, (_, index) => index * step);
  return { max, ticks };
}

function HomeDashboardPage() {
  const [data, setData] = useState<OzonOrdersResponse | null>(null);
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchOzonOrders(days)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [days]);

  const todayStr = new Date().toISOString().slice(0, 10);
  const todayItem = data?.daily.find((d) => d.date === todayStr);
  const todayRevenue = todayItem?.revenue ?? 0;
  const todayQty = todayItem?.qty ?? 0;

  const currentMonth = todayStr.slice(0, 7);
  const monthItems = data?.daily.filter((d) => d.date.startsWith(currentMonth)) ?? [];
  const monthRevenue = monthItems.reduce((sum, d) => sum + d.revenue, 0);
  const monthQty = monthItems.reduce((sum, d) => sum + d.qty, 0);

  const periodLabels: Record<number, string> = {
    7: "7 дней",
    14: "2 недели",
    28: "4 недели",
    30: "Месяц",
  };

  const chartDays = data ? zeroFilledDaily(data.daily, days) : [];
  const maxRevenue = Math.max(1, ...chartDays.map((d) => d.revenue));
  const chartScale = revenueScale(maxRevenue);
  const labelEvery = days > 14 ? 4 : days > 7 ? 2 : 1;

  return (
    <div>
      <header className="pageHeader homePageHeader">
        <div className="ozonSalesHeading">
          <img className="ozonSalesLogo" src="/ozon-icon.png" alt="Ozon" />
          <h1><span>OZON</span> Продажи</h1>
        </div>
      </header>

      {error && <div className="alert">{error}</div>}

      <div className="periodTabs" style={{ display: "flex", gap: 8, margin: "16px 0" }}>
        {[7, 14, 28, 30].map((d) => (
          <button
            key={d}
            type="button"
            className={days === d ? "sortButton active" : "sortButton"}
            onClick={() => setDays(d)}
            style={{ fontWeight: days === d ? 700 : 400 }}
          >
            {periodLabels[d]}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="eyebrow">Загрузка…</p>
      ) : !data || data.total_orders === 0 ? (
        <div className="comingSoon">
          <p className="eyebrow">Нет данных</p>
          <h2>Заказов за выбранный период не найдено</h2>
          <p>Проверьте подключение к Ozon Seller API или выберите другой период.</p>
        </div>
      ) : (
        <>
          <div className="heroRow">
            <div className="heroCard">
              <p className="eyebrow">Продажи сегодня</p>
              <strong>{rub(todayRevenue)}</strong>
              <span>{todayQty} шт.</span>
            </div>
            <div className="heroSideCard">
              <p className="eyebrow">Текущий месяц</p>
              <strong>{rub(monthRevenue)}</strong>
              <span>{monthQty} шт.</span>
            </div>
            <div className="heroSideCard">
              <p className="eyebrow">{periodLabels[days]}</p>
              <strong>{rub(data.total_revenue)}</strong>
              <span>{data.total_qty} шт. · {data.total_orders} заказ{orderSuffix(data.total_orders)}</span>
            </div>
          </div>

          <section className="revenueChartSection">
            <div className="revenueChartHeader">
              <p className="eyebrow">Продажи по дням</p>
              <span className="revenueChartScale">Пик: {rub(maxRevenue)}</span>
            </div>
            <div className="revenueChartFrame">
              <div className="revenueChartAxis" aria-hidden="true">
                {chartScale.ticks.map((tick) => (
                  <span key={tick} style={{ bottom: `${(tick / chartScale.max) * 100}%` }}>
                    {formatRevenueScale(tick)}
                  </span>
                ))}
              </div>
              <div className="revenueChart">
              <div className="revenueChartGrid" aria-hidden="true">
                {chartScale.ticks.slice(1).map((tick) => (
                  <span key={tick} style={{ bottom: `${(tick / chartScale.max) * 100}%` }} />
                ))}
              </div>
              {hoverIndex !== null && chartDays[hoverIndex] && (
                <div
                  className="revenueChartTooltip"
                  style={{
                    left: `${((hoverIndex + 0.5) / chartDays.length) * 100}%`,
                    top: `${100 - Math.max(2, (chartDays[hoverIndex].revenue / chartScale.max) * 100)}%`,
                  }}
                >
                  <strong>{formatDateLong(chartDays[hoverIndex].date)}</strong>
                  <div className="tooltipRow">
                    <span>Выручка</span>
                    <b>{rub(chartDays[hoverIndex].revenue)}</b>
                  </div>
                  <div className="tooltipRow">
                    <span>Заказов</span>
                    <b>
                      {chartDays[hoverIndex].orders} заказ
                      {orderSuffix(chartDays[hoverIndex].orders)}
                    </b>
                  </div>
                  <div className="tooltipRow">
                    <span>Товаров продано</span>
                    <b>{chartDays[hoverIndex].qty} шт.</b>
                  </div>
                </div>
              )}
              {chartDays.map((d, i) => {
                const heightPct = Math.max(2, (d.revenue / chartScale.max) * 100);
                const isToday = d.date === todayStr;
                return (
                  <div
                    key={d.date}
                    className="revenueChartCol"
                    onMouseEnter={() => setHoverIndex(i)}
                    onMouseLeave={() => setHoverIndex(null)}
                  >
                    <div className="revenueChartBarTrack">
                      <div
                        className={isToday ? "revenueChartBar revenueChartBar-today" : "revenueChartBar"}
                        style={{ height: `${heightPct}%` }}
                      />
                    </div>
                    <span className="revenueChartLabel">
                      {i % labelEvery === 0 || isToday ? formatDateShort(d.date) : ""}
                    </span>
                  </div>
                );
              })}
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

type Theme = "dark" | "light";
const themeStorageKey = "leto_theme_v2";

function readStoredTheme(): Theme {
  try {
    const stored = localStorage.getItem(themeStorageKey);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // localStorage недоступен (приватный режим) — используем тёмную тему по умолчанию
  }
  return "dark";
}

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function EditableCell({
  value,
  onCommit,
  type = "number",
}: {
  value: string | number | null;
  onCommit: (value: string) => void;
  type?: "number" | "text";
}) {
  const normalizedValue = value ?? "";
  const [draft, setDraft] = useState(String(normalizedValue));

  useEffect(() => {
    setDraft(String(normalizedValue));
  }, [normalizedValue]);

  return (
    <input
      className="unitkaCellInput"
      type={type}
      step={type === "number" ? "any" : undefined}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        if (draft !== String(normalizedValue)) onCommit(draft);
      }}
    />
  );
}

type UnitkaInputField = Exclude<keyof UnitkaRow, "id">;
type UnitkaComputedField = keyof UnitkaItem["computed"];
type UnitkaComputedFormat = "money" | "percent" | "number";
type UnitkaColumn =
  | {
      letter: string;
      label: string;
      kind: "input";
      field: UnitkaInputField;
      inputType: "number" | "text";
      nullable?: boolean;
      className?: string;
    }
  | {
      letter: string;
      label: string;
      kind: "computed";
      field: UnitkaComputedField;
      format?: UnitkaComputedFormat;
      className?: string;
    };

// Все содержательные A..AX из UnitkaRow/UnitkaRowComputed. AY..BD в исходном
// листе пустые и без заголовков, поэтому намеренно не отображаются и не выдумываются.
const unitkaColumns: readonly UnitkaColumn[] = [
  { letter: "A", label: "Номер", kind: "input", field: "row_number", inputType: "number", nullable: true },
  { letter: "B", label: "Артикул прайс", kind: "input", field: "supplier_article", inputType: "text" },
  { letter: "C", label: "Схема реализации", kind: "input", field: "fulfillment_scheme", inputType: "text", nullable: true },
  { letter: "D", label: "Выкладка Ozon", kind: "input", field: "ozon_listing", inputType: "text", nullable: true },
  { letter: "E", label: "Остатки", kind: "input", field: "stock", inputType: "number", nullable: true },
  { letter: "F", label: "Ozon SKU ID", kind: "input", field: "ozon_sku_id", inputType: "text", nullable: true },
  { letter: "G", label: "Название", kind: "input", field: "title", inputType: "text", className: "unitkaTitleCell" },
  { letter: "H", label: "Тип", kind: "input", field: "product_type", inputType: "text", nullable: true },
  { letter: "I", label: "Статус", kind: "input", field: "status", inputType: "text", nullable: true },
  { letter: "J", label: "Видимость Ozon", kind: "input", field: "ozon_visibility", inputType: "text", nullable: true },
  { letter: "K", label: "На складе Ozon", kind: "input", field: "in_stock_ozon", inputType: "number", nullable: true },
  { letter: "L", label: "На моих складах", kind: "input", field: "in_stock_own", inputType: "number", nullable: true },
  { letter: "M", label: "Объём, л (ручной)", kind: "input", field: "volume_liters_manual", inputType: "number", nullable: true },
  { letter: "N", label: "Вес, кг", kind: "input", field: "weight_kg", inputType: "number", nullable: true },
  { letter: "O", label: "Размеры, мм", kind: "input", field: "dimensions_mm", inputType: "text", nullable: true },
  { letter: "P", label: "ТН ВЭД", kind: "input", field: "tn_ved", inputType: "text", nullable: true },
  { letter: "Q", label: "Честный знак", kind: "input", field: "honest_mark_required", inputType: "text", nullable: true },
  { letter: "R", label: "Цена до скидки", kind: "computed", field: "price_before_discount_vat_included", format: "money" },
  { letter: "S", label: "Цена с учётом скидки", kind: "computed", field: "price_with_discount_vat_included", format: "money" },
  { letter: "T", label: "Процент соинвест", kind: "input", field: "coinvest_percent", inputType: "number" },
  { letter: "U", label: "Скидка баллами Ozon", kind: "computed", field: "ozon_points_discount", format: "money" },
  { letter: "V", label: "Торговая наценка", kind: "input", field: "markup_multiplier", inputType: "number" },
  { letter: "W", label: "Цена покупателя", kind: "computed", field: "customer_price", format: "money" },
  { letter: "X", label: "Закупочная цена с НДС", kind: "input", field: "purchase_price_vat_included", inputType: "number" },
  { letter: "Y", label: "Отвоз на сортировку", kind: "computed", field: "sorting_delivery_cost", format: "money" },
  { letter: "Z", label: "FBS затраты", kind: "computed", field: "fbs_costs", format: "money" },
  { letter: "AA", label: "Фулфилмент", kind: "computed", field: "fulfillment_cost", format: "money" },
  { letter: "AB", label: "Зарплата дизайнера", kind: "computed", field: "designer_salary_cost", format: "money" },
  { letter: "AC", label: "Быстрый вывод Ozon", kind: "computed", field: "fast_payout_cost", format: "money" },
  { letter: "AD", label: "Комиссия Ozon", kind: "input", field: "ozon_commission_percent", inputType: "number" },
  { letter: "AE", label: "Вознаграждение Ozon", kind: "computed", field: "ozon_commission_amount", format: "money" },
  { letter: "AF", label: "Реклама и продвижение", kind: "computed", field: "advertising_cost", format: "money" },
  { letter: "AG", label: "Эквайринг", kind: "computed", field: "acquiring_cost", format: "money" },
  { letter: "AH", label: "Сбор за интеграцию", kind: "input", field: "integration_fee", inputType: "number" },
  { letter: "AI", label: "Прочие расходы", kind: "computed", field: "other_costs", format: "money" },
  { letter: "AJ", label: "Налог", kind: "computed", field: "tax_amount", format: "money" },
  { letter: "AK", label: "Прибыль", kind: "computed", field: "net_profit", format: "money" },
  { letter: "AL", label: "Рентабельность", kind: "computed", field: "profitability_percent", format: "percent" },
  { letter: "AM", label: "Разница с Идеи для дома", kind: "computed", field: "idd_price_gap", format: "money" },
  { letter: "AN", label: "Себестоимость", kind: "computed", field: "cost_basis", format: "money" },
  { letter: "AO", label: "Себест. + реклама", kind: "computed", field: "cost_basis_with_advertising", format: "money" },
  { letter: "AP", label: "Себест. + рекл. + ком.", kind: "computed", field: "cost_basis_with_advertising_and_commission", format: "money" },
  { letter: "AQ", label: "Цена Идеи для дома", kind: "input", field: "competitor_price_idd", inputType: "number", nullable: true },
  { letter: "AR", label: "Цена конкурента Ozon", kind: "input", field: "competitor_price_ozon", inputType: "number", nullable: true },
  { letter: "AS", label: "Ссылка Идеи для дома", kind: "input", field: "url_idd", inputType: "text", nullable: true },
  { letter: "AT", label: "Ссылка Центр СМ", kind: "input", field: "url_tdcsm", inputType: "text", nullable: true },
  { letter: "AU", label: "Ссылка конкурента", kind: "input", field: "url_competitor", inputType: "text", nullable: true },
  { letter: "AV", label: "Объём, л (формула)", kind: "computed", field: "volume_liters_computed", format: "number" },
  { letter: "AW", label: "Логистика Ozon (справочно)", kind: "computed", field: "ozon_volume_logistics_reference", format: "money" },
  { letter: "AX", label: "Фулфилмент-контора", kind: "computed", field: "fulfillment_office_cost", format: "money" },
];

const assumptionFields: ReadonlyArray<{
  key: keyof UnitkaAssumptions;
  label: string;
  suffix: "%" | "₽/кг";
}> = [
  { key: "sorting_delivery_rate", label: "Отвоз на сортировку Ozon", suffix: "%" },
  { key: "designer_salary_rate", label: "Зарплата дизайнера", suffix: "%" },
  { key: "fast_payout_rate", label: "Быстрый вывод с Ozon", suffix: "%" },
  { key: "advertising_rate", label: "Реклама и продвижение", suffix: "%" },
  { key: "acquiring_rate", label: "Эквайринг", suffix: "%" },
  { key: "other_costs_rate", label: "Прочие расходы", suffix: "%" },
  { key: "tax_rate", label: "Налог", suffix: "%" },
  { key: "fulfillment_office_rate_per_kg", label: "Фулфилмент-контора", suffix: "₽/кг" },
];

function formatComputedValue(value: number | null, format?: UnitkaComputedFormat) {
  if (value === null) return "—";
  if (format === "money") return rub(value);
  if (format === "percent") return pct(value);
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 }).format(value);
}

type UnitkaSort = { letter: string; direction: "asc" | "desc" } | null;
type UnitkaRowDensity = "compact" | "normal" | "comfortable";
type UnitkaConditionKey = "stockZero" | "stockLow" | "positive" | "negative";
type UnitkaRuleOperator = "gt" | "gte" | "lt" | "lte" | "eq";

type UnitkaColumnRule = {
  operator: UnitkaRuleOperator;
  threshold: number;
  color: string;
};

type UnitkaAppearance = {
  frozenCount: number;
  columnColors: Record<string, string>;
  conditionColors: Record<UnitkaConditionKey, string>;
  columnRules: Record<string, UnitkaColumnRule>;
};

const unitkaDensityHeights: Record<UnitkaRowDensity, number> = {
  compact: 34,
  normal: 44,
  comfortable: 56,
};

const defaultUnitkaAppearance: UnitkaAppearance = {
  frozenCount: 0,
  columnColors: {},
  conditionColors: {
    stockZero: "#ffd9dd",
    stockLow: "#fff1c7",
    positive: "#dff3e4",
    negative: "#ffdfe3",
  },
  columnRules: {},
};

function initialUnitkaAppearance(): UnitkaAppearance {
  try {
    const stored = localStorage.getItem("leto_unitka_appearance_v1");
    if (stored) {
      const parsed = JSON.parse(stored) as Partial<UnitkaAppearance> & { freezeBaseColumns?: boolean };
      return {
        frozenCount: Math.max(0, Math.min(unitkaColumns.length, parsed.frozenCount ?? (parsed.freezeBaseColumns ? 7 : 0))),
        columnColors: parsed.columnColors ?? {},
        conditionColors: { ...defaultUnitkaAppearance.conditionColors, ...parsed.conditionColors },
        columnRules: parsed.columnRules ?? {},
      };
    }
  } catch {
    // Оформление — личная настройка браузера и не должно мешать работе с данными.
  }
  return defaultUnitkaAppearance;
}

function defaultUnitkaColumnWidth(column: UnitkaColumn): number {
  if (column.letter === "A") return 72;
  if (column.letter === "G") return 380;
  if (column.letter === "O") return 190;
  if (["AS", "AT", "AU"].includes(column.letter)) return 230;
  if (["B", "F", "P"].includes(column.letter)) return 138;
  if (column.kind === "computed") return 142;
  return 126;
}

function initialUnitkaColumnWidths(): Record<string, number> {
  try {
    const stored = localStorage.getItem("leto_unitka_column_widths_v1");
    if (stored) {
      const parsed = JSON.parse(stored) as Record<string, number>;
      if (Object.values(parsed).every((width) => Number.isFinite(width) && width >= 72)) return parsed;
    }
  } catch {
    // Локальная настройка не критична — используем безопасные размеры по умолчанию.
  }
  return Object.fromEntries(unitkaColumns.map((column) => [column.letter, defaultUnitkaColumnWidth(column)]));
}

function unitkaRawValue(item: UnitkaItem, column: UnitkaColumn): string | number | null {
  if (column.kind === "input") return item.row[column.field] as string | number | null;
  return item.computed[column.field] as number | null;
}

function matchesUnitkaFilter(value: string | number | null, filter: string): boolean {
  const query = filter.trim().toLocaleLowerCase("ru-RU");
  if (!query) return true;
  const raw = value === null ? "" : String(value);
  const numeric = Number(raw);
  const numericFilter = query.match(/^(>=|<=|>|<|=)?\s*(-?\d+(?:[.,]\d+)?)\s*(?:[-–]\s*(-?\d+(?:[.,]\d+)?))?$/);
  if (Number.isFinite(numeric) && numericFilter) {
    const [, operator = "=", firstRaw, secondRaw] = numericFilter;
    const first = Number(firstRaw.replace(",", "."));
    const second = secondRaw ? Number(secondRaw.replace(",", ".")) : null;
    if (second !== null) return numeric >= Math.min(first, second) && numeric <= Math.max(first, second);
    if (operator === ">") return numeric > first;
    if (operator === ">=") return numeric >= first;
    if (operator === "<") return numeric < first;
    if (operator === "<=") return numeric <= first;
    return numeric === first;
  }
  return raw.toLocaleLowerCase("ru-RU").includes(query);
}

function UnitkaAssumptionsPanel({
  assumptions,
  saving,
  onSave,
}: {
  assumptions: UnitkaAssumptions;
  saving: boolean;
  onSave: (value: UnitkaAssumptions) => Promise<void>;
}) {
  const [draft, setDraft] = useState<UnitkaAssumptions>(assumptions);

  useEffect(() => setDraft(assumptions), [assumptions]);

  return (
    <form
      className="unitkaAssumptions"
      onSubmit={(event) => {
        event.preventDefault();
        void onSave(draft);
      }}
    >
      <div>
        <h3>Допущения расчёта</h3>
        <p>Изменение ставки пересчитает все формульные столбцы, но не изменит Excel-файл.</p>
      </div>
      <div className="unitkaAssumptionsGrid">
        {assumptionFields.map(({ key, label, suffix }) => {
          const isRate = suffix === "%";
          return (
            <label key={key}>
              <span>{label}</span>
              <div>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={isRate ? draft[key] * 100 : draft[key]}
                  onChange={(event) => {
                    const raw = Number(event.target.value.replace(",", "."));
                    setDraft((previous) => ({ ...previous, [key]: isRate ? raw / 100 : raw }));
                  }}
                />
                <em>{suffix}</em>
              </div>
            </label>
          );
        })}
      </div>
      <div className="actions">
        <button className="uploadButton" type="submit" disabled={saving}>
          {saving ? "Сохраняю…" : "Сохранить допущения"}
        </button>
      </div>
    </form>
  );
}

function UnitkaPage() {
  const [items, setItems] = useState<UnitkaItem[]>([]);
  const [assumptions, setAssumptions] = useState<UnitkaAssumptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [savingAssumptions, setSavingAssumptions] = useState(false);
  const [showAssumptions, setShowAssumptions] = useState(false);
  const [columnFilters, setColumnFilters] = useState<Record<string, string>>({});
  const [sort, setSort] = useState<UnitkaSort>(null);
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>(initialUnitkaColumnWidths);
  const [tableScale, setTableScale] = useState(100);
  const [rowDensity, setRowDensity] = useState<UnitkaRowDensity>("normal");
  const [appearance, setAppearance] = useState<UnitkaAppearance>(initialUnitkaAppearance);
  const [showAppearance, setShowAppearance] = useState(false);
  const [colorColumn, setColorColumn] = useState("E");

  useEffect(() => {
    try {
      localStorage.setItem("leto_unitka_column_widths_v1", JSON.stringify(columnWidths));
    } catch {
      // Таблица остаётся рабочей, даже если браузер не разрешил сохранить настройки.
    }
  }, [columnWidths]);

  useEffect(() => {
    try {
      localStorage.setItem("leto_unitka_appearance_v1", JSON.stringify(appearance));
    } catch {
      // Таблица продолжает работать, даже если браузер запретил localStorage.
    }
  }, [appearance]);

  const visibleItems = useMemo(() => {
    const filtered = items.filter((item) =>
      unitkaColumns.every((column) => matchesUnitkaFilter(unitkaRawValue(item, column), columnFilters[column.letter] ?? "")),
    );
    if (!sort) return filtered;
    const column = unitkaColumns.find((candidate) => candidate.letter === sort.letter);
    if (!column) return filtered;
    return [...filtered].sort((left, right) => {
      const first = unitkaRawValue(left, column);
      const second = unitkaRawValue(right, column);
      const numericFirst = typeof first === "number" ? first : Number(first);
      const numericSecond = typeof second === "number" ? second : Number(second);
      const comparison =
        Number.isFinite(numericFirst) && Number.isFinite(numericSecond)
          ? numericFirst - numericSecond
          : String(first ?? "").localeCompare(String(second ?? ""), "ru", { numeric: true, sensitivity: "base" });
      return sort.direction === "asc" ? comparison : -comparison;
    });
  }, [items, columnFilters, sort]);

  const totalTableWidth = useMemo(
    () => unitkaColumns.reduce((sum, column) => sum + (columnWidths[column.letter] ?? defaultUnitkaColumnWidth(column)), 0) + 52,
    [columnWidths],
  );

  const frozenOffsets = useMemo(() => {
    let offset = 0;
    return unitkaColumns.map((column) => {
      const current = offset;
      offset += columnWidths[column.letter] ?? defaultUnitkaColumnWidth(column);
      return current;
    });
  }, [columnWidths]);

  function toggleSort(letter: string) {
    setSort((previous) =>
      previous?.letter === letter
        ? { letter, direction: previous.direction === "asc" ? "desc" : "asc" }
        : { letter, direction: "asc" },
    );
  }

  function beginColumnResize(letter: string, startX: number) {
    const initialWidth = columnWidths[letter] ?? defaultUnitkaColumnWidth(unitkaColumns.find((column) => column.letter === letter)!);
    const onMove = (event: PointerEvent) => {
      setColumnWidths((previous) => ({ ...previous, [letter]: Math.max(72, initialWidth + event.clientX - startX) }));
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
  }

  function resetTableLayout() {
    setColumnWidths(Object.fromEntries(unitkaColumns.map((column) => [column.letter, defaultUnitkaColumnWidth(column)])));
    setColumnFilters({});
    setSort(null);
    setTableScale(100);
    setRowDensity("normal");
    setAppearance(defaultUnitkaAppearance);
  }

  function updateConditionColor(key: UnitkaConditionKey, color: string) {
    setAppearance((previous) => ({
      ...previous,
      conditionColors: { ...previous.conditionColors, [key]: color },
    }));
  }

  function updateColumnColor(letter: string, color: string) {
    setAppearance((previous) => ({
      ...previous,
      columnColors: { ...previous.columnColors, [letter]: color },
    }));
  }

  function clearColumnColor(letter: string) {
    setAppearance((previous) => {
      const columnColors = { ...previous.columnColors };
      delete columnColors[letter];
      return { ...previous, columnColors };
    });
  }

  function updateColumnRule(letter: string, change: Partial<UnitkaColumnRule>) {
    setAppearance((previous) => ({
      ...previous,
      columnRules: {
        ...previous.columnRules,
        [letter]: { ...(previous.columnRules[letter] ?? { operator: "lt", threshold: 0, color: "#fff1c7" }), ...change },
      },
    }));
  }

  function clearColumnRule(letter: string) {
    setAppearance((previous) => {
      const columnRules = { ...previous.columnRules };
      delete columnRules[letter];
      return { ...previous, columnRules };
    });
  }

  function matchesColumnRule(value: string | number | null, rule: UnitkaColumnRule | undefined): boolean {
    if (!rule) return false;
    const numeric = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(numeric)) return false;
    if (rule.operator === "gt") return numeric > rule.threshold;
    if (rule.operator === "gte") return numeric >= rule.threshold;
    if (rule.operator === "lt") return numeric < rule.threshold;
    if (rule.operator === "lte") return numeric <= rule.threshold;
    return numeric === rule.threshold;
  }

  function conditionClass(column: UnitkaColumn, item: UnitkaItem): string {
    const value = unitkaRawValue(item, column);
    if (column.letter === "E" && typeof value === "number") {
      if (value <= 0) return "unitkaConditionStockZero";
      if (value < 10) return "unitkaConditionStockLow";
    }
    if ((column.field === "net_profit" || column.field === "profitability_percent") && typeof value === "number") {
      return value >= 0 ? "unitkaPositiveValue" : "unitkaNegativeValue";
    }
    return "";
  }

  function load() {
    setLoading(true);
    setError(null);
    Promise.all([fetchUnitkaRows(), fetchUnitkaAssumptions()])
      .then(([loadedItems, loadedAssumptions]) => {
        setItems(loadedItems);
        setAssumptions(loadedAssumptions);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function commitField(column: Extract<UnitkaColumn, { kind: "input" }>, item: UnitkaItem, raw: string) {
    const value =
      raw.trim() === ""
        ? column.nullable
          ? null
          : column.inputType === "number"
            ? 0
            : ""
        : column.inputType === "number"
          ? Number(raw.replace(",", "."))
          : raw;
    if (typeof value === "number" && Number.isNaN(value)) {
      setError(`«${column.label}»: введите число.`);
      return;
    }
    const updatedRow = { ...item.row, [column.field]: value } as UnitkaRow;
    setSavingId(item.row.id);
    setError(null);
    try {
      const saved = await updateUnitkaRow(item.row.id, updatedRow);
      setItems((prev) => prev.map((it) => (it.row.id === saved.row.id ? saved : it)));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingId(null);
    }
  }

  async function handleAddRow() {
    try {
      const created = await createUnitkaRow({
        supplier_article: `новый-${Date.now()}`,
        title: "Новый товар",
        purchase_price_vat_included: 0,
        markup_multiplier: 1,
      });
      setItems((prev) => [...prev, created]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleDeleteRow(id: string) {
    if (!window.confirm("Удалить эту строку из юнитки?")) return;
    try {
      await deleteUnitkaRow(id);
      setItems((prev) => prev.filter((it) => it.row.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleImport(file: File | undefined) {
    if (!file) return;
    setError(null);
    setNotice(null);
    try {
      const result = await importUnitkaFile(file);
      setNotice(
        `Импортировано новых: ${result.imported}, обновлено: ${result.updated}` +
          (result.skipped ? `, пропущено: ${result.skipped}` : "")
      );
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleSaveAssumptions(value: UnitkaAssumptions) {
    setSavingAssumptions(true);
    setError(null);
    try {
      const saved = await updateUnitkaAssumptions(value);
      setAssumptions(saved);
      setItems(await fetchUnitkaRows());
      setNotice("Допущения сохранены, формульные столбцы пересчитаны.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingAssumptions(false);
    }
  }

  return (
    <div>
      <header className="pageHeader">
        <div>
          <h2>Юнитка</h2>
        </div>
        <div className="actions">
          <button className="secondaryButton" type="button" onClick={() => setShowAssumptions((value) => !value)}>
            {showAssumptions ? "Скрыть допущения" : "Допущения"}
          </button>
          <label className="iconButton" title="Импортировать из Excel">
            <FileSpreadsheet size={18} />
            <input
              type="file"
              accept=".xlsx,.xlsm"
              onChange={(e) => void handleImport(e.target.files?.[0])}
            />
          </label>
          <button className="uploadButton" type="button" onClick={() => void handleAddRow()}>
            + Добавить строку
          </button>
        </div>
      </header>

      {error && <div className="alert">{error}</div>}
      {notice && <div className="alert alert-notice">{notice}</div>}

      {showAssumptions && assumptions && (
        <UnitkaAssumptionsPanel
          assumptions={assumptions}
          saving={savingAssumptions}
          onSave={handleSaveAssumptions}
        />
      )}

      {loading ? (
        <p className="eyebrow">Загрузка…</p>
      ) : items.length === 0 ? (
        <div className="comingSoon">
          <p className="eyebrow">Пока пусто</p>
          <h2>Загрузите Юнитку из Excel</h2>
          <p>Кнопка со значком таблицы вверху — выберите ваш файл «Юнитка Лето СМ.xlsx».</p>
        </div>
      ) : (
        <>
          <div className="unitkaSpreadsheetControls">
            <strong>{visibleItems.length} из {items.length} строк</strong>
            <label>
              <span>Масштаб: {tableScale}%</span>
              <input
                type="range"
                min="70"
                max="130"
                step="5"
                value={tableScale}
                onChange={(event) => setTableScale(Number(event.target.value))}
              />
            </label>
            <label>
              <span>Высота строк</span>
              <select value={rowDensity} onChange={(event) => setRowDensity(event.target.value as UnitkaRowDensity)}>
                <option value="compact">Компактная</option>
                <option value="normal">Обычная</option>
                <option value="comfortable">Свободная</option>
              </select>
            </label>
            <div className="unitkaFreezeControls">
              <span>
                Закреплено: {appearance.frozenCount ? `A–${unitkaColumns[appearance.frozenCount - 1].letter}` : "нет"}
              </span>
              <div>
                <button
                  className="secondaryButton"
                  type="button"
                  onClick={() => setAppearance((previous) => ({ ...previous, frozenCount: unitkaColumns.findIndex((column) => column.letter === colorColumn) + 1 }))}
                >
                  Закрепить до {colorColumn}
                </button>
                <button
                  className="secondaryButton"
                  type="button"
                  disabled={!appearance.frozenCount}
                  onClick={() => setAppearance((previous) => ({ ...previous, frozenCount: 0 }))}
                >
                  Снять
                </button>
              </div>
            </div>
            <button className="secondaryButton" type="button" onClick={() => setShowAppearance((value) => !value)}>
              {showAppearance ? "Скрыть оформление" : "Оформление"}
            </button>
            <button className="secondaryButton" type="button" onClick={resetTableLayout}>
              Сбросить вид
            </button>
          </div>
          {showAppearance && (
            <section className="unitkaAppearancePanel">
              <div>
                <h3>Оформление таблицы</h3>
                <p>Нажмите на букву столбца сверху: он станет выбранным для ручного цвета и правила. Настройки хранятся только в этом браузере и не меняют данные Юнитки.</p>
              </div>
              <div className="unitkaAppearanceGrid">
                <label>
                  <span>Нулевой остаток</span>
                  <input
                    type="color"
                    value={appearance.conditionColors.stockZero}
                    onChange={(event) => updateConditionColor("stockZero", event.target.value)}
                  />
                </label>
                <label>
                  <span>Остаток меньше 10</span>
                  <input
                    type="color"
                    value={appearance.conditionColors.stockLow}
                    onChange={(event) => updateConditionColor("stockLow", event.target.value)}
                  />
                </label>
                <label>
                  <span>Прибыль в плюс</span>
                  <input
                    type="color"
                    value={appearance.conditionColors.positive}
                    onChange={(event) => updateConditionColor("positive", event.target.value)}
                  />
                </label>
                <label>
                  <span>Убыток или минус</span>
                  <input
                    type="color"
                    value={appearance.conditionColors.negative}
                    onChange={(event) => updateConditionColor("negative", event.target.value)}
                  />
                </label>
                <label className="unitkaColumnColorPicker">
                  <span>Цвет столбца</span>
                  <select value={colorColumn} onChange={(event) => setColorColumn(event.target.value)}>
                    {unitkaColumns.map((column) => (
                      <option key={column.letter} value={column.letter}>
                        {column.letter} · {column.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="unitkaColumnColorPicker">
                  <span>Выбранный цвет</span>
                  <input
                    type="color"
                    value={appearance.columnColors[colorColumn] ?? "#d9eff3"}
                    onChange={(event) => updateColumnColor(colorColumn, event.target.value)}
                  />
                </label>
                <button className="secondaryButton" type="button" onClick={() => clearColumnColor(colorColumn)}>
                  Сбросить цвет столбца
                </button>
                <div className="unitkaRuleEditor">
                  <strong>Условное правило · {colorColumn} · {unitkaColumns.find((column) => column.letter === colorColumn)?.label}</strong>
                  <select
                    aria-label="Условие форматирования"
                    value={appearance.columnRules[colorColumn]?.operator ?? "lt"}
                    onChange={(event) => updateColumnRule(colorColumn, { operator: event.target.value as UnitkaRuleOperator })}
                  >
                    <option value="lt">меньше</option>
                    <option value="lte">меньше или равно</option>
                    <option value="gt">больше</option>
                    <option value="gte">больше или равно</option>
                    <option value="eq">равно</option>
                  </select>
                  <input
                    aria-label="Значение для условного форматирования"
                    type="number"
                    step="any"
                    value={appearance.columnRules[colorColumn]?.threshold ?? 0}
                    onChange={(event) => updateColumnRule(colorColumn, { threshold: Number(event.target.value) || 0 })}
                  />
                  <input
                    aria-label="Цвет условного форматирования"
                    type="color"
                    value={appearance.columnRules[colorColumn]?.color ?? "#fff1c7"}
                    onChange={(event) => updateColumnRule(colorColumn, { color: event.target.value })}
                  />
                  <button className="secondaryButton" type="button" onClick={() => clearColumnRule(colorColumn)}>
                    Убрать правило
                  </button>
                </div>
              </div>
            </section>
          )}
          <div className="unitkaTableWrap unitkaSpreadsheetWrap">
            <table
              className="unitkaTable unitkaSpreadsheet"
              style={
                {
                  width: totalTableWidth,
                  fontSize: `${(12 * tableScale) / 100}px`,
                  "--unitka-row-height": `${Math.round(
                    (unitkaDensityHeights[rowDensity] * tableScale) / 100,
                  )}px`,
                  "--unitka-stock-zero": appearance.conditionColors.stockZero,
                  "--unitka-stock-low": appearance.conditionColors.stockLow,
                  "--unitka-positive": appearance.conditionColors.positive,
                  "--unitka-negative": appearance.conditionColors.negative,
                } as CSSProperties
              }
            >
              <colgroup>
                {unitkaColumns.map((column) => (
                  <col key={column.letter} style={{ width: columnWidths[column.letter] ?? defaultUnitkaColumnWidth(column) }} />
                ))}
                <col style={{ width: 52 }} />
              </colgroup>
              <thead>
                <tr className="unitkaColumnLettersRow">
                  {unitkaColumns.map((column, index) => {
                    const isFrozen = index < appearance.frozenCount;
                    const customColor = appearance.columnColors[column.letter];
                    const style = {
                      ...(customColor ? { "--unitka-custom-column-color": customColor } : {}),
                      ...(isFrozen ? { left: frozenOffsets[index] } : {}),
                    } as CSSProperties;
                    return (
                      <th
                        key={column.letter}
                        className={`${customColor ? "unitkaColumnTint " : ""}${isFrozen ? "unitkaFrozenCell" : ""}`}
                        style={style}
                      >
                        <button
                          className={`unitkaColumnLetterButton ${colorColumn === column.letter ? "unitkaColumnLetterButton-selected" : ""}`}
                          type="button"
                          title={`Выбрать столбец «${column.label}» для оформления`}
                          onClick={() => {
                            setColorColumn(column.letter);
                            setShowAppearance(true);
                          }}
                        >
                          {column.letter}
                        </button>
                        <span
                          className="unitkaResizeHandle"
                          role="separator"
                          aria-label={`Изменить ширину столбца «${column.label}»`}
                          onPointerDown={(event) => {
                            event.preventDefault();
                            beginColumnResize(column.letter, event.clientX);
                          }}
                        />
                      </th>
                    );
                  })}
                  <th className="unitkaDeleteHeader" rowSpan={2} />
                </tr>
                <tr className="unitkaColumnHeadersRow">
                  {unitkaColumns.map((column, index) => {
                    const sortIndicator = sort?.letter === column.letter ? (sort.direction === "asc" ? "↑" : "↓") : "↕";
                    const isFrozen = index < appearance.frozenCount;
                    const customColor = appearance.columnColors[column.letter];
                    const style = {
                      ...(customColor ? { "--unitka-custom-column-color": customColor } : {}),
                      ...(isFrozen ? { left: frozenOffsets[index] } : {}),
                    } as CSSProperties;
                    return (
                      <th
                        key={column.letter}
                        className={`unitkaHeader unitkaHeader-${column.kind} ${customColor ? "unitkaColumnTint" : ""} ${
                          isFrozen ? "unitkaFrozenCell" : ""
                        }`}
                        style={style}
                      >
                        <button
                          className="unitkaSortButton"
                          type="button"
                          title={`Сортировать по «${column.label}»`}
                          onClick={() => toggleSort(column.letter)}
                        >
                          <span className="unitkaColumnLabel">{column.label}</span>
                          <b aria-hidden="true">{sortIndicator}</b>
                        </button>
                        <input
                          className="unitkaFilterInput"
                          value={columnFilters[column.letter] ?? ""}
                          onChange={(event) => setColumnFilters((previous) => ({ ...previous, [column.letter]: event.target.value }))}
                          placeholder="Фильтр"
                          aria-label={`Фильтр: ${column.label}`}
                        />
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {visibleItems.map((item) => (
                  <tr key={item.row.id} className={savingId === item.row.id ? "unitkaRowSaving" : ""}>
                    {unitkaColumns.map((column, index) => {
                      const isFrozen = index < appearance.frozenCount;
                      const customColor = appearance.columnColors[column.letter];
                      const toneClass = conditionClass(column, item);
                      const matchesRule = matchesColumnRule(unitkaRawValue(item, column), appearance.columnRules[column.letter]);
                      const style = {
                        ...(customColor ? { "--unitka-custom-column-color": customColor } : {}),
                        ...(matchesRule ? { "--unitka-rule-color": appearance.columnRules[column.letter]?.color } : {}),
                        ...(isFrozen ? { left: frozenOffsets[index] } : {}),
                      } as CSSProperties;
                      if (column.kind === "input") {
                        return (
                          <td
                            key={column.letter}
                            className={`${column.className ?? ""} ${toneClass} ${matchesRule ? "unitkaConditionCustom" : ""} ${customColor ? "unitkaColumnTint" : ""} ${
                              isFrozen ? "unitkaFrozenCell" : ""
                            }`}
                            style={style}
                          >
                            <EditableCell
                              type={column.inputType}
                              value={item.row[column.field] as string | number | null}
                              onCommit={(value) => void commitField(column, item, value)}
                            />
                          </td>
                        );
                      }
                      const value = item.computed[column.field] as number | null;
                      const signClass =
                        (column.field === "net_profit" || column.field === "profitability_percent") && value !== null
                          ? value >= 0
                            ? " unitkaPositiveValue"
                            : " unitkaNegativeValue"
                          : "";
                      return (
                        <td
                          key={column.letter}
                          className={`unitkaComputedCell${signClass} ${toneClass} ${matchesRule ? "unitkaConditionCustom" : ""} ${column.className ?? ""} ${
                            customColor ? "unitkaColumnTint" : ""
                          } ${isFrozen ? "unitkaFrozenCell" : ""}`}
                          style={style}
                        >
                          {formatComputedValue(value, column.format)}
                        </td>
                      );
                    })}
                    <td className="unitkaDeleteCell">
                      <button
                        className="iconButton"
                        type="button"
                        title="Удалить строку"
                        onClick={() => void handleDeleteRow(item.row.id)}
                      >
                        ×
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {visibleItems.length === 0 && <p className="unitkaNoRows">По фильтрам ничего не найдено.</p>}
          </div>
        </>
      )}
    </div>
  );
}

function PurchasePricesPage() {
  const [snapshot, setSnapshot] = useState<PurchasePriceSnapshot | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function handleRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      setSnapshot(await refreshPurchasePrices());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }

  async function handleApply() {
    if (!snapshot || snapshot.diff_count === 0) return;
    if (
      !window.confirm(
        `Обновить закупочные цены в живой Юнитке для ${snapshot.diff_count} SKU? ` +
          "Excel-файл и цены на Ozon не изменятся.",
      )
    ) {
      return;
    }
    setApplying(true);
    setError(null);
    try {
      const result = await applyPurchasePrices();
      setNotice(result.message);
      if (result.ok) await handleRefresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setApplying(false);
    }
  }

  return (
    <div>
      <header className="pageHeader">
        <div>
          <h2>Закупочные цены</h2>
        </div>
        <button className="uploadButton" type="button" onClick={() => void handleRefresh()} disabled={refreshing}>
          <RefreshCw size={16} />
          {refreshing ? "Сверяю…" : "Сверить сейчас"}
        </button>
      </header>

      {error && <div className="alert">{error}</div>}
      {notice && <div className="alert alert-notice">{notice}</div>}

      {!snapshot ? (
        <div className="comingSoon">
          <h2>Проверьте закупочные цены</h2>
          <p>Сервис возьмёт опубликованные offer_id из Ozon и сопоставит их с ценой tdcsm.ru и Юниткой.</p>
        </div>
      ) : (
        <>
          <div className="kpis">
            <div className="coverageItem"><span>Опубликовано на Ozon</span><strong>{snapshot.total_published}</strong></div>
            <div className="coverageItem"><span>Есть в Юнитке</span><strong>{snapshot.matched_to_unitka}</strong></div>
            <div className="coverageItem"><span>Не найдено у поставщика</span><strong>{snapshot.supplier_not_found}</strong></div>
            <div className="coverageItem"><span>Расхождения цен</span><strong>{snapshot.diff_count}</strong></div>
          </div>
          <div className="importHeader purchasePricesMeta">
            <span>Проверено: {new Date(snapshot.checked_at).toLocaleString("ru-RU")}</span>
            <button
              className="uploadButton"
              type="button"
              onClick={() => void handleApply()}
              disabled={applying || snapshot.diff_count === 0}
            >
              {applying ? "Применяю…" : `Применить в Юнитку (${snapshot.diff_count})`}
            </button>
          </div>
          <div className="purchasePricesTableWrap">
            <table className="purchasePricesTable">
              <thead>
                <tr>
                  <th>offer_id</th><th>Товар</th><th>Цена в Юнитке</th><th>Цена tdcsm.ru</th><th>Дельта</th><th>Статус</th>
                </tr>
              </thead>
              <tbody>
                {snapshot.rows.map((row) => {
                  const status = !row.in_unitka
                    ? "Нет в Юнитке"
                    : !row.supplier_found
                      ? "Не найден у поставщика"
                      : row.delta === 0
                        ? "Актуально"
                        : "Нужно обновить";
                  return (
                    <tr key={row.offer_id}>
                      <td>{row.offer_id}</td>
                      <td>{row.unitka_title ?? row.supplier_name ?? "—"}</td>
                      <td>{row.current_purchase_price === null ? "—" : rub(row.current_purchase_price)}</td>
                      <td>{row.supplier_purchase_price === null ? "—" : rub(row.supplier_purchase_price)}</td>
                      <td className={row.delta === null ? "" : row.delta > 0 ? "unitkaNegativeValue" : "unitkaPositiveValue"}>
                        {row.delta === null ? "—" : rub(row.delta)}
                      </td>
                      <td><span className={`purchasePriceStatus ${row.delta && row.delta !== 0 ? "purchasePriceStatus-diff" : ""}`}>{status}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function App() {
  const [section, setSection] = useState<Section>("home");
  const [theme, setTheme] = useState<Theme>(readStoredTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(themeStorageKey, theme);
    } catch {
      // см. readStoredTheme
    }
  }, [theme]);

  return (
    <div className="appShell">
      <aside className="sidebar">
        <div className="sidebarBrand">
          <img className="brandMark" src="/logo.svg" alt="Лето СМ" />
        </div>
        <nav className="sidebarNav" aria-label="Разделы платформы">
          {sectionNavItems.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              className={section === key ? "active" : ""}
              onClick={() => setSection(key)}
            >
              <Icon size={18} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <button
          type="button"
          className="themeToggle"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          title={theme === "dark" ? "Включить светлую тему" : "Включить тёмную тему"}
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          <span>{theme === "dark" ? "Светлая тема" : "Тёмная тема"}</span>
        </button>
      </aside>
      <div className="appContent">
        {section === "home" && <HomeDashboardPage />}
        {section === "unitka" && <UnitkaPage />}
        {section === "purchase-prices" && <PurchasePricesPage />}
        {section === "orders" && (
          <ComingSoonPanel
            title="Заказы"
            description="Список заказов с Ozon и чистая прибыль по каждому заказу — на основе того же расчёта, что и в Юнитке."
          />
        )}
        {section === "stock" && <StockMonitorPage />}
        {section === "catalog" && <SupplierCatalogPage />}
      </div>
    </div>
  );
}

function SupplierCatalogPage() {
  const [rows, setRows] = useState<ProductAnalysis[]>([]);
  const [shortlistItems, setShortlistItems] = useState<ShortlistItem[]>([]);
  const [activeTab, setActiveTab] = useState<ActiveTab>("catalog");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<(typeof statusOptions)[number]>("Все");
  const [category, setCategory] = useState("Все");
  const [supplier, setSupplier] = useState("Все");
  const [importFilter, setImportFilter] = useState("latest");
  const [readinessFilter, setReadinessFilter] = useState<ReadinessFilter>("Все");
  const [supplierName, setSupplierName] = useState("");
  const [group, setGroup] = useState("Все");
  const [profitFilter, setProfitFilter] = useState<ProfitFilter>("Все");
  const [minMargin, setMinMargin] = useState(-100);
  const [purchaseMin, setPurchaseMin] = useState("");
  const [purchaseMax, setPurchaseMax] = useState("");
  const [stockFilter, setStockFilter] = useState<StockFilter>("В наличии");
  const [stockMin, setStockMin] = useState("");
  const [stockMax, setStockMax] = useState("");
  const [ordersMin, setOrdersMin] = useState("");
  const [ordersMax, setOrdersMax] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("profit");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [tableFullscreen, setTableFullscreen] = useState(false);
  const [tableFontSize, setTableFontSize] = useState(13);
  const [tablePage, setTablePage] = useState(1);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stockRefreshInfo, setStockRefreshInfo] = useState<string | null>(null);
  const [sellerStatus, setSellerStatus] = useState<OzonStatusResponse | null>(null);
  const [performanceStatus, setPerformanceStatus] = useState<OzonStatusResponse | null>(null);
  const [sellerAnalyticsStatus, setSellerAnalyticsStatus] =
    useState<OzonSellerAnalyticsStatusResponse | null>(null);
  const [categoryCheck, setCategoryCheck] = useState<OzonCategoryTreeCheckResponse | null>(null);
  const [productCheck, setProductCheck] = useState<OzonProductListResponse | null>(null);
  const [tokenCheck, setTokenCheck] = useState<OzonPerformanceTokenCheckResponse | null>(null);
  const [imports, setImports] = useState<PriceImportVersion[]>([]);
  const [latestImport, setLatestImport] = useState<PriceImportVersion | null>(null);
  const [competitorImportInfo, setCompetitorImportInfo] = useState<string | null>(null);
  const [competitorPlans, setCompetitorPlans] = useState<OzonSellerAnalyticsPlanResponse[]>([]);
  const [competitorPlanInfo, setCompetitorPlanInfo] = useState<string | null>(null);
  const [sellerAnalyticsAccess, setSellerAnalyticsAccess] =
    useState<OzonSellerAnalyticsAccessCheckResponse | null>(null);
  const [planningCompetitors, setPlanningCompetitors] = useState(false);
  const [importingCompetitors, setImportingCompetitors] = useState(false);
  const [checkingSellerAnalytics, setCheckingSellerAnalytics] = useState(false);
  const [competitorDrafts, setCompetitorDrafts] = useState<Record<string, CompetitorDraft>>({});
  const [savingCompetitorId, setSavingCompetitorId] = useState<string | null>(null);
  const loadRequestRef = useRef(0);

  async function load() {
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;
    setBusy(true);
    setError(null);
    try {
      const [dashboard, importVersions, shortlist] = await Promise.all([
        fetchDashboard(),
        fetchImports(),
        fetchShortlist(),
      ]);
      if (requestId !== loadRequestRef.current) return;
      setRows(dashboard.rows);
      setShortlistItems(shortlist.items);
      setImports(importVersions);
      setLatestImport((current) => current ?? importVersions[0] ?? null);
      const [seller, performance, sellerAnalytics] = await Promise.all([
        fetchOzonStatus(),
        fetchOzonPerformanceStatus(),
        fetchOzonSellerAnalyticsStatus(),
      ]);
      if (requestId !== loadRequestRef.current) return;
      setSellerStatus(seller);
      setPerformanceStatus(performance);
      setSellerAnalyticsStatus(sellerAnalytics);
    } catch (loadError) {
      if (requestId === loadRequestRef.current) {
        setError(loadError instanceof Error ? loadError.message : "Ошибка загрузки");
      }
    } finally {
      if (requestId === loadRequestRef.current) setBusy(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const filtered = useMemo(() => {
    const minPurchase = parseOptionalNumber(purchaseMin);
    const maxPurchase = parseOptionalNumber(purchaseMax);
    const minStock = parseOptionalNumber(stockMin);
    const maxStock = parseOptionalNumber(stockMax);
    const minOrders = parseOptionalNumber(ordersMin);
    const maxOrders = parseOptionalNumber(ordersMax);

    return rows
      .filter((row) => {
        const competitorOrders = maxCompetitorOrders(row);
        const haystack = `${row.product.title} ${row.product.supplier_article} ${row.product.supplier_name} ${row.product.category ?? ""}`.toLowerCase();
        const matchesImport =
          importFilter === "all" ||
          (importFilter === "latest" && latestImport !== null && productImportKey(row.product) === importVersionKey(latestImport)) ||
          productImportKey(row.product) === importFilter;
        const matchesQuery = haystack.includes(query.toLowerCase());
        const matchesStatus = status === "Все" || row.economics.recommendation === status;
        const matchesCategory = category === "Все" || row.product.category === category;
        const matchesSupplier = supplier === "Все" || row.product.supplier_name === supplier;
        const matchesReadiness =
          readinessFilter === "Все" || row.readiness.status === readinessFilter;
        const matchesGroup = group === "Все" || productGroup(row) === group;
        const matchesPurchaseMin =
          minPurchase === null || row.economics.purchase_price_vat_included >= minPurchase;
        const matchesPurchaseMax =
          maxPurchase === null || row.economics.purchase_price_vat_included <= maxPurchase;
        const productStock = row.product.stock;
        const matchesStockFilter =
          stockFilter === "Все" ||
          (stockFilter === "В наличии" && productStock !== null && productStock > 0) ||
          (stockFilter === "Нет в наличии" && productStock !== null && productStock <= 0) ||
          (stockFilter === "Не указан" && productStock === null);
        const matchesStockMin = minStock === null || (productStock !== null && productStock >= minStock);
        const matchesStockMax = maxStock === null || (productStock !== null && productStock <= maxStock);
        const matchesOrdersMin =
          minOrders === null || (competitorOrders !== null && competitorOrders >= minOrders);
        const matchesOrdersMax =
          maxOrders === null || (competitorOrders !== null && competitorOrders <= maxOrders);
        const matchesProfit =
          profitFilter === "Все" ||
          (profitFilter === "В плюс" && row.economics.net_profit > 0) ||
          (profitFilter === "В минус" && row.economics.net_profit <= 0);
        return (
          matchesImport &&
          matchesQuery &&
          matchesStatus &&
          matchesCategory &&
          matchesSupplier &&
          matchesReadiness &&
          matchesGroup &&
          matchesPurchaseMin &&
          matchesPurchaseMax &&
          matchesStockFilter &&
          matchesStockMin &&
          matchesStockMax &&
          matchesOrdersMin &&
          matchesOrdersMax &&
          matchesProfit &&
          row.economics.margin_percent >= minMargin
        );
      })
      .sort((left, right) => {
        const result = compareRows(left, right, sortKey);
        return sortDirection === "asc" ? result : -result;
      });
  }, [
    category,
    importFilter,
    latestImport,
    supplier,
    readinessFilter,
    group,
    minMargin,
    ordersMax,
    ordersMin,
    profitFilter,
    purchaseMax,
    purchaseMin,
    query,
    rows,
    sortDirection,
    sortKey,
    stockFilter,
    stockMax,
    stockMin,
    status,
  ]);

  useEffect(() => {
    setTablePage(1);
    setExpanded(null);
  }, [
    category,
    importFilter,
    supplier,
    readinessFilter,
    group,
    minMargin,
    ordersMax,
    ordersMin,
    profitFilter,
    purchaseMax,
    purchaseMin,
    query,
    sortDirection,
    sortKey,
    stockFilter,
    stockMax,
    stockMin,
    status,
  ]);

  const visibleKpi = useMemo(() => kpiFromRows(filtered), [filtered]);

  const totalPages = Math.max(Math.ceil(filtered.length / tablePageSize), 1);
  const safeTablePage = Math.min(tablePage, totalPages);
  const visibleRows = filtered.slice(
    (safeTablePage - 1) * tablePageSize,
    safeTablePage * tablePageSize,
  );

  const categories = useMemo(() => {
    return Array.from(new Set(rows.map((row) => row.product.category).filter(Boolean))).sort() as string[];
  }, [rows]);
  const groups = useMemo(() => {
    return Array.from(new Set(rows.map((row) => productGroup(row)))).sort();
  }, [rows]);
  const suppliers = useMemo(() => {
    return Array.from(new Set(rows.map((row) => row.product.supplier_name))).sort();
  }, [rows]);
  const shortlistedArticles = useMemo(() => {
    return new Set(shortlistItems.map((item) => catalogProductKey(item.entry)));
  }, [shortlistItems]);

  async function handleUpload(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const imported = await uploadPrice(file, supplierName);
      setLatestImport(imported);
      setSupplierName("");
      await load();
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Ошибка импорта");
    } finally {
      setBusy(false);
    }
  }

  async function handleCompetitorUpload(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const imported = await uploadCompetitors(file);
      setRows(imported.rows);
      setCompetitorImportInfo(
        `${imported.result.filename}: импортировано ${imported.result.imported_rows}, сопоставлено ${imported.result.matched_products}`,
      );
      await load();
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Ошибка импорта конкурентов");
    } finally {
      setBusy(false);
    }
  }

  async function handleBuildCompetitorPlans() {
    const sourceGroups = competitorPlanGroups(rows);
    if (sourceGroups.length === 0) {
      setError("Сначала загрузите прайс, чтобы построить группы для автосбора.");
      return;
    }
    setPlanningCompetitors(true);
    setError(null);
    try {
      const plans = await Promise.all(
        sourceGroups.map((item) => buildOzonBestsellersPlan(item.search)),
      );
      setCompetitorPlans(plans);
      setCompetitorPlanInfo(
        `Подготовлено ${plans.length} запросов: ${sourceGroups
          .map((item) => `${item.search} (${item.count})`)
          .join(", ")}`,
      );
    } catch (planError) {
      setError(
        planError instanceof Error ? planError.message : "Не удалось построить план автосбора",
      );
    } finally {
      setPlanningCompetitors(false);
    }
  }

  async function handleRunCompetitorImport() {
    const sourceGroups = competitorPlanGroups(rows);
    if (sourceGroups.length === 0) {
      setError("Сначала загрузите прайс, чтобы построить группы для автосбора.");
      return;
    }
    setImportingCompetitors(true);
    setError(null);
    try {
      const imported = await importOzonBestsellers(sourceGroups.map((item) => item.search));
      setRows(imported.rows);
      setCompetitorImportInfo(
        `Ozon Seller: загружено ${imported.offers_loaded}, сопоставлено ${imported.result.matched_products}`,
      );
      setCompetitorPlanInfo(null);
      await load();
    } catch (importError) {
      setError(
        importError instanceof Error ? importError.message : "Не удалось запустить автосбор",
      );
    } finally {
      setImportingCompetitors(false);
    }
  }

  async function handleCheckSellerAnalyticsAccess() {
    setCheckingSellerAnalytics(true);
    setError(null);
    try {
      const result = await checkOzonSellerAnalyticsAccess();
      setSellerAnalyticsAccess(result);
      setCompetitorImportInfo(result.result.message);
    } catch (checkError) {
      setError(
        checkError instanceof Error
          ? checkError.message
          : "Не удалось проверить доступ к Ozon Seller",
      );
    } finally {
      setCheckingSellerAnalytics(false);
    }
  }

  async function runOzonChecks() {
    setBusy(true);
    setError(null);
    try {
      const [category, products, token] = await Promise.all([
        checkOzonCategoryTree(),
        fetchOzonProducts(),
        checkOzonPerformanceToken(),
      ]);
      setCategoryCheck(category);
      setProductCheck(products);
      setTokenCheck(token);
    } catch (checkError) {
      setError(checkError instanceof Error ? checkError.message : "Ошибка проверки Ozon API");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddToShortlist(row: ProductAnalysis) {
    setError(null);
    if (shortlistedArticles.has(catalogProductKey(row.product))) {
      setActiveTab("shortlist");
      return;
    }
    try {
      const item = await addShortlistItem(row.product.id, {
        supplier_name: row.product.supplier_name,
        supplier_article: row.product.supplier_article,
        product_title: row.product.title,
        group_name: productGroup(row),
        sale_price_vat_included: row.economics.real_fbs_price_vat_included,
      });
      setShortlistItems((current) => upsertShortlistItem(current, item));
    } catch (addError) {
      setError(addError instanceof Error ? addError.message : "Не удалось добавить в отбор");
    }
  }

  async function handleUpdateShortlistItem(productId: string, patch: ShortlistUpdatePayload) {
    setError(null);
    try {
      const item = await updateShortlistItem(productId, patch);
      setShortlistItems((current) => upsertShortlistItem(current, item));
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "Не удалось обновить отбор");
    }
  }

  async function handleDeleteShortlistItem(item: ShortlistItem) {
    setError(null);
    try {
      await deleteShortlistItem(item.analysis.product.id);
      setShortlistItems((current) =>
        current.filter(
          (currentItem) => currentItem.entry.supplier_article !== item.entry.supplier_article,
        ),
      );
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Не удалось удалить из отбора");
    }
  }

  async function handleShortlistUpload(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const imported = await uploadShortlistFile(file);
      setShortlistItems(imported.items);
      setActiveTab("shortlist");
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Не удалось загрузить отбор");
    } finally {
      setBusy(false);
    }
  }

  async function handleRefreshShortlistStocks() {
    setBusy(true);
    setError(null);
    setStockRefreshInfo(null);
    try {
      const result = await refreshShortlistStocks();
      setShortlistItems(result.items);
      setStockRefreshInfo(
        `Остатки: найдено ${result.matched}, обновлено ${result.updated}, не найдено ${result.unmatched}`,
      );
    } catch (refreshError) {
      setError(
        refreshError instanceof Error ? refreshError.message : "Не удалось обновить остатки",
      );
    } finally {
      setBusy(false);
    }
  }

  function competitorDraft(row: ProductAnalysis): CompetitorDraft {
    const saved = row.competitor.offers[0];
    return (
      competitorDrafts[row.product.id] ?? {
        price: saved?.price_vat_included ? String(Math.round(saved.price_vat_included)) : "",
        url: saved?.url ?? "",
        title: saved?.title ?? "",
        matchType: saved?.match_type ?? "analog",
      }
    );
  }

  function updateCompetitorDraft(productId: string, patch: Partial<CompetitorDraft>) {
    setCompetitorDrafts((current) => {
      const existing = current[productId] ?? {
        price: "",
        url: "",
        title: "",
        matchType: "analog" as MatchType,
      };
      return { ...current, [productId]: { ...existing, ...patch } };
    });
  }

  async function handleCompetitorSave(row: ProductAnalysis) {
    const draft = competitorDraft(row);
    const price = Number(draft.price.replace(",", ".").replace(/\s/g, ""));
    if (!Number.isFinite(price) || price <= 0 || !draft.url.trim()) {
      setError("Укажите цену конкурента и ссылку на Ozon.");
      return;
    }
    setSavingCompetitorId(row.product.id);
    setError(null);
    try {
      await saveManualCompetitor(row.product.id, {
        price_vat_included: price,
        url: draft.url.trim(),
        title: draft.title.trim() || undefined,
        match_type: draft.matchType,
      });
      await load();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Не удалось сохранить конкурента");
    } finally {
      setSavingCompetitorId(null);
    }
  }

  function changeSort(next: SortKey) {
    if (sortKey === next) {
      setSortDirection(sortDirection === "desc" ? "asc" : "desc");
      return;
    }
    setSortKey(next);
    setSortDirection("desc");
  }

  return (
    <main className="shell">
      <header className="pageHeader">
        <div>
          <h2>Каталог поставщиков</h2>
        </div>
        <div className="actions">
          <label className="iconButton" title="Импорт Excel-прайса">
            <FileSpreadsheet size={18} />
            <input
              type="file"
              accept=".xlsx,.xls"
              onChange={(event) => void handleUpload(event.target.files?.[0])}
            />
          </label>
          <button className="iconButton" type="button" onClick={() => void load()} title="Обновить">
            <RefreshCw size={18} />
          </button>
        </div>
      </header>

      {error && <div className="alert">{error}</div>}

      <nav className="tabs" aria-label="Разделы платформы">
        <button
          className={activeTab === "catalog" ? "active" : ""}
          type="button"
          onClick={() => setActiveTab("catalog")}
        >
          Каталог
        </button>
        <button
          className={activeTab === "shortlist" ? "active" : ""}
          type="button"
          onClick={() => setActiveTab("shortlist")}
        >
          Отбор
          <span>{shortlistItems.length}</span>
        </button>
      </nav>

      <section className="importPanel">
        <div className="importHeader">
          <div>
            <p className="bandLabel">Импорт прайса</p>
            <strong>{latestImport?.filename ?? "Прайс еще не загружен"}</strong>
            <span>
              {latestImport
                ? `${latestImport.supplier_name} · ${formatDate(latestImport.imported_at)} · версий: ${imports.length}`
                : "Excel-прайсы поставщиков хранятся версиями"}
            </span>
          </div>
          <div className="importActions">
            <label className="supplierInput">
              <span>Поставщик</span>
              <input
                value={supplierName}
                onChange={(event) => setSupplierName(event.target.value)}
                placeholder="Определится из файла"
              />
            </label>
            <label className="uploadButton">
              <FileSpreadsheet size={17} />
              Загрузить Excel
              <input
                type="file"
                accept=".xlsx,.xls"
                onChange={(event) => void handleUpload(event.target.files?.[0])}
              />
            </label>
          </div>
        </div>

        <div className="importStats">
          <Metric label="Строк в файле" value={String(latestImport?.total_rows ?? 0)} />
          <Metric label="Принято" value={String(latestImport?.accepted_rows ?? 0)} />
          <Metric label="Отклонено" value={String(latestImport?.rejected_rows ?? 0)} />
          <Metric label="Ошибки" value={String(latestImport?.error_count ?? 0)} />
          <Metric label="Предупреждения" value={String(latestImport?.warning_count ?? 0)} />
        </div>

        {latestImport && (
          <div className="importDetails">
            <div className="coverageGrid">
              {latestImport.field_coverage
                .filter((field) =>
                  [
                    "supplier_article",
                    "title",
                    "purchase_price_vat_included",
                    "category",
                    "weight_kg",
                    "stock",
                    "barcode",
                  ].includes(field.field),
                )
                .map((field) => (
                  <div className="coverageItem" key={field.field}>
                    <span>{field.label}</span>
                    <strong>{field.coverage_percent}%</strong>
                    <small>{field.source_column ?? "нет колонки"}</small>
                  </div>
                ))}
            </div>

            <div className="issueList">
              {latestImport.issues.slice(0, 6).map((issue) => (
                <div className={`issue ${issue.severity}`} key={`${issue.row_number}-${issue.field}-${issue.message}`}>
                  <span>{issueLabel(issue.severity, issue.row_number)}</span>
                  <strong>{issue.message}</strong>
                </div>
              ))}
              {latestImport.issues.length === 0 && <div className="noIssues">Ошибок импорта нет</div>}
            </div>
          </div>
        )}
      </section>

      <section className="kpis">
        <Kpi label="Товаров" value={visibleKpi.total_products} />
        <Kpi label="Выгодных" value={visibleKpi.profitable_products} tone="good" />
        <Kpi label="Убыточных" value={visibleKpi.unprofitable_products} tone="bad" />
        <Kpi label="Средняя маржа" value={`${visibleKpi.average_margin_percent}%`} />
        <Kpi label="Потенц. прибыль" value={rub(visibleKpi.potential_profit)} tone="money" />
        <Kpi label="Риск" value={visibleKpi.high_risk_products} tone="warn" />
      </section>

      <section className="integrationBand">
        <div>
          <p className="bandLabel">Ozon API</p>
          <strong>{sellerStatus?.integration.message ?? "Проверка Seller API"}</strong>
          <span>
            {sellerStatus?.integration.account_label ?? "Кабинет не определен"} →{" "}
            {sellerStatus?.integration.target_store_name ?? "Лето стройматериалы"}
          </span>
          <span>{sellerStatus?.integration.client_id_masked ?? "client id скрыт"}</span>
        </div>
        <div>
          <p className="bandLabel">Performance API</p>
          <strong>{performanceStatus?.integration.message ?? "Проверка рекламы"}</strong>
          <span>{performanceStatus?.integration.usage_mode ?? "target_store"}</span>
          <span>{performanceStatus?.integration.client_id_masked ?? "client id скрыт"}</span>
        </div>
        <div className="integrationResult">
          <span>Категории: {categoryCheck?.categories_count ?? "—"}</span>
          <span>Товары: {productCheck?.total_returned ?? "—"}</span>
          <span>Токен: {tokenCheck?.result.token_type ?? "—"}</span>
        </div>
        <button className="sortButton" type="button" onClick={() => void runOzonChecks()}>
          <PlugZap size={16} />
          Проверить
        </button>
      </section>

      <section className="competitorImportBand">
        <div>
          <p className="bandLabel">Конкуренты Ozon</p>
          <strong>Автосбор через Ozon Seller + fallback XLSX</strong>
          <span>
            {competitorPlanInfo ??
              competitorImportInfo ??
              sellerAnalyticsStatus?.integration.message ??
              "Источник: кабинет Ozon Seller / аналитика конкурентов."}
          </span>
          <div className="sellerWebStatus">
            <b className={sellerAnalyticsStatus?.integration.configured ? "statusOk" : "statusMuted"}>
              {sellerAnalyticsStatus?.integration.configured
                ? `Локальная авторизация: ${sellerAnalyticsStatus.integration.cookie_masked ?? "подключена"}`
                : "Локальная авторизация не подключена"}
            </b>
            {sellerAnalyticsAccess ? (
              <b className={sellerAnalyticsAccess.result.ok ? "statusOk" : "statusWarn"}>
                {sellerAnalyticsAccess.result.ok
                  ? `Тест Ozon: доступ есть, строк ${sellerAnalyticsAccess.result.offers_seen}`
                  : `Тест Ozon: ${sellerAnalyticsAccess.result.status_code ?? "нет доступа"}`}
              </b>
            ) : null}
          </div>
        </div>
        <div className="competitorActions">
          <button
            className="secondaryButton"
            type="button"
            disabled={checkingSellerAnalytics}
            onClick={() => void handleCheckSellerAnalyticsAccess()}
          >
            <PlugZap size={16} />
            {checkingSellerAnalytics ? "Проверяю" : "Проверить доступ"}
          </button>
          <button
            className="primaryOutlineButton"
            type="button"
            disabled={importingCompetitors}
            onClick={() => void handleRunCompetitorImport()}
          >
            <PlugZap size={16} />
            {importingCompetitors ? "Собираю" : "Запустить автосбор"}
          </button>
          <button
            className="secondaryButton"
            type="button"
            disabled={planningCompetitors}
            onClick={() => void handleBuildCompetitorPlans()}
          >
            <PlugZap size={16} />
            {planningCompetitors ? "Готовлю" : "План автосбора"}
          </button>
          <label className="uploadButton compact">
            <FileSpreadsheet size={17} />
            Загрузить XLSX
            <input
              type="file"
              accept=".xlsx,.xls"
              onChange={(event) => void handleCompetitorUpload(event.target.files?.[0])}
            />
          </label>
        </div>
        {competitorPlans.length > 0 && (
          <div className="competitorPlanGrid">
            {competitorPlans.slice(0, 8).map((plan) => (
              <article className="planCard" key={plan.request.search ?? plan.json_endpoint}>
                <span>{plan.request.search}</span>
                <strong>{plan.json_endpoint}</strong>
                <code>{JSON.stringify(plan.json_payload)}</code>
              </article>
            ))}
          </div>
        )}
      </section>

      {(sellerStatus?.integration.data_scope_warning ||
        performanceStatus?.integration.data_scope_warning) && (
        <section className="scopeNotice">
          {sellerStatus?.integration.data_scope_warning ??
            performanceStatus?.integration.data_scope_warning}
        </section>
      )}

      {activeTab === "catalog" ? (
        <>
      <section className="toolbar">
        <label className="filterField">
          <span>Поиск</span>
          <div className="search">
            <Search size={17} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Артикул или товар" />
          </div>
        </label>
        <label className="filterField">
          <span>Прайс</span>
          <select value={importFilter} onChange={(event) => setImportFilter(event.target.value)}>
            <option value="latest">Последний загруженный</option>
            <option value="all">Все прайсы</option>
            {imports.map((version) => (
              <option value={importVersionKey(version)} key={version.id}>
                {version.filename}
              </option>
            ))}
          </select>
        </label>
        <label className="filterField">
          <span>Поставщик</span>
          <select value={supplier} onChange={(event) => setSupplier(event.target.value)}>
            <option>Все</option>
            {suppliers.map((option) => <option key={option}>{option}</option>)}
          </select>
        </label>
        <label className="filterField">
          <span>Готовность</span>
          <select
            value={readinessFilter}
            onChange={(event) => setReadinessFilter(event.target.value as ReadinessFilter)}
          >
            <option>Все</option>
            <option>Готов к запуску</option>
            <option>Нужны данные</option>
            <option>Стоп</option>
          </select>
        </label>
        <label className="filterField">
          <span>Рекомендация</span>
          <select value={status} onChange={(event) => setStatus(event.target.value as Recommendation | "Все")}>
            {statusOptions.map((option) => (
              <option key={option}>{option}</option>
            ))}
          </select>
        </label>
        <label className="filterField">
          <span>Группа</span>
          <select value={group} onChange={(event) => setGroup(event.target.value)}>
            <option>Все</option>
            {groups.map((option) => (
              <option key={option}>{option}</option>
            ))}
          </select>
        </label>
        <label className="filterField">
          <span>Категория</span>
          <select value={category} onChange={(event) => setCategory(event.target.value)}>
            <option>Все</option>
            {categories.map((option) => (
              <option key={option}>{option}</option>
            ))}
          </select>
        </label>
        <label className="filterField">
          <span>Прибыль</span>
          <select value={profitFilter} onChange={(event) => setProfitFilter(event.target.value as ProfitFilter)}>
            <option>Все</option>
            <option>В плюс</option>
            <option>В минус</option>
          </select>
        </label>
        <fieldset className="filterField purchaseRange">
          <legend>Закупка, ₽</legend>
          <input
            inputMode="decimal"
            placeholder="от"
            value={purchaseMin}
            onChange={(event) => setPurchaseMin(event.target.value)}
            aria-label="Закупка от"
          />
          <input
            inputMode="decimal"
            placeholder="до"
            value={purchaseMax}
            onChange={(event) => setPurchaseMax(event.target.value)}
            aria-label="Закупка до"
          />
        </fieldset>
        <label className="filterField">
          <span>Наличие</span>
          <select
            value={stockFilter}
            onChange={(event) => setStockFilter(event.target.value as StockFilter)}
          >
            <option>В наличии</option>
            <option>Все</option>
            <option>Нет в наличии</option>
            <option>Не указан</option>
          </select>
        </label>
        <fieldset className="filterField purchaseRange">
          <legend>Остаток, шт.</legend>
          <input
            inputMode="decimal"
            placeholder="от"
            value={stockMin}
            onChange={(event) => setStockMin(event.target.value)}
            aria-label="Остаток от"
          />
          <input
            inputMode="decimal"
            placeholder="до"
            value={stockMax}
            onChange={(event) => setStockMax(event.target.value)}
            aria-label="Остаток до"
          />
        </fieldset>
        <fieldset className="filterField purchaseRange">
          <legend>Заказы конкур.</legend>
          <input
            inputMode="numeric"
            placeholder="от"
            value={ordersMin}
            onChange={(event) => setOrdersMin(event.target.value)}
            aria-label="Заказы конкурентов от"
          />
          <input
            inputMode="numeric"
            placeholder="до"
            value={ordersMax}
            onChange={(event) => setOrdersMax(event.target.value)}
            aria-label="Заказы конкурентов до"
          />
        </fieldset>
        <label className="filterField range">
          <span>Мин. маржа {minMargin}%</span>
          <input
            type="range"
            min="-100"
            max="60"
            step="5"
            value={minMargin}
            onChange={(event) => setMinMargin(Number(event.target.value))}
          />
        </label>
        <div className="tableTools">
          <button className="sortButton" type="button" onClick={() => setTableFontSize((size) => Math.max(size - 1, 11))}>
            A-
          </button>
          <button className="sortButton" type="button" onClick={() => setTableFontSize((size) => Math.min(size + 1, 18))}>
            A+
          </button>
          <button className="sortButton" type="button" onClick={() => setTableFullscreen((value) => !value)}>
            {tableFullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
          <a className="sortButton exportLink" href={unitEconomicsExportUrl()}>
            <Download size={16} />
            Excel
          </a>
        </div>
      </section>

      <section
        className={`tableWrap ${tableFullscreen ? "fullscreen" : ""}`}
        style={{ "--table-font-size": `${tableFontSize}px` } as CSSProperties}
        aria-busy={busy}
      >
        {tableFullscreen && (
          <button
            className="fullscreenClose"
            type="button"
            onClick={() => setTableFullscreen(false)}
            title="Выйти из полноэкранного режима"
          >
            <Minimize2 size={16} />
          </button>
        )}
        <div className="tablePager">
          <span>
            Показано {visibleRows.length === 0 ? 0 : (safeTablePage - 1) * tablePageSize + 1}-
            {Math.min(safeTablePage * tablePageSize, filtered.length)} из {filtered.length}
          </span>
          <div>
            <button
              type="button"
              disabled={safeTablePage <= 1}
              onClick={() => setTablePage((page) => Math.max(page - 1, 1))}
            >
              Назад
            </button>
            <strong>
              {safeTablePage} / {totalPages}
            </strong>
            <button
              type="button"
              disabled={safeTablePage >= totalPages}
              onClick={() => setTablePage((page) => Math.min(page + 1, totalPages))}
            >
              Вперед
            </button>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <SortableTh active={sortKey === "article"} direction={sortDirection} onClick={() => changeSort("article")} title="Артикул поставщика из прайса.">
                Артикул
              </SortableTh>
              <th title="Поставщик и дата последнего загруженного прайса.">Поставщик</th>
              <SortableTh active={sortKey === "title"} direction={sortDirection} onClick={() => changeSort("title")} title="Название товара из прайса поставщика.">
                Товар
              </SortableTh>
              <SortableTh active={sortKey === "category"} direction={sortDirection} onClick={() => changeSort("category")} title="Категория из прайса или строк-разделов.">
                Категория
              </SortableTh>
              <SortableTh active={sortKey === "purchase"} direction={sortDirection} onClick={() => changeSort("purchase")} title="Закупочная цена с НДС из прайса.">
                Закупка
              </SortableTh>
              <SortableTh active={sortKey === "stock"} direction={sortDirection} onClick={() => changeSort("stock")} title="Доступный остаток поставщика из прайса. Если в прайсе несколько складов без общего итога, они суммируются.">
                Остаток
              </SortableTh>
              <SortableTh active={sortKey === "listPrice"} direction={sortDirection} onClick={() => changeSort("listPrice")} title="Цена, которую ставим в Ozon без учета соинвеста. Внутри строки показано: что видит покупатель, соинвест Ozon и сколько ориентировочно придет после услуг Ozon.">
                Цена / счет
              </SortableTh>
              <SortableTh active={sortKey === "competitor"} direction={sortDirection} onClick={() => changeSort("competitor")} title="Оценка конкурентной цены до подключения реальных данных конкурентов.">
                Конкурент
              </SortableTh>
              <SortableTh active={sortKey === "orders"} direction={sortDirection} onClick={() => changeSort("orders")} title="Максимальное количество заказов среди найденных конкурентов из Ozon Seller / XLSX. Если данных нет, товар не пройдет фильтр по заказам.">
                Заказы
              </SortableTh>
              <SortableTh active={sortKey === "profit"} direction={sortDirection} onClick={() => changeSort("profit")} title="Сверху чистая прибыль Ozon как раньше. Ниже чистая прибыль бизнеса после быстрого вывода, дизайнера/контента и фулфилмента/забора.">
                Прибыль
              </SortableTh>
              <SortableTh active={sortKey === "margin"} direction={sortDirection} onClick={() => changeSort("margin")} title="Чистая прибыль / цена выкладки.">
                Маржа
              </SortableTh>
              <SortableTh active={sortKey === "recommended"} direction={sortDirection} onClick={() => changeSort("recommended")} title="Цена для целевой маржи с учетом примерной конкурентности.">
                Рекоменд.
              </SortableTh>
              <th title="Итоговая рекомендация backend-расчета.">Статус</th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => {
              const isShortlisted = shortlistedArticles.has(catalogProductKey(row.product));

              return (
                <Fragment key={row.product.id}>
                  <tr
                    className={isShortlisted ? "shortlistedRow" : undefined}
                    onClick={() => setExpanded(expanded === row.product.id ? null : row.product.id)}
                  >
                  <td>{row.product.supplier_article}</td>
                  <td>
                    <strong>{row.product.supplier_name}</strong>
                    <span>{row.product.source_imported_at ? formatDate(row.product.source_imported_at) : "дата н/д"}</span>
                  </td>
                  <td>
                    <strong>{row.product.title}</strong>
                    <span>{row.product.brand ?? "Без бренда"}</span>
                    {row.product.package && <span>фасовка {row.product.package}</span>}
                  </td>
                  <td>{row.product.category ?? "Не указана"}</td>
                  <td>{rub(row.economics.purchase_price_vat_included)}</td>
                  <td className={stockClass(row.product.stock)}>{stockLabel(row.product.stock)}</td>
                  <td>
                    {rub(row.economics.real_fbs_price_vat_included)}
                    <span>поставить в Ozon</span>
                    <span>покупатель видит {rub(row.economics.buyer_payment_price_vat_included)}</span>
                    <span>соинвест {rub(row.economics.ozon_bonus_accrual)}</span>
                    <span>нам начислят {rub(row.economics.marketplace_gross_accrual_vat_included)}</span>
                    <span>после услуг Ozon {rub(row.economics.expected_payout_after_ozon_services)}</span>
                  </td>
                  <td>
                    {rub(row.economics.estimated_competitor_price_vat_included ?? 0)}
                    <span>{competitorSourceLabel(row.competitor.source)}</span>
                    {row.competitor.leader_url ? (
                      <a href={row.competitor.leader_url} target="_blank" rel="noreferrer">
                        конкурент
                      </a>
                    ) : null}
                    <a href={ozonSearchUrl(row)} target="_blank" rel="noreferrer">
                      поиск
                    </a>
                  </td>
                  <td>
                    {ordersLabel(maxCompetitorOrders(row))}
                    <span>конкурент</span>
                  </td>
                  <td className={row.economics.net_profit >= 0 ? "positive" : "negative"}>
                    {rub(row.economics.net_profit)}
                    <span>Ozon</span>
                    <span className={row.economics.business_net_profit >= 0 ? "positive" : "negative"}>
                      бизнес {rub(row.economics.business_net_profit)}
                    </span>
                  </td>
                  <td>{row.economics.margin_percent}%</td>
                  <td>
                    {rub(row.economics.recommended_price_vat_included)}
                    <span>поставить</span>
                    <span>мин. {rub(row.economics.break_even_price_vat_included)}</span>
                  </td>
                  <td>
                    <span className={`pill ${pillClass(row.economics.recommendation)}`}>
                      {row.economics.recommendation}
                    </span>
                    <span className={`pill ${readinessPillClass(row.readiness.status)}`} title={row.readiness.reasons.join(" ")}>
                      {row.readiness.status}
                    </span>
                    <button
                      className={`inlineAction ${isShortlisted ? "selected" : ""}`}
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleAddToShortlist(row);
                      }}
                    >
                      {isShortlisted ? "В отборе" : "В отбор"}
                    </button>
                  </td>
                </tr>
                {expanded === row.product.id && (
                  <tr className="details">
                    <td colSpan={13}>
                      <EconomicsDetails row={row}>
                        <ManualCompetitorForm
                          draft={competitorDraft(row)}
                          isSaving={savingCompetitorId === row.product.id}
                          row={row}
                          onChange={(patch) => updateCompetitorDraft(row.product.id, patch)}
                          onSave={() => void handleCompetitorSave(row)}
                        />
                      </EconomicsDetails>
                    </td>
                  </tr>
                )}
              </Fragment>
              );
            })}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={13} className="empty">
                  Нет товаров. Импортируйте Excel-прайс.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
        </>
      ) : (
        <ShortlistView
          busy={busy}
          items={shortlistItems}
          onDelete={(item) => void handleDeleteShortlistItem(item)}
          onImport={(file) => void handleShortlistUpload(file)}
          onRefreshStocks={() => void handleRefreshShortlistStocks()}
          onUpdate={({ productId, patch }) => void handleUpdateShortlistItem(productId, patch)}
          stockRefreshInfo={stockRefreshInfo}
        />
      )}
    </main>
  );
}

function EconomicsDetails({
  children,
  onDrrChange,
  onFulfillmentProcessingChange,
  onPackageCostChange,
  onSmallGoodsPreset,
  offerQuantity = 1,
  row,
}: {
  children?: ReactNode;
  onDrrChange?: Dispatch<number>;
  onFulfillmentProcessingChange?: Dispatch<number>;
  onPackageCostChange?: Dispatch<number>;
  onSmallGoodsPreset?: () => void;
  offerQuantity?: number;
  row: ProductAnalysis;
}) {
  const shares = row.economics.expense_shares_percent;
  const profitTone = row.economics.business_net_profit >= 0 ? "positive" : "negative";
  const share = (key: string) => `${shares[key] ?? 0}% от начислений`;
  const dimensionsReady = row.product.dimensions.volume_liters !== null;
  return (
    <>
      <section className="decisionSummary" aria-label="Краткий итог расчета">
        <article>
          <span>Цена в Ozon</span>
          <strong>{rub(row.economics.real_fbs_price_vat_included)}</strong>
        </article>
        <article>
          <span>Покупатель видит</span>
          <strong>{rub(row.economics.buyer_payment_price_vat_included)}</strong>
        </article>
        <article>
          <span>Ozon начислит</span>
          <strong>{rub(row.economics.marketplace_gross_accrual_vat_included)}</strong>
        </article>
        <article>
          <span>После услуг Ozon</span>
          <strong>{rub(row.economics.expected_payout_after_ozon_services)}</strong>
        </article>
        <article className={profitTone}>
          <span>Прибыль бизнеса до рейса</span>
          <strong>{rub(row.economics.business_net_profit)}</strong>
          <small>{row.economics.business_margin_percent}% от цены</small>
        </article>
      </section>

      <div className="calculationAccuracy">
        <strong>Точность расчета</strong>
        <span className={row.economics.matched_ozon_product_type ? "confirmed" : "estimate"}>
          Комиссия: {row.economics.matched_ozon_product_type ? "сопоставлена" : "оценка"}
        </span>
        <span className={dimensionsReady ? "confirmed" : "estimate"}>
          Габариты: {dimensionsReady ? "указаны" : "не заполнены"}
        </span>
        <span className="estimate">Логистика: оценка</span>
        <span className="estimate">Рейс FBS: отдельно</span>
      </div>

      <div className="economicsTree">
        <CalculationGroup
          title="Цена и начисления"
          totalLabel="Начисления всего"
          totalValue={rub(row.economics.marketplace_gross_accrual_vat_included)}
          defaultOpen={false}
        >
          <CalculationRow label="Поставить в Ozon" value={rub(row.economics.real_fbs_price_vat_included)} help="Цена продавца без учета соинвеста Ozon. Именно ее мы указываем в кабинете." />
          <CalculationRow label="Цена до скидки Ozon" value={rub(row.economics.ozon_price_before_discount_vat_included)} detail={`видимая скидка ${row.economics.ozon_visible_discount_percent}%`} help="Расчетная зачеркнутая цена до видимой скидки Ozon." />
          <CalculationRow label="Цена с картой" value={rub(row.economics.bank_card_price_vat_included)} detail={`скидка банка ${row.economics.bank_card_discount_percent}%`} help="Сценарная цена при оплате картой. Скидка банка не считается расходом продавца без подтверждения Ozon." />
          <CalculationRow label="Минимальная цена Ozon" value={rub(row.economics.ozon_min_price_vat_included)} help="Защитный порог для настройки минимальной цены в кабинете Ozon." />
          <CalculationRow label="Покупатель видит" value={rub(row.economics.buyer_payment_price_vat_included)} help="Оценочная цена после соинвеста. Она может отличаться по региону и способу оплаты." />
          <CalculationRow label={`Соинвест Ozon ${row.economics.seller_bonus_percent}%`} value={rub(row.economics.ozon_bonus_accrual)} help="Оценочное положительное начисление баллами за скидки. Это не обычная скидка продавца." />
          <CalculationRow label="Программы партнеров" value={rub(row.economics.partner_program_accrual)} help="Оценочное положительное начисление из отчета Ozon по партнерским программам." />
        </CalculationGroup>

        <CalculationGroup
          title="Услуги Ozon"
          totalLabel="Удержания Ozon"
          totalValue={rub(row.economics.ozon_services_total)}
          totalDetail={share("ozon_services")}
          defaultOpen={false}
        >
          <CalculationRow label={`Комиссия за продажу ${row.economics.ozon_commission_percent}%`} value={rub(row.economics.ozon_commission)} detail={row.economics.commission_source_label} help={`Комиссия FBS зависит от типа товара и цены. Сопоставлено: ${row.economics.matched_ozon_category ?? "категория не определена"} / ${row.economics.matched_ozon_product_type ?? "тип не определен"}.`} />
          <CalculationRow label="Логистика Ozon" value={rub(row.economics.logistics)} detail={share("logistics")} help="Предварительная оценка по весу и объему. После заполнения габаритов она точнее, но до сверки с калькулятором Ozon остается оценочной." />
          <CalculationRow label="Эквайринг" value={rub(row.economics.acquiring)} detail={share("acquiring")} help="Плата за обработку платежа. В текущем сценарии применяется ставка тарифа расчета." />
          <CalculationRow label="Хранение Ozon" value={rub(row.economics.storage)} detail={share("storage")} help="Для FBS товар хранится у продавца, поэтому хранение Ozon равно нулю." />
          <CalculationRow label="После услуг Ozon" value={rub(row.economics.expected_payout_after_ozon_services)} emphasis help="Начисления всего минус комиссия, логистика, эквайринг и хранение Ozon. Упаковка и внешний фулфилмент сюда не входят." />
        </CalculationGroup>

        <CalculationGroup
          title="Себестоимость и подготовка"
          totalLabel="Расходы до налога"
          totalValue={rub(row.economics.total_expenses_before_tax)}
          totalDetail={share("expenses_before_tax")}
          defaultOpen={false}
        >
          {onSmallGoodsPreset && (
            <div className="fulfillmentPreset">
              <div>
                <strong>Профиль мелкого товара</strong>
                <span>6 ₽ упаковка + 16 ₽ маркировка и проверка. Рейс FBS считается отдельно.</span>
              </div>
              <button type="button" onClick={onSmallGoodsPreset}>Применить 22 ₽</button>
            </div>
          )}
          <CalculationRow label={offerQuantity > 1 ? `Закупка комплекта, ${offerQuantity} шт.` : "Закупочная цена"} value={rub(row.economics.purchase_price_vat_included)} detail={offerQuantity > 1 ? `${rub(row.economics.purchase_price_vat_included / offerQuantity)} за шт.` : share("purchase")} help="Цена поставщика с НДС. Для комплекта закупка всех единиц суммируется backend-расчетом." />
          <CalculationRow label="Упаковочные материалы на заказ" value={rub(row.economics.package_cost)} detail={share("package")} help="Пакет, стрейч, коробка и другие материалы на один заказ Ozon, а не на каждую штуку внутри комплекта." control={onPackageCostChange && <InlineMoneyEditor ariaLabel="Упаковочные материалы" value={row.economics.package_cost} onCommit={onPackageCostChange} />} />
          <CalculationRow label="Обработка фулфилментом на заказ" value={rub(row.economics.fulfillment_processing_cost)} detail={share("fulfillment_processing")} help="Маркировка, визуальная проверка и операции упаковщика на один заказ. Если каждую штуку комплекта маркируют отдельно, сумму нужно увеличить вручную." control={onFulfillmentProcessingChange && <InlineMoneyEditor ariaLabel="Обработка фулфилментом" value={row.economics.fulfillment_processing_cost} onCommit={onFulfillmentProcessingChange} />} />
          <CalculationRow label={`Реклама, DRR ${row.economics.advertising_drr_percent}%`} value={rub(row.economics.advertising)} help="Рекламные расходы как процент от цены продажи. Выбор сохраняется для товара в отборе." control={onDrrChange && <DrrSelector value={row.economics.advertising_drr_percent} onChange={onDrrChange} />} />
          <CalculationRow label="Себестоимость без комиссии" value={rub(row.economics.cost_basis_without_commission)} help="Закупка, логистика, эквайринг, упаковка, обработка, хранение и прочие расходы, но без комиссии Ozon и рекламы." />
          <CalculationRow label="Себестоимость + Ozon" value={rub(row.economics.cost_basis_with_commission)} help="Себестоимость без комиссии плюс комиссия Ozon." />
          <CalculationRow label="Торговая наценка" value={`${row.economics.markup_percent}%`} help="Разница между ценой продажи и закупкой относительно закупочной цены. Это не маржинальность после расходов." />
        </CalculationGroup>

        <CalculationGroup
          title="Налоги"
          totalLabel="Налоги всего"
          totalValue={rub(row.economics.profit_tax)}
          totalDetail={share("taxes")}
          defaultOpen={false}
        >
          <CalculationRow label="Налоговый режим" value={taxRegimeLabel(row.economics.tax_regime)} />
          <CalculationRow label="База УСН" value={rub(row.economics.tax_income_basis)} help="Доход, с которого считается УСН. Здесь это все начисления от Ozon до удержания комиссии и других услуг, а не прибыль." />
          <CalculationRow label="УСН 6%" value={rub(row.economics.usn_tax)} detail="6% от базы УСН" help="Налог по режиму ИП УСН «Доходы»." />
          <CalculationRow label="Дополнительный взнос 1%" value={rub(row.economics.usn_additional_contribution)} detail="оценка 1% от базы" help="Предварительный резерв после превышения 300 000 ₽ годового дохода. Точный расчет требует накопительного дохода за год." />
          <CalculationRow label="Налоги всего" value={rub(row.economics.profit_tax)} detail={share("taxes")} emphasis />
        </CalculationGroup>

        <CalculationGroup
          title="Бизнес-расходы"
          totalLabel="Дополнительные расходы"
          totalValue={rub(row.economics.business_extra_costs_total)}
          totalDetail={share("business_extra")}
          defaultOpen={false}
        >
          <CalculationRow label={`Быстрый вывод ${row.economics.fast_payout_fee_percent}%`} value={rub(row.economics.fast_payout_fee)} help="Начисления всего × 2,45%." />
          <CalculationRow label={`Дизайнер / контент ${row.economics.designer_content_percent}%`} value={rub(row.economics.designer_content_cost)} help="Начисления всего × 4%." />
          <CalculationRow label={`Резерв фулфилмента ${row.economics.business_fulfillment_pickup_percent}%`} value={rub(row.economics.business_fulfillment_pickup_cost)} detail={row.economics.business_fulfillment_pickup_percent ? "включен дополнительно" : "выключен: используются прямые расходы"} help="Дополнительный процентный резерв. По умолчанию выключен, чтобы не дублировать упаковку, обработку и фиксированный рейс FBS." />
          <CalculationRow label="Дополнительные расходы" value={rub(row.economics.business_extra_costs_total)} detail={share("business_extra")} emphasis />
        </CalculationGroup>

        <CalculationGroup
          title="Итог"
          totalLabel="Чистая прибыль бизнеса"
          totalValue={rub(row.economics.business_net_profit)}
          totalDetail={share("business_net_profit")}
          tone={profitTone}
          defaultOpen
        >
          <CalculationRow label="Прибыль до налогов" value={rub(row.economics.profit_before_tax)} />
          <CalculationRow label="Чистая прибыль Ozon" value={rub(row.economics.net_profit)} detail={`${row.economics.margin_percent}% от цены`} help="Текущая прибыль после закупки, услуг Ozon, рекламы, упаковки, обработки и налогов, но до дополнительных бизнес-расходов." />
          <CalculationRow label="Чистая прибыль бизнеса" value={rub(row.economics.business_net_profit)} detail={`${row.economics.business_margin_percent}% от цены`} emphasis tone={profitTone} help="Чистая прибыль Ozon минус быстрый вывод, дизайнер и включенный процентный резерв." />
        </CalculationGroup>

        <CalculationGroup
          title="Цены и переговоры с поставщиком"
          totalLabel={`Приемлемая закупка для маржи ${row.economics.target_margin_percent}%`}
          totalValue={rub(row.economics.target_purchase_price_vat_included)}
          totalDetail={supplierDiscountLabel(
            row.economics.required_supplier_discount_target_amount,
            row.economics.required_supplier_discount_target_percent,
            row.economics.supplier_discount_target_feasible,
          )}
          defaultOpen
        >
          <CalculationRow label="Текущая цена в Ozon" value={rub(row.economics.real_fbs_price_vat_included)} />
          <CalculationRow label={offerQuantity > 1 ? `Текущая закупка комплекта, ${offerQuantity} шт.` : "Текущая закупка"} value={rub(row.economics.purchase_price_vat_included)} detail={offerQuantity > 1 ? `${rub(row.economics.purchase_price_vat_included / offerQuantity)} за шт.` : undefined} />
          <CalculationRow label="Безубыточная цена продажи" value={rub(row.economics.break_even_price_vat_included)} help="Цена Ozon, при которой чистая прибыль бизнеса равна нулю до распределения фиксированного рейса FBS." />
          <CalculationRow label={`Цена продажи для маржи ${row.economics.target_margin_percent}%`} value={rub(row.economics.recommended_price_vat_included)} detail={`целевая прибыль ${rub(row.economics.target_business_profit)}`} help="Цена Ozon для целевой чистой маржи бизнеса при текущей закупке и расходах." />
          <CalculationRow
            label="Предельная закупка для безубытка"
            value={rub(row.economics.max_purchase_price_break_even_vat_included)}
            detail={`${supplierDiscountLabel(
              row.economics.required_supplier_discount_break_even_amount,
              row.economics.required_supplier_discount_break_even_percent,
              row.economics.supplier_discount_break_even_feasible,
            )}${offerQuantity > 1 ? ` · ${rub(row.economics.max_purchase_price_break_even_vat_included / offerQuantity)} за шт.` : ""}`}
            help="Максимальная закупочная цена, при которой чистая прибыль бизнеса будет не ниже нуля при текущей цене Ozon."
          />
          <CalculationRow
            label={`Приемлемая закупка для маржи ${row.economics.target_margin_percent}%`}
            value={rub(row.economics.target_purchase_price_vat_included)}
            detail={`${supplierDiscountLabel(
              row.economics.required_supplier_discount_target_amount,
              row.economics.required_supplier_discount_target_percent,
              row.economics.supplier_discount_target_feasible,
            )}${offerQuantity > 1 ? ` · ${rub(row.economics.target_purchase_price_vat_included / offerQuantity)} за шт.` : ""}`}
            emphasis
            help="Закупочная цена, которая позволит получить целевую чистую маржу бизнеса при неизменных цене Ozon и расходах."
          />
        </CalculationGroup>
      </div>
      <details className="advancedScenarios">
        <summary>Сценарии DRR и фиксированного рейса FBS</summary>
        <div className="scenarioBlock">
          <span className="sectionLabel">Сценарии рекламы</span>
          <div className="scenarioGrid">
            {row.economics.drr_scenarios.map((scenario) => (
              <Metric
                key={scenario.drr_percent}
                label={`DRR ${scenario.drr_percent}%`}
                value={`${rub(scenario.net_profit)} · ${scenario.margin_percent}%`}
              />
            ))}
          </div>
        </div>
        <div className="fbsBatchBlock">
          <span className="sectionLabel">FBS под заказ: фиксированный рейс дня</span>
          <p>
            Забор у Центр СМ + доставка на СЦ Ozon ={" "}
            {rub(row.economics.fbs_batch_scenarios[0]?.fixed_costs_total ?? 0)}.
            Итог зависит от числа заказов, между которыми делится рейс.
          </p>
          <div className="scenarioGrid fbs">
            {row.economics.fbs_batch_scenarios.map((scenario) => (
              <Metric
                key={scenario.orders_per_day}
                label={`${scenario.orders_per_day} заказ${orderSuffix(scenario.orders_per_day)} / день`}
                value={`${rub(scenario.business_net_profit_after_fixed)} · рейс ${rub(scenario.allocated_fixed_cost_per_order)}`}
              />
            ))}
          </div>
        </div>
      </details>
      {children}
      <div className="calcSummary">
        «Поставить в Ozon» — цена без учета соинвеста. Покупатель может видеть
        цену ниже, а Ozon компенсирует разницу начислением. После услуг Ozon из
        начислений вычтены только услуги Ozon. Внешний фулфилмент разделен на
        материалы, операции на единицу и фиксированный рейс дня, поэтому эти
        расходы больше не смешиваются. Подробные формулы остаются в Excel на листе
        «Пояснения».
      </div>
      {row.economics.warnings.length > 0 && (
        <div className="warnings">{row.economics.warnings.join(" ")}</div>
      )}
    </>
  );
}

function CalculationGroup({
  children,
  defaultOpen,
  title,
  tone,
  totalLabel,
  totalDetail,
  totalValue,
}: {
  children: ReactNode;
  defaultOpen?: boolean;
  title: string;
  tone?: "positive" | "negative";
  totalLabel: string;
  totalDetail?: string;
  totalValue: string;
}) {
  return (
    <details className="calculationGroup" open={defaultOpen}>
      <summary>
        <span>
          <strong>{title}</strong>
          <small>{totalLabel}{totalDetail ? ` · ${totalDetail}` : ""}</small>
        </span>
        <b className={tone}>{totalValue}</b>
      </summary>
      <div className="calculationRows">{children}</div>
    </details>
  );
}

function CalculationRow({
  control,
  detail,
  emphasis = false,
  help,
  label,
  tone,
  value,
}: {
  control?: ReactNode;
  detail?: string;
  emphasis?: boolean;
  help?: string;
  label: string;
  tone?: "positive" | "negative";
  value: string;
}) {
  return (
    <div className={`calculationRow${emphasis ? " emphasis" : ""}`}>
      <span className="calculationLabel">
        {label}
        {help && (
          <span className="calculationHelp" data-tooltip={help} title={help}>
            <CircleHelp aria-hidden="true" size={14} />
          </span>
        )}
      </span>
      {control}
      <span className="calculationValue">
        <strong className={tone}>{value}</strong>
        {detail && <small>{detail}</small>}
      </span>
    </div>
  );
}

function DrrSelector({ onChange, value }: { onChange: Dispatch<number>; value: number }) {
  return (
    <div className="drrSelector" aria-label="Выбор DRR">
      {[8, 10, 12, 15].map((option) => (
        <button
          className={value === option ? "active" : ""}
          key={option}
          type="button"
          onClick={() => onChange(option)}
        >
          {option}%
        </button>
      ))}
    </div>
  );
}

function InlineMoneyEditor({
  ariaLabel,
  onCommit,
  value,
}: {
  ariaLabel: string;
  onCommit: Dispatch<number>;
  value: number;
}) {
  return (
    <div className="inlineMoneyEditor">
      <EditableNumber
        ariaLabel={ariaLabel}
        value={value}
        min={0}
        fractionDigits={0}
        onCommit={onCommit}
      />
      <span>₽</span>
    </div>
  );
}

function supplierDiscountLabel(amount: number, percent: number, feasible: boolean) {
  if (!feasible) {
    return "скидкой на закуп цель недостижима";
  }
  if (amount <= 0) {
    return "скидка поставщика не требуется";
  }
  return `просить скидку ${rub(amount)} · ${percent}% на закуп`;
}

function ShortlistView({
  busy,
  items,
  onDelete,
  onImport,
  onRefreshStocks,
  onUpdate,
  stockRefreshInfo,
}: {
  busy: boolean;
  items: ShortlistItem[];
  onDelete: Dispatch<ShortlistItem>;
  onImport: Dispatch<File | undefined>;
  onRefreshStocks: () => void;
  onUpdate: Dispatch<{ productId: string; patch: ShortlistUpdatePayload }>;
  stockRefreshInfo: string | null;
}) {
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState("Все");
  const [subgroup, setSubgroup] = useState("Все");
  const [stockFilter, setStockFilter] = useState<StockFilter>("Все");
  const [expanded, setExpanded] = useState<string | null>(null);

  const groups = useMemo(
    () =>
      Array.from(new Set(items.map((item) => item.entry.group_name).filter(Boolean))).sort(),
    [items],
  );
  const subgroups = useMemo(
    () =>
      Array.from(new Set(items.map((item) => item.entry.subgroup_name).filter(Boolean))).sort(),
    [items],
  );
  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      const row = item.analysis;
      const haystack =
        `${row.product.supplier_article} ${row.product.title} ${row.product.category ?? ""}`.toLowerCase();
      return (
        haystack.includes(query.toLowerCase()) &&
        (group === "Все" || item.entry.group_name === group) &&
        (subgroup === "Все" || item.entry.subgroup_name === subgroup) &&
        (stockFilter === "Все" ||
          (stockFilter === "В наличии" && row.product.stock !== null && row.product.stock > 0) ||
          (stockFilter === "Нет в наличии" && row.product.stock !== null && row.product.stock <= 0) ||
          (stockFilter === "Не указан" && row.product.stock === null))
      );
    });
  }, [group, items, query, stockFilter, subgroup]);
  const selectedTurnover = filteredItems.reduce(
    (sum, item) =>
      sum + item.analysis.economics.real_fbs_price_vat_included * item.entry.sold_qty,
    0,
  );
  const selectedBusinessProfit = filteredItems.reduce(
    (sum, item) => sum + item.analysis.economics.business_net_profit * item.entry.sold_qty,
    0,
  );

  useEffect(() => {
    setExpanded(null);
  }, [group, query, stockFilter, subgroup]);

  return (
    <section className="shortlistPanel">
      <div className="shortlistHeader">
        <div>
          <p className="bandLabel">Рабочий отбор</p>
          <strong>Товары для запуска и теста FBS</strong>
          <span>Список сохраняется в базе. Цена, группы и продажи редактируются здесь.</span>
        </div>
        <div className="shortlistSide">
          <div className="shortlistKpis">
            <Metric label="Позиций" value={String(filteredItems.length)} />
            <Metric label="Факт оборота" value={rub(selectedTurnover)} />
            <Metric label="Факт прибыль" value={rub(selectedBusinessProfit)} />
          </div>
          <div className="shortlistActions">
            <button
              className="sortButton exportLink"
              type="button"
              disabled={busy}
              onClick={onRefreshStocks}
            >
              <RefreshCw size={16} />
              Обновить остатки
            </button>
            <a className="sortButton exportLink" href={shortlistExportUrl()}>
              <Download size={16} />
              Excel отбор
            </a>
            <a className="sortButton exportLink" href={shortlistFileExportUrl()}>
              <Download size={16} />
              Сохранить отбор
            </a>
            <label className="sortButton exportLink">
              <FileSpreadsheet size={16} />
              Загрузить отбор
              <input
                type="file"
                accept=".json,application/json"
                onChange={(event) => onImport(event.target.files?.[0])}
              />
            </label>
          </div>
          {stockRefreshInfo && <span className="stockRefreshInfo">{stockRefreshInfo}</span>}
        </div>
      </div>

      <div className="shortlistFilters">
        <label className="filterField">
          <span>Поиск в отборе</span>
          <div className="search">
            <Search size={17} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Артикул или товар"
            />
          </div>
        </label>
        <label className="filterField">
          <span>Группа</span>
          <select value={group} onChange={(event) => setGroup(event.target.value)}>
            <option>Все</option>
            {groups.map((option) => (
              <option key={option}>{option}</option>
            ))}
          </select>
        </label>
        <label className="filterField">
          <span>Подгруппа</span>
          <select value={subgroup} onChange={(event) => setSubgroup(event.target.value)}>
            <option>Все</option>
            {subgroups.map((option) => (
              <option key={option}>{option}</option>
            ))}
          </select>
        </label>
        <label className="filterField">
          <span>Наличие поставщика</span>
          <select
            value={stockFilter}
            onChange={(event) => setStockFilter(event.target.value as StockFilter)}
          >
            <option>Все</option>
            <option>В наличии</option>
            <option>Нет в наличии</option>
            <option>Не указан</option>
          </select>
        </label>
      </div>

      <div className="shortlistTableWrap">
        <table className="shortlistTable">
          <thead>
            <tr>
              <th>Артикул</th>
              <th>Товар</th>
              <th>Группа</th>
              <th>Подгруппа</th>
              <th>Цена Ozon</th>
              <th>Комплект</th>
              <th>Габариты, см</th>
              <th>Соинвест</th>
              <th>DRR</th>
              <th>План</th>
              <th>Продано</th>
              <th>Закупка</th>
              <th>Остаток</th>
              <th>Прибыль</th>
              <th>Заказы</th>
              <th>Заметка</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {filteredItems.map((item) => {
              const row = item.analysis;
              return (
                <Fragment key={item.entry.supplier_article}>
                  <tr onClick={() => setExpanded(expanded === row.product.id ? null : row.product.id)}>
                    <td>{row.product.supplier_article}</td>
                    <td>
                      <strong>{row.product.title}</strong>
                      <span>{row.product.category ?? "Без категории"}</span>
                      {row.product.package && <span>фасовка {row.product.package}</span>}
                      <span>прайс: {shortlistSourceLabel(item.entry)}</span>
                    </td>
                    <td>
                      <EditableText
                        ariaLabel="Группа отбора"
                        value={item.entry.group_name}
                        onCommit={(value) =>
                          onUpdate({ productId: row.product.id, patch: { group_name: value } })
                        }
                      />
                    </td>
                    <td>
                      <EditableText
                        ariaLabel="Подгруппа отбора"
                        value={item.entry.subgroup_name}
                        onCommit={(value) =>
                          onUpdate({ productId: row.product.id, patch: { subgroup_name: value } })
                        }
                      />
                    </td>
                    <td>
                      <EditableNumber
                        ariaLabel="Цена продажи Ozon"
                        value={item.entry.sale_price_vat_included ?? row.economics.real_fbs_price_vat_included}
                        min={0.01}
                        fractionDigits={0}
                        onCommit={(value) =>
                          onUpdate({
                            productId: row.product.id,
                            patch: { sale_price_vat_included: value },
                          })
                        }
                      />
                      <span>видит {rub(row.economics.buyer_payment_price_vat_included)}</span>
                      {item.entry.offer_quantity > 1 && (
                        <span>{rub(row.economics.buyer_payment_price_vat_included / item.entry.offer_quantity)} за шт.</span>
                      )}
                    </td>
                    <td>
                      <EditableInteger
                        ariaLabel="Штук в комплекте"
                        value={item.entry.offer_quantity}
                        min={1}
                        onCommit={(value) =>
                          onUpdate({ productId: row.product.id, patch: { offer_quantity: value } })
                        }
                      />
                      <span>закуп {rub(row.economics.purchase_price_vat_included)}</span>
                    </td>
                    <td>
                      <div className="dimensionInputs">
                        <EditableNumber
                          ariaLabel="Длина, см"
                          value={item.entry.length_cm ?? row.product.dimensions.length_cm ?? 0}
                          min={0.01}
                          fractionDigits={1}
                          placeholder="Д"
                          onCommit={(value) =>
                            onUpdate({ productId: row.product.id, patch: { length_cm: value } })
                          }
                        />
                        <EditableNumber
                          ariaLabel="Ширина, см"
                          value={item.entry.width_cm ?? row.product.dimensions.width_cm ?? 0}
                          min={0.01}
                          fractionDigits={1}
                          placeholder="Ш"
                          onCommit={(value) =>
                            onUpdate({ productId: row.product.id, patch: { width_cm: value } })
                          }
                        />
                        <EditableNumber
                          ariaLabel="Высота, см"
                          value={item.entry.height_cm ?? row.product.dimensions.height_cm ?? 0}
                          min={0.01}
                          fractionDigits={1}
                          placeholder="В"
                          onCommit={(value) =>
                            onUpdate({ productId: row.product.id, patch: { height_cm: value } })
                          }
                        />
                      </div>
                      <span>литры {row.product.dimensions.volume_liters ?? "н/д"}</span>
                    </td>
                    <td>
                      <EditableNumber
                        ariaLabel="Соинвест Ozon, процент"
                        value={item.entry.seller_bonus_percent ?? row.economics.seller_bonus_percent}
                        min={0}
                        fractionDigits={1}
                        onCommit={(value) =>
                          onUpdate({
                            productId: row.product.id,
                            patch: { seller_bonus_percent: value },
                          })
                        }
                      />
                      <span>{rub(row.economics.ozon_bonus_accrual)}</span>
                    </td>
                    <td>
                      <EditableNumber
                        ariaLabel="DRR, процент"
                        value={item.entry.advertising_drr_percent ?? row.economics.advertising_drr_percent}
                        min={0}
                        fractionDigits={1}
                        onCommit={(value) =>
                          onUpdate({
                            productId: row.product.id,
                            patch: { advertising_drr_percent: value },
                          })
                        }
                      />
                      <span>{rub(row.economics.advertising)}</span>
                    </td>
                    <td>
                      <EditableInteger
                        ariaLabel="План продаж"
                        value={item.entry.planned_sales_qty}
                        onCommit={(value) =>
                          onUpdate({
                            productId: row.product.id,
                            patch: { planned_sales_qty: value },
                          })
                        }
                      />
                    </td>
                    <td>
                      <EditableInteger
                        ariaLabel="Факт продаж"
                        value={item.entry.sold_qty}
                        onCommit={(value) =>
                          onUpdate({ productId: row.product.id, patch: { sold_qty: value } })
                        }
                      />
                    </td>
                    <td>
                      <EditableNumber
                        ariaLabel="Целевая закупочная цена"
                        value={
                          item.entry.purchase_price_vat_included
                          ?? row.economics.purchase_price_vat_included
                        }
                        min={0.01}
                        fractionDigits={0}
                        onCommit={(value) =>
                          onUpdate({
                            productId: row.product.id,
                            patch: { purchase_price_vat_included: value },
                          })
                        }
                      />
                      <span>
                        прайс {rub(
                          item.entry.product_snapshot?.purchase_price_vat_included
                          ?? row.economics.purchase_price_vat_included,
                        )}
                      </span>
                    </td>
                    <td className={stockClass(row.product.stock)}>
                      {stockLabel(row.product.stock)}
                    </td>
                    <td className={row.economics.business_net_profit >= 0 ? "positive" : "negative"}>
                      {rub(row.economics.business_net_profit)}
                      <span>бизнес</span>
                    </td>
                    <td>{ordersLabel(maxCompetitorOrders(row))}</td>
                    <td>
                      <EditableText
                        ariaLabel="Заметка отбора"
                        value={item.entry.note}
                        onCommit={(value) =>
                          onUpdate({ productId: row.product.id, patch: { note: value } })
                        }
                      />
                    </td>
                    <td>
                      <button
                        className="inlineAction danger"
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          onDelete(item);
                        }}
                      >
                        Убрать
                      </button>
                    </td>
                  </tr>
                  {expanded === row.product.id && (
                    <tr className="details">
                      <td colSpan={17}>
                        <EconomicsDetails
                          row={row}
                          offerQuantity={item.entry.offer_quantity}
                          onDrrChange={(value) =>
                            onUpdate({
                              productId: row.product.id,
                              patch: { advertising_drr_percent: value },
                            })
                          }
                          onPackageCostChange={(value) =>
                            onUpdate({
                              productId: row.product.id,
                              patch: { package_cost: value },
                            })
                          }
                          onFulfillmentProcessingChange={(value) =>
                            onUpdate({
                              productId: row.product.id,
                              patch: { fulfillment_processing_cost: value },
                            })
                          }
                          onSmallGoodsPreset={() =>
                            onUpdate({
                              productId: row.product.id,
                              patch: { package_cost: 6, fulfillment_processing_cost: 16 },
                            })
                          }
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            {filteredItems.length === 0 && (
              <tr>
                <td colSpan={17} className="empty">
                  В отборе пока нет товаров. Добавьте позиции из каталога.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function EditableText({
  ariaLabel,
  value,
  onCommit,
}: {
  ariaLabel: string;
  value: string;
  onCommit: Dispatch<string>;
}) {
  return (
    <input
      aria-label={ariaLabel}
      className="editableCell"
      defaultValue={value}
      key={`${ariaLabel}-${value}`}
      onClick={(event) => event.stopPropagation()}
      onBlur={(event) => {
        const next = event.target.value.trim();
        if (next !== value) onCommit(next);
      }}
    />
  );
}

function EditableNumber({
  ariaLabel,
  fractionDigits = 2,
  min = 0.01,
  placeholder,
  value,
  onCommit,
}: {
  ariaLabel: string;
  fractionDigits?: number;
  min?: number;
  placeholder?: string;
  value: number;
  onCommit: Dispatch<number>;
}) {
  return (
    <input
      aria-label={ariaLabel}
      className="editableCell"
      defaultValue={formatEditableNumber(value, fractionDigits)}
      inputMode="decimal"
      key={`${ariaLabel}-${value}`}
      placeholder={placeholder}
      onClick={(event) => event.stopPropagation()}
      onBlur={(event) => {
        const next = parseOptionalNumber(event.target.value);
        if (next !== null && next >= min) {
          const normalized = Math.round(next * 100) / 100;
          if (normalized !== Math.round(value * 100) / 100) {
            onCommit(normalized);
          }
        }
      }}
    />
  );
}

function EditableInteger({
  ariaLabel,
  min = 0,
  value,
  onCommit,
}: {
  ariaLabel: string;
  min?: number;
  value: number;
  onCommit: Dispatch<number>;
}) {
  return (
    <input
      aria-label={ariaLabel}
      className="editableCell"
      defaultValue={String(value)}
      inputMode="numeric"
      key={`${ariaLabel}-${value}`}
      onClick={(event) => event.stopPropagation()}
      onBlur={(event) => {
        const next = Math.max(Math.floor(parseOptionalNumber(event.target.value) ?? min), min);
        if (next !== value) onCommit(next);
      }}
    />
  );
}

function ManualCompetitorForm({
  draft,
  isSaving,
  onChange,
  onSave,
  row,
}: {
  draft: CompetitorDraft;
  isSaving: boolean;
  onChange: Dispatch<Partial<CompetitorDraft>>;
  onSave(): void;
  row: ProductAnalysis;
}) {
  return (
    <div className="manualCompetitor">
      <div>
        <span className="sectionLabel">Ручной конкурент</span>
        <strong>{row.competitor.leader_url ? "Сохраненная карточка влияет на расчет" : "Можно заменить оценку реальной карточкой"}</strong>
      </div>
      <label>
        <span>Цена</span>
        <input
          inputMode="decimal"
          placeholder="239"
          value={draft.price}
          onChange={(event) => onChange({ price: event.target.value })}
        />
      </label>
      <label className="wide">
        <span>Ссылка Ozon</span>
        <input
          placeholder="https://www.ozon.ru/product/..."
          value={draft.url}
          onChange={(event) => onChange({ url: event.target.value })}
        />
      </label>
      <label>
        <span>Тип</span>
        <select value={draft.matchType} onChange={(event) => onChange({ matchType: event.target.value as MatchType })}>
          <option value="analog">Аналог</option>
          <option value="exact">Точный</option>
          <option value="reference">Ориентир</option>
        </select>
      </label>
      <label className="wide">
        <span>Название конкурента</span>
        <input
          placeholder="Можно оставить пустым"
          value={draft.title}
          onChange={(event) => onChange({ title: event.target.value })}
        />
      </label>
      <button className="saveButton" type="button" disabled={isSaving} onClick={onSave}>
        {isSaving ? "Сохраняю" : "Сохранить"}
      </button>
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <article className={`kpi ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SortableTh({
  active,
  children,
  direction,
  onClick,
  title,
}: {
  active: boolean;
  children: string;
  direction: SortDirection;
  onClick: () => void;
  title: string;
}) {
  return (
    <th title={title}>
      <button className={`thButton ${active ? "active" : ""}`} type="button" onClick={onClick}>
        {children}
        <ArrowDownUp size={13} />
        {active && <span>{direction === "desc" ? "↓" : "↑"}</span>}
      </button>
    </th>
  );
}

function compareRows(left: ProductAnalysis, right: ProductAnalysis, key: SortKey): number {
  if (key === "article") return compareText(left.product.supplier_article, right.product.supplier_article);
  if (key === "title") return compareText(left.product.title, right.product.title);
  if (key === "category") return compareText(left.product.category ?? "", right.product.category ?? "");
  if (key === "purchase") {
    return left.economics.purchase_price_vat_included - right.economics.purchase_price_vat_included;
  }
  if (key === "stock") return (left.product.stock ?? -1) - (right.product.stock ?? -1);
  if (key === "listPrice") {
    return left.economics.real_fbs_price_vat_included - right.economics.real_fbs_price_vat_included;
  }
  if (key === "competitor") {
    return (
      (left.economics.estimated_competitor_price_vat_included ?? 0) -
      (right.economics.estimated_competitor_price_vat_included ?? 0)
    );
  }
  if (key === "orders") {
    return (maxCompetitorOrders(left) ?? 0) - (maxCompetitorOrders(right) ?? 0);
  }
  if (key === "margin") return left.economics.margin_percent - right.economics.margin_percent;
  if (key === "recommended") {
    return (
      left.economics.recommended_price_vat_included -
      right.economics.recommended_price_vat_included
    );
  }
  return left.economics.net_profit - right.economics.net_profit;
}

function compareText(left: string, right: string): number {
  return left.localeCompare(right, "ru");
}

function productGroup(row: ProductAnalysis): string {
  const text = `${row.product.category ?? ""} ${row.product.title}`.toLowerCase();
  const groups: Array<[string, string[]]> = [
    ["Гвозди", ["гвозд"]],
    ["Саморезы", ["саморез", "шуруп"]],
    ["Дюбели", ["дюбел"]],
    ["Крепеж", ["крепеж", "анкера", "анкер", "болт", "гайк", "шайб"]],
    ["Клей", ["клей", "герметик", "пена"]],
    ["Цемент и смеси", ["цемент", "смесь", "штукатур", "шпатлев", "стяжк"]],
    ["Электрика", ["кабель", "провод", "розетк", "выключател", "электр"]],
    ["Свет", ["ламп", "свет", "люстр", "бра", "фонар"]],
    ["Инструмент", ["инструмент", "сверл", "диск", "насадк"]],
  ];
  const matched = groups.find(([, tokens]) => tokens.some((token) => text.includes(token)));
  return matched?.[0] ?? row.product.category ?? "Без группы";
}

function competitorPlanGroups(rows: ProductAnalysis[]): Array<{ search: string; count: number }> {
  const counts = rows.reduce<Record<string, number>>((acc, row) => {
    const search = groupSearchTerm(productGroup(row));
    acc[search] = (acc[search] ?? 0) + 1;
    return acc;
  }, {});
  return Object.entries(counts)
    .map(([search, count]) => ({ search, count }))
    .sort((left, right) => right.count - left.count)
    .slice(0, 12);
}

function groupSearchTerm(group: string): string {
  const map: Record<string, string> = {
    "Гвозди": "гвозди",
    "Саморезы": "саморезы",
    "Дюбели": "дюбели",
    "Крепеж": "крепеж",
    "Клей": "клей строительный",
    "Цемент и смеси": "сухие строительные смеси",
    "Электрика": "электрика",
    "Свет": "светильник",
    "Инструмент": "строительный инструмент",
  };
  return map[group] ?? group.toLowerCase();
}

function ozonSearchUrl(row: ProductAnalysis): string {
  const query = [row.product.title, row.product.category ?? "", row.product.brand ?? ""]
    .filter(Boolean)
    .join(" ");
  return `https://www.ozon.ru/search/?text=${encodeURIComponent(query)}`;
}

function rub(value: number): string {
  if (!Number.isFinite(value)) return "н/д";
  return new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 }).format(value);
}

function stockLabel(value: number | null): string {
  if (value === null) return "не указан";
  return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 3 }).format(value)} шт.`;
}

function stockClass(value: number | null): string {
  if (value === null) return "";
  return value > 0 ? "positive" : "negative";
}

function formatEditableNumber(value: number, fractionDigits: number): string {
  if (!Number.isFinite(value) || value <= 0) return "";
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: fractionDigits,
    minimumFractionDigits: 0,
    useGrouping: false,
  }).format(value);
}

function shortlistSourceLabel(entry: ShortlistItem["entry"]): string {
  if (!entry.source_import_filename) return "не указан";
  const date = entry.source_imported_at
    ? new Date(entry.source_imported_at).toLocaleDateString("ru-RU")
    : null;
  return date ? `${entry.source_import_filename}, ${date}` : entry.source_import_filename;
}

function upsertShortlistItem(items: ShortlistItem[], item: ShortlistItem): ShortlistItem[] {
  const existingIndex = items.findIndex(
    (current) => current.entry.supplier_article === item.entry.supplier_article,
  );
  if (existingIndex === -1) return [item, ...items];
  return items.map((current, index) => (index === existingIndex ? item : current));
}

function maxCompetitorOrders(row: ProductAnalysis): number | null {
  const orders = row.competitor.offers
    .map((offer) => offer.orders_count)
    .filter((value): value is number => value !== null && Number.isFinite(value));
  if (orders.length === 0) return null;
  return Math.max(...orders);
}

function ordersLabel(value: number | null): string {
  if (value === null) return "н/д";
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(value);
}

function orderSuffix(value: number): string {
  const normalized = Math.abs(value) % 100;
  const lastDigit = normalized % 10;
  if (normalized > 10 && normalized < 20) return "ов";
  if (lastDigit === 1) return "";
  if (lastDigit >= 2 && lastDigit <= 4) return "а";
  return "ов";
}

function parseOptionalNumber(value: string): number | null {
  const normalized = value.replace(/\s/g, "").replace(",", ".");
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function importVersionKey(version: PriceImportVersion): string {
  return `${version.filename}::${version.imported_at}`;
}

function productImportKey(product: ProductAnalysis["product"]): string {
  return `${product.source_import_filename ?? ""}::${product.source_imported_at ?? ""}`;
}

function kpiFromRows(rows: ProductAnalysis[]): DashboardKpi {
  const profitable = rows.filter((row) => row.economics.net_profit > 0);
  const highRisk = rows.filter(
    (row) =>
      row.readiness.status === "Стоп" ||
      row.economics.recommendation === "Только при повышении цены" ||
      row.economics.recommendation === "Не заводить",
  );
  const competitorBelowBreakEven = rows.filter(
    (row) =>
      row.economics.estimated_competitor_price_vat_included !== null &&
      row.economics.estimated_competitor_price_vat_included < row.economics.break_even_price_vat_included,
  );
  const averageMargin =
    rows.length === 0
      ? 0
      : rows.reduce((sum, row) => sum + row.economics.margin_percent, 0) / rows.length;

  return {
    total_products: rows.length,
    profitable_products: profitable.length,
    unprofitable_products: rows.length - profitable.length,
    average_margin_percent: Math.round(averageMargin * 100) / 100,
    potential_profit: Math.round(rows.reduce((sum, row) => sum + row.economics.net_profit, 0) * 100) / 100,
    high_risk_products: highRisk.length,
    competitor_below_break_even: competitorBelowBreakEven.length,
  };
}

function taxRegimeLabel(value: string): string {
  if (value === "ip_usn_6") return "ИП УСН 6%";
  if (value === "osno") return "ОСНО";
  return value;
}

function competitorSourceLabel(value: string): string {
  if (value === "manual") return "ручной";
  if (value === "missing") return "оценка";
  if (value === "api") return "API";
  if (value === "excel") return "Excel";
  return value;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(value));
}

function issueLabel(severity: "warning" | "error", rowNumber: number | null): string {
  const prefix = severity === "error" ? "Ошибка" : "Предупреждение";
  return rowNumber ? `${prefix} · строка ${rowNumber}` : prefix;
}

function pillClass(status: Recommendation): string {
  if (status === "Заводить") return "ok";
  if (status === "Заводить осторожно" || status === "Нужна ручная проверка") return "caution";
  return "stop";
}

function readinessPillClass(status: ProductAnalysis["readiness"]["status"]): string {
  if (status === "Готов к запуску") return "ok";
  if (status === "Нужны данные") return "caution";
  return "stop";
}

function catalogProductKey(item: { supplier_name: string; supplier_article: string }): string {
  return `${item.supplier_name.trim().toLocaleLowerCase("ru-RU")}::${item.supplier_article
    .trim()
    .toLocaleLowerCase("ru-RU")}`;
}

function LoginGate() {
  const [authed, setAuthed] = useState(() => Boolean(getStoredAuthToken()));
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setChecking(true);
    setError(null);
    const token = btoa(`${username}:${password}`);
    try {
      const response = await fetch(`${API_URL}/health`, {
        headers: { Authorization: `Basic ${token}` },
      });
      if (!response.ok) {
        setError("Неверный логин или пароль.");
        return;
      }
      storeAuthToken(token);
      setAuthed(true);
    } catch {
      setError("Не удалось связаться с сервером. Попробуйте ещё раз.");
    } finally {
      setChecking(false);
    }
  }

  if (authed) {
    return <App />;
  }

  return (
    <div className="loginGate">
      <form className="loginCard" onSubmit={(e) => void handleSubmit(e)}>
        <img className="brandMark" src="/logo.svg" alt="Лето СМ" />
        <p className="eyebrow">Закрытая платформа</p>
        <h2>Вход</h2>
        {error && <div className="alert">{error}</div>}
        <label>
          <span>Логин</span>
          <input
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </label>
        <label>
          <span>Пароль</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <button className="uploadButton" type="submit" disabled={checking}>
          {checking ? "Проверяю…" : "Войти"}
        </button>
      </form>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<LoginGate />);
