import { useMemo, useState } from "react";
import { AlertTriangle, LoaderCircle, Plus, Sparkles, X } from "lucide-react";
import ozonLogo from "../assets/ozon-icon.png";
import {
  BrandHeader,
  FileField,
  NumericField,
  ToggleField,
  ToolError,
  ToolResult,
} from "../components/MarketplaceToolKit";
import { runMarketplaceTool } from "../marketplaceToolsApi";
import "../marketplaceTools.css";

const RESULT_STATS = [
  { key: "total_product_rows", label: "Товарных строк" },
  { key: "in_discount_range", label: "В диапазоне" },
  { key: "excluded_direct_ads", label: "Исключено рекламой" },
  { key: "added_to_promo", label: "Добавлено в акцию" },
];

const formatPrice = (value) =>
  value === null || value === undefined
    ? "—"
    : `${Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ₽`;

function buildResultColumns({ excludedIdentifiers, onToggleExclude }) {
  return [
    { key: "article", label: "Артикул" },
    { key: "sku", label: "SKU" },
    { key: "product_name", label: "Товар" },
    {
      key: "your_price",
      label: "Цена без акции",
      format: formatPrice,
    },
    {
      key: "ozon_suggested_promo_price",
      label: "Цена по акции (Ozon)",
      format: formatPrice,
    },
    {
      key: "promo_price",
      label: "Цена по моей акции",
      format: (value, row) =>
        row.result === "Да" ? formatPrice(value) : "—",
    },
    {
      key: "discount_percent",
      label: "Скидка",
      format: (value) => {
        if (value === null || value === undefined) return "—";
        if (value < 0) {
          return (
            <span
              className="boosting-negative-discount"
              title="Цена для минимального бустинга теперь выше вашей текущей цены - похоже, цену на товар снизили, а порог бустинга остался старым"
            >
              <AlertTriangle size={12} aria-hidden="true" />
              {value}%
            </span>
          );
        }
        return `${value}%`;
      },
    },
    {
      key: "promo_discount_percent",
      label: "Скидка по акции",
      format: (value) => (value === null || value === undefined ? "—" : `${value}%`),
    },
    { key: "ad_status", label: "Реклама" },
    { key: "result", label: "Участие" },
    { key: "reason", label: "Решение" },
    {
      key: "__exclude_action",
      label: "Вручную",
      format: (_value, row) => {
        const identifier = row.article || row.sku;
        if (!identifier) return "—";
        const isExcluded = excludedIdentifiers.includes(identifier);
        return (
          <button
            type="button"
            className={
              isExcluded ? "boosting-exclude-button active" : "boosting-exclude-button"
            }
            onClick={() => onToggleExclude(identifier)}
          >
            {isExcluded ? "Вернуть" : "Исключить"}
          </button>
        );
      },
    },
  ];
}

const OVER_MAX_REASON = "Скидка для входа больше максимальной";

const hasNegativeDiscount = (row) =>
  row.discount_percent !== null && row.discount_percent !== undefined && row.discount_percent < 0;

const RESULT_FILTERS = [
  {
    key: "added",
    label: "Добавлено в акцию",
    predicate: (row) => row.result === "Да",
  },
  {
    key: "negative-discount",
    label: "Отрицательная скидка (цену снизили)",
    predicate: hasNegativeDiscount,
  },
  {
    key: "ads",
    label: "В рекламе",
    predicate: (row) => Boolean(row.ad_status),
  },
  {
    key: "over-max",
    label: "Скидка больше максимальной",
    predicate: (row) => row.reason === OVER_MAX_REASON,
  },
  {
    key: "other",
    label: "Не подошло по другой причине",
    predicate: (row) =>
      row.result !== "Да" &&
      !row.ad_status &&
      row.reason !== OVER_MAX_REASON &&
      !hasNegativeDiscount(row),
  },
];

const SEARCH_KEYS = ["article", "sku", "product_name"];

function ozonBoostingRowVariant(row) {
  if (row.result === "Да") return "success";
  if (hasNegativeDiscount(row)) return "negative";
  if (row.ad_status) return "warning";
  if (row.reason === OVER_MAX_REASON) return "danger";
  return "muted";
}

