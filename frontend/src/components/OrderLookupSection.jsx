import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Clock,
  FileDown,
  LoaderCircle,
  RefreshCw,
  Search,
  Truck,
} from "lucide-react";
import "./orderLookupSection.css";

const TODAY_REFRESH_INTERVAL_MS = 5 * 60 * 1000;

const formatMoney = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return `${Number(value).toLocaleString("ru-RU", {
    maximumFractionDigits: 0,
  })} ₽`;
};

const formatPercent = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return `${Number(value).toLocaleString("ru-RU", {
    maximumFractionDigits: 1,
  })}%`;
};

const formatTime = (isoValue) => {
  if (!isoValue) return "—";
  const date = new Date(isoValue);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Europe/Moscow",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
};

function DeliveryTransferredCell({ order }) {
  const total = order.delivery_total_transferred;
  if (total === null || total === undefined) return <span>—</span>;
  return (
    <span className="ols-delivery-sum">
      <span className="ols-tooltip" data-tooltip="Перевод за доставку от покупателя (данные Ozon)">
        {formatMoney(order.delivery_price_transferred)}
      </span>
      <span className="ols-delivery-sum-op">+</span>
      <span className="ols-tooltip" data-tooltip="Оплата за подъём/лифт (данные Ozon)">
        {formatMoney(order.lift_price || 0)}
      </span>
      <span className="ols-delivery-sum-op">+</span>
      <span className="ols-tooltip" data-tooltip="Компенсация логистики (юнитка)">
        {formatMoney(order.logistics_compensation_total || 0)}
      </span>
      <span className="ols-delivery-sum-op">=</span>
      <span className="ols-delivery-sum-total">{formatMoney(total)}</span>
    </span>
  );
}

function DeliveryResultCell({ order }) {
  const result = order.delivery_result;
  if (result === null || result === undefined) return <span>—</span>;
  return (
    <span className={result < 0 ? "ols-delivery-result-negative" : "ols-delivery-result-positive"}>
      {result < 0 ? "" : "+"}
      {formatMoney(result)}
    </span>
  );
}

function NetProfitAndDeliveryCell({ order }) {
  if (
    order.is_cancelled ||
    order.net_profit_total === null ||
    order.net_profit_total === undefined
  ) {
    return <span>—</span>;
  }
  // Same convention as the "Доставка итог за заказ" column: add the
  // delivery result if it's positive, subtract if it's negative - orders
  // without a "факт" yet just fall back to plain net profit (0 added).
  const combined = order.net_profit_total + (order.delivery_result || 0);
  const sign = combined < 0 ? "ols-delivery-result-negative" : "ols-delivery-result-positive";
  return (
    <span className={`ols-net-profit-and-delivery ${sign}`}>{formatMoney(combined)}</span>
  );
}

const getMoscowTodayIso = () => {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Moscow",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(
    parts.filter((part) => part.type !== "literal").map((part) => [part.type, part.value])
  );
  return `${values.year}-${values.month}-${values.day}`;
};

const formatDateLabel = (isoValue) => {
  const date = new Date(`${isoValue}T00:00:00`);
  if (Number.isNaN(date.getTime())) return isoValue;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(date);
};

const readApiError = async (response) => {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // ignore, fall through to generic message
  }
  return `Ошибка API: ${response.status}`;
};

