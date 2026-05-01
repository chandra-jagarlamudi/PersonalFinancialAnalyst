"""Envelope projection math (deterministic, date-driven)."""

from datetime import date
from decimal import Decimal

from pfa.budget_math import (
    days_in_month,
    linear_project_month_spend,
    month_date_range,
)


def test_days_in_month_march():
    assert days_in_month(date(2025, 3, 15)) == 31


def test_month_date_range():
    start, end = month_date_range(date(2025, 3, 1))
    assert start == date(2025, 3, 1)
    assert end == date(2025, 3, 31)


def test_linear_projection_mid_month():
    month_start = date(2025, 3, 1)
    as_of = date(2025, 3, 10)
    spent_mtd = Decimal("100")
    projected = linear_project_month_spend(spent_mtd, month_start, as_of)
    assert projected == Decimal("310")


def test_linear_projection_first_day_scales_to_full_month():
    month_start = date(2025, 3, 1)
    as_of = date(2025, 3, 1)
    spent_mtd = Decimal("31")
    projected = linear_project_month_spend(spent_mtd, month_start, as_of)
    assert projected == Decimal("961")


def test_projection_after_month_end_is_actual_mtd():
    month_start = date(2025, 2, 1)
    as_of = date(2025, 3, 5)
    spent_mtd = Decimal("200")
    projected = linear_project_month_spend(spent_mtd, month_start, as_of)
    assert projected == Decimal("200")


def test_projection_before_month_starts_is_zero():
    month_start = date(2025, 4, 1)
    as_of = date(2025, 3, 1)
    projected = linear_project_month_spend(Decimal("50"), month_start, as_of)
    assert projected == Decimal("0")


def test_zero_spend_projects_zero():
    projected = linear_project_month_spend(
        Decimal("0"), date(2025, 5, 1), date(2025, 5, 15)
    )
    assert projected == Decimal("0")
