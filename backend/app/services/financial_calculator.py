from decimal import Decimal, ROUND_HALF_UP


VAT_RATE = Decimal("0.22")
VAT_MULTIPLIER = Decimal("1.22")
PROFIT_TAX_RATE = Decimal("0.22")
MONEY_QUANT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def without_vat(value_with_vat: Decimal) -> Decimal:
    return value_with_vat / VAT_MULTIPLIER


def profit_tax(profit_before_tax: Decimal) -> Decimal:
    if profit_before_tax <= 0:
        return Decimal("0")
    return profit_before_tax * PROFIT_TAX_RATE


def net_after_profit_tax(profit_before_tax: Decimal) -> Decimal:
    return profit_before_tax - profit_tax(profit_before_tax)
