import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import ozonLogo from "../assets/ozon-icon.png";
import yandexLogo from "../assets/yandex-market.svg";
import { getMarketplaceSalesDashboard } from "../dashboardApi";
import "../homeDashboard.css";

const PERIODS = [
  { id: "7d", label: "7 дней" },
  { id: "14d", label: "2 недели" },
  { id: "28d", label: "4 недели" },
  { id: "month", label: "Месяц" },
];

const AUTO_REFRESH_MS = 10 * 60 * 1000;
const PARTIAL_RETRY_MS = 30 * 1000;

const moneyFormatter = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  maximumFractionDigits: 0,
});

const compactMoneyFormatter = new Intl.NumberFormat("ru-RU", {
  notation: "compact",
  maximumFractionDigits: 1,
});

const unitsFormatter = new Intl.NumberFormat("ru-RU");

const dateFormatter = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "short",
});

const timeFormatter = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Europe/Moscow",
  hour: "2-digit",
  minute: "2-digit",
});

function formatMoney(value) {
  return moneyFormatter.format(Number(value || 0));
}

function formatUnits(value) {
  return `${unitsFormatter.format(Number(value || 0))} шт.`;
}

function formatDate(value) {
  return dateFormatter.format(new Date(`${value}T12:00:00+03:00`));
}

function formatTime(value) {
  return value ? timeFormatter.format(new Date(value)) : "—";
}

function MarketplaceLogo({ logo, name, logoClassName = "" }) {
  return (
    <div className="home-marketplace-brand">
      <span className={`home-marketplace-logo ${logoClassName}`.trim()}>
        <img src={logo} alt="" aria-hidden="true" />
      </span>
      <span>{name}</span>
    </div>
  );
}

function SummaryMetric({ label, metric, prominent = false }) {
  return (
    <div className={`home-summary-metric${prominent ? " prominent" : ""}`}>
      <span>{label}</span>
      <strong>{formatMoney(metric?.revenue_with_vat)}</strong>
      <small>{formatUnits(metric?.ordered_units)}</small>
    </div>
  );
}

