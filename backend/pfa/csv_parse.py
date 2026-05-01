"""Parse uploaded CSV rows into normalized ingest inputs."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import BinaryIO


class CsvParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedCsvRow:
    transaction_date: date
    posted_date: date | None
    amount: Decimal
    currency: str
    description_raw: str


_REQUIRED = frozenset({"transaction_date", "amount", "description"})


def _norm_header(h: str) -> str:
    return h.strip().lower().replace(" ", "_")


def _parse_date(value: str, *, field: str) -> date:
    raw = value.strip()
    if not raw:
        raise CsvParseError(f"empty {field}")
    try:
        return date.fromisoformat(raw)
    except ValueError as e:
        raise CsvParseError(f"invalid date for {field}: {raw!r}") from e


def _parse_amount(value: str) -> Decimal:
    t = value.strip().replace(",", "").replace("$", "").replace("€", "").strip()
    if not t:
        raise CsvParseError("empty amount")
    try:
        return Decimal(t)
    except InvalidOperation as e:
        raise CsvParseError(f"invalid amount: {value!r}") from e


def parse_csv_bytes(data: bytes) -> list[ParsedCsvRow]:
    text = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8-sig", newline="")
    reader = csv.DictReader(text)
    if reader.fieldnames is None:
        raise CsvParseError("missing header row")
    fields = {_norm_header(h) for h in reader.fieldnames if h is not None}
    missing = _REQUIRED - fields
    if missing:
        raise CsvParseError(f"missing required columns: {sorted(missing)}")
    rows: list[ParsedCsvRow] = []
    for i, raw in enumerate(reader, start=2):
        if raw is None:
            continue
        row = {_norm_header(k): (v or "").strip() for k, v in raw.items() if k}
        if not any(row.values()):
            continue
        try:
            td = _parse_date(row["transaction_date"], field="transaction_date")
            posted = None
            if row.get("posted_date"):
                posted = _parse_date(row["posted_date"], field="posted_date")
            amt = _parse_amount(row["amount"])
            desc = row["description"]
            if not desc:
                raise CsvParseError(f"row {i}: empty description")
            cur = row.get("currency") or "USD"
            if not cur:
                cur = "USD"
            rows.append(
                ParsedCsvRow(
                    transaction_date=td,
                    posted_date=posted,
                    amount=amt,
                    currency=cur.upper(),
                    description_raw=desc,
                )
            )
        except CsvParseError as e:
            raise CsvParseError(f"row {i}: {e}") from e
    return rows


def parse_csv_file(fp: BinaryIO) -> list[ParsedCsvRow]:
    return parse_csv_bytes(fp.read())
