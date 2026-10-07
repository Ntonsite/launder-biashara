from decimal import ROUND_HALF_UP, Decimal


def tzs(value: Decimal | int) -> int:
    """Round an exact Decimal to whole shillings (half-up, the convention used on Tanzanian receipts)."""
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def line_total(unit_price: int, quantity: Decimal) -> int:
    return tzs(Decimal(unit_price) * quantity)


def percentage_of(amount: int, rate_percent: Decimal) -> int:
    return tzs(Decimal(amount) * Decimal(rate_percent) / Decimal(100))
