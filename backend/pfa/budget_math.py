"""Calendar helpers and linear MTD spend projection for envelope budgets."""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal


def days_in_month(d: date) -> int:
    return calendar.monthrange(d.year, d.month)[1]


def month_date_range(month_start: date) -> tuple[date, date]:
    if month_start.day != 1:
        raise ValueError("month_start must be the first calendar day of the month")
    end = date(month_start.year, month_start.month, days_in_month(month_start))
    return month_start, end


def linear_project_month_spend(
    spent_mtd: Decimal, month_start: date, as_of: date
) -> Decimal:
    """Scale observed MTD expense spending to a full-month estimate (linear burn).

    ``spent_mtd`` is the sum of spending (positive numbers) from envelope start through the MTD window.
    """
    _, month_end = month_date_range(month_start)
    if as_of < month_start:
        return Decimal("0").quantize(Decimal("0.0001"))
    mtd_end = min(as_of, month_end)
    days_elapsed = (mtd_end - month_start).days + 1
    dim = days_in_month(month_start)
    if days_elapsed <= 0 or dim <= 0:
        return Decimal("0").quantize(Decimal("0.0001"))
    projected = spent_mtd * Decimal(dim) / Decimal(days_elapsed)
    return projected.quantize(Decimal("0.0001"))