export default function OzonBoostingPage() {
  const [promoFile, setPromoFile] = useState(null);
  const [adsFile, setAdsFile] = useState(null);
  const [minDiscount, setMinDiscount] = useState("0.1");
  const [maxDiscount, setMaxDiscount] = useState("11");
  const [targetDiscount, setTargetDiscount] = useState("");
  const [excludeDirectAds, setExcludeDirectAds] = useState(true);
  const [strictUnionExclusion, setStrictUnionExclusion] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const [categories, setCategories] = useState([]);
  const [loadingCategories, setLoadingCategories] = useState(false);
  const [categoryToAdd, setCategoryToAdd] = useState("");
  const [categoryOverrides, setCategoryOverrides] = useState([]);

  const [excludedIdentifiers, setExcludedIdentifiers] = useState([]);

  const toggleExcludedIdentifier = (identifier) => {
    setExcludedIdentifiers((prev) =>
      prev.includes(identifier)
        ? prev.filter((item) => item !== identifier)
        : [...prev, identifier]
    );
  };

  const handlePromoFileChange = async (file) => {
    setPromoFile(file);
    setCategories([]);
    setCategoryOverrides([]);
    setCategoryToAdd("");
    setExcludedIdentifiers([]);
    if (!file) return;

    setLoadingCategories(true);
    try {
      const form = new FormData();
      form.append("promo_file", file);
      const payload = await runMarketplaceTool(
        "/api/tools/ozon-elastic-boosting/categories",
        form
      );
      setCategories(payload.categories || []);
    } catch {
      // category list is a convenience picker - a failed load just leaves it empty
    } finally {
      setLoadingCategories(false);
    }
  };

  const addCategoryOverride = () => {
    if (!categoryToAdd) return;
    if (categoryOverrides.some((item) => item.category === categoryToAdd)) return;
    setCategoryOverrides((prev) => [
      ...prev,
      { category: categoryToAdd, minDiscount: minDiscount, maxDiscount: maxDiscount, exclude: false },
    ]);
    setCategoryToAdd("");
  };

  const addAllCategoryOverrides = () => {
    const remaining = categories.filter(
      (item) => !categoryOverrides.some((o) => o.category === item.category)
    );
    if (remaining.length === 0) return;
    setCategoryOverrides((prev) => [
      ...prev,
      ...remaining.map((item) => ({
        category: item.category,
        minDiscount: minDiscount,
        maxDiscount: maxDiscount,
        exclude: false,
      })),
    ]);
    setCategoryToAdd("");
  };

  const excludeAllCategoryOverrides = () => {
    setCategoryOverrides((prev) => prev.map((item) => ({ ...item, exclude: true })));
  };

  const updateCategoryOverride = (category, patch) => {
    setCategoryOverrides((prev) =>
      prev.map((item) => (item.category === category ? { ...item, ...patch } : item))
    );
  };

  const removeCategoryOverride = (category) => {
    setCategoryOverrides((prev) => prev.filter((item) => item.category !== category));
  };

  const resultColumns = useMemo(
    () => buildResultColumns({ excludedIdentifiers, onToggleExclude: toggleExcludedIdentifier }),
    [excludedIdentifiers]
  );

  const processFiles = async () => {
    if (!promoFile || !adsFile) {
      setError("Загрузите шаблон акции и отчёт продвижения Ozon");
      return;
    }
    const form = new FormData();
    form.append("promo_file", promoFile);
    form.append("ads_file", adsFile);
    form.append("min_discount", minDiscount);
    form.append("max_discount", maxDiscount);
    form.append("exclude_direct_ads", String(excludeDirectAds));
    form.append("strict_union_exclusion", String(strictUnionExclusion));
    if (targetDiscount !== "") {
      form.append("target_discount_percent", targetDiscount);
    }
    form.append(
      "category_overrides_json",
      JSON.stringify(
        categoryOverrides.map((item) => ({
          category: item.category,
          exclude: item.exclude,
          min_discount:
            !item.exclude && item.minDiscount !== "" ? Number(item.minDiscount) : null,
          max_discount:
            !item.exclude && item.maxDiscount !== "" ? Number(item.maxDiscount) : null,
        }))
      )
    );
    form.append("excluded_identifiers_json", JSON.stringify(excludedIdentifiers));
    setLoading(true);
    setError("");
    try {
      setResult(await runMarketplaceTool("/api/tools/ozon-elastic-boosting", form));
    } catch (requestError) {
      setResult(null);
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="marketplace-tool-page">
      <BrandHeader
        logo={ozonLogo}
        logoAlt="Ozon"
        eyebrow="Ozon"
        title="Эластичный бустинг"
        description="Отбор товаров в акцию с исключением рекламируемых SKU"
      />

      <section className="marketplace-form-panel">
        <div className="marketplace-file-grid">
          <FileField label="Шаблон акции" file={promoFile} onChange={handlePromoFileChange} />
          <FileField label="Отчёт продвижения" file={adsFile} onChange={setAdsFile} />
        </div>
        <div className="marketplace-options-row">
          <NumericField
            label="Скидка от, %"
            value={minDiscount}
            onChange={setMinDiscount}
            min={-100}
            max={100}
          />
          <NumericField
            label="Скидка до, %"
            value={maxDiscount}
            onChange={setMaxDiscount}
            min={-100}
            max={100}
          />
          <NumericField
            label="Скидка для акции, %"
            value={targetDiscount}
            onChange={setTargetDiscount}
            max={99}
          />
          <ToggleField
            label="Исключать прямую рекламу"
            checked={excludeDirectAds}
            onChange={setExcludeDirectAds}
          />
          <ToggleField
            label="Учитывать объединённые карточки"
            checked={strictUnionExclusion}
            onChange={setStrictUnionExclusion}
          />
          <button
            className="marketplace-run-button"
            type="button"
            onClick={processFiles}
            disabled={loading}
          >
            {loading ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <Sparkles size={17} />
            )}
            {loading ? "Обрабатываю" : "Сформировать"}
          </button>
        </div>
        <p className="boosting-category-hint">
          «Скидка от/до» теперь можно задавать и отрицательной (например
          −3…5%) — так в отбор попадут и товары, у которых цена уже
          опустилась ниже порога минимального бустинга. «Скидка для акции» —
          необязательно: если задать, всем товарам, прошедшим отбор,
          проставится именно эта скидка от «Вашей цены». Если оставить
          пустым, останется предложенная Ozon цена из шаблона (а для
          отрицательных — «Ваша цена» без скидки).
        </p>

        {promoFile && (
          <div className="boosting-category-panel">
            <div className="boosting-category-header">
              <span className="marketplace-field-label">
                Отдельные правила по категориям (необязательно)
              </span>
              <p className="boosting-category-hint">
                Для выбранной категории можно задать свой диапазон «скидка
                от/до» вместо общего выше, или исключить всю категорию из
                акции
              </p>
            </div>

            <div className="boosting-category-add-row">
              <select
                value={categoryToAdd}
                onChange={(event) => setCategoryToAdd(event.target.value)}
                disabled={loadingCategories || categories.length === 0}
              >
                <option value="">
                  {loadingCategories
                    ? "Загружаю категории…"
                    : categories.length === 0
                    ? "Категории не найдены в файле"
                    : "Выберите категорию"}
                </option>
                {categories
                  .filter(
                    (item) =>
                      !categoryOverrides.some((o) => o.category === item.category)
                  )
                  .map((item) => (
                    <option key={item.category} value={item.category}>
                      {item.category} ({item.product_count})
                    </option>
                  ))}
              </select>
              <button
                type="button"
                className="boosting-category-add-button"
                onClick={addCategoryOverride}
                disabled={!categoryToAdd}
              >
                <Plus size={15} />
                Добавить категорию
              </button>
              <button
                type="button"
                className="boosting-category-add-all-button"
                onClick={addAllCategoryOverrides}
                disabled={
                  categories.length === 0 ||
                  categories.every((item) =>
                    categoryOverrides.some((o) => o.category === item.category)
                  )
                }
              >
                <Plus size={15} />
                Выбрать все
              </button>
              <button
                type="button"
                className="boosting-category-exclude-all-button"
                onClick={excludeAllCategoryOverrides}
                disabled={
                  categoryOverrides.length === 0 ||
                  categoryOverrides.every((item) => item.exclude)
                }
              >
                <X size={15} />
                Исключить все из акции
              </button>
            </div>

            {categoryOverrides.length > 0 && (
              <div className="boosting-category-list">
                {categoryOverrides.map((item) => (
                  <div key={item.category} className="boosting-category-row">
                    <strong className="boosting-category-name">{item.category}</strong>

                    <label className="boosting-category-exclude">
                      <input
                        type="checkbox"
                        checked={item.exclude}
                        onChange={(event) =>
                          updateCategoryOverride(item.category, {
                            exclude: event.target.checked,
                          })
                        }
                      />
                      Исключить из акции
                    </label>

                    <label className="boosting-category-range-field">
                      <span>от, %</span>
                      <input
                        type="number"
                        step="0.1"
                        min="0"
                        max="99"
                        value={item.minDiscount}
                        disabled={item.exclude}
                        onChange={(event) =>
                          updateCategoryOverride(item.category, {
                            minDiscount: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label className="boosting-category-range-field">
                      <span>до, %</span>
                      <input
                        type="number"
                        step="0.1"
                        min="0"
                        max="99"
                        value={item.maxDiscount}
                        disabled={item.exclude}
                        onChange={(event) =>
                          updateCategoryOverride(item.category, {
                            maxDiscount: event.target.value,
                          })
                        }
                      />
                    </label>

                    <button
                      type="button"
                      className="boosting-category-remove"
                      onClick={() => removeCategoryOverride(item.category)}
                      aria-label={`Убрать правило для «${item.category}»`}
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      {excludedIdentifiers.length > 0 && (
        <div className="boosting-category-panel">
          <div className="boosting-category-header">
            <span className="marketplace-field-label">
              Исключено вручную ({excludedIdentifiers.length})
            </span>
            <p className="boosting-category-hint">
              Найдите товар через поиск в результатах ниже и нажмите
              «Исключить» в столбце «Вручную», либо верните его тем же
              нажатием («Вернуть»). Чтобы исключения применились к файлу,
              нажмите «Сформировать» ещё раз.
            </p>
          </div>
          <div className="boosting-category-chips">
            {excludedIdentifiers.map((identifier) => (
              <div key={identifier} className="boosting-category-chip">
                <strong>{identifier}</strong>
                <button
                  type="button"
                  onClick={() => toggleExcludedIdentifier(identifier)}
                  aria-label={`Вернуть ${identifier}`}
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <ToolError message={error} />
      <ToolResult
        result={result}
        statItems={RESULT_STATS}
        columns={resultColumns}
        filters={RESULT_FILTERS}
        searchKeys={SEARCH_KEYS}
        searchPlaceholder="Поиск по артикулу, SKU или названию"
        rowVariant={ozonBoostingRowVariant}
      />
    </div>
  );
}
