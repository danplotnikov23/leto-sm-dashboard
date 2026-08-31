import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileSpreadsheet,
  LoaderCircle,
  Search,
} from "lucide-react";
import "./ozonAdsAttribution.css";

const ALL_CAMPAIGNS = "ALL";
const MODELS_MODE = "with_models";
const DIRECT_MODE = "direct";

const getMoscowDateParts = () => {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Europe/Moscow",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(
    parts
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value])
  );
  return values;
};

const getDefaultDates = () => {
  const { year, month, day } = getMoscowDateParts();
  return {
    dateFrom: `${year}-${month}-01`,
    dateTo: `${year}-${month}-${day}`,
  };
};

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
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })}%`;
};

const formatNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return Number(value).toLocaleString("ru-RU");
};

const formatPeriodBig = (dateFrom, dateTo) => {
  if (!dateFrom || !dateTo) return "—";
  const fromDate = new Date(`${dateFrom}T00:00:00`);
  const toDate = new Date(`${dateTo}T00:00:00`);
  if (Number.isNaN(fromDate.getTime()) || Number.isNaN(toDate.getTime())) {
    return `${dateFrom} – ${dateTo}`;
  }

  const fullFmt = new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  if (dateFrom === dateTo) return fullFmt.format(fromDate);

  const sameYear = fromDate.getFullYear() === toDate.getFullYear();
  const sameMonth = sameYear && fromDate.getMonth() === toDate.getMonth();
  if (sameMonth) {
    const dayFmt = new Intl.DateTimeFormat("ru-RU", { day: "numeric" });
    return `${dayFmt.format(fromDate)}–${fullFmt.format(toDate)}`;
  }

  const fromFmt = new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: sameYear ? undefined : "numeric",
  });
  return `${fromFmt.format(fromDate)} – ${fullFmt.format(toDate)}`;
};

const formatPeriodChip = (dateFrom, dateTo) => {
  if (!dateFrom || !dateTo) return "—";
  const fromDate = new Date(`${dateFrom}T00:00:00`);
  const toDate = new Date(`${dateTo}T00:00:00`);
  if (Number.isNaN(fromDate.getTime()) || Number.isNaN(toDate.getTime())) {
    return `${dateFrom} – ${dateTo}`;
  }

  const fullFmt = new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  if (dateFrom === dateTo) return fullFmt.format(fromDate);
  return `${fullFmt.format(fromDate)} – ${fullFmt.format(toDate)}`;
};

const formatUnitEconomyVersion = (value) => {
  if (!value) return "не определена";
  const [date, filename] = String(value).split(":");
  return filename ? `${date} · ${filename}` : date;
};

const readApiError = async (response) => {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (body.detail?.message) return body.detail.message;
    if (body.detail) return JSON.stringify(body.detail);
    if (body.error) return String(body.error);
  } catch {
    // The API may return a plain-text proxy error.
  }
  return `Ошибка API: ${response.status}`;
};

const statusLabels = {
  OK: "Рассчитано",
  SPEND_WITHOUT_SALES: "Расход без продаж",
  MODEL_SKU_UNAVAILABLE: "Нужен XLSX для моделей",
  SKU_MAPPING_NOT_FOUND: "SKU не сопоставлен",
  SKU_MAPPING_CONFLICT: "Конфликт SKU",
  UNIT_ECONOMICS_NOT_FOUND: "Нет в юнитке",
  UNIT_COST_NOT_FOUND: "Нет себеса",
  UNION_QUANTITY_MISMATCH: "Не сходится количество",
  UNION_REVENUE_MISMATCH: "Не сходится выручка",
  INVALID_QUANTITY: "Ошибка количества",
  INVALID_REVENUE: "Ошибка выручки",
  CALCULATION_ERROR: "Расчёт неполный",
  NO_SALES: "Нет продаж",
};

const metricDefinitions = [
  {
    key: "spend_without_vat",
    label: "Расход без НДС",
    format: formatMoney,
    hint: "Расход на рекламу без учёта НДС.",
  },
  {
    key: "revenue_without_vat",
    label: "Продажи рекламы без НДС",
    format: formatMoney,
    hint: "Продажи по атрибутированным рекламе заказам без учёта НДС.",
  },
  {
    key: "orders",
    label: "Заказы рекламы",
    format: formatNumber,
    hint: "Количество заказов, атрибутированных рекламе за период.",
  },
  {
    key: "drr_percent",
    label: "DRR",
    format: formatPercent,
    hint: "ДРР = Расход без НДС / Продажи рекламы без НДС × 100%.",
  },
  {
    key: "net_profit",
    label: "Чистая прибыль",
    format: formatMoney,
    hint: "Продажи без НДС − себестоимость и комиссия − налог − расход на рекламу без НДС.",
  },
  {
    key: "romi_percent",
    label: "ROMI",
    format: formatPercent,
    hint: "ROMI = Чистая прибыль / Расход без НДС × 100%.",
  },
];

const columns = [
  { key: "product", label: "Товар", className: "ad-attr-product-column" },
  { key: "campaign", label: "Кампания", className: "ad-attr-campaign-column" },
  { key: "orders", label: "Заказы" },
  { key: "revenue_without_vat", label: "Продажи без НДС" },
  { key: "spend_without_vat", label: "Расход без НДС" },
  { key: "drr_percent", label: "DRR" },
  {
    key: "total_cost",
    label: "Себес + комиссия",
    title: "Сумма столбца AL юнит-экономики × количество по всем покупкам",
  },
  {
    key: "tax",
    label: "Налог",
    title: "Налог на положительную прибыль рассчитан backend",
  },
  { key: "net_profit", label: "Чистая прибыль" },
  { key: "romi_percent", label: "ROMI" },
  { key: "status", label: "Статус" },
];

function StatusBadge({ status, complete }) {
  const isComplete = complete && ["OK", "NO_SALES"].includes(status);
  return (
    <span className={`ad-attr-status ${isComplete ? "is-complete" : "is-warning"}`}>
      {isComplete ? (
        <CheckCircle2 aria-hidden="true" size={14} />
      ) : (
        <AlertTriangle aria-hidden="true" size={14} />
      )}
      {statusLabels[status] || status || "Неизвестно"}
    </span>
  );
}

function OzonAdsAttributionPage({ apiBase }) {
  const defaults = useMemo(() => getDefaultDates(), []);
  const [dateFrom, setDateFrom] = useState(defaults.dateFrom);
  const [dateTo, setDateTo] = useState(defaults.dateTo);
  const [campaigns, setCampaigns] = useState([]);
  const [campaignId, setCampaignId] = useState(ALL_CAMPAIGNS);
  const [campaignPickerOpen, setCampaignPickerOpen] = useState(false);
  const [campaignSearch, setCampaignSearch] = useState("");
  const [campaignsError, setCampaignsError] = useState("");
  const [mode, setMode] = useState(MODELS_MODE);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingKind, setLoadingKind] = useState("api");
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [profitFilter, setProfitFilter] = useState("all");
  const [sort, setSort] = useState({ key: "net_profit", direction: "asc" });
  const [expandedRows, setExpandedRows] = useState(() => new Set());
  const [importFilename, setImportFilename] = useState("");
  const [savedImports, setSavedImports] = useState([]);
  const [savedImportsError, setSavedImportsError] = useState("");
  const [activeSavedImportId, setActiveSavedImportId] = useState(null);
  const pickerRef = useRef(null);
  const fileInputRef = useRef(null);
  const requestControllerRef = useRef(null);

  const today = defaults.dateTo;
  const metricsKey = mode === MODELS_MODE ? "with_models" : "direct";
  const totals = report?.[`${metricsKey}_total`] || null;

  useEffect(() => {
    const closePicker = (event) => {
      if (pickerRef.current && !pickerRef.current.contains(event.target)) {
        setCampaignPickerOpen(false);
      }
    };
    document.addEventListener("mousedown", closePicker);
    return () => document.removeEventListener("mousedown", closePicker);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const loadCampaigns = async () => {
      setCampaignsError("");
      try {
        const response = await fetch(
          `${apiBase}/api/ozon/campaigns/period?date_from=${encodeURIComponent(
            dateFrom
          )}&date_to=${encodeURIComponent(dateTo)}`,
          { signal: controller.signal }
        );
        if (!response.ok) throw new Error(await readApiError(response));
        const payload = await response.json();
        const nextCampaigns = payload.campaigns || [];
        setCampaigns(nextCampaigns);
        setCampaignId((current) =>
          current === ALL_CAMPAIGNS ||
          nextCampaigns.some((campaign) => String(campaign.id) === current)
            ? current
            : ALL_CAMPAIGNS
        );
      } catch (requestError) {
        if (requestError.name !== "AbortError") {
          setCampaignsError(requestError.message || "Не удалось загрузить кампании");
        }
      }
    };
    loadCampaigns();
    return () => controller.abort();
  }, [apiBase, dateFrom, dateTo]);

  useEffect(() => {
    return () => requestControllerRef.current?.abort();
  }, []);

  const loadSavedImports = async () => {
    try {
      const response = await fetch(
        `${apiBase}/api/ozon/promotion-analytics-imports`
      );
      if (!response.ok) throw new Error(await readApiError(response));
      const payload = await response.json();
      setSavedImports(payload.imports || []);
      setSavedImportsError("");
    } catch (requestError) {
      setSavedImportsError(
        requestError.message || "Не удалось загрузить список сохранённых отчётов"
      );
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    const loadInitialSavedImports = async () => {
      try {
        const response = await fetch(
          `${apiBase}/api/ozon/promotion-analytics-imports`,
          { signal: controller.signal }
        );
        if (!response.ok) throw new Error(await readApiError(response));
        const payload = await response.json();
        setSavedImports(payload.imports || []);
        setSavedImportsError("");
      } catch (requestError) {
        if (requestError.name !== "AbortError") {
          setSavedImportsError(
            requestError.message || "Не удалось загрузить список сохранённых отчётов"
          );
        }
      }
    };
    loadInitialSavedImports();
    return () => controller.abort();
  }, [apiBase]);

  const selectSavedImport = async (savedImport) => {
    setLoading(true);
    setLoadingKind("xlsx");
    setError("");
    try {
      const response = await fetch(
        `${apiBase}/api/ozon/promotion-analytics-imports/${savedImport.id}`
      );
      if (!response.ok) throw new Error(await readApiError(response));
      const payload = await response.json();
      setReport(payload);
      setCampaignId(payload.campaign_id);
      setDateFrom(payload.date_from);
      setDateTo(payload.date_to);
      setImportFilename(savedImport.source_filename);
      setActiveSavedImportId(savedImport.id);
      setExpandedRows(new Set());
    } catch (requestError) {
      setError(requestError.message || "Не удалось открыть сохранённый отчёт");
    } finally {
      setLoading(false);
    }
  };

  const selectedCampaign = useMemo(
    () => campaigns.find((campaign) => String(campaign.id) === campaignId),
    [campaignId, campaigns]
  );

  const selectedCampaignLabel =
    campaignId === ALL_CAMPAIGNS
      ? `Все кампании за период (${campaigns.length})`
      : `${selectedCampaign?.id || campaignId} — ${
          selectedCampaign?.title || "Кампания Ozon"
        }`;

  const filteredCampaigns = useMemo(() => {
    const query = campaignSearch.trim().toLocaleLowerCase("ru-RU");
    if (!query) return campaigns;
    return campaigns.filter((campaign) =>
      `${campaign.id} ${campaign.title || ""}`
        .toLocaleLowerCase("ru-RU")
        .includes(query)
    );
  }, [campaignSearch, campaigns]);

  const runReport = async ({ file = null } = {}) => {
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setLoading(true);
    setLoadingKind(file ? "xlsx" : "api");
    setError("");
    setReport(null);
    setActiveSavedImportId(null);
    setExpandedRows(new Set());

    const baseUrl = `${apiBase}/api/ozon/campaigns/${encodeURIComponent(
      campaignId
    )}/ad-attribution`;
    const query = `date_from=${encodeURIComponent(
      dateFrom
    )}&date_to=${encodeURIComponent(dateTo)}`;

    try {
      const options = { signal: controller.signal };
      let url = `${baseUrl}?${query}`;
      if (file) {
        const body = new FormData();
        body.append("file", file);
        options.method = "POST";
        options.body = body;
        url = `${baseUrl}/import?${query}`;
      }
      const response = await fetch(url, options);
      if (!response.ok) throw new Error(await readApiError(response));
      const payload = await response.json();
      setReport(payload);
      if (file) {
        setImportFilename(file.name);
        setDateFrom(payload.date_from);
        setDateTo(payload.date_to);
        loadSavedImports();
      }
    } catch (requestError) {
      if (requestError.name !== "AbortError") {
        setError(requestError.message || "Не удалось построить отчёт");
      }
    } finally {
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null;
        setLoading(false);
      }
    }
  };

  const handleImport = (event) => {
    const selectedFile = event.target.files?.[0];
    event.target.value = "";
    if (selectedFile) runReport({ file: selectedFile });
  };

  const rows = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("ru-RU");
    const filtered = (report?.rows || []).filter((row) => {
      const metrics = row[metricsKey];
      const searchValue = [
        row.offer_id,
        row.promoted_sku,
        row.title,
        ...(row.campaign_ids || []),
        ...(row.campaign_titles || []),
      ]
        .filter(Boolean)
        .join(" ")
        .toLocaleLowerCase("ru-RU");
      if (query && !searchValue.includes(query)) return false;
      if (profitFilter === "negative") return Number(metrics.net_profit) < 0;
      if (profitFilter === "positive") return Number(metrics.net_profit) > 0;
      if (profitFilter === "no_data") return !metrics.complete;
      return true;
    });

    const direction = sort.direction === "asc" ? 1 : -1;
    return filtered.sort((left, right) => {
      const leftMetrics = left[metricsKey];
      const rightMetrics = right[metricsKey];
      let leftValue;
      let rightValue;
      if (sort.key === "product") {
        leftValue = `${left.offer_id || ""} ${left.title || ""} ${left.promoted_sku}`;
        rightValue = `${right.offer_id || ""} ${right.title || ""} ${right.promoted_sku}`;
      } else if (sort.key === "campaign") {
        leftValue = (left.campaign_titles?.[0] || left.campaign_ids?.[0] || "");
        rightValue = (right.campaign_titles?.[0] || right.campaign_ids?.[0] || "");
      } else if (sort.key === "status") {
        leftValue = left.status || "";
        rightValue = right.status || "";
      } else {
        leftValue = leftMetrics?.[sort.key];
        rightValue = rightMetrics?.[sort.key];
      }
      if (leftValue === null || leftValue === undefined) return 1;
      if (rightValue === null || rightValue === undefined) return -1;
      if (typeof leftValue === "string") {
        return leftValue.localeCompare(String(rightValue), "ru") * direction;
      }
      return (Number(leftValue) - Number(rightValue)) * direction;
    });
  }, [metricsKey, profitFilter, report, search, sort]);

  const setSorting = (key) => {
    setSort((current) => ({
      key,
      direction:
        current.key === key && current.direction === "asc" ? "desc" : "asc",
    }));
  };

  const toggleRow = (rowKey) => {
    setExpandedRows((current) => {
      const next = new Set(current);
      if (next.has(rowKey)) next.delete(rowKey);
      else next.add(rowKey);
      return next;
    });
  };

  const visibleChildren = (row) =>
    mode === MODELS_MODE
      ? row.children || []
      : (row.children || []).filter((child) => child.sale_type === "direct");

  const selectCampaign = (nextCampaignId) => {
    setCampaignId(String(nextCampaignId));
    setCampaignSearch("");
    setCampaignPickerOpen(false);
    setReport(null);
    setActiveSavedImportId(null);
    setError("");
  };

  return (
    <div className="ad-attr-page">
      <header className="topbar ad-attr-title">
        <div>
          <h1>Реклама Ozon</h1>
          <p>Финансовая эффективность атрибутированных рекламных продаж</p>
        </div>
      </header>

      <section className="ad-attr-upload-panel">
        <div className="ad-attr-upload-primary">
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xlsm"
            onChange={handleImport}
            hidden
          />
          <button
            type="button"
            className="ad-attr-upload-button"
            onClick={() => fileInputRef.current?.click()}
            disabled={loading}
          >
            <FileSpreadsheet aria-hidden="true" size={20} />
            Загрузить отчёт «Аналитика продвижения»
          </button>
          {importFilename && (
            <span className="ad-attr-upload-filename" title={importFilename}>
              {importFilename}
            </span>
          )}
        </div>

        {savedImports.length > 0 && (
          <div className="ad-attr-saved-imports">
            <span className="ad-attr-saved-imports-label">
              Сохранённые периоды:
            </span>
            <div className="ad-attr-saved-imports-list">
              {savedImports.map((savedImport) => (
                <button
                  key={savedImport.id}
                  type="button"
                  className={
                    activeSavedImportId === savedImport.id ? "is-active" : ""
                  }
                  disabled={loading}
                  onClick={() => selectSavedImport(savedImport)}
                  title={savedImport.source_filename}
                >
                  <Calendar aria-hidden="true" size={15} />
                  <span>
                    {formatPeriodChip(savedImport.date_from, savedImport.date_to)}
                    {savedImport.campaign_id !== ALL_CAMPAIGNS &&
                      ` · ${savedImport.campaign_id}`}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </section>

      {savedImportsError && (
        <div className="ad-attr-inline-warning">{savedImportsError}</div>
      )}
      {error && <div className="error-box">{error}</div>}
      {report?.unit_economy_warning && (
        <div className="ad-attr-inline-warning">{report.unit_economy_warning}</div>
      )}

      {report && (
        <section className="ad-attr-period-heading">
          <span className="ad-attr-period-label">Период</span>
          <strong>{formatPeriodBig(report.date_from, report.date_to)}</strong>
          {report.campaign_id !== ALL_CAMPAIGNS && (
            <span className="ad-attr-period-campaign">
              Кампания {report.campaign_id}
            </span>
          )}
        </section>
      )}

      <section className="ad-attr-mode-row">
        <div className="ad-attr-mode-control" aria-label="Режим атрибуции">
          <button
            type="button"
            className={mode === MODELS_MODE ? "is-active" : ""}
            onClick={() => setMode(MODELS_MODE)}
          >
            С учётом моделей
          </button>
          <button
            type="button"
            className={mode === DIRECT_MODE ? "is-active" : ""}
            onClick={() => setMode(DIRECT_MODE)}
          >
            Без учёта моделей
          </button>
        </div>
      </section>

      <details className="ad-attr-api-fallback">
        <summary>Получить через API Ozon без файла (кампания и период)</summary>
        <section className="ad-attr-control-panel">
          <div className="ad-attr-campaign-picker" ref={pickerRef}>
            <span className="ad-attr-field-label">Кампания</span>
            <button
              type="button"
              className="ad-attr-campaign-trigger"
              aria-expanded={campaignPickerOpen}
              onClick={() => setCampaignPickerOpen((current) => !current)}
              disabled={loading}
            >
              <span>{selectedCampaignLabel}</span>
              <ChevronDown aria-hidden="true" size={17} />
            </button>
            {campaignPickerOpen && (
              <div className="ad-attr-campaign-menu">
                <label className="ad-attr-campaign-search">
                  <Search aria-hidden="true" size={16} />
                  <input
                    autoFocus
                    value={campaignSearch}
                    onChange={(event) => setCampaignSearch(event.target.value)}
                    placeholder="ID, артикул или название"
                  />
                </label>
                <div className="ad-attr-campaign-options">
                  <button
                    type="button"
                    className={campaignId === ALL_CAMPAIGNS ? "is-selected" : ""}
                    onClick={() => selectCampaign(ALL_CAMPAIGNS)}
                  >
                    <strong>Все кампании за период</strong>
                    <span>{campaigns.length} кампаний</span>
                  </button>
                  {filteredCampaigns.map((campaign) => (
                    <button
                      type="button"
                      key={campaign.id}
                      className={
                        String(campaign.id) === campaignId ? "is-selected" : ""
                      }
                      onClick={() => selectCampaign(campaign.id)}
                    >
                      <strong>{campaign.id}</strong>
                      <span>{campaign.title || "Без названия"}</span>
                    </button>
                  ))}
                  {!filteredCampaigns.length && (
                    <div className="ad-attr-no-campaigns">Ничего не найдено</div>
                  )}
                </div>
              </div>
            )}
          </div>

          <label className="ad-attr-date-field">
            <span>С</span>
            <input
              type="date"
              value={dateFrom}
              max={dateTo || today}
              onChange={(event) => {
                setDateFrom(event.target.value);
                setReport(null);
                setActiveSavedImportId(null);
              }}
              disabled={loading}
            />
          </label>
          <label className="ad-attr-date-field">
            <span>По</span>
            <input
              type="date"
              value={dateTo}
              min={dateFrom}
              max={today}
              onChange={(event) => {
                setDateTo(event.target.value);
                setReport(null);
                setActiveSavedImportId(null);
              }}
              disabled={loading}
            />
          </label>
          <button
            type="button"
            className="ad-attr-primary-button"
            onClick={() => runReport()}
            disabled={loading || !dateFrom || !dateTo}
          >
            Создать отчёт
          </button>
        </section>

        {campaignsError && (
          <div className="ad-attr-inline-warning">
            Кампании не обновлены: {campaignsError}. Отчёт по всем кампаниям можно
            запустить.
          </div>
        )}
      </details>

      <section className="ad-attr-kpi-grid">
        {metricDefinitions.map((definition) => {
          const value = totals?.[definition.key];
          const isProfit = ["net_profit", "romi_percent"].includes(definition.key);
          const valueClass = isProfit
            ? Number(value) < 0
              ? "is-negative"
              : Number(value) > 0
                ? "is-positive"
                : ""
            : "";
          return (
            <article className="ad-attr-kpi" key={definition.key}>
              <span
                className="ad-attr-kpi-label"
                data-tooltip={definition.hint}
                tabIndex={definition.hint ? 0 : undefined}
              >
                {definition.label}
              </span>
              <strong className={valueClass}>
                {totals ? definition.format(value) : "—"}
              </strong>
            </article>
          );
        })}
      </section>

      <section className="ad-attr-table-card">
        <div className="ad-attr-table-heading">
          <div>
            <h2>Эффективность по артикулам</h2>
            <p>
              Расход списывается один раз, себестоимость модельной продажи
              относится к фактически купленному SKU
            </p>
          </div>
          <div className="ad-attr-table-tools">
            <label className="ad-attr-table-search">
              <Search aria-hidden="true" size={16} />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Артикул, SKU, кампания"
              />
            </label>
            <div className="ad-attr-profit-filter">
              {[
                ["all", "Все"],
                ["negative", "Минус"],
                ["positive", "Плюс"],
                ["no_data", "Нет данных"],
              ].map(([value, label]) => (
                <button
                  type="button"
                  key={value}
                  className={profitFilter === value ? "is-active" : ""}
                  onClick={() => setProfitFilter(value)}
                >
                  {label}
                </button>
              ))}
            </div>
            <span className="ad-attr-row-count">
              {rows.length} / {report?.rows?.length || 0}
            </span>
          </div>
        </div>

        {report && (
          <div className="ad-attr-service-line">
            <span>
              Источник: <strong>{report.source === "xlsx" ? "XLSX Ozon" : "Ozon API"}</strong>
            </span>
            <span>
              Юнитка:{" "}
              <strong title={report.unit_economy_version || undefined}>
                {formatUnitEconomyVersion(report.unit_economy_version)}
              </strong>
            </span>
            <span>
              Покрытие: <strong>{formatPercent(totals?.coverage_percent)}</strong>
            </span>
            <span>
              Кампаний: <strong>{report.campaign_count}</strong>
            </span>
            <span>
              Режим:{" "}
              <strong>
                {mode === MODELS_MODE ? "с учётом моделей" : "только прямые SKU"}
              </strong>
            </span>
          </div>
        )}

        <div className="ad-attr-table-wrap">
          {!report ? (
            <div className="ad-attr-empty">
              Создай отчёт из Ozon API. Для точной расшифровки модельных продаж
              можно загрузить XLSX «Аналитика продвижения».
            </div>
          ) : !rows.length ? (
            <div className="ad-attr-empty">По выбранным фильтрам строк нет</div>
          ) : (
            <table className="ad-attr-table">
              <thead>
                <tr>
                  {columns.map((column) => (
                    <th
                      key={column.key}
                      className={column.className || ""}
                      title={column.title}
                    >
                      <button
                        type="button"
                        onClick={() => setSorting(column.key)}
                      >
                        {column.label}
                        {sort.key === column.key && (
                          <span>{sort.direction === "asc" ? "↑" : "↓"}</span>
                        )}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const metrics = row[metricsKey];
                  const expanded = expandedRows.has(row.row_key);
                  const children = visibleChildren(row);
                  const displayStatus =
                    mode === DIRECT_MODE &&
                    metrics.complete &&
                    row.status === "MODEL_SKU_UNAVAILABLE"
                      ? "OK"
                      : row.status;
                  return (
                    <OzonAttributionRow
                      key={row.row_key}
                      row={row}
                      metrics={metrics}
                      status={displayStatus}
                      expanded={expanded}
                      children={children}
                      onToggle={() => toggleRow(row.row_key)}
                    />
                  );
                })}
                <tr className="ad-attr-total-row">
                  <td className="ad-attr-product-column">
                    <strong>Итого</strong>
                  </td>
                  <td className="ad-attr-campaign-column">
                    {report.campaign_count} кампаний
                  </td>
                  <td>{formatNumber(totals?.orders)}</td>
                  <td>{formatMoney(totals?.revenue_without_vat)}</td>
                  <td>{formatMoney(totals?.spend_without_vat)}</td>
                  <td>{formatPercent(totals?.drr_percent)}</td>
                  <td>{formatMoney(totals?.total_cost)}</td>
                  <td>{formatMoney(totals?.tax)}</td>
                  <td className={Number(totals?.net_profit) < 0 ? "is-negative" : "is-positive"}>
                    {formatMoney(totals?.net_profit)}
                  </td>
                  <td className={Number(totals?.romi_percent) < 0 ? "is-negative" : "is-positive"}>
                    {formatPercent(totals?.romi_percent)}
                  </td>
                  <td>
                    <StatusBadge
                      status={totals?.complete ? "OK" : "CALCULATION_ERROR"}
                      complete={Boolean(totals?.complete)}
                    />
                  </td>
                </tr>
              </tbody>
            </table>
          )}
        </div>
      </section>

      {report?.errors?.length > 0 && (
        <details className="ad-attr-errors">
          <summary>Контроль данных: {report.errors.length}</summary>
          <ul>
            {report.errors.map((reportError, index) => (
              <li key={`${reportError}-${index}`}>{reportError}</li>
            ))}
          </ul>
        </details>
      )}

      {loading && (
        <div className="report-modal-backdrop">
          <section className="report-modal ad-attr-loading-modal">
            <LoaderCircle className="ad-attr-spinner" aria-hidden="true" size={23} />
            <div>
              <h2>
                {loadingKind === "xlsx"
                  ? "Проверяю XLSX Ozon"
                  : "Считаю рекламу Ozon"}
              </h2>
              <p>
                Backend получает отчёты пакетами, сопоставляет купленные SKU с
                юниткой и рассчитывает прибыль.
              </p>
            </div>
            <div className="ad-attr-indeterminate" aria-hidden="true">
              <span />
            </div>
            <div className="ad-attr-loading-stages">
              <span>Отчёт Ozon</span>
              <span>Сопоставление SKU</span>
              <span>Финансовый расчёт</span>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function OzonAttributionRow({
  row,
  metrics,
  status,
  expanded,
  children,
  onToggle,
}) {
  const negativeProfit = Number(metrics.net_profit) < 0;
  const positiveProfit = Number(metrics.net_profit) > 0;
  const campaigns = row.campaign_ids || [];
  const campaignTitles = row.campaign_titles || [];

  return (
    <>
      <tr className={!metrics.complete ? "has-missing-data" : ""}>
        <td className="ad-attr-product-column">
          <button type="button" className="ad-attr-expand-button" onClick={onToggle}>
            {expanded ? (
              <ChevronDown aria-hidden="true" size={16} />
            ) : (
              <ChevronRight aria-hidden="true" size={16} />
            )}
          </button>
          <div className="ad-attr-product">
            <strong>{row.offer_id || "Артикул не найден"}</strong>
            <span>{row.title || "Название не получено"}</span>
            <small>SKU {row.promoted_sku}</small>
          </div>
        </td>
        <td className="ad-attr-campaign-column">
          <div className="ad-attr-campaign-cell">
            <strong>{campaigns[0] || "—"}</strong>
            <span>{campaignTitles[0] || "Кампания Ozon"}</span>
            {campaigns.length > 1 && <small>+ ещё {campaigns.length - 1}</small>}
          </div>
        </td>
        <td>{formatNumber(metrics.orders)}</td>
        <td>{formatMoney(metrics.revenue_without_vat)}</td>
        <td>{formatMoney(metrics.spend_without_vat)}</td>
        <td>{formatPercent(metrics.drr_percent)}</td>
        <td>{formatMoney(metrics.total_cost)}</td>
        <td>{formatMoney(metrics.tax)}</td>
        <td
          className={
            negativeProfit ? "is-negative" : positiveProfit ? "is-positive" : ""
          }
        >
          {formatMoney(metrics.net_profit)}
        </td>
        <td
          className={
            Number(metrics.romi_percent) < 0
              ? "is-negative"
              : Number(metrics.romi_percent) > 0
                ? "is-positive"
                : ""
          }
        >
          {formatPercent(metrics.romi_percent)}
        </td>
        <td>
          <StatusBadge status={status} complete={metrics.complete} />
          {!metrics.complete && (
            <small className="ad-attr-coverage">
              покрытие {formatPercent(metrics.coverage_percent)}
            </small>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="ad-attr-detail-row">
          <td colSpan={11}>
            <div className="ad-attr-detail">
              <div className="ad-attr-detail-heading">
                <div>
                  <strong>Купленные позиции</strong>
                  <span>
                    Прямые продажи используют себестоимость продвигаемого SKU,
                    модельные — фактически купленного SKU.
                  </span>
                </div>
                <span>{children.length} строк</span>
              </div>
              <div className="ad-attr-child-wrap">
                <table className="ad-attr-child-table">
                  <thead>
                    <tr>
                      <th>Тип</th>
                      <th>Купленный SKU / артикул</th>
                      <th>Инструмент / место</th>
                      <th>Кол-во</th>
                      <th>Продажи без НДС</th>
                      <th>Цена без НДС</th>
                      <th>Себес за шт.</th>
                      <th>Себес итого</th>
                      <th>Налог</th>
                      <th>Прибыль до рекламы</th>
                      <th>Статус</th>
                    </tr>
                  </thead>
                  <tbody>
                    {children.map((child, index) => (
                      <tr
                        key={`${child.sale_type}-${child.purchased_sku}-${child.instrument}-${child.placement}-${index}`}
                      >
                        <td>
                          <span className={`ad-attr-sale-type is-${child.sale_type}`}>
                            {child.sale_type === "model" ? "Модель" : "Прямая"}
                          </span>
                        </td>
                        <td>
                          <div className="ad-attr-child-product">
                            <strong>{child.offer_id || "Артикул не найден"}</strong>
                            <span>{child.title || "Название не получено"}</span>
                            <small>SKU {child.purchased_sku || "не передан Ozon"}</small>
                          </div>
                        </td>
                        <td>
                          <strong>{child.instrument || "—"}</strong>
                          <small>{child.placement || "—"}</small>
                        </td>
                        <td>{formatNumber(child.quantity)}</td>
                        <td>{formatMoney(child.revenue_without_vat)}</td>
                        <td>{formatMoney(child.average_price_without_vat)}</td>
                        <td>{formatMoney(child.unit_cost)}</td>
                        <td>{formatMoney(child.total_cost)}</td>
                        <td>{formatMoney(child.tax)}</td>
                        <td
                          className={
                            Number(child.profit_before_ads) < 0
                              ? "is-negative"
                              : Number(child.profit_before_ads) > 0
                                ? "is-positive"
                                : ""
                          }
                        >
                          {formatMoney(child.profit_before_ads)}
                        </td>
                        <td>
                          <StatusBadge
                            status={child.status}
                            complete={["OK", "NO_SALES"].includes(child.status)}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {row.issues?.length > 0 && (
                <ul className="ad-attr-row-issues">
                  {row.issues.map((issue, index) => (
                    <li key={`${issue}-${index}`}>{issue}</li>
                  ))}
                </ul>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default OzonAdsAttributionPage;
