from app.domain.models import CompetitorOffer, CompetitorSnapshot, DataSource, SupplierProduct


class CompetitorAnalysisService:
    """Keeps competitor data source-aware until Ozon/API imports are connected."""

    def empty_snapshot(self, product: SupplierProduct) -> CompetitorSnapshot:
        return CompetitorSnapshot(product_id=product.id, offers=[], source=DataSource.MISSING)

    def from_manual_rows(
        self,
        product: SupplierProduct,
        rows: list[dict[str, object]],
        source: DataSource = DataSource.EXCEL,
    ) -> CompetitorSnapshot:
        offers: list[CompetitorOffer] = []
        for row in rows:
            price = self._float(row.get("price_vat_included"))
            title = str(row.get("title") or "").strip()
            if not title or price is None:
                continue
            offers.append(
                CompetitorOffer(
                    sku=str(row.get("sku") or "") or None,
                    title=title,
                    price_vat_included=price,
                    url=str(row.get("url") or "") or None,
                    match_type=self._match_type(row.get("match_type")),
                    orders_count=self._int(row.get("orders_count")),
                    avg_purchase_price=self._float(row.get("avg_purchase_price")),
                    buyout_rate=self._float(row.get("buyout_rate")),
                    is_promo=bool(row.get("is_promo", False)),
                    source=source,
                )
            )
        return CompetitorSnapshot(
            product_id=product.id,
            offers=offers,
            source=source if offers else DataSource.MISSING,
        )

    def _float(self, value: object) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(str(value).replace(",", "."))
        except ValueError:
            return None

    def _int(self, value: object) -> int | None:
        parsed = self._float(value)
        return None if parsed is None else int(parsed)

    def _match_type(self, value: object) -> str:
        parsed = str(value or "").strip()
        if parsed in {"exact", "analog", "reference"}:
            return parsed
        return "analog"
