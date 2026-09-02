import json
from io import BytesIO
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from app.api.auth import require_dashboard_auth
from app.api.schemas import (
    AnalyzeRequest,
    CompetitorImportResponse,
    CompetitorOffersImportRequest,
    CompetitorOverrideRequest,
    DashboardResponse,
    OzonCategoryTreeCheckResponse,
    OzonPerformanceStatusResponse,
    OzonPerformanceTokenCheckResponse,
    OzonProductListItem,
    OzonProductListResponse,
    OzonSellerAnalyticsAccessCheckResponse,
    OzonSellerAnalyticsImportResponse,
    OzonSellerAnalyticsPlanResponse,
    OzonSellerAnalyticsStatusResponse,
    OzonStatusResponse,
    ShortlistResponse,
    ShortlistStockRefreshResponse,
    ShortlistUpdateRequest,
)
from app.core.config import get_settings
from app.domain.models import (
    CompetitorImportResult,
    CompetitorOffer,
    DataSource,
    EconomicsInput,
    ImportIssue,
    PriceImportVersion,
    ProductAnalysis,
    ShortlistEntry,
    ShortlistItem,
    SupplierProduct,
)
from app.domain.stock import StockApplyResult, StockSnapshot
from app.domain.purchase_prices import PurchasePriceApplyResult, PurchasePriceSnapshot
from app.domain.unitka import (
    UnitkaAssumptions,
    UnitkaImportResult,
    UnitkaItem,
    UnitkaRow,
)
from app.ingestion.excel_importer import ExcelImportService
from app.repositories.products import repository
from app.services.analysis import ProductAnalysisService
from app.services.competitor_import import CompetitorImportService
from app.services.economics import EconomicsService
from app.services.excel_export import UnitEconomicsExcelExporter
from app.services.ozon_client import OzonClientFactory, OzonPerformanceClientFactory
from app.services.stock_monitor import (
    StockMonitorNotConfigured,
    apply_stock_to_ozon,
    refresh_snapshot,
)
from app.services.stock_storage import latest_snapshot as latest_stock_snapshot
from app.services.purchase_price_monitor import (
    PurchasePriceMonitorNotConfigured,
    apply_purchase_prices,
    refresh_purchase_prices,
)
from app.services.unitka_engine import compute_row
from app.services.unitka_importer import read_assumptions as import_read_assumptions
from app.services.unitka_importer import read_rows as import_read_rows
from app.services.unitka_storage import (
    create_row as unitka_create_row,
)
from app.services.unitka_storage import (
    delete_row as unitka_delete_row,
)
from app.services.unitka_storage import (
    get_assumptions as unitka_get_assumptions,
)
from app.services.unitka_storage import (
    get_row as unitka_get_row,
)
from app.services.unitka_storage import (
    list_rows as unitka_list_rows,
)
from app.services.unitka_storage import (
    save_assumptions as unitka_save_assumptions,
)
from app.services.unitka_storage import (
    update_row as unitka_update_row,
)
from app.services.ozon_seller_analytics import (
    OzonBestsellersImportRequest,
    OzonBestsellersRequest,
    OzonSellerAnalyticsAccessCheck,
    OzonSellerAnalyticsClient,
    OzonSellerAnalyticsFactory,
)

router = APIRouter(dependencies=[Depends(require_dashboard_auth)])
excel_importer = ExcelImportService()
analysis_service = ProductAnalysisService()
economics_service = EconomicsService()
competitor_importer = CompetitorImportService()
excel_exporter = UnitEconomicsExcelExporter()
ozon_factory = OzonClientFactory(get_settings())
ozon_performance_factory = OzonPerformanceClientFactory(get_settings())
ozon_seller_analytics_factory = OzonSellerAnalyticsFactory(get_settings())


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": get_settings().app_name}


@router.post("/imports/prices", response_model=PriceImportVersion)
async def upload_price(
    file: Annotated[UploadFile, File(...)],
    supplier_name: Annotated[str | None, Form()] = None,
) -> PriceImportVersion:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Файл должен иметь имя.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой.")
    version = excel_importer.import_bytes(content, file.filename, supplier_name)
    return repository.save_import(version)


@router.get("/imports", response_model=list[PriceImportVersion])
def list_imports() -> list[PriceImportVersion]:
    return repository.list_versions()


@router.get("/products", response_model=list[SupplierProduct])
def list_products() -> list[SupplierProduct]:
    return repository.list_products()


