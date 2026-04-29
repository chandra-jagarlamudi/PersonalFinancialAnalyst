"""Bank statement parsers.

T-046: bank auto-detection (CSV header sniffing + PDF first-page text)
T-047: Chase CSV parser (checking + credit variants)
T-048: Amex CSV and PDF parser
T-049: Capital One CSV parser
T-050: Robinhood CSV parser (cash transactions only)
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RawRow:
    date_str: str
    description: str
    amount: float  # signed: negative = debit/charge
    category: Optional[str] = None
    credit_hint: Optional[bool] = None  # True = credit, False = debit (Robinhood)


# ── T-046: Auto-detection ─────────────────────────────────────────────────────

_CHASE_HEADERS = {"transaction date", "post date"}
_AMEX_HEADERS_CSV = {"date", "description", "amount"}
_CAPITAL_ONE_HEADERS = {"debit", "credit", "card no."}
_ROBINHOOD_HEADERS = {"trans code", "activity date", "instrument"}


def detect_bank(filename: str, content: bytes) -> Optional[str]:
    """T-046: Detect source bank from file content. Returns bank slug or None."""
    low_name = filename.lower()

    # PDF: text from first page
    if low_name.endswith(".pdf"):
        text = _pdf_first_page_text(content).lower()
        if "chase" in text:
            return "chase"
        if "american express" in text or "amex" in text:
            return "amex"
        if "capital one" in text:
            return "capital_one"
        return None

    # CSV: header row
    first_line = content.decode("utf-8", errors="replace").split("\n")[0].lower()
    cols = {c.strip().strip('"') for c in first_line.split(",")}

    if _ROBINHOOD_HEADERS & cols:
        return "robinhood"
    if _CAPITAL_ONE_HEADERS & cols:
        return "capital_one"
    if _CHASE_HEADERS & cols:
        return "chase"
    if _AMEX_HEADERS_CSV <= cols and len(cols) <= 5:
        return "amex"

    return None


def _pdf_first_page_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        if reader.pages:
            return reader.pages[0].extract_text() or ""
    except Exception:
        pass
    return ""


# ── T-047: Chase CSV parser ───────────────────────────────────────────────────

# Chase checking: Transaction Date,Post Date,Description,Category,Type,Amount,Memo
# Chase credit:   Transaction Date,Post Date,Description,Category,Type,Amount,Memo
# Older export:   Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #

def parse_chase(content: bytes) -> list[RawRow]:
    """T-047: Parse Chase bank/credit card CSV."""
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[RawRow] = []

    for raw in reader:
        # Normalize keys
        keys = {k.strip().lower(): v.strip() for k, v in raw.items() if k}

        date_str = (
            keys.get("transaction date")
            or keys.get("posting date")
            or keys.get("date")
            or ""
        )
        description = keys.get("description") or keys.get("memo") or ""
        amount_str = keys.get("amount", "0").replace(",", "").replace("$", "")
        category = keys.get("category")

        if not date_str or not amount_str:
            continue

        try:
            amount = float(amount_str)
        except ValueError:
            continue

        rows.append(RawRow(date_str=date_str, description=description, amount=amount, category=category))

    return rows


# ── T-048: Amex CSV + PDF parser ─────────────────────────────────────────────

_AMEX_PDF_ROW = re.compile(
    r"(\d{2}/\d{2}/\d{4})\s+(.+?)\s+(-?\$?[\d,]+\.\d{2})\s*$",
    re.MULTILINE,
)


def parse_amex(content: bytes, is_pdf: bool) -> list[RawRow]:
    """T-048: Parse Amex CSV or PDF. Amount negative = charge."""
    if is_pdf:
        return _parse_amex_pdf(content)
    return _parse_amex_csv(content)


def _parse_amex_csv(content: bytes) -> list[RawRow]:
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[RawRow] = []

    for raw in reader:
        keys = {k.strip().lower(): v.strip() for k, v in raw.items() if k}
        date_str = keys.get("date") or ""
        description = keys.get("description") or ""
        amount_str = keys.get("amount", "0").replace(",", "").replace("$", "")

        if not date_str:
            continue
        try:
            amount = float(amount_str)
        except ValueError:
            continue

        rows.append(RawRow(date_str=date_str, description=description, amount=amount))

    return rows


def _parse_amex_pdf(content: bytes) -> list[RawRow]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        full_text = "\n".join(
            page.extract_text() or "" for page in reader.pages
        )
    except Exception:
        return []

    rows: list[RawRow] = []
    for m in _AMEX_PDF_ROW.finditer(full_text):
        date_str = m.group(1)
        description = m.group(2).strip()
        amount_str = m.group(3).replace(",", "").replace("$", "")
        try:
            amount = float(amount_str)
        except ValueError:
            continue
        rows.append(RawRow(date_str=date_str, description=description, amount=amount))

    return rows


# ── T-049: Capital One CSV parser ─────────────────────────────────────────────

# Columns: Transaction Date, Posted Date, Card No., Description, Category, Debit, Credit

def parse_capital_one(content: bytes) -> list[RawRow]:
    """T-049: Parse Capital One CSV. amount = Credit - Debit (positive = credit)."""
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[RawRow] = []

    for raw in reader:
        keys = {k.strip().lower(): v.strip() for k, v in raw.items() if k}
        date_str = keys.get("transaction date") or keys.get("posted date") or ""
        description = keys.get("description") or ""
        category = keys.get("category")
        debit_str = (keys.get("debit") or "0").replace(",", "").replace("$", "")
        credit_str = (keys.get("credit") or "0").replace(",", "").replace("$", "")

        if not date_str:
            continue

        try:
            debit = float(debit_str) if debit_str else 0.0
            credit = float(credit_str) if credit_str else 0.0
        except ValueError:
            continue

        # positive = credit to account, negative = debit (charge)
        amount = credit - debit
        rows.append(RawRow(date_str=date_str, description=description, amount=amount, category=category))

    return rows


# ── T-050: Robinhood CSV parser ───────────────────────────────────────────────

# Cash transaction codes (deposits, withdrawals, dividends)
_CASH_CODES = {"ach", "jnlc", "jnls", "div", "cdiv", "int", "wire", "cash"}

def parse_robinhood(content: bytes) -> list[RawRow]:
    """T-050: Parse Robinhood CSV. Cash transactions only; skip equity trades."""
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[RawRow] = []

    for raw in reader:
        keys = {k.strip().lower(): v.strip() for k, v in raw.items() if k}
        trans_code = (keys.get("trans code") or "").lower()

        # Skip equity trades
        if trans_code not in _CASH_CODES:
            continue

        date_str = keys.get("activity date") or keys.get("settle date") or ""
        description = keys.get("description") or trans_code
        amount_str = (keys.get("amount") or "0").replace(",", "").replace("$", "")

        if not date_str:
            continue

        try:
            amount = float(amount_str)
        except ValueError:
            continue

        # Positive amount = credit (deposit/dividend), negative = debit (withdrawal)
        rows.append(RawRow(date_str=date_str, description=description, amount=amount))

    return rows