export default function OrderLookupSection({ apiBase }) {
  const [postingNumber, setPostingNumber] = useState("");
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [deliveryActualInput, setDeliveryActualInput] = useState("");
  const [savingDeliveryActual, setSavingDeliveryActual] = useState(false);
  const [deliveryActualError, setDeliveryActualError] = useState("");
  const [syncedDeliveryActualKey, setSyncedDeliveryActualKey] = useState(null);
  const [calculatingDeliveryCost, setCalculatingDeliveryCost] = useState(false);
  const [calculateDeliveryNote, setCalculateDeliveryNote] = useState("");

  const [todayOrders, setTodayOrders] = useState([]);
  const [todayLoading, setTodayLoading] = useState(true);
  const [todayError, setTodayError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNote, setRefreshNote] = useState("");
  const [refreshingAdSpend, setRefreshingAdSpend] = useState(false);
  const [adSpendRefreshNote, setAdSpendRefreshNote] = useState("");
  const [summary, setSummary] = useState(null);

  const todayIso = getMoscowTodayIso();
  const [selectedDate, setSelectedDate] = useState(todayIso);
  const isToday = selectedDate === todayIso;
  const [dateOrders, setDateOrders] = useState([]);
  const [dateLoading, setDateLoading] = useState(false);
  const [dateError, setDateError] = useState("");

  // Flip the loading flag the instant the picked date changes (render-time
  // state adjustment, not inside the effect below) so the UI shows
  // "Загружаю…" immediately instead of stale/empty content for a beat.
  const [loadingSinceDate, setLoadingSinceDate] = useState(null);
  if (!isToday && selectedDate !== loadingSinceDate) {
    setLoadingSinceDate(selectedDate);
    setDateLoading(true);
  }

  useEffect(() => {
    if (selectedDate === todayIso) return;
    const controller = new AbortController();
    const fetchOrdersForDate = async () => {
      try {
        const response = await fetch(
          `${apiBase}/api/ozon/orders/by-date?date=${encodeURIComponent(selectedDate)}`,
          { signal: controller.signal }
        );
        if (!response.ok) throw new Error(await readApiError(response));
        setDateOrders((await response.json()) || []);
        setDateError("");
      } catch (requestError) {
        if (requestError.name !== "AbortError") {
          setDateError(requestError.message || "Не удалось загрузить заказы за эту дату");
        }
      } finally {
        setDateLoading(false);
      }
    };
    fetchOrdersForDate();
    return () => controller.abort();
  }, [apiBase, selectedDate, todayIso]);

  const [calculatingBatchDelivery, setCalculatingBatchDelivery] = useState(false);
  const [batchDeliveryNote, setBatchDeliveryNote] = useState("");
  const [batchDeliveryError, setBatchDeliveryError] = useState("");

  const calculateAllActualDelivery = async () => {
    setCalculatingBatchDelivery(true);
    setBatchDeliveryError("");
    setBatchDeliveryNote("");
    try {
      const response = await fetch(
        `${apiBase}/api/ozon/orders/by-date/calculate-actual-delivery?date=${encodeURIComponent(selectedDate)}`,
        { method: "POST" }
      );
      if (!response.ok) throw new Error(await readApiError(response));
      const payload = await response.json();
      if (isToday) setTodayOrders(payload.orders || []);
      else setDateOrders(payload.orders || []);
      const failedCount = payload.failed_count || 0;
      setBatchDeliveryNote(
        `Готово: посчитано ${payload.calculated_count}, пропущено ${payload.skipped_count}` +
          (failedCount > 0
            ? `, не удалось у ${failedCount} — впишите вручную (в карточке заказа видно, какой город/регион распознался, если нужно сверить с dellin.ru)`
            : "")
      );
    } catch (requestError) {
      setBatchDeliveryError(
        requestError.message || "Не удалось посчитать фактическую доставку"
      );
    } finally {
      setCalculatingBatchDelivery(false);
    }
  };

  const refreshDateOrders = async () => {
    setDateLoading(true);
    setDateError("");
    try {
      // POST .../refresh, not the plain GET - the GET serves whatever was
      // cached the first time this date was viewed, so it can't ever pick
      // up a юнитка version uploaded/corrected afterwards. This always
      // recomputes from scratch and overwrites that cache.
      const response = await fetch(
        `${apiBase}/api/ozon/orders/by-date/refresh?date=${encodeURIComponent(selectedDate)}`,
        { method: "POST" }
      );
      if (!response.ok) throw new Error(await readApiError(response));
      setDateOrders((await response.json()) || []);
    } catch (requestError) {
      setDateError(requestError.message || "Не удалось обновить заказы за эту дату");
    } finally {
      setDateLoading(false);
    }
  };

  const displayedOrders = isToday ? todayOrders : dateOrders;
  const displayedLoading = isToday ? todayLoading : dateLoading;
  const displayedError = isToday ? todayError : dateError;

  const [dateAdSpend, setDateAdSpend] = useState(null);
  const [dateAdSpendWarning, setDateAdSpendWarning] = useState("");

  useEffect(() => {
    if (selectedDate === todayIso) return;
    const controller = new AbortController();
    const loadAdSpend = async () => {
      try {
        const response = await fetch(
          `${apiBase}/api/ozon/ad-spend?date=${encodeURIComponent(selectedDate)}`,
          { signal: controller.signal }
        );
        if (!response.ok) throw new Error(await readApiError(response));
        const payload = await response.json();
        setDateAdSpend(
          payload.ad_spend_without_vat === null || payload.ad_spend_without_vat === undefined
            ? null
            : payload.ad_spend_without_vat
        );
        setDateAdSpendWarning(payload.warning || "");
      } catch (requestError) {
        if (requestError.name !== "AbortError") {
          setDateAdSpend(null);
          setDateAdSpendWarning(requestError.message || "Не удалось получить расход на рекламу");
        }
      }
    };
    loadAdSpend();
    return () => controller.abort();
  }, [apiBase, selectedDate, todayIso]);

  // "Реестр прибыли"/"сегодня" already subtract ad spend from net profit -
  // this mirrors the same logic for an arbitrary selected date, using the
  // dedicated /ad-spend endpoint instead of guessing it from the orders list
  // (ad spend is an account-level daily total, not something attributable
  // per order).
  const dateSummary = useMemo(() => {
    if (isToday) return null;
    const active = displayedOrders.filter((item) => !item.is_cancelled);
    const revenueTotal = active.reduce(
      (sum, item) => sum + (item.revenue_without_vat_total || 0),
      0
    );
    const matched = active.filter(
      (item) => item.net_profit_total !== null && item.net_profit_total !== undefined
    );
    const profitBeforeAdsTotal = matched.reduce(
      (sum, item) => sum + item.net_profit_total,
      0
    );
    const netProfitTotal =
      dateAdSpend === null ? null : profitBeforeAdsTotal - dateAdSpend;
    const deliveryResultSum = matched.reduce(
      (sum, item) => sum + (item.delivery_result || 0),
      0
    );
    const netProfitAndDeliveryTotal =
      netProfitTotal === null ? null : netProfitTotal + deliveryResultSum;
    return {
      revenueTotal,
      profitBeforeAdsTotal,
      adSpend: dateAdSpend,
      netProfitTotal,
      netProfitAndDeliveryTotal,
      hasUnmatched: matched.length < active.length,
    };
  }, [isToday, displayedOrders, dateAdSpend]);

  const loadSummary = async (signal) => {
    try {
      const response = await fetch(`${apiBase}/api/ozon/orders/today/summary`, { signal });
      if (!response.ok) throw new Error(await readApiError(response));
      setSummary(await response.json());
    } catch (requestError) {
      if (requestError.name !== "AbortError") {
        // summary is a secondary tile row - don't clobber the main list error
      }
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    const loadToday = async () => {
      try {
        const response = await fetch(`${apiBase}/api/ozon/orders/today`, {
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(await readApiError(response));
        const payload = await response.json();
        setTodayOrders(payload || []);
        setTodayError("");
      } catch (requestError) {
        if (requestError.name !== "AbortError") {
          setTodayError(requestError.message || "Не удалось загрузить заказы за сегодня");
        }
      } finally {
        setTodayLoading(false);
      }
    };
    const loadInitialSummary = async () => {
      try {
        const response = await fetch(`${apiBase}/api/ozon/orders/today/summary`, {
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(await readApiError(response));
        setSummary(await response.json());
      } catch {
        // summary is a secondary tile row - a failed load just leaves it hidden
      }
    };
    loadToday();
    loadInitialSummary();
    const intervalId = window.setInterval(() => {
      loadToday();
      loadSummary();
    }, TODAY_REFRESH_INTERVAL_MS);
    return () => {
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, [apiBase]);

  const refreshTodayNow = async () => {
    setRefreshing(true);
    setTodayError("");
    setRefreshNote("");
    try {
      const response = await fetch(`${apiBase}/api/ozon/orders/today/refresh`, {
        method: "POST",
      });
      if (!response.ok) throw new Error(await readApiError(response));
      const payload = await response.json();
      setTodayOrders(payload || []);
      await loadSummary();
      setRefreshNote(
        "Заказы обновлены. Реклама пересчитывается в фоне у Ozon и обновится " +
          "сама в плашках через несколько минут."
      );
      window.setTimeout(() => setRefreshNote(""), 4 * 60 * 1000);
    } catch (requestError) {
      setTodayError(requestError.message || "Не удалось обновить заказы за сегодня");
    } finally {
      setRefreshing(false);
    }
  };

  const refreshAdSpendNow = async () => {
    setRefreshingAdSpend(true);
    setAdSpendRefreshNote(
      "Считаю рекламу за сегодня — может занять несколько минут, не закрывайте страницу…"
    );
    const before = summary?.ad_spend_without_vat ?? null;
    const beforeComputedAt = summary?.computed_at ?? null;
    try {
      const response = await fetch(`${apiBase}/api/ozon/orders/today/refresh-ad-spend`, {
        method: "POST",
      });
      if (!response.ok) throw new Error(await readApiError(response));

      // Fire-and-forget on the backend - poll the summary until the number
      // actually changes (or we give up), instead of guessing a fixed delay.
      const maxAttempts = 20;
      for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 15000));
        const summaryResponse = await fetch(`${apiBase}/api/ozon/orders/today/summary`);
        if (!summaryResponse.ok) continue;
        const fresh = await summaryResponse.json();
        const changed =
          fresh.computed_at !== beforeComputedAt || fresh.ad_spend_without_vat !== before;
        if (changed) {
          setSummary(fresh);
          setAdSpendRefreshNote("Готово - реклама за сегодня обновлена.");
          window.setTimeout(() => setAdSpendRefreshNote(""), 4 * 60 * 1000);
          return;
        }
      }
      setAdSpendRefreshNote(
        "Ozon пока не отдал новые данные - посчитается фоном в течение часа."
      );
      window.setTimeout(() => setAdSpendRefreshNote(""), 4 * 60 * 1000);
    } catch (requestError) {
      setAdSpendRefreshNote(requestError.message || "Не удалось запустить пересчёт рекламы");
    } finally {
      setRefreshingAdSpend(false);
    }
  };

  const showOrderFromList = (clickedOrder) => {
    setOrder(clickedOrder);
    setPostingNumber(clickedOrder.posting_number);
    setError("");
  };

  // After saving a manual "факт доставки" from the detail card, patch the
  // matching row in whichever list (today/selected date) has it - so the
  // table below reflects the new number immediately, without a full
  // "Обновить сейчас" re-fetch of every order.
  const updateOrderInLists = (updatedOrder) => {
    setTodayOrders((prev) =>
      prev.map((item) =>
        item.posting_number === updatedOrder.posting_number ? updatedOrder : item
      )
    );
    setDateOrders((prev) =>
      prev.map((item) =>
        item.posting_number === updatedOrder.posting_number ? updatedOrder : item
      )
    );
  };

  const lookupOrder = async () => {
    const trimmed = postingNumber.trim();
    if (!trimmed) return;
    setLoading(true);
    setError("");
    setOrder(null);
    try {
      const response = await fetch(
        `${apiBase}/api/ozon/orders/${encodeURIComponent(trimmed)}`
      );
      if (!response.ok) throw new Error(await readApiError(response));
      const payload = await response.json();
      setOrder(payload);
    } catch (requestError) {
      setError(requestError.message || "Не удалось найти заказ");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter") lookupOrder();
  };

  const deliveryActualSyncKey = order
    ? `${order.posting_number}:${order.delivery_cost_actual}`
    : null;
  if (deliveryActualSyncKey !== syncedDeliveryActualKey) {
    setSyncedDeliveryActualKey(deliveryActualSyncKey);
    setDeliveryActualInput(
      order?.delivery_cost_actual !== null && order?.delivery_cost_actual !== undefined
        ? String(order.delivery_cost_actual)
        : ""
    );
    setDeliveryActualError("");
    setCalculateDeliveryNote("");
  }

  const saveDeliveryActualCost = async () => {
    if (!order) return;
    const parsed = Number(deliveryActualInput);
    if (deliveryActualInput.trim() === "" || Number.isNaN(parsed)) {
      setDeliveryActualError("Введите число");
      return;
    }
    setSavingDeliveryActual(true);
    setDeliveryActualError("");
    try {
      const response = await fetch(
        `${apiBase}/api/ozon/orders/${encodeURIComponent(order.posting_number)}/delivery-actual-cost`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ actual_cost: parsed }),
        }
      );
      if (!response.ok) throw new Error(await readApiError(response));
      const updated = await response.json();
      setOrder(updated);
      updateOrderInLists(updated);
    } catch (requestError) {
      setDeliveryActualError(requestError.message || "Не удалось сохранить");
    } finally {
      setSavingDeliveryActual(false);
    }
  };

  const calculateDeliveryCostFromDelovyeLinii = async () => {
    if (!order) return;
    if (!order.delivery_address) {
      setDeliveryActualError("В заказе нет адреса доставки - посчитать не получится");
      return;
    }
    setCalculatingDeliveryCost(true);
    setDeliveryActualError("");
    setCalculateDeliveryNote("");
    try {
      const requestItems = order.items.map((item) => ({
        offer_id: item.offer_id,
        quantity: item.quantity,
      }));
      const response = await fetch(`${apiBase}/api/ozon/logistics/address-quote`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin_city: "Вологда",
          address: order.delivery_address,
          items: requestItems,
          include_loading: Boolean(order.lift_option_code) && order.lift_option_code !== "none",
          loading_floor: order.lift_floor ? Math.max(1, Math.min(99, Number(order.lift_floor) || 2)) : 2,
          loading_lift: order.lift_option_code === "lift",
          effective_date: order.in_process_at ? order.in_process_at.slice(0, 10) : null,
        }),
      });
      if (!response.ok) throw new Error(await readApiError(response));
      const payload = await response.json();
      const cost = payload.best_quote?.cost_rub;
      if (cost === null || cost === undefined) {
        throw new Error(
          (payload.warnings || []).join(" ") ||
            "Деловые Линии не смогли посчитать по этому адресу - проверьте адрес на их сайте (dellin.ru) и впишите сумму вручную"
        );
      }
      setDeliveryActualInput(String(Math.round(cost)));
      setCalculateDeliveryNote(
        `Посчитано через Деловые Линии: ${Math.round(cost).toLocaleString("ru-RU")} ₽ - проверьте и нажмите «Сохранить»`
      );
    } catch (requestError) {
      setDeliveryActualError(requestError.message || "Не удалось рассчитать доставку");
    } finally {
      setCalculatingDeliveryCost(false);
    }
  };

  return (
    <section className="order-lookup-section">
      <div className="ols-today-card">
        <div className="ols-today-header">
          <div>
            <h3>Заказы за {isToday ? "сегодня" : formatDateLabel(selectedDate)}</h3>
            <p>
              {isToday
                ? refreshing
                  ? "Пересчитываю заказы — обычно пару секунд"
                  : "Обновляется автоматически каждые 30 минут"
                : dateLoading
                ? "Загружаю…"
                : "Данные за выбранный день - можно открыть заказ и вписать факт доставки"}
            </p>
          </div>
          <div className="ols-today-header-controls">
            <label className="ols-date-picker">
              <span>Дата</span>
              <input
                type="date"
                value={selectedDate}
                max={todayIso}
                onChange={(event) => setSelectedDate(event.target.value)}
              />
            </label>
            {!isToday && (
              <button
                type="button"
                className="ols-refresh-button"
                onClick={() => setSelectedDate(todayIso)}
              >
                Сегодня
              </button>
            )}
            <button
              type="button"
              className="ols-refresh-button"
              onClick={isToday ? refreshTodayNow : refreshDateOrders}
              disabled={isToday ? refreshing : dateLoading}
            >
              {(isToday ? refreshing : dateLoading) ? (
                <LoaderCircle className="ols-spin" aria-hidden="true" size={16} />
              ) : (
                <RefreshCw aria-hidden="true" size={16} />
              )}
              {(isToday ? refreshing : dateLoading) ? "Считаю…" : "Обновить сейчас"}
            </button>
            <button
              type="button"
              className="ols-refresh-button"
              onClick={calculateAllActualDelivery}
              disabled={calculatingBatchDelivery}
              title="Посчитать фактическую стоимость доставки через Деловые Линии сразу у всех заказов дня, у которых она ещё не заполнена"
            >
              {calculatingBatchDelivery ? (
                <LoaderCircle className="ols-spin" aria-hidden="true" size={16} />
              ) : (
                <Truck aria-hidden="true" size={16} />
              )}
              {calculatingBatchDelivery ? "Считаю факт…" : "Посчитать факт у всех"}
            </button>
            <a
              className="ols-refresh-button"
              href={`${apiBase}/api/ozon/orders/by-date/export.xlsx?date=${encodeURIComponent(
                selectedDate
              )}`}
              download
              title="Скачать заказы за этот день в Excel - с адресом, подъёмом и разбивкой по доставке"
            >
              <FileDown aria-hidden="true" size={16} />
              Скачать в Excel
            </a>
          </div>
        </div>

        {refreshNote && <div className="ols-refresh-note">{refreshNote}</div>}
        {adSpendRefreshNote && (
          <div className="ols-refresh-note">{adSpendRefreshNote}</div>
        )}
        {batchDeliveryNote && <div className="ols-refresh-note">{batchDeliveryNote}</div>}
        {batchDeliveryError && (
          <div className="ols-refresh-note ols-refresh-note--error">{batchDeliveryError}</div>
        )}

        {isToday && summary && (
          <div className="ols-tiles">
            <div className="ols-tile">
              <span className="ols-tile-label">Выручка без НДС</span>
              <span className="ols-tile-value">
                {formatMoney(summary.revenue_without_vat_total)}
              </span>
            </div>
            <div className="ols-tile">
              <span className="ols-tile-label">Прибыль до рекламы</span>
              <span className="ols-tile-value">
                {formatMoney(summary.net_profit_before_ads_total)}
              </span>
            </div>
            <div className="ols-tile">
              <span className="ols-tile-label ols-tile-label-row">
                Реклама за сегодня
                <button
                  type="button"
                  className="ols-ad-spend-refresh"
                  onClick={refreshAdSpendNow}
                  disabled={refreshingAdSpend}
                  title="Пересчитать расход на рекламу за сегодня прямо сейчас (может занять несколько минут)"
                >
                  {refreshingAdSpend ? (
                    <LoaderCircle className="ols-spin" aria-hidden="true" size={11} />
                  ) : (
                    <RefreshCw aria-hidden="true" size={11} />
                  )}
                </button>
              </span>
              <span className="ols-tile-value">
                {formatMoney(summary.ad_spend_without_vat)}
              </span>
            </div>
            <div className="ols-tile">
              <span className="ols-tile-label">Чистая прибыль</span>
              <span className="ols-tile-value">
                {formatMoney(summary.net_profit_total)}
                {summary.warning && (
                  <span className="ols-tooltip" data-tooltip={summary.warning}>
                    <AlertTriangle
                      aria-hidden="true"
                      size={14}
                      className="ols-row-warning-icon"
                    />
                  </span>
                )}
              </span>
            </div>
            <div className="ols-tile ols-tile--accent">
              <span className="ols-tile-label">Чистая прибыль и доставка</span>
              <span className="ols-tile-value">
                {formatMoney(summary.net_profit_and_delivery_total)}
              </span>
            </div>
          </div>
        )}

        {!isToday && dateSummary && (
          <div className="ols-tiles">
            <div className="ols-tile">
              <span className="ols-tile-label">Выручка без НДС</span>
              <span className="ols-tile-value">{formatMoney(dateSummary.revenueTotal)}</span>
            </div>
            <div className="ols-tile">
              <span className="ols-tile-label">Прибыль до рекламы</span>
              <span className="ols-tile-value">
                {formatMoney(dateSummary.profitBeforeAdsTotal)}
                {dateSummary.hasUnmatched && (
                  <span
                    className="ols-tooltip"
                    data-tooltip="У части заказов есть товары, не найденные в юнит-экономике - они не учтены в сумме"
                  >
                    <AlertTriangle
                      aria-hidden="true"
                      size={14}
                      className="ols-row-warning-icon"
                    />
                  </span>
                )}
              </span>
            </div>
            <div className="ols-tile">
              <span className="ols-tile-label">Реклама за день</span>
              <span className="ols-tile-value">
                {formatMoney(dateSummary.adSpend)}
                {dateAdSpendWarning && (
                  <span className="ols-tooltip" data-tooltip={dateAdSpendWarning}>
                    <AlertTriangle
                      aria-hidden="true"
                      size={14}
                      className="ols-row-warning-icon"
                    />
                  </span>
                )}
              </span>
            </div>
            <div className="ols-tile">
              <span className="ols-tile-label">Чистая прибыль</span>
              <span className="ols-tile-value">{formatMoney(dateSummary.netProfitTotal)}</span>
            </div>
            <div className="ols-tile ols-tile--accent">
              <span className="ols-tile-label">Чистая прибыль и доставка</span>
              <span className="ols-tile-value">
                {formatMoney(dateSummary.netProfitAndDeliveryTotal)}
              </span>
            </div>
          </div>
        )}

        {displayedError && (
          <div className="ols-warning">
            <AlertTriangle aria-hidden="true" size={15} />
            {displayedError}
          </div>
        )}

        {displayedLoading ? (
          <div className="ols-today-empty">Загружаю заказы…</div>
        ) : displayedOrders.length === 0 ? (
          <div className="ols-today-empty">
            {isToday
              ? "За сегодня заказов пока нет — список обновится сам, когда появятся новые"
              : "За этот день заказов нет"}
          </div>
        ) : (
          <div className="ols-table-wrap">
            <table className="ols-table ols-today-table">
              <thead>
                <tr>
                  <th>Время</th>
                  <th>Заказ</th>
                  <th>Статус</th>
                  <th>Выручка без НДС</th>
                  <th>Чистая прибыль</th>
                  <th>Перевели за доставку</th>
                  <th>Доставка факт</th>
                  <th>Доставка итог за заказ</th>
                  <th>Чистая прибыль и доставка</th>
                </tr>
              </thead>
              <tbody>
                {displayedOrders.map((item) => (
                  <tr
                    key={item.posting_number}
                    className="ols-today-row"
                    onClick={() => showOrderFromList(item)}
                  >
                    <td className="ols-today-time">
                      <Clock aria-hidden="true" size={13} />
                      {formatTime(item.in_process_at)}
                    </td>
                    <td>{item.order_number}</td>
                    <td>
                      <span
                        className={`ols-badge ${
                          item.is_cancelled ? "ols-badge--cancelled" : "ols-badge--active"
                        }`}
                      >
                        {item.status_label}
                      </span>
                    </td>
                    <td>{formatMoney(item.revenue_without_vat_total)}</td>
                    <td className="ols-net-profit">
                      {formatMoney(item.net_profit_total)}
                      {item.warning && (
                        <span className="ols-tooltip" data-tooltip={item.warning}>
                          <AlertTriangle
                            aria-hidden="true"
                            size={13}
                            className="ols-row-warning-icon"
                          />
                        </span>
                      )}
                    </td>
                    <td className="ols-delivery-cell">
                      <DeliveryTransferredCell order={item} />
                    </td>
                    <td>{formatMoney(item.delivery_cost_actual)}</td>
                    <td>
                      <DeliveryResultCell order={item} />
                    </td>
                    <td>
                      <NetProfitAndDeliveryCell order={item} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="ols-search-form">
        <label className="ols-search-field">
          <span>Номер отправления</span>
          <input
            type="text"
            placeholder="Например 93909349-0350-1"
            value={postingNumber}
            onChange={(event) => setPostingNumber(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
          />
        </label>
        <button
          type="button"
          className="ols-search-button"
          onClick={lookupOrder}
          disabled={loading || !postingNumber.trim()}
        >
          {loading ? (
            <LoaderCircle className="ols-spin" aria-hidden="true" size={16} />
          ) : (
            <Search aria-hidden="true" size={16} />
          )}
          {loading ? "Ищу…" : "Найти заказ"}
        </button>
      </div>

      {error && (
        <div className="ols-warning">
          <AlertTriangle aria-hidden="true" size={15} />
          {error}
        </div>
      )}

      {order && (
        <div className="ols-order-card">
          <div className="ols-order-header">
            <div>
              <h3>Заказ {order.order_number}</h3>
              <span className="ols-posting-number">{order.posting_number}</span>
            </div>
            <span
              className={`ols-badge ${
                order.is_cancelled ? "ols-badge--cancelled" : "ols-badge--active"
              }`}
            >
              {order.status_label}
            </span>
          </div>

          {order.warning && (
            <div className="ols-warning">
              <AlertTriangle aria-hidden="true" size={15} />
              {order.warning}
            </div>
          )}

          <div className="ols-delivery-info">
            <div className="ols-delivery-row">
              <span className="ols-delivery-label">Адрес доставки</span>
              <span className="ols-delivery-value">{order.delivery_address || "—"}</span>
            </div>
            {order.delivery_comment && (
              <div className="ols-delivery-row">
                <span className="ols-delivery-label">Комментарий</span>
                <span className="ols-delivery-value">{order.delivery_comment}</span>
              </div>
            )}
            <div className="ols-delivery-row">
              <span className="ols-delivery-label">Служба доставки</span>
              <span className="ols-delivery-value">{order.delivery_method_name || "—"}</span>
            </div>
            <div className="ols-delivery-row">
              <span className="ols-delivery-label">Подъём</span>
              <span className="ols-delivery-value">
                {order.lift_option_label || "—"}
                {order.lift_floor ? ` (${order.lift_floor} этаж)` : ""}
                {order.lift_price ? ` · ${formatMoney(order.lift_price)}` : ""}
              </span>
            </div>
            <div className="ols-delivery-row">
              <span className="ols-delivery-label">Перевели за доставку</span>
              <span className="ols-delivery-value">
                <DeliveryTransferredCell order={order} />
              </span>
            </div>
            <div className="ols-delivery-row ols-delivery-actual-row">
              <label className="ols-delivery-label" htmlFor="ols-delivery-actual-input">
                Фактическая стоимость доставки, ₽
              </label>
              <div className="ols-delivery-actual-input-row">
                <input
                  id="ols-delivery-actual-input"
                  type="number"
                  step="0.01"
                  placeholder="впишите вручную"
                  value={deliveryActualInput}
                  onChange={(event) => setDeliveryActualInput(event.target.value)}
                  onKeyDown={(event) => event.key === "Enter" && saveDeliveryActualCost()}
                  disabled={savingDeliveryActual}
                />
                <button
                  type="button"
                  className="ols-delivery-actual-calc"
                  onClick={calculateDeliveryCostFromDelovyeLinii}
                  disabled={calculatingDeliveryCost || savingDeliveryActual}
                  title="Посчитать через Деловые Линии по адресу и товарам заказа"
                >
                  {calculatingDeliveryCost ? (
                    <LoaderCircle className="ols-spin" aria-hidden="true" size={14} />
                  ) : (
                    "Рассчитать"
                  )}
                </button>
                <button
                  type="button"
                  className="ols-delivery-actual-save"
                  onClick={saveDeliveryActualCost}
                  disabled={savingDeliveryActual}
                >
                  {savingDeliveryActual ? (
                    <LoaderCircle className="ols-spin" aria-hidden="true" size={14} />
                  ) : (
                    "Сохранить"
                  )}
                </button>
              </div>
              {calculateDeliveryNote && !deliveryActualError && (
                <span className="ols-delivery-actual-note">{calculateDeliveryNote}</span>
              )}
              {deliveryActualError && (
                <span className="ols-delivery-actual-error">{deliveryActualError}</span>
              )}
            </div>
            <div className="ols-delivery-row">
              <span className="ols-delivery-label">Доставка итог за заказ</span>
              <span className="ols-delivery-value">
                <DeliveryResultCell order={order} />
              </span>
            </div>
          </div>

          <div className="ols-tiles ols-order-tiles">
            <div className="ols-tile">
              <span className="ols-tile-label">Чистая без учёта доставки</span>
              <span className="ols-tile-value">{formatMoney(order.net_profit_total)}</span>
            </div>
            <div className="ols-tile">
              <span className="ols-tile-label">Чистая с учётом доставки от покупателя</span>
              <span className="ols-tile-value">
                {formatMoney(order.net_profit_with_delivery_transferred)}
              </span>
            </div>
            <div className="ols-tile ols-tile--accent">
              <span className="ols-tile-label">
                Чистая с учётом доставки (перевели минус факт)
              </span>
              <span className="ols-tile-value">
                {order.delivery_cost_actual !== null && order.delivery_cost_actual !== undefined
                  ? formatMoney(order.net_profit_with_delivery_actual)
                  : "—"}
              </span>
            </div>
          </div>

          <div className="ols-table-wrap">
            <table className="ols-table">
              <thead>
                <tr>
                  <th>Товар</th>
                  <th>Артикул</th>
                  <th>Кол-во</th>
                  <th>Цена</th>
                  <th>Выручка без НДС</th>
                  <th>Себестоимость + комиссия</th>
                  <th>Комиссия, ₽</th>
                  <th>Комиссия, %</th>
                  <th>Наценка, %</th>
                  <th>Цена в юнитке</th>
                  <th>Себестоимость (юнитка)</th>
                  <th>Компенсация логистики</th>
                  <th>Чистая прибыль</th>
                </tr>
              </thead>
              <tbody>
                {order.items.map((item) => (
                  <tr key={item.offer_id}>
                    <td className="ols-item-name" title={item.name}>{item.name}</td>
                    <td>{item.offer_id}</td>
                    <td>{item.quantity}</td>
                    <td>{formatMoney(item.price_with_vat)}</td>
                    <td>{formatMoney(item.revenue_without_vat)}</td>
                    <td>{formatMoney(item.cost_with_commission)}</td>
                    <td>{formatMoney(item.ozon_commission_rub)}</td>
                    <td>{formatPercent(item.ozon_commission_percent)}</td>
                    <td>{formatPercent(item.markup_percent)}</td>
                    <td>{formatMoney(item.unit_economy_price)}</td>
                    <td>{formatMoney(item.unit_economy_cost)}</td>
                    <td>{formatMoney(item.logistics_compensation)}</td>
                    <td className="ols-net-profit">
                      {item.unit_economy_matched ? (
                        formatMoney(item.net_profit)
                      ) : (
                        <span className="ols-not-matched" title="Не найден в юнит-экономике по артикулу">
                          не найден
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={4}>Итого</td>
                  <td>{formatMoney(order.revenue_without_vat_total)}</td>
                  <td></td>
                  <td></td>
                  <td></td>
                  <td></td>
                  <td></td>
                  <td></td>
                  <td></td>
                  <td className="ols-net-profit">{formatMoney(order.net_profit_total)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