@router.post("/imports/competitors", response_model=CompetitorImportResponse)
async def upload_competitors(file: Annotated[UploadFile, File(...)]) -> CompetitorImportResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Файл должен иметь имя.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой.")

    products = repository.list_products()
    result, matches = competitor_importer.import_bytes(content, file.filename, products)
    products_by_id = {product.id: product for product in products}
    for product_id, offer in matches.items():
        product = products_by_id.get(product_id)
        if product is not None:
            repository.save_competitor_offer(product, offer, offer.source)

    analyses = _analysis_rows()
    return CompetitorImportResponse(
        result=result,
        kpi=analysis_service.kpi(analyses),
        rows=analyses,
    )


@router.post("/imports/competitors/offers", response_model=CompetitorImportResponse)
def import_competitor_offers(request: CompetitorOffersImportRequest) -> CompetitorImportResponse:
    products = repository.list_products()
    offers = [
        _normalized_competitor_offer(offer)
        for offer in request.offers
        if offer.price_vat_included > 0 and offer.title.strip()
    ]
    matches, issues = competitor_importer.match_offers(offers, products)
    products_by_id = {product.id: product for product in products}
    for product_id, offer in matches.items():
        product = products_by_id.get(product_id)
        if product is not None:
            repository.save_competitor_offer(product, offer, DataSource.API)

    result = CompetitorImportResult(
        filename=request.filename,
        imported_rows=len(offers),
        matched_products=len(matches),
        skipped_rows=max(len(request.offers) - len(offers), 0),
        source=DataSource.API,
        issues=issues[:50],
    )
    analyses = _analysis_rows()
    return CompetitorImportResponse(
        result=result,
        kpi=analysis_service.kpi(analyses),
        rows=analyses,
    )


def _normalized_competitor_offer(offer: CompetitorOffer) -> CompetitorOffer:
    price = offer.price_vat_included
    if offer.avg_purchase_price is not None and price < offer.avg_purchase_price * 0.3:
        price = offer.avg_purchase_price
    return offer.model_copy(
        update={
            "price_vat_included": price,
            "source": DataSource.API,
        }
    )


@router.post("/products/{product_id}/analysis", response_model=ProductAnalysis)
def analyze_product(product_id: str, request: AnalyzeRequest) -> ProductAnalysis:
    product = repository.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не найден.")
    competitor = repository.get_competitor_snapshot(product)
    sale_price = request.sale_price_vat_included or analysis_service.starter_price(
        product,
        competitor,
    )
    economics = economics_service.calculate(
        EconomicsInput(
            product=product,
            sale_price_vat_included=sale_price,
            competitor=competitor,
            package_cost=request.package_cost,
            fulfillment_processing_cost=request.fulfillment_processing_cost,
            advertising_drr_percent=request.advertising_drr_percent,
            ozon_visible_discount_percent=request.ozon_visible_discount_percent,
            bank_card_discount_percent=request.bank_card_discount_percent,
            discount_percent=request.discount_percent,
            seller_bonus_percent=request.seller_bonus_percent,
            partner_program_percent=request.partner_program_percent,
            delivery_accrual_percent=request.delivery_accrual_percent,
            tax_regime=request.tax_regime,
            use_vat=request.use_vat,
            usn_tax_rate=request.usn_tax_rate,
            usn_additional_contribution_rate=request.usn_additional_contribution_rate,
            fast_payout_fee_percent=request.fast_payout_fee_percent,
            designer_content_percent=request.designer_content_percent,
            business_fulfillment_pickup_percent=request.business_fulfillment_pickup_percent,
        )
    )
    return ProductAnalysis(
        product=product,
        economics=economics,
        competitor=competitor,
        readiness=analysis_service._readiness(product, economics, competitor),
    )


@router.post("/products/{product_id}/competitor", response_model=ProductAnalysis)
def save_competitor_override(
    product_id: str,
    request: CompetitorOverrideRequest,
) -> ProductAnalysis:
    product = repository.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не найден.")
    offer = CompetitorOffer(
        title=(request.title or product.title).strip(),
        price_vat_included=float(request.price_vat_included),
        url=str(request.url),
        match_type=request.match_type,
    )
    competitor = repository.save_competitor_override(product, offer)
    return analysis_service.analyze_product(product, competitor=competitor)


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard() -> DashboardResponse:
    analyses = _analysis_rows()
    return DashboardResponse(kpi=analysis_service.kpi(analyses), rows=analyses)


@router.get("/shortlist", response_model=ShortlistResponse)
def shortlist() -> ShortlistResponse:
    return ShortlistResponse(items=_shortlist_items())


