from datetime import date
from io import BytesIO
import json
from zipfile import ZipFile

from decimal import Decimal

from app.services.yandex_market_client import (
    _aggregate_sales_report_rows,
    _date_chunks,
    _parse_order,
    _parse_sales_report_archive,
    _report_row_date,
    _sales_report_scope,
)


CANCELLED_STATUSES = {"CANCELLED", "RETURNED"}


def test_parses_buyer_payment_and_cashback_for_active_items() -> None:
    order = {
        "id": 1,
        "creationDate": "2026-07-30T10:00:00+03:00",
        "status": "PROCESSING",
        "items": [
            {
                "offerId": "A-1",
                "count": 2,
                "prices": {
                    "payment": {"value": 1900},
                    "cashback": {"value": 100},
                },
            }
        ],
    }

    parsed = _parse_order(order, CANCELLED_STATUSES)

    assert parsed is not None
    _, revenue, units = parsed
    assert revenue == Decimal("2000")
    assert units == 2


def test_excludes_cancelled_item_units_proportionally() -> None:
    order = {
        "id": 2,
        "creationDate": "2026-07-30",
        "status": "DELIVERY",
        "items": [
            {
                "offerId": "A-2",
                "count": 3,
                "itemStatuses": [{"status": "CANCELLED", "count": 1}],
                "prices": {
                    "payment": {"value": 3000},
                    "cashback": {"value": 0},
                },
            }
        ],
    }

    parsed = _parse_order(order, CANCELLED_STATUSES)

    assert parsed is not None
    _, revenue, units = parsed
    assert revenue == Decimal("2000")
    assert units == 2


def test_splits_yandex_ranges_into_exclusive_thirty_day_chunks() -> None:
    chunks = _date_chunks("2026-06-01", "2026-07-30", 30)

    assert chunks == [
        ("2026-06-01", "2026-07-01"),
        ("2026-07-01", "2026-07-31"),
    ]


def test_parses_yandex_sales_analytics_json_archive() -> None:
    payload = [
        {
            "day": "29",
            "month": "7",
            "year": 2026,
            "offerId": "A-1",
            "orderItems": 2,
            "orderItemsTotalAmount": 25000,
        }
    ]
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "sales_funnel_report.json",
            json.dumps(payload, ensure_ascii=False),
        )

    rows = _parse_sales_report_archive(buffer.getvalue())

    assert rows == payload


def test_parses_yandex_sales_analytics_csv_archive() -> None:
    csv_content = (
        "DAY;MONTH;YEAR;OFFER_ID;ORDER_ITEMS;"
        "ORDER_ITEMS_TOTAL_AMOUNT\n"
        "29;Июль;2026;A-1;2;25000\n"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("sales_funnel_report.csv", csv_content)

    rows = _parse_sales_report_archive(buffer.getvalue())

    assert rows == [
        {
            "DAY": "29",
            "MONTH": "Июль",
            "YEAR": "2026",
            "OFFER_ID": "A-1",
            "ORDER_ITEMS": "2",
            "ORDER_ITEMS_TOTAL_AMOUNT": "25000",
        }
    ]
    assert _aggregate_sales_report_rows(rows) == [
        (date(2026, 7, 29), Decimal("25000"), 2)
    ]


def test_aggregates_exact_yandex_ordered_amount_by_day() -> None:
    rows = [
        {
            "day": "29",
            "month": "Июль",
            "year": 2026,
            "offerId": "A-1",
            "orderItems": 2,
            "orderItemsTotalAmount": 25000,
        },
        {
            "day": "29",
            "month": "Июль",
            "year": 2026,
            "offerId": "A-2",
            "orderItems": 1,
            "orderItemsTotalAmount": 12000,
        },
        {
            "day": "30",
            "month": "7",
            "year": 2026,
            "offerId": "A-1",
            "orderItems": 4,
            "orderItemsTotalAmount": 48000,
        },
    ]

    result = _aggregate_sales_report_rows(rows)

    assert result == [
        (date(2026, 7, 29), Decimal("37000"), 3),
        (date(2026, 7, 30), Decimal("48000"), 4),
    ]


def test_parses_iso_date_from_yandex_day_column() -> None:
    assert _report_row_date(
        {
            "DAY": "2026-07-29",
            "MONTH": "2026-07",
            "YEAR": "2026",
        }
    ) == date(2026, 7, 29)


def test_parses_russian_date_from_yandex_day_column() -> None:
    assert _report_row_date(
        {
            "DAY": "29.07.2026",
            "MONTH": "07.2026",
            "YEAR": "2026",
        }
    ) == date(2026, 7, 29)


def test_scopes_sales_report_to_configured_campaign() -> None:
    scope_kind, scope_id, report_body = _sales_report_scope(
        business_id=None,
        campaign_id=148830985,
    )

    assert scope_kind == "campaign"
    assert scope_id == 148830985
    assert report_body == {"campaignId": 148830985}
