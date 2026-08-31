import { useState } from "react";
import { LoaderCircle, Sparkles } from "lucide-react";
import yandexLogo from "../assets/yandex-market.svg";
import {
  BrandHeader,
  FileField,
  NumericField,
  ToolError,
  ToolResult,
} from "../components/MarketplaceToolKit";
import { runMarketplaceTool } from "../marketplaceToolsApi";
import "../marketplaceTools.css";

const PROMOTION_STATS = [
  { key: "rows_total", label: "Товарных строк" },
  { key: "rows_selected", label: "Добавлено вручную" },
  { key: "rows_not_selected", label: "Не добавлено" },
  { key: "rows_with_errors", label: "Проверить" },
];

const PROMOTION_COLUMNS = [
  { key: "sku", label: "SKU" },
  { key: "name", label: "Товар" },
  {
    key: "effective_discount",
    label: "Скидка",
    format: (value) => (value === null || value === undefined ? "—" : `${value}%`),
  },
  { key: "new_promo_price", label: "Новая цена" },
  { key: "method", label: "Способ" },
  { key: "issue", label: "Контроль" },
];

const BOOST_STATS = [
  { key: "products_unique", label: "Уникальных SKU" },
  { key: "promo_participants", label: "Исключено акцией" },
  { key: "rows_for_boost", label: "В файл Буста" },
  { key: "products_duplicates", label: "Дубли" },
];

const BOOST_COLUMNS = [
  { key: "sku", label: "SKU" },
  { key: "name", label: "Товар" },
  { key: "price", label: "Цена" },
  {
    key: "bid",
    label: "Ставка",
    format: (value) => (value === null || value === undefined ? "—" : `${value}%`),
  },
];

export default function YandexPromotionsPage() {
  const [mode, setMode] = useState("promotion");
  const [promotionFile, setPromotionFile] = useState(null);
  const [productsFile, setProductsFile] = useState(null);
  const [boostPromotionFile, setBoostPromotionFile] = useState(null);
  const [templateFile, setTemplateFile] = useState(null);
  const [minDiscount, setMinDiscount] = useState("1");
  const [maxDiscount, setMaxDiscount] = useState("6");
  const [targetDiscount, setTargetDiscount] = useState("10");
  const [bid, setBid] = useState("17");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [promotionResult, setPromotionResult] = useState(null);
  const [boostResult, setBoostResult] = useState(null);

  const runPromotion = async () => {
    if (!promotionFile) {
      setError("Загрузите файл товаров для акции Яндекс Маркета");
      return;
    }
    const form = new FormData();
    form.append("promotions_file", promotionFile);
    form.append("min_discount", minDiscount);
    form.append("max_discount", maxDiscount);
    form.append("target_discount", targetDiscount);
    await execute(
      "/api/tools/yandex/promotion",
      form,
      setPromotionResult,
    );
  };

  const runBoost = async () => {
    if (!productsFile || !templateFile) {
      setError("Загрузите каталог товаров и шаблон Буста");
      return;
    }
    const form = new FormData();
    form.append("products_file", productsFile);
    form.append("template_file", templateFile);
    form.append("bid", bid);
    if (boostPromotionFile) form.append("promotions_file", boostPromotionFile);
    await execute("/api/tools/yandex/boost", form, setBoostResult);
  };

  const execute = async (path, form, setResult) => {
    setLoading(true);
    setError("");
    try {
      setResult(await runMarketplaceTool(path, form));
    } catch (requestError) {
      setResult(null);
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  const isPromotion = mode === "promotion";
  return (
    <div className="marketplace-tool-page">
      <BrandHeader
        logo={yandexLogo}
        logoAlt="Яндекс Маркет"
        eyebrow="Яндекс Маркет"
        title="Акции и Буст"
        description="Подготовка акционных цен и файла Буста продаж"
      />

      <div className="marketplace-mode-switch" role="tablist">
        <button
          className={isPromotion ? "active" : ""}
          onClick={() => setMode("promotion")}
          type="button"
        >
          Подготовить акцию
        </button>
        <button
          className={!isPromotion ? "active" : ""}
          onClick={() => setMode("boost")}
          type="button"
        >
          Собрать Буст
        </button>
      </div>

      {isPromotion ? (
        <section className="marketplace-form-panel">
          <div className="marketplace-file-grid single">
            <FileField
              label="Товары для акции"
              file={promotionFile}
              onChange={setPromotionFile}
            />
          </div>
          <div className="marketplace-options-row">
            <NumericField
              label="Скидка от, %"
              value={minDiscount}
              onChange={setMinDiscount}
              max={99}
            />
            <NumericField
              label="Скидка до, %"
              value={maxDiscount}
              onChange={setMaxDiscount}
              max={99}
            />
            <NumericField
              label="Новая скидка, %"
              value={targetDiscount}
              onChange={setTargetDiscount}
              max={99}
            />
            <RunButton
              loading={loading}
              onClick={runPromotion}
              label="Подготовить акцию"
            />
          </div>
        </section>
      ) : (
        <section className="marketplace-form-panel">
          <div className="marketplace-file-grid three">
            <FileField
              label="Все товары"
              file={productsFile}
              onChange={setProductsFile}
            />
            <FileField
              label="Подготовленная акция"
              file={boostPromotionFile}
              onChange={setBoostPromotionFile}
            />
            <FileField
              label="Шаблон Буста"
              file={templateFile}
              onChange={setTemplateFile}
            />
          </div>
          <div className="marketplace-options-row">
            <NumericField
              label="Ставка Буста, %"
              value={bid}
              onChange={setBid}
              min={0.1}
              max={99.9}
            />
            <RunButton
              loading={loading}
              onClick={runBoost}
              label="Собрать файл"
            />
          </div>
        </section>
      )}

      <ToolError message={error} />
      <ToolResult
        result={isPromotion ? promotionResult : boostResult}
        statItems={isPromotion ? PROMOTION_STATS : BOOST_STATS}
        columns={isPromotion ? PROMOTION_COLUMNS : BOOST_COLUMNS}
      />
    </div>
  );
}

function RunButton({ loading, onClick, label }) {
  return (
    <button
      className="marketplace-run-button"
      type="button"
      onClick={onClick}
      disabled={loading}
    >
      {loading ? (
        <LoaderCircle className="spin" size={17} />
      ) : (
        <Sparkles size={17} />
      )}
      {loading ? "Обрабатываю" : label}
    </button>
  );
}