@router.post("/shortlist/refresh-stocks", response_model=ShortlistStockRefreshResponse)
def refresh_shortlist_stocks() -> ShortlistStockRefreshResponse:
    latest_products: dict[tuple[str, str, str], SupplierProduct] = {}
    for product in repository.list_products():
        key = _supplier_product_key(
            product.supplier_name,
            product.supplier_article,
            product.title,
        )
        latest_products[key] = product

    matched = 0
    updated = 0
    unmatched = 0
    for entry in repository.list_shortlist_entries():
        snapshot = _shortlist_base_product(entry)
        if snapshot is None:
            unmatched += 1
            continue
        product = latest_products.get(
            _supplier_product_key(entry.supplier_name, entry.supplier_article, snapshot.title)
        )
        if product is None:
            unmatched += 1
            continue
        matched += 1
        if snapshot.stock == product.stock:
            continue
        repository.save_shortlist_entry(
            entry.model_copy(
                update={"product_snapshot": snapshot.model_copy(update={"stock": product.stock})}
            )
        )
        updated += 1

    return ShortlistStockRefreshResponse(
        matched=matched,
        updated=updated,
        unmatched=unmatched,
        items=_shortlist_items(),
    )


@router.post("/imports/shortlist", response_model=ShortlistResponse)
async def upload_shortlist(file: Annotated[UploadFile, File(...)]) -> ShortlistResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Файл должен иметь имя.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой.")
    try:
        payload = json.loads(content.decode("utf-8-sig"))
        entries = _shortlist_entries_from_payload(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as error:
        raise HTTPException(status_code=400, detail="Не удалось прочитать файл отбора.") from error

    for entry in entries:
        product = repository.get_product_by_supplier_article(
            entry.supplier_article,
            entry.supplier_name,
        )
        if product is None and entry.product_snapshot is None:
            continue
        source = repository.get_product_import_source(product.id) if product is not None else None
        repository.save_shortlist_entry(
            _entry_with_product_snapshot(entry, product, source),
        )
    return ShortlistResponse(items=_shortlist_items())


@router.post("/shortlist/products/{product_id}", response_model=ShortlistItem)
def add_shortlist_product(
    product_id: str,
    request: ShortlistUpdateRequest | None = None,
) -> ShortlistItem:
    patch = request or ShortlistUpdateRequest()
    product = repository.get_product(product_id)
    if product is None and patch.supplier_article:
        candidate = repository.get_product_by_supplier_article(
            patch.supplier_article,
            patch.supplier_name,
        )
        if candidate is not None and patch.product_title:
            expected_key = _supplier_product_key(
                patch.supplier_name or candidate.supplier_name,
                patch.supplier_article,
                patch.product_title,
            )
            candidate_key = _supplier_product_key(
                candidate.supplier_name,
                candidate.supplier_article,
                candidate.title,
            )
            if expected_key != candidate_key:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Прайс обновился, но артикул теперь относится к другому товару. "
                        "Обновите каталог и повторите выбор."
                    ),
                )
        product = candidate
    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Товар больше не найден в текущем прайсе. Обновите каталог.",
        )
    existing = repository.get_shortlist_entry(
        product.supplier_article,
        product.supplier_name,
    )
    base_analysis = analysis_service.analyze_product(
        product,
        competitor=repository.get_competitor_snapshot(product),
    )
    source = repository.get_product_import_source(product.id) if existing is None else None
    snapshot_product = product if existing is None else existing.product_snapshot or product
    base_entry = existing or ShortlistEntry(
        supplier_name=product.supplier_name,
        supplier_article=product.supplier_article,
        product_id=product.id,
        sale_price_vat_included=(base_analysis.economics.real_fbs_price_vat_included),
    )
    entry = _merge_shortlist_patch(
        _entry_with_product_snapshot(base_entry, snapshot_product, source),
        patch,
    )
    saved = repository.save_shortlist_entry(entry)
    return _shortlist_item(saved)