function SalesBarChart({ dashboard, loading, tone }) {
  const points = dashboard?.points || [];
  const maxRevenue = Math.max(
    ...points.map((point) => Number(point.revenue_with_vat || 0)),
    1
  );
  const labelStep = points.length > 21 ? 4 : points.length > 10 ? 2 : 1;

  if (loading && !dashboard) {
    return <div className="home-chart-empty">Загружаю данные API...</div>;
  }

  if (!points.length) {
    return <div className="home-chart-empty">За выбранный период заказов нет</div>;
  }

  return (
    <div
      className={`home-bar-chart tone-${tone}`}
      style={{ "--point-count": points.length }}
    >
      <div className="home-chart-grid" aria-hidden="true">
        <span>{compactMoneyFormatter.format(maxRevenue)} ₽</span>
        <span>{compactMoneyFormatter.format(maxRevenue / 2)} ₽</span>
        <span>0</span>
      </div>
      <div className="home-bars">
        {points.map((point, index) => {
          const revenue = Number(point.revenue_with_vat || 0);
          const height = Math.max((revenue / maxRevenue) * 100, 2);
          const isToday = point.date === dashboard?.date_to;
          const showLabel =
            index % labelStep === 0 || index === points.length - 1;

          return (
            <div className="home-bar-column" key={point.date}>
              <div
                className={`home-bar-tooltip${isToday ? " today" : ""}`}
                style={{ "--bar-height": `${height}%` }}
                tabIndex={0}
                aria-label={`${formatDate(point.date)}: ${formatMoney(
                  revenue
                )}, ${formatUnits(point.ordered_units)}`}
              >
                <span className="home-bar-popover" aria-hidden="true">
                  <span>{formatDate(point.date)}</span>
                  <strong>{formatMoney(revenue)}</strong>
                  <span>{formatUnits(point.ordered_units)}</span>
                </span>
                <span className="home-bar-fill" />
              </div>
              <span className="home-bar-label">
                {showLabel ? formatDate(point.date) : ""}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MarketplaceSection({
  dashboard,
  error,
  loading,
  logo,
  logoClassName,
  name,
  tone,
}) {
  return (
    <section className={`home-provider-section tone-${tone}`}>
      <div className="home-provider-header">
        <div>
          <MarketplaceLogo
            logo={logo}
            name={name}
            logoClassName={logoClassName}
          />
          <p>Заказано на сумму, с НДС</p>
        </div>
        {dashboard && (
          <span className="home-provider-updated">
            {formatDate(dashboard.date_from)} — {formatDate(dashboard.date_to)}
            {" · "}
            обновлено в {formatTime(dashboard.updated_at)}
          </span>
        )}
      </div>

      {error && (
        <div className="home-provider-error" role="status">
          {error}
        </div>
      )}

      {dashboard ? (
        <>
          <div className="home-provider-metrics">
            <SummaryMetric label="Сегодня" metric={dashboard.today} prominent />
            <SummaryMetric label="Текущий месяц" metric={dashboard.month} />
            <SummaryMetric
              label="Выбранный период"
              metric={dashboard.selected_period}
            />
          </div>
          <div className="home-provider-chart">
            <SalesBarChart
              dashboard={dashboard}
              loading={loading}
              tone={tone}
            />
          </div>
          {dashboard.warning && (
            <div className="home-provider-warning" role="status">
              {dashboard.warning}
            </div>
          )}
        </>
      ) : (
        <div className="home-provider-placeholder">
          {loading ? "Подключаю площадку..." : "Данные площадки недоступны"}
        </div>
      )}
    </section>
  );
}

function HomeDashboardPage() {
  const [period, setPeriod] = useState("28d");
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const loadDashboard = useCallback(
    async ({ forceRefresh = false, signal } = {}) => {
      forceRefresh ? setRefreshing(true) : setLoading(true);
      setError("");

      try {
        const payload = await getMarketplaceSalesDashboard(period, {
          forceRefresh,
          signal,
        });
        setDashboard(payload);
      } catch (requestError) {
        if (requestError.name !== "AbortError") {
          setError(requestError.message);
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [period]
  );

  useEffect(() => {
    const controller = new AbortController();
    getMarketplaceSalesDashboard(period, { signal: controller.signal })
      .then((payload) => {
        setDashboard(payload);
        setError("");
      })
      .catch((requestError) => {
        if (requestError.name !== "AbortError") {
          setError(requestError.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });

    const refreshTimer = window.setInterval(() => {
      loadDashboard({ forceRefresh: true });
    }, AUTO_REFRESH_MS);

    return () => {
      controller.abort();
      window.clearInterval(refreshTimer);
    };
  }, [loadDashboard, period]);

  useEffect(() => {
    const hasPartialDashboard =
      dashboard && (!dashboard.ozon || !dashboard.yandex);
    if (!hasPartialDashboard || loading || refreshing) {
      return undefined;
    }

    const retryTimer = window.setTimeout(() => {
      loadDashboard();
    }, PARTIAL_RETRY_MS);

    return () => window.clearTimeout(retryTimer);
  }, [dashboard, loadDashboard, loading, refreshing]);

  const combined = dashboard?.combined;
  const providerErrors = dashboard?.provider_errors || {};

  return (
    <div className="home-dashboard">
      <header className="topbar home-topbar">
        <div>
          <h1>Главная</h1>
          <p>Продажи Ozon и Яндекс Маркета · обновление каждые 10 минут</p>
        </div>
        <button
          type="button"
          className="home-refresh-button"
          onClick={() => loadDashboard({ forceRefresh: true })}
          disabled={loading || refreshing}
        >
          <RefreshCw
            aria-hidden="true"
            size={16}
            strokeWidth={1.8}
            className={refreshing ? "is-spinning" : ""}
          />
          Обновить
        </button>
      </header>

      {error && (
        <div className="home-alert home-alert-error" role="alert">
          {error}
        </div>
      )}

      <section className="home-overview">
        <div className="home-overview-copy">
          <span className="home-overview-kicker">Все площадки</span>
          <h2>Продажи сегодня</h2>
          <strong>
            {loading && !combined
              ? "Загрузка..."
              : formatMoney(combined?.today?.revenue_with_vat)}
          </strong>
          <span>{formatUnits(combined?.today?.ordered_units)}</span>
        </div>
        <div className="home-overview-secondary">
          <SummaryMetric label="Текущий месяц" metric={combined?.month} />
          <SummaryMetric
            label="Выбранный период"
            metric={combined?.selected_period}
          />
        </div>
      </section>

      <div className="home-dashboard-controls">
        <div className="home-period-tabs" aria-label="Период графиков">
          {PERIODS.map((item) => (
            <button
              type="button"
              key={item.id}
              className={period === item.id ? "active" : ""}
              onClick={() => {
                setLoading(true);
                setPeriod(item.id);
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
        <span>
          Период применяется одновременно к обеим площадкам
        </span>
      </div>

      {combined?.warning && (
        <div className="home-alert home-alert-warning" role="status">
          {combined.warning}
        </div>
      )}

      <div className="home-provider-list">
        <MarketplaceSection
          dashboard={dashboard?.ozon}
          error={providerErrors.ozon}
          loading={loading}
          logo={ozonLogo}
          logoClassName="ozon"
          name="Ozon"
          tone="ozon"
        />
        <MarketplaceSection
          dashboard={dashboard?.yandex}
          error={providerErrors.yandex}
          loading={loading}
          logo={yandexLogo}
          logoClassName="yandex"
          name="Яндекс Маркет"
          tone="yandex"
        />
      </div>
    </div>
  );
}

export default HomeDashboardPage;
