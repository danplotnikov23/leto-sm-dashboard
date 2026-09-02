from app.core.config import Settings
from app.services.ozon_seller_analytics import (
    OzonBestsellersImportRequest,
    OzonBestsellersRequest,
    OzonSellerAnalyticsClient,
    OzonSellerAnalyticsFactory,
    parse_bestsellers_offers,
)


def test_ozon_seller_analytics_status_without_cookie() -> None:
    status = OzonSellerAnalyticsFactory(
        Settings(ozon_seller_web_cookie=None)
    ).status()

    assert status.configured is False
    assert status.cookie_masked is None
    assert status.json_data_endpoint.endswith("/what_to_sell/data/v3")
    assert "fallback" in status.warning


def test_ozon_seller_analytics_status_masks_cookie() -> None:
    status = OzonSellerAnalyticsFactory(
        Settings(ozon_seller_web_cookie="abcd0123456789secret")
    ).status()

    assert status.configured is True
    assert status.cookie_masked == "abcd***cret"


def test_bestsellers_payload_uses_name_search() -> None:
    client = OzonSellerAnalyticsClient()
    payload = client.build_bestsellers_payload(
        OzonBestsellersRequest(search="гвозди", limit=25, offset=50)
    )

    assert payload["limit"] == "25"
    assert payload["offset"] == "50"
    assert payload["filter"] == {
        "stock": "any_stock",
        "period": "weekly",
        "name": "гвозди",
    }
    assert payload["sort"] == {"key": "GmvSum_desc"}


def test_bestsellers_payload_uses_sku_search_and_categories() -> None:
    client = OzonSellerAnalyticsClient()
    payload = client.build_bestsellers_payload(
        OzonBestsellersRequest(
            search="164844946",
            categories=["123", "456"],
            period="monthly",
        )
    )

    assert payload["filter"] == {
        "stock": "any_stock",
        "period": "monthly",
        "sku": "164844946",
        "categories": ["123", "456"],
    }


def test_report_payload_excludes_pagination() -> None:
    client = OzonSellerAnalyticsClient()
    payload = client.build_report_payload(OzonBestsellersRequest(search="саморезы"))

    assert "limit" not in payload
    assert "offset" not in payload
    assert payload["filter"] == {
        "stock": "any_stock",
        "period": "weekly",
        "name": "саморезы",
    }


def test_import_request_fetch_payload_keeps_pages_explicit() -> None:
    request = OzonBestsellersImportRequest(
        searches=["гвозди", "саморезы"],
        limit_per_search=25,
        max_pages_per_search=2,
    )

    assert request.searches == ["гвозди", "саморезы"]
    assert request.limit_per_search == 25
    assert request.max_pages_per_search == 2


def test_parse_bestsellers_offers_from_ozon_money_shape() -> None:
    offers = parse_bestsellers_offers(
        {
            "items": [
                {
                    "sku": "164844946",
                    "title": "Гвозди Стройметиз строительные 1.2x16",
                    "minSellerPrice": {"units": "239", "nanos": 500000000},
                    "avgPrice": {"units": "252", "nanos": 0},
                    "soldCount": "25",
                    "nullableRedemptionRate": "95.5%",
                }
            ]
        }
    )

    assert len(offers) == 1
    assert offers[0].sku == "164844946"
    assert offers[0].price_vat_included == 239.5
    assert offers[0].avg_purchase_price == 252
    assert offers[0].orders_count == 25
    assert offers[0].buyout_rate == 0.955
    assert offers[0].url == "https://www.ozon.ru/product/164844946/"
    assert offers[0].source == "api"