@router.patch("/shortlist/products/{product_id}", response_model=ShortlistItem)
def update_shortlist_product(product_id: str, request: ShortlistUpdateRequest) -> ShortlistItem:
    product = repository.get_product(product_id)
    existing = None
    if product is not None:
        existing = repository.get_shortlist_entry(
            product.supplier_article,
            product.supplier_name,
        )
    if existing is None:
        existing = repository.get_shortlist_entry_by_product_id(product_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Товар не найден в отборе.")
    source = repository.get_product_import_source(product.id) if product is not None else None
    entry = _merge_shortlist_patch(
        _entry_with_product_snapshot(existing, product, source),
        request,
    )
    saved = repository.save_shortlist_entry(entry)
    return _shortlist_item(saved)


@router.delete("/shortlist/products/{product_id}", status_code=204)
def delete_shortlist_product(product_id: str) -> Response:
    product = repository.get_product(product_id)
    existing = None
    if product is not None:
        existing = repository.get_shortlist_entry(
            product.supplier_article,
            product.supplier_name,
        )
    if existing is None:
        existing = repository.get_shortlist_entry_by_product_id(product_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Товар не найден.")
    repository.delete_shortlist_entry(existing.supplier_article, existing.supplier_name)
    return Response(status_code=204)


@router.get("/exports/unit-economics.xlsx")
def export_unit_economics() -> Response:
    analyses = _analysis_rows()
    content = excel_exporter.export(analyses, analysis_service.kpi(analyses))
    return Response(
        content=content,
        media_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        headers={"Content-Disposition": 'attachment; filename="leto-sm-unit-economics.xlsx"'},
    )


@router.get("/exports/shortlist.xlsx")
def export_shortlist() -> Response:
    content = excel_exporter.export_shortlist(_shortlist_items())
    return Response(
        content=content,
        media_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        headers={"Content-Disposition": 'attachment; filename="leto-sm-shortlist.xlsx"'},
    )


@router.get("/exports/shortlist.json")
def export_shortlist_file() -> Response:
    payload = {
        "format": "leto-sm-shortlist",
        "version": 1,
        "items": [{"entry": item.entry.model_dump(mode="json")} for item in _shortlist_items()],
    }
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="leto-sm-shortlist.json"'},
    )


def _analysis_rows() -> list[ProductAnalysis]:
    return [
        analysis_service.analyze_product(
            product,
            competitor=repository.get_competitor_snapshot(product),
        )
        for product in repository.list_products()
    ]


def _shortlist_entries_from_payload(payload: object) -> list[ShortlistEntry]:
    raw_items: object = payload.get("items", []) if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        raise HTTPException(status_code=400, detail="Файл отбора должен содержать список товаров.")

    entries: list[ShortlistEntry] = []
    for raw_item in raw_items:
        raw_entry = raw_item.get("entry", raw_item) if isinstance(raw_item, dict) else raw_item
        entries.append(ShortlistEntry.model_validate(raw_entry))
    return entries


def _shortlist_items() -> list[ShortlistItem]:
    items: list[ShortlistItem] = []
    for entry in repository.list_shortlist_entries():
        product = _shortlist_base_product(entry)
        if product is None:
            continue
        product = _with_current_supplier_stock(entry, product)
        current_entry = _entry_with_product_snapshot(
            entry,
            product,
            repository.get_product_import_source(product.id),
        )
        if current_entry != entry:
            repository.save_shortlist_entry(current_entry)
        items.append(_shortlist_item(current_entry, product))
    return items


def _with_current_supplier_stock(
    entry: ShortlistEntry,
    snapshot: SupplierProduct,
) -> SupplierProduct:
    current = repository.get_product_by_supplier_article(
        entry.supplier_article,
        entry.supplier_name,
    )
    if current is None:
        return snapshot
    if _supplier_product_key(
        current.supplier_name,
        current.supplier_article,
        current.title,
    ) != _supplier_product_key(
        snapshot.supplier_name,
        snapshot.supplier_article,
        snapshot.title,
    ):
        return snapshot
    return snapshot.model_copy(update={"stock": current.stock})


def _supplier_product_key(
    supplier_name: str,
    supplier_article: str,
    title: str,
) -> tuple[str, str, str]:
    return (
        " ".join(supplier_name.casefold().split()),
        " ".join(supplier_article.casefold().split()),
        " ".join(title.casefold().replace("ё", "е").split()),
    )


def _shortlist_item(
    entry: ShortlistEntry,
    product: SupplierProduct | None = None,
) -> ShortlistItem:
    selected_product = product or _shortlist_base_product(entry)
    if selected_product is None:
        raise HTTPException(status_code=404, detail="Товар из отбора не найден в текущем прайсе.")
    selected_product = _product_with_shortlist_overrides(selected_product, entry)
    competitor = repository.get_competitor_snapshot(selected_product)
    analysis = analysis_service.analyze_product(
        selected_product,
        sale_price_vat_included=entry.sale_price_vat_included,
        competitor=competitor,
        seller_bonus_percent=entry.seller_bonus_percent,
        advertising_drr_percent=entry.advertising_drr_percent,
        package_cost=entry.package_cost,
        fulfillment_processing_cost=entry.fulfillment_processing_cost,
    )
    return ShortlistItem(
        entry=entry.model_copy(update={"product_id": selected_product.id}),
        analysis=analysis,
    )


def _shortlist_base_product(entry: ShortlistEntry) -> SupplierProduct | None:
    if entry.product_snapshot is not None:
        return entry.product_snapshot
    return repository.get_product_by_supplier_article(entry.supplier_article, entry.supplier_name)


def _entry_with_product_snapshot(
    entry: ShortlistEntry,
    product: SupplierProduct | None,
    source: tuple[str, str] | None,
) -> ShortlistEntry:
    selected_product = product or entry.product_snapshot
    if selected_product is None:
        return entry
    updates: dict[str, object] = {
        "supplier_name": selected_product.supplier_name,
        "supplier_article": selected_product.supplier_article,
        "product_id": selected_product.id,
        "product_snapshot": selected_product,
    }
    if entry.length_cm is None:
        updates["length_cm"] = selected_product.dimensions.length_cm
    if entry.width_cm is None:
        updates["width_cm"] = selected_product.dimensions.width_cm
    if entry.height_cm is None:
        updates["height_cm"] = selected_product.dimensions.height_cm
    if entry.purchase_price_vat_included is None:
        updates["purchase_price_vat_included"] = selected_product.purchase_price_vat_included
    if source is not None:
        updates["source_import_filename"] = source[0]
        updates["source_imported_at"] = source[1]
    elif entry.source_import_filename is None:
        updates["source_import_filename"] = "сохраненный отбор"
    return entry.model_copy(update=updates)


def _merge_shortlist_patch(
    entry: ShortlistEntry,
    request: ShortlistUpdateRequest,
) -> ShortlistEntry:
    updates: dict[str, object] = {}
    for field in (
        "group_name",
        "subgroup_name",
        "offer_quantity",
        "purchase_price_vat_included",
        "sale_price_vat_included",
        "length_cm",
        "width_cm",
        "height_cm",
        "seller_bonus_percent",
        "advertising_drr_percent",
        "package_cost",
        "fulfillment_processing_cost",
        "planned_sales_qty",
        "sold_qty",
        "note",
    ):
        value = getattr(request, field)
        if value is not None:
            updates[field] = float(value) if field.endswith("_percent") else value
    return entry.model_copy(update=updates)


def _product_with_shortlist_overrides(
    product: SupplierProduct,
    entry: ShortlistEntry,
) -> SupplierProduct:
    dimensions = product.dimensions.model_copy(
        update={
            "length_cm": entry.length_cm
            if entry.length_cm is not None
            else product.dimensions.length_cm,
            "width_cm": entry.width_cm
            if entry.width_cm is not None
            else product.dimensions.width_cm,
            "height_cm": entry.height_cm
            if entry.height_cm is not None
            else product.dimensions.height_cm,
        }
    )
    purchase_price_per_unit = (
        entry.purchase_price_vat_included
        if entry.purchase_price_vat_included is not None
        else product.purchase_price_vat_included
    )
    purchase_price = purchase_price_per_unit * entry.offer_quantity
    return product.model_copy(
        update={
            "dimensions": dimensions,
            "purchase_price_vat_included": purchase_price,
        }
    )


@router.get("/ozon/status", response_model=OzonStatusResponse)
def ozon_status() -> OzonStatusResponse:
    return OzonStatusResponse(integration=ozon_factory.status())


@router.post("/ozon/check-category-tree", response_model=OzonCategoryTreeCheckResponse)
async def ozon_check_category_tree() -> OzonCategoryTreeCheckResponse:
    if not ozon_factory.status().configured:
        raise HTTPException(status_code=400, detail=ozon_factory.status().message)

    try:
        response = await ozon_factory.create().get_description_category_tree()
    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=error.response.status_code,
            detail="Ozon API отклонил запрос. Проверьте Client ID, API key и права токена.",
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Ошибка связи с Ozon API: {error}") from error

    result = response.get("result")
    categories = result if isinstance(result, list) else []
    return OzonCategoryTreeCheckResponse(
        ok=True,
        categories_count=len(categories),
        message="Дерево категорий Ozon успешно получено.",
    )


@router.get("/ozon/products", response_model=OzonProductListResponse)
async def ozon_products(limit: int = 10, visibility: str = "ALL") -> OzonProductListResponse:
    if not ozon_factory.status().configured:
        raise HTTPException(status_code=400, detail=ozon_factory.status().message)

    try:
        response = await ozon_factory.create().list_products(limit=limit, visibility=visibility)
    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=error.response.status_code,
            detail="Ozon API отклонил запрос. Проверьте Client ID, API key и права токена.",
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Ошибка связи с Ozon API: {error}") from error

    result = response.get("result")
    if not isinstance(result, dict):
        return OzonProductListResponse(ok=True, total_returned=0, last_id=None, items=[])

    raw_items = result.get("items")
    item_rows = raw_items if isinstance(raw_items, list) else []
    items = [
        OzonProductListItem(
            product_id=item.get("product_id") or item.get("id"),
            offer_id=str(item.get("offer_id")) if item.get("offer_id") else None,
        )
        for item in item_rows
        if isinstance(item, dict)
    ]

    return OzonProductListResponse(
        ok=True,
        total_returned=len(items),
        last_id=str(result.get("last_id")) if result.get("last_id") else None,
        items=items,
    )


@router.get("/ozon/orders")
async def ozon_orders(
    days: int = 7,
) -> dict[str, object]:
    if not ozon_factory.status().configured:
        raise HTTPException(status_code=400, detail=ozon_factory.status().message)

    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    try:
        response = await ozon_factory.create().list_orders(
            since=since,
            to=now,
            limit=1000,
        )
    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=error.response.status_code,
            detail="Ozon API отклонил запрос. Проверьте Client ID, API key и права токена.",
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Ошибка связи с Ozon API: {error}") from error

    # Ozon /v3/posting/fbs/list вкладывает список в "result", не в корень ответа —
    # response.get("postings") тут всегда был бы None, поэтому total_orders всегда
    # выходил 0 независимо от реальных данных.
    result = response.get("result", {})
    postings = result.get("postings", []) if isinstance(result, dict) else []

    total_revenue = 0.0
    total_orders = len(postings)
    total_qty = 0
    daily: dict[str, dict[str, float]] = {}

    for posting in postings:
        if not isinstance(posting, dict):
            continue
        date_str = posting.get("in_process_at", "")[:10] or posting.get("created_at", "")[:10]
        if date_str not in daily:
            daily[date_str] = {"revenue": 0.0, "orders": 0, "qty": 0}
        daily[date_str]["orders"] += 1

        products = posting.get("products", [])
        if isinstance(products, list):
            for product in products:
                if not isinstance(product, dict):
                    continue
                try:
                    price = float(product.get("price", "0"))
                    quantity = int(product.get("quantity", 1) or 1)
                except (ValueError, TypeError):
                    continue
                # Цена в ответе Ozon — за ЕДИНИЦУ товара, не за всю строку заказа —
                # без умножения на quantity выручка занижалась при quantity > 1.
                line_revenue = price * quantity
                total_revenue += line_revenue
                total_qty += quantity
                daily[date_str]["revenue"] += line_revenue
                daily[date_str]["qty"] += quantity

    return {
        "ok": True,
        "period_days": days,
        "total_orders": total_orders,
        "total_revenue": round(total_revenue, 2),
        "total_qty": total_qty,
        "daily": [
            {
                "date": d,
                "orders": v["orders"],
                "revenue": round(v["revenue"], 2),
                "qty": int(v["qty"]),
            }
            for d, v in sorted(daily.items())
        ],
    }


@router.get("/ozon/performance/status", response_model=OzonPerformanceStatusResponse)
def ozon_performance_status() -> OzonPerformanceStatusResponse:
    return OzonPerformanceStatusResponse(integration=ozon_performance_factory.status())


@router.post(
    "/ozon/performance/check-token",
    response_model=OzonPerformanceTokenCheckResponse,
)
async def ozon_performance_check_token() -> OzonPerformanceTokenCheckResponse:
    if not ozon_performance_factory.status().configured:
        raise HTTPException(status_code=400, detail=ozon_performance_factory.status().message)

    try:
        result = await ozon_performance_factory.create().check_token()
    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=error.response.status_code,
            detail="Ozon Performance API отклонил запрос. Проверьте client id/secret.",
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=502,
            detail=f"Ошибка связи с Ozon Performance API: {error}",
        ) from error

    return OzonPerformanceTokenCheckResponse(result=result)


