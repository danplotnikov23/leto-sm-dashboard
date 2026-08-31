import { useState, useEffect } from "react";
import {
  LayoutDashboard,
  ShoppingCart,
  Package,
  BarChart3,
  Settings,
  LogOut,
  Sun,
  Moon,
} from "lucide-react";
import "./index.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8010";

/* ─── Helpers ─── */
const formatMoney = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return `${Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 0 })} ₽`;
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

/* ─── Orders Section ─── */
function OrdersSection() {
  const [todayOrders, setTodayOrders] = useState([]);
  const [todayLoading, setTodayLoading] = useState(true);
  const [todayError, setTodayError] = useState("");
  const [summary, setSummary] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const todayIso = getMoscowTodayIso();

  useEffect(() => {
    const loadToday = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/ozon/orders/today`);
        if (!response.ok) throw new Error(`Ошибка API: ${response.status}`);
        const payload = await response.json();
        setTodayOrders(payload || []);
        setTodayError("");
      } catch (err) {
        setTodayError(err.message || "Не удалось загрузить заказы");
      } finally {
        setTodayLoading(false);
      }
    };
    const loadSummary = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/ozon/orders/today/summary`);
        if (!response.ok) return;
        setSummary(await response.json());
      } catch {
        // ignore
      }
    };
    loadToday();
    loadSummary();
    const interval = setInterval(() => {
      loadToday();
      loadSummary();
    }, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  const refreshNow = async () => {
    setRefreshing(true);
    setTodayError("");
    try {
      const response = await fetch(`${API_BASE}/api/ozon/orders/today/refresh`, {
        method: "POST",
      });
      if (!response.ok) throw new Error(`Ошибка API: ${response.status}`);
      const payload = await response.json();
      setTodayOrders(payload || []);
    } catch (err) {
      setTodayError(err.message || "Не удалось обновить заказы");
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="section-container">
      <div className="section-header">
        <h2>Заказы за сегодня</h2>
        <div className="section-actions">
          <button className="btn-secondary" onClick={refreshNow} disabled={refreshing}>
            {refreshing ? "Обновление…" : "Обновить сейчас"}
          </button>
        </div>
      </div>

      {summary && (
        <div className="tiles-row">
          <div className="tile">
            <span className="tile-label">Выручка без НДС</span>
            <span className="tile-value">{formatMoney(summary.revenue_without_vat_total)}</span>
          </div>
          <div className="tile">
            <span className="tile-label">Прибыль до рекламы</span>
            <span className="tile-value">{formatMoney(summary.net_profit_before_ads_total)}</span>
          </div>
          <div className="tile">
            <span className="tile-label">Реклама за сегодня</span>
            <span className="tile-value">{formatMoney(summary.ad_spend_without_vat)}</span>
          </div>
          <div className="tile tile-accent">
            <span className="tile-label">Чистая прибыль</span>
            <span className="tile-value">{formatMoney(summary.net_profit_total)}</span>
          </div>
        </div>
      )}

      {todayError && <div className="alert alert-error">{todayError}</div>}

      {todayLoading ? (
        <div className="empty-state">Загружаю заказы…</div>
      ) : todayOrders.length === 0 ? (
        <div className="empty-state">За сегодня заказов пока нет</div>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Время</th>
                <th>Заказ</th>
                <th>Статус</th>
                <th>Выручка без НДС</th>
                <th>Чистая прибыль</th>
              </tr>
            </thead>
            <tbody>
              {todayOrders.map((item) => (
                <tr key={item.posting_number}>
                  <td>{formatTime(item.in_process_at)}</td>
                  <td>{item.order_number}</td>
                  <td>
                    <span className={`badge ${item.is_cancelled ? "badge-cancelled" : "badge-active"}`}>
                      {item.status_label}
                    </span>
                  </td>
                  <td>{formatMoney(item.revenue_without_vat_total)}</td>
                  <td className={item.net_profit_total < 0 ? "negative" : "positive"}>
                    {formatMoney(item.net_profit_total)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ─── Stock Section ─── */
function StockSection() {
  const [stocks, setStocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/ozon/stocks`);
        if (!response.ok) throw new Error(`Ошибка API: ${response.status}`);
        const payload = await response.json();
        setStocks(payload || []);
        setError("");
      } catch (err) {
        setError(err.message || "Не удалось загрузить остатки");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const filtered = stocks.filter((item) => {
    const text = search.toLowerCase();
    const offerId = (item.offer_id || "").toLowerCase();
    const sku = String(item.sku || "").toLowerCase();
    return offerId.includes(text) || sku.includes(text);
  });

  return (
    <div className="section-container">
      <div className="section-header">
        <h2>Остатки на Ozon</h2>
        <div className="section-actions">
          <input
            type="text"
            placeholder="Поиск по артикулу или SKU…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="search-input"
          />
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {loading ? (
        <div className="empty-state">Загружаю остатки…</div>
      ) : filtered.length === 0 ? (
        <div className="empty-state">
          <Package size={48} />
          <p>Ничего не найдено</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Артикул (offer_id)</th>
                <th>На складе Ozon</th>
                <th>В пути</th>
                <th>Резерв</th>
                <th>Доступно</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr key={item.sku || item.offer_id}>
                  <td>{item.sku}</td>
                  <td>{item.offer_id || "—"}</td>
                  <td>{item.present || 0}</td>
                  <td>{item.shipped || 0}</td>
                  <td>{item.reserved || 0}</td>
                  <td className="positive">{(item.present || 0) - (item.reserved || 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ─── Main App ─── */
function App() {
  const [activeTab, setActiveTab] = useState("orders");
  const [darkMode, setDarkMode] = useState(true);

  const menuItems = [
    { id: "dashboard", label: "Главная", icon: LayoutDashboard },
    { id: "orders", label: "Заказы", icon: ShoppingCart },
    { id: "stock", label: "Остатки", icon: Package },
    { id: "analytics", label: "Аналитика", icon: BarChart3 },
    { id: "settings", label: "Настройки", icon: Settings },
  ];

  return (
    <div className={`app ${darkMode ? "dark" : "light"}`}>
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="logo">
            <img src="/logo.png" alt="Лето СМ" className="logo-img" />
            <span className="logo-text">Лето СМ</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          {menuItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={`nav-item ${activeTab === item.id ? "nav-item-active" : ""}`}
                onClick={() => setActiveTab(item.id)}
              >
                <Icon size={20} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <button className="nav-item" onClick={() => setDarkMode(!darkMode)}>
            {darkMode ? <Sun size={20} /> : <Moon size={20} />}
            <span>{darkMode ? "Светлая тема" : "Тёмная тема"}</span>
          </button>
          <button className="nav-item">
            <LogOut size={20} />
            <span>Выйти</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <header className="content-header">
          <h1>
            {menuItems.find((i) => i.id === activeTab)?.label || "Главная"}
          </h1>
        </header>

        <div className="content-body">
          {activeTab === "orders" && <OrdersSection />}
          {activeTab === "stock" && <StockSection />}
          {activeTab === "dashboard" && (
            <div className="section-container">
              <div className="empty-state">
                <LayoutDashboard size={48} />
                <p>Главная страница в разработке</p>
              </div>
            </div>
          )}
          {activeTab === "analytics" && (
            <div className="section-container">
              <div className="empty-state">
                <BarChart3 size={48} />
                <p>Аналитика в разработке</p>
              </div>
            </div>
          )}
          {activeTab === "settings" && (
            <div className="section-container">
              <div className="empty-state">
                <Settings size={48} />
                <p>Настройки в разработке</p>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
