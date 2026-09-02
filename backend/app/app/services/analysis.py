from app.domain.models import (
    CompetitorSnapshot,
    DashboardKpi,
    EconomicsBreakdown,
    EconomicsInput,
    LaunchReadiness,
    LaunchReadinessStatus,
    ProductAnalysis,
    RecommendationStatus,
    SupplierProduct,
)
from app.services.competitors import CompetitorAnalysisService
from app.services.economics import EconomicsService


class ProductAnalysisService:
    def __init__(
        self,
        economics: EconomicsService | None = None,
        competitors: CompetitorAnalysisService | None = None,
    ) -> None:
        self.economics = economics or EconomicsService()
        self.competitors = competitors or CompetitorAnalysisService()

    def analyze_product(
        self,
        product: SupplierProduct,
        sale_price_vat_included: float | None = None,
        competitor: CompetitorSnapshot | None = None,
        seller_bonus_percent: float | None = None,
        advertising_drr_percent: float | None = None,
        package_cost: float | None = None,
        fulfillment_processing_cost: float | None = None,
    ) -> ProductAnalysis:
        selected_competitor = competitor or self.competitors.empty_snapshot(product)
        price = sale_price_vat_included or self.starter_price(product, selected_competitor)
        economics = self.economics.calculate(
            EconomicsInput(
                product=product,
                sale_price_vat_included=price,
                competitor=selected_competitor,
                seller_bonus_percent=(
                    seller_bonus_percent if seller_bonus_percent is not None else 45.0
                ),
                advertising_drr_percent=(
                    advertising_drr_percent if advertising_drr_percent is not None else 12.0
                ),
                package_cost=package_cost if package_cost is not None else 25.0,
                fulfillment_processing_cost=(
                    fulfillment_processing_cost
                    if fulfillment_processing_cost is not None
                    else 45.0
                ),
            )
        )
        return ProductAnalysis(
            product=product,
            economics=economics,
            competitor=selected_competitor,
            readiness=self._readiness(product, economics, selected_competitor),
        )

    @staticmethod
    def _readiness(
        product: SupplierProduct,
        economics: EconomicsBreakdown,
        competitor: CompetitorSnapshot,
    ) -> LaunchReadiness:
        checks = {
            "stock_available": product.stock is not None and product.stock > 0,
            "category_known": bool(product.category),
            "dimensions_complete": product.dimensions.volume_liters is not None,
            "weight_known": product.weight_kg is not None and product.weight_kg > 0,
            "competitor_verified": bool(competitor.offers),
            "business_profitable": economics.business_net_profit > 0,
        }
        missing_labels = {
            "stock_available": "остаток",
            "category_known": "категория",
            "dimensions_complete": "габариты",
            "weight_known": "вес",
            "competitor_verified": "проверенный конкурент",
        }
        missing = [label for key, label in missing_labels.items() if not checks[key]]
        reasons: list[str] = []
        if product.stock is not None and product.stock <= 0:
            reasons.append("Нет остатка у поставщика.")
        if economics.business_net_profit <= 0:
            reasons.append("Чистая прибыль бизнеса не положительная.")
        if missing:
            reasons.append(f"Не хватает данных: {', '.join(missing)}.")
        if product.stock is not None and product.stock <= 0 or economics.business_net_profit <= 0:
            status = LaunchReadinessStatus.STOP
        elif missing:
            status = LaunchReadinessStatus.NEEDS_DATA
        else:
            status = LaunchReadinessStatus.READY
        return LaunchReadiness(status=status, checks=checks, missing_fields=missing, reasons=reasons)

    def analyze_many(self, products: list[SupplierProduct]) -> list[ProductAnalysis]:
        return [self.analyze_product(product) for product in products]

    def kpi(self, analyses: list[ProductAnalysis]) -> DashboardKpi:
        total = len(analyses)
        margins = [item.economics.margin_percent for item in analyses]
        profitable = [item for item in analyses if item.economics.net_profit > 0]
        unprofitable = [item for item in analyses if item.economics.net_profit <= 0]
        risky = [
            item
            for item in analyses
            if item.economics.recommendation
            in {RecommendationStatus.LIST_CAREFULLY, RecommendationStatus.MANUAL_REVIEW}
        ]
        competitor_below_break_even = [
            item
            for item in analyses
            if item.competitor.min_price is not None
            and item.competitor.min_price < item.economics.break_even_price_vat_included
        ]
        return DashboardKpi(
            total_products=total,
            profitable_products=len(profitable),
            unprofitable_products=len(unprofitable),
            average_margin_percent=round(sum(margins) / total, 2) if total else 0.0,
            potential_profit=round(sum(item.economics.net_profit for item in analyses), 2),
            high_risk_products=len(risky),
            competitor_below_break_even=len(competitor_below_break_even),
        )

    def starter_price(self, product: SupplierProduct, competitor: CompetitorSnapshot) -> float:
        if competitor.min_price is not None:
            return competitor.min_price
        if product.purchase_price_vat_included <= 100:
            # Keep inexpensive goods in the <=100 RUB commission band until a
            # deliberate bundle price is selected in the shortlist.
            return 99.0
        return max(
            product.purchase_price_vat_included * 1.75,
            product.purchase_price_vat_included + 500,
        )