@router.get(
    "/ozon/seller-analytics/status",
    response_model=OzonSellerAnalyticsStatusResponse,
)
def ozon_seller_analytics_status() -> OzonSellerAnalyticsStatusResponse:
    return OzonSellerAnalyticsStatusResponse(integration=ozon_seller_analytics_factory.status())


@router.post(
    "/ozon/seller-analytics/check-access",
    response_model=OzonSellerAnalyticsAccessCheckResponse,
)
async def ozon_seller_analytics_check_access() -> OzonSellerAnalyticsAccessCheckResponse:
    status = ozon_seller_analytics_factory.status()
    if not status.configured:
        return OzonSellerAnalyticsAccessCheckResponse(
            result=OzonSellerAnalyticsAccessCheck(
                ok=False,
                configured=False,
                message=(
                    "Нет OZON_SELLER_WEB_COOKIE в backend/.env. "
                    "Автосбор пока выключен, XLSX-импорт остается доступен."
                ),
                warning=status.warning,
            )
        )

    try:
        result = await ozon_seller_analytics_factory.create().check_access()
    except httpx.HTTPStatusError as error:
        result = OzonSellerAnalyticsAccessCheck(
            ok=False,
            configured=True,
            status_code=error.response.status_code,
            message=(
                "Ozon Seller web-API отклонил тестовый запрос. "
                "Вероятно, cookie устарел или не хватает авторизации кабинета."
            ),
            warning=status.warning,
        )
    except httpx.HTTPError as error:
        result = OzonSellerAnalyticsAccessCheck(
            ok=False,
            configured=True,
            message=f"Ошибка связи с Ozon Seller web-API: {error}",
            warning=status.warning,
        )
    except ValueError as error:
        result = OzonSellerAnalyticsAccessCheck(
            ok=False,
            configured=True,
            message=f"Ozon Seller вернул неожиданный формат: {error}",
            warning=status.warning,
        )

    return OzonSellerAnalyticsAccessCheckResponse(result=result)


