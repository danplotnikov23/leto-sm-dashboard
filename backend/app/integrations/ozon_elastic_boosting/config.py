from __future__ import annotations

from dataclasses import dataclass


DEFAULT_MIN_DISCOUNT = 0.10
DEFAULT_MAX_DISCOUNT = 11.0
STRICT_UNION_EXCLUSION = True
EXCLUDE_DIRECT_ADS = True
CLEAR_NON_ELIGIBLE = True
ROUND_DISCOUNT_TO = 2


@dataclass(frozen=True)
class CategoryOverride:
    """Per-category rule that replaces the global discount range.

    ``exclude=True`` drops every row in this category from the promo
    regardless of its own entry discount, ignoring min/max entirely.
    Otherwise min_discount/max_discount replace the global range for rows
    whose category matches (case/whitespace-insensitive).
    """

    category: str
    min_discount: float | None = None
    max_discount: float | None = None
    exclude: bool = False


@dataclass(frozen=True)
class ProcessingConfig:
    min_discount: float = DEFAULT_MIN_DISCOUNT
    max_discount: float = DEFAULT_MAX_DISCOUNT
    strict_union_exclusion: bool = STRICT_UNION_EXCLUSION
    exclude_direct_ads: bool = EXCLUDE_DIRECT_ADS
    clear_non_eligible: bool = CLEAR_NON_ELIGIBLE
    # When your_price dropped below Ozon's own min_boost_price threshold
    # (entry discount goes negative), add the row anyway at 0% - write
    # "Итоговая цена по акции" = "Ваша цена" instead of always excluding it.
    zero_discount_for_negative: bool = False
    # When set, every row added to the promo gets "Итоговая цена по акции"
    # overwritten to your_price * (1 - target_discount_percent/100),
    # instead of leaving Ozon's own pre-filled suggested price untouched.
    target_discount_percent: float | None = None
    # SKUs or articles (offer_id) to force out of the promo regardless of
    # how they'd otherwise score against the discount range - a manual
    # override for a specific product the seller found by search.
    excluded_identifiers: frozenset[str] = frozenset()
    round_discount_to: int = ROUND_DISCOUNT_TO
    category_overrides: tuple[CategoryOverride, ...] = ()
    promo_sheet_name: str = "Товары и цены"
    auto_add_sheet_prefix: str = "Участвуют с"
    statistics_sheet_name: str = "Statistics"
    union_sheet_name: str = "Union"
    header_row: int = 2
    hint_row: int = 3
    data_start_row: int = 4
