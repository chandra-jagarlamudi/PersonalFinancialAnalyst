"""Targeted credit-card PDF parse ladder — text extraction + line heuristics."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from pypdf import PdfReader

from pfa.csv_parse import ParsedCsvRow

HITL_CONFIDENCE_THRESHOLD = Decimal("0.85")


@dataclass(frozen=True, slots=True)
class TargetedPdfParseOutcome:
    rows: tuple[ParsedCsvRow, ...]
    confidence: Decimal
    notes: str


# Leading date + rest (single-line amount on same line, or start of AmEx-style multiline block).
_HEAD_SLASH_DATE = re.compile(r"^\s*(\d{1,2}/\d{1,2}/\d{2,4})\*?\s+(.*)$")
_HEAD_ISO = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})\s+(.*)$")
_TAIL_AMOUNT = re.compile(r"\s+(-?\(?\$?\s*[\d,]+\.\d{2}\)?)\s*$")

# Amount alone on a line (AmEx Pay Over Time detail: amount then optional ⧫).
_AMOUNT_ONLY_LINE = re.compile(r"^\s*(-?\$[\d,]+\.\d{2}|-?[\d,]+\.\d{2})\s*(?:⧫|\*)?\s*$")

# Abort multiline accumulation when we hit statement section headers / footers.
_SECTION_BREAK = re.compile(
    r"^(Fees\b|Interest Charged\b|About Trailing|Total Fees|Total Interest|"
    r"Payments Amount|Credits Amount|New Charges\b|Summary\b|Pay In Full\b|"
    r"Detail Continued|Continued on|p\.\s*\d+/\d+|Important Notices|"
    r"Membership Rewards|Transactions Dated|Annual\b|Percentage\b|Balance\b Subject)",
    re.I,
)

_SKIP_DESCRIPTIONS = frozenset(
    {
        "amount",
        "balance",
        "credit",
        "date",
        "debit",
        "description",
        "merchant",
        "posted",
        "transaction",
        "transactions",
        "withdrawals",
        "deposits",
        "payments",
        "credits",
    }
)

# Lines that start like a transaction date but are not merchant activity.
_REST_BOILERPLATE_PREFIXES = (
    "closing date ",
    "payment due date ",
    "late payment warning",
    "minimum payment warning",
)


def _extract_pdf_text(raw: bytes) -> str:
    reader = PdfReader(io.BytesIO(raw), strict=False)
    chunks: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text()
        except Exception:
            text = ""
        if text:
            chunks.append(text)
    return "\n".join(chunks)


def _parse_slash_date(ds: str) -> date:
    parts = ds.split("/")
    if len(parts) != 3:
        raise ValueError("expected MM/DD/YY or MM/DD/YYYY")
    month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
    if year < 100:
        year += 2000
    return date(year, month, day)


def _parse_amount_token(token: str) -> Decimal:
    t = re.sub(r"\s+", "", token.strip())
    negative = False
    if t.startswith("(") and t.endswith(")"):
        negative = True
        t = t[1:-1]
    t = t.replace("$", "").replace("€", "").replace(",", "").strip()
    if not t:
        raise InvalidOperation
    d = Decimal(t)
    return -d if negative else d


def _skip_multiline_rest(rest: str) -> bool:
    low = rest.lower()
    return any(low.startswith(p) for p in _REST_BOILERPLATE_PREFIXES)


def _try_parse_line(line: str) -> ParsedCsvRow | None:
    """Single-line: date … description … amount (same row)."""
    line = line.strip()
    if not line:
        return None

    ds: str | None = None
    rest: str | None = None
    m = _HEAD_SLASH_DATE.match(line)
    if m:
        ds, rest = m.groups()
    else:
        m = _HEAD_ISO.match(line)
        if not m:
            return None
        ds, rest = m.groups()

    if rest and _skip_multiline_rest(rest.strip()):
        return None

    ta = _TAIL_AMOUNT.search(rest)
    if not ta:
        return None

    amt_tok = ta.group(1)
    desc = rest[: ta.start()].strip()

    if len(desc) < 2:
        return None
    if desc.lower() in _SKIP_DESCRIPTIONS:
        return None

    try:
        if "/" in ds:
            td = _parse_slash_date(ds)
        else:
            td = date.fromisoformat(ds)
        amt = _parse_amount_token(amt_tok)
    except (ValueError, InvalidOperation):
        return None

    return ParsedCsvRow(td, None, amt, "USD", desc)


def _normalize_desc(parts: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _parse_amex_style_multiline(lines: list[str]) -> list[ParsedCsvRow]:
    """American Express-style blocks: MM/DD/YY merchant … ; amount on its own line with ⧫."""
    rows: list[ParsedCsvRow] = []
    i = 0
    n = len(lines)

    while i < n:
        raw_ln = lines[i]
        line = raw_ln.strip()
        if not line:
            i += 1
            continue

        m = _HEAD_SLASH_DATE.match(line)
        if not m:
            i += 1
            continue

        ds, rest = m.group(1), m.group(2).strip()
        if _skip_multiline_rest(rest):
            i += 1
            continue

        if _TAIL_AMOUNT.search(rest):
            # Same-line amount belongs to single-line parser, not multiline block.
            i += 1
            continue

        parts: list[str] = [rest]
        i += 1

        while i < n:
            ln = lines[i].strip()
            if not ln:
                i += 1
                continue
            if _SECTION_BREAK.match(ln):
                i += 1
                break
            if _HEAD_SLASH_DATE.match(ln) and not _AMOUNT_ONLY_LINE.match(ln):
                # Next dated row without closing amount — drop incomplete block.
                break
            if _AMOUNT_ONLY_LINE.match(ln):
                amt_m = _AMOUNT_ONLY_LINE.match(ln)
                assert amt_m is not None
                try:
                    td = _parse_slash_date(ds)
                    amt = _parse_amount_token(amt_m.group(1))
                    desc = _normalize_desc(parts)
                    if len(desc) >= 2 and desc.lower() not in _SKIP_DESCRIPTIONS:
                        rows.append(ParsedCsvRow(td, None, amt, "USD", desc))
                except (ValueError, InvalidOperation):
                    pass
                i += 1
                break

            parts.append(ln)
            i += 1

    return rows


def _row_dedupe_key(r: ParsedCsvRow) -> tuple[date, Decimal, str]:
    return (r.transaction_date, r.amount, r.description_raw[:160])


def _merge_many(*sources: list[ParsedCsvRow]) -> list[ParsedCsvRow]:
    seen: set[tuple[date, Decimal, str]] = set()
    out: list[ParsedCsvRow] = []
    for src in sources:
        for r in src:
            k = _row_dedupe_key(r)
            if k in seen:
                continue
            seen.add(k)
            out.append(r)
    out.sort(key=lambda x: (x.transaction_date, x.description_raw))
    return out


def _month_abbr_to_int(tok: str) -> int:
    a = tok.lower()[:3]
    m = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    if a not in m:
        raise ValueError(tok)
    return m[a]


_CAP1_PAIR = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})\s+"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})\s+",
    re.I,
)


def _capital_one_billing_year(text: str) -> int | None:
    m = re.search(
        r"\b([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})\s*-\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})\b",
        text,
    )
    if not m:
        return None
    return int(m.group(6))


def _capital_one_transaction_blob(text: str) -> str:
    """Capital One lists payments/credits then purchases; both use Mon D Mon D … $amount."""
    parts: list[str] = []
    pay = re.search(
        r"Payments, Credits and Adjustments\s+Trans Date\s+Post Date\s+Description\s+Amount\s+",
        text,
        re.I,
    )
    if pay:
        rest = text[pay.end() :]
        split_mark = re.search(r"CHANDRA S JAGARLAMUDI\s+#\d{4}:\s*Transactions", rest, re.I)
        if split_mark:
            parts.append(rest[: split_mark.start()])
            rest = rest[split_mark.end() :]
        end2 = re.search(
            r"\b(?:ABHIRAM|LAVANYA|LASYA)\s+JAGARLAMUDI|Total Transactions for This Period",
            rest,
            re.I,
        )
        parts.append(rest[: end2.start()] if end2 else rest)
    if parts:
        return "\n".join(parts)
    m = re.search(r"#\d{4}:\s*Transactions", text, re.I)
    if not m:
        m = re.search(r"Trans\s+Date\s+Post\s+Date\s+Description\s+Amount", text, re.I)
    if not m:
        return text
    sub = text[m.end() :]
    m2 = re.search(
        r"\b(?:ABHIRAM|LAVANYA|LASYA)\s+JAGARLAMUDI|Total Transactions for This Period",
        sub,
        re.I,
    )
    if m2:
        sub = sub[: m2.start()]
    return sub


def _parse_capital_one_transactions(text: str) -> list[ParsedCsvRow]:
    if "capitalone" not in text.lower() and "venture" not in text.lower():
        return []
    year = _capital_one_billing_year(text)
    if year is None:
        return []
    blob = _capital_one_transaction_blob(text)
    rows: list[ParsedCsvRow] = []
    for m in _CAP1_PAIR.finditer(blob):
        tm1, d1s = m.group(1), m.group(2)
        d1 = int(d1s)
        start = m.end()
        m2 = _CAP1_PAIR.search(blob, start)
        chunk = blob[start : m2.start() if m2 else len(blob)]
        chunk = re.sub(
            r"\s*Trans Date\s+Post Date\s+Description\s+Amount\s*$",
            "",
            chunk,
            flags=re.I,
        )
        chunk = re.split(r"\bTotal Transactions\b", chunk, 1, flags=re.I)[0]
        chunk = re.split(r"\s*CHANDRA S JAGARLAMUDI\b", chunk, 1, flags=re.I)[0]
        chunk = chunk.strip()
        am = re.search(r"(-?\s*\$[\d,]+\.\d{2})\s*$", chunk)
        if not am:
            continue
        desc = re.sub(r"\s+", " ", chunk[: am.start()].strip())
        if len(desc) < 3 or desc.lower().startswith("trans date"):
            continue
        try:
            mo = _month_abbr_to_int(tm1)
            td = date(year, mo, d1)
            amt = _parse_amount_token(am.group(1))
        except (ValueError, InvalidOperation, OverflowError):
            continue
        rows.append(ParsedCsvRow(td, None, amt, "USD", desc))
    return rows


_CITI_BILLING_YY = re.compile(
    r"Billing\s+Period:\s*\d{1,2}/\d{1,2}/(\d{2})\s*-\s*\d{1,2}/\d{1,2}/(\d{2})",
    re.I,
)
_MM_DD_ALONE = re.compile(r"^\d{1,2}/\d{1,2}$")
_CITI_AMOUNT_LINE = re.compile(r"^\s*-?\$?[\d,]+\.\d{2}\s*$")

_CITI_SKIP_LINE = re.compile(
    r"^(Fees Charged|Interest Charged|TOTAL FEES|TOTAL INTEREST|Promo Purchase|"
    r"CARDHOLDER SUMMARY|ACCOUNT SUMMARY|Sale\b|Post\b|Description\b|Amount\b|"
    r"Payments, Credits and Adjustments|Your Annual Percentage Rate|Balance type|"
    r"Important Information|p\.\s*\d+/\d+)",
    re.I,
)


def _citi_statement_year(text: str) -> int | None:
    m = _CITI_BILLING_YY.search(text)
    if not m:
        return None
    return 2000 + int(m.group(2))


def _parse_citi_mmdd_lines(lines: list[str], year: int) -> list[ParsedCsvRow]:
    rows: list[ParsedCsvRow] = []
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i].strip()
        if _CITI_SKIP_LINE.match(line) or not line:
            i += 1
            continue
        if re.match(r"^[A-Z][A-Z\s'.-]+\s+JAGARLAMUDI\s*$", line):
            i += 1
            continue
        if not _MM_DD_ALONE.match(line):
            i += 1
            continue
        sale_raw = line
        i += 1
        if i >= n:
            break
        nxt = lines[i].strip()
        if _MM_DD_ALONE.match(nxt):
            i += 1
        parts: list[str] = []
        negate_next_amount = False
        while i < n:
            ln = lines[i].strip()
            if not ln:
                i += 1
                continue
            if _MM_DD_ALONE.match(ln) and parts:
                break
            if _CITI_SKIP_LINE.match(ln) or re.match(r"^[A-Z][A-Z\s'.-]+\s+JAGARLAMUDI\s*$", ln):
                parts = []
                break
            if ln == "-":
                negate_next_amount = True
                i += 1
                continue
            if _CITI_AMOUNT_LINE.match(ln):
                try:
                    sm, sd = sale_raw.split("/")
                    td = date(year, int(sm), int(sd))
                    amt = _parse_amount_token(ln)
                    if negate_next_amount:
                        amt = -amt
                    desc = _normalize_desc(parts)
                    if len(desc) >= 3:
                        rows.append(ParsedCsvRow(td, None, amt, "USD", desc))
                except (ValueError, InvalidOperation, OverflowError):
                    pass
                i += 1
                break
            parts.append(ln)
            i += 1
    return rows


def _parse_citi_transactions(text: str) -> list[ParsedCsvRow]:
    if "citicards.com" not in text.lower() and "costco anywhere" not in text.lower():
        return []
    year = _citi_statement_year(text)
    if year is None:
        return []
    return _parse_citi_mmdd_lines(text.splitlines(), year)


def _parse_statement_text(text: str) -> list[ParsedCsvRow]:
    lines = text.splitlines()
    amex = _parse_amex_style_multiline(lines)
    single: list[ParsedCsvRow] = []
    for raw_line in lines:
        row = _try_parse_line(raw_line)
        if row is not None:
            single.append(row)
    cap1 = _parse_capital_one_transactions(text)
    citi = _parse_citi_transactions(text)
    return _merge_many(amex, cap1, citi, single)


def _confidence(row_count: int) -> Decimal:
    if row_count <= 0:
        return Decimal("0.35")
    if row_count == 1:
        return Decimal("0.72")
    if row_count == 2:
        return Decimal("0.80")
    return Decimal("0.90")


def parse_targeted_credit_card_pdf(raw: bytes) -> TargetedPdfParseOutcome:
    """Extract text from PDF and parse statement-like lines into ledger rows."""
    try:
        text = _extract_pdf_text(raw)
    except Exception as exc:  # noqa: BLE001 — tolerate malformed PDFs
        return TargetedPdfParseOutcome(
            (),
            Decimal("0.35"),
            f"pdf_read_error:{type(exc).__name__}",
        )

    cleaned = text.strip()
    if not cleaned:
        return TargetedPdfParseOutcome(
            (),
            Decimal("0.35"),
            "pdf_text_extraction:empty_or_unavailable",
        )

    parsed = _parse_statement_text(cleaned)
    n = len(parsed)
    conf = _confidence(n)
    notes = f"pdf_parser_v3:rows={n}"
    return TargetedPdfParseOutcome(tuple(parsed), conf, notes)


def requires_hitl(confidence: Decimal, *, threshold: Decimal = HITL_CONFIDENCE_THRESHOLD) -> bool:
    return confidence < threshold


def outcome_requires_hitl(
    outcome: TargetedPdfParseOutcome,
    *,
    threshold: Decimal = HITL_CONFIDENCE_THRESHOLD,
) -> bool:
    """Human review when confidence is low or the parser produced no rows to persist."""
    if requires_hitl(outcome.confidence, threshold=threshold):
        return True
    return len(outcome.rows) == 0