@router.post(
    "/ozon/seller-analytics/bestsellers-plan",
    response_model=OzonSellerAnalyticsPlanResponse,
)
def ozon_seller_analytics_bestsellers_plan(
    request: OzonBestsellersRequest,
) -> OzonSellerAnalyticsPlanResponse:
    client = ozon_seller_analytics_factory.create_planner()
    return OzonSellerAnalyticsPlanResponse(
        request=request,
        json_endpoint=OzonSellerAnalyticsClient.data_endpoint,
        json_payload=client.build_bestsellers_payload(request),
        report_endpoint=OzonSellerAnalyticsClient.report_create_endpoint,
        report_payload=client.build_report_payload(request),
        warning=ozon_seller_analytics_factory.status().warning,
    )


@router.post(
    "/ozon/seller-analytics/import-bestsellers",
    response_model=OzonSellerAnalyticsImportResponse,
)
async def ozon_seller_analytics_import_bestsellers(
    request: OzonBestsellersImportRequest,
) -> OzonSellerAnalyticsImportResponse:
    status = ozon_seller_analytics_factory.status()
    if not status.configured:
        raise HTTPException(
            status_code=400,
            detail=(
                "Прямой автосбор Ozon Seller выключен: нет OZON_SELLER_WEB_COOKIE. "
                "Пока используйте 'Загрузить XLSX' или настройте безопасную авторизацию."
            ),
        )
    if not request.searches:
        raise HTTPException(status_code=400, detail="Нет поисковых групп для автосбора.")

    try:
        offers = await ozon_seller_analytics_factory.create().fetch_bestsellers_offers(request)
    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=error.response.status_code,
            detail="Ozon Seller web-API отклонил запрос. Проверьте авторизацию кабинета.",
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=502,
            detail=f"Ошибка связи с Ozon Seller web-API: {error}",
        ) from error

    products = repository.list_products()
    matches, issues = competitor_importer.match_offers(offers, products)
    products_by_id = {product.id: product for product in products}
    for product_id, offer in matches.items():
        product = products_by_id.get(product_id)
        if product is not None:
            repository.save_competitor_offer(product, offer, DataSource.API)

    result = CompetitorImportResult(
        filename="Ozon Seller Analytics / Товары на Ozon",
        imported_rows=len(offers),
        matched_products=len(matches),
        skipped_rows=max(len(offers) - len(matches), 0),
        source=DataSource.API,
        issues=[
            *issues[:45],
            *(
                [
                    ImportIssue(
                        row_number=None,
                        field="auth",
                        message=status.warning,
                        severity="warning",
                    )
                ]
                if status.warning
                else []
            ),
        ][:50],
    )
    analyses = _analysis_rows()
    return OzonSellerAnalyticsImportResponse(
        result=result,
        kpi=analysis_service.kpi(analyses),
        rows=analyses,
        searches=request.searches,
        offers_loaded=len(offers),
        request=request,
    )


# --- Остатки: сверка Ozon vs поставщик tdcsm.ru (см. app/services/stock_monitor.py) ---


@router.get("/stock/status", response_model=StockSnapshot)
def stock_status() -> StockSnapshot:
    """Последний сохранённый снимок — без обращения к Ozon/tdcsm.ru (быстро, для загрузки страницы)."""
    return latest_stock_snapshot()


@router.post("/stock/refresh", response_model=StockSnapshot)
async def stock_refresh() -> StockSnapshot:
    """Тянет свежие данные из Ozon + tdcsm.ru прямо сейчас и сохраняет новый снимок."""
    try:
        return await refresh_snapshot(get_settings())
    except StockMonitorNotConfigured as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Не удалось обновить остатки: {error}") from error


@router.post("/stock/apply", response_model=StockApplyResult)
async def stock_apply() -> StockApplyResult:
    """Проставляет на Ozon остаток поставщика для всех расхождений последнего снимка."""
    try:
        return await apply_stock_to_ozon(get_settings())
    except StockMonitorNotConfigured as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


# --- Живая Юнитка (см. app/domain/unitka.py, app/services/unitka_engine.py) ---


def _unitka_item(row: UnitkaRow) -> UnitkaItem:
    return UnitkaItem(row=row, computed=compute_row(row, unitka_get_assumptions()))


@router.get("/unitka/rows", response_model=list[UnitkaItem])
def unitka_list() -> list[UnitkaItem]:
    return [_unitka_item(row) for row in unitka_list_rows()]


@router.post("/unitka/rows", response_model=UnitkaItem)
def unitka_create(row: UnitkaRow) -> UnitkaItem:
    saved = unitka_create_row(row)
    return _unitka_item(saved)


@router.patch("/unitka/rows/{row_id}", response_model=UnitkaItem)
def unitka_update(row_id: str, row: UnitkaRow) -> UnitkaItem:
    if unitka_get_row(row_id) is None:
        raise HTTPException(status_code=404, detail="Строка юнитки не найдена.")
    updated = unitka_update_row(row_id, row.model_copy(update={"id": row_id}))
    return _unitka_item(updated)


@router.delete("/unitka/rows/{row_id}", status_code=204)
def unitka_delete(row_id: str) -> None:
    unitka_delete_row(row_id)


@router.get("/unitka/assumptions", response_model=UnitkaAssumptions)
def unitka_assumptions_get() -> UnitkaAssumptions:
    return unitka_get_assumptions()


@router.patch("/unitka/assumptions", response_model=UnitkaAssumptions)
def unitka_assumptions_update(assumptions: UnitkaAssumptions) -> UnitkaAssumptions:
    return unitka_save_assumptions(assumptions)


@router.post("/purchase-prices/refresh", response_model=PurchasePriceSnapshot)
async def purchase_prices_refresh() -> PurchasePriceSnapshot:
    try:
        return await refresh_purchase_prices(get_settings())
    except PurchasePriceMonitorNotConfigured as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Не удалось получить цены: {error}") from error


@router.post("/purchase-prices/apply", response_model=PurchasePriceApplyResult)
async def purchase_prices_apply() -> PurchasePriceApplyResult:
    try:
        return await apply_purchase_prices(get_settings())
    except PurchasePriceMonitorNotConfigured as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Не удалось получить цены: {error}") from error


@router.post("/unitka/import", response_model=UnitkaImportResult)
async def unitka_import(file: Annotated[UploadFile, File(...)]) -> UnitkaImportResult:
    """Импорт из загруженного .xlsx — бэкенд на Render не видит локальный диск, поэтому
    файл приходит через загрузку в браузере, как и прайсы поставщиков. Идемпотентно
    по supplier_article: существующие строки обновляются, новые — создаются."""
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Нужен файл .xlsx.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой.")

    try:
        rows, warnings = import_read_rows(BytesIO(content))
        assumptions = import_read_assumptions(BytesIO(content))
    except KeyError as error:
        raise HTTPException(
            status_code=400,
            detail=f"Не найден лист '15.06.26' или ожидаемый столбец: {error}",
        ) from error

    unitka_save_assumptions(assumptions)

    existing_by_article = {row.supplier_article: row for row in unitka_list_rows()}
    imported = 0
    updated = 0
    for new_row in rows:
        existing = existing_by_article.get(new_row.supplier_article)
        if existing is None:
            unitka_create_row(new_row)
            imported += 1
        else:
            unitka_update_row(existing.id, new_row.model_copy(update={"id": existing.id}))
            updated += 1

    return UnitkaImportResult(
        imported=imported,
        updated=updated,
        skipped=len(warnings),
        warnings=warnings[:50],
    )
