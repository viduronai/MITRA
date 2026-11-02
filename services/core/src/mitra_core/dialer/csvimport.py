"""Campaign lists from a CSV file or pasted rows: +91 phone validation, dedupe, column mapping.

Pure (no database). The web app reads the uploaded file in the browser and sends its text, so
pasted rows (tabs from a spreadsheet, or commas) and files go through the same parser.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from mitra_core.dialer.queue import VARIABLE_NAME

MAX_TEXT_BYTES = 2_000_000
PHONE_HEADERS = (
    "phone",
    "mobile",
    "number",
    "phone_number",
    "mobile_number",
    "contact",
    "ఫోన్",
    "फ़ोन",
    "फोन",
)
NAME_HEADERS = ("name", "lead_name", "customer", "customer_name", "full_name", "పేరు", "नाम")
_INDIAN = re.compile(r"^\+91[1-9][0-9]{9}$")
_SLUG = re.compile(r"[^a-z0-9]+")

SAMPLE_CSV = (
    "name,phone,interest,area\n"
    "Ravi Kumar,98765 43210,2BHK flat,Kondapur\n"
    "Lakshmi,+91 91234 56789,Plot,Shamshabad\n"
    "Arjun Rao,08012345678,3BHK villa,Gachibowli\n"
)


class ListError(ValueError):
    pass


def normalize_phone(raw: str) -> str | None:
    """Indian numbers -> +91XXXXXXXXXX: 9876543210, 09876543210, 919876543210, +91 98765-43210."""
    digits = re.sub(r"[\s().-]", "", raw or "")
    if digits.startswith("+"):
        candidate = digits
    elif len(digits) == 10:
        candidate = "+91" + digits
    elif len(digits) == 11 and digits.startswith("0"):
        candidate = "+91" + digits[1:]
    elif len(digits) == 12 and digits.startswith("91"):
        candidate = "+" + digits
    else:
        return None
    return candidate if _INDIAN.fullmatch(candidate) else None


def slug(header: str) -> str:
    s = _SLUG.sub("_", header.strip().lower()).strip("_")[:40]
    if not s or not s[0].isalpha():
        s = ("col_" + s)[:40].rstrip("_")
    return s


@dataclass(frozen=True, slots=True)
class ParsedRow:
    row_number: int  # 1-based data row (excluding the header)
    phone: str
    name: str | None
    variables: dict[str, str]


@dataclass(frozen=True, slots=True)
class RowError:
    row_number: int
    reason: str  # invalid_phone | duplicate


@dataclass
class ParsedList:
    headers: list[str]
    phone_column: str
    name_column: str | None
    column_map: dict[str, str]
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)

    @property
    def duplicates(self) -> int:
        return sum(e.reason == "duplicate" for e in self.errors)

    @property
    def invalid(self) -> int:
        return sum(e.reason == "invalid_phone" for e in self.errors)


def _rows(text: str) -> list[list[str]]:
    sample = text[:4096]
    delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
    if delimiter == "," and sample.count(";") > sample.count(","):
        delimiter = ";"
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [[c.strip() for c in r] for r in reader if any(c.strip() for c in r)]


def _pick(headers: list[str], candidates: tuple[str, ...]) -> str | None:
    lowered = {h.strip().lower(): h for h in headers}
    for c in candidates:
        if c in lowered:
            return lowered[c]
    return None


def default_column_map(
    headers: list[str], phone_column: str, name_column: str | None
) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in headers:
        if h == phone_column:
            continue
        var = "lead_name" if h == name_column else slug(h)
        if var not in out.values():
            out[h] = var
    return out


def parse_list(
    text: str,
    *,
    phone_column: str | None = None,
    name_column: str | None = None,
    column_map: dict[str, str] | None = None,
    max_rows: int = 5000,
) -> ParsedList:
    if len(text.encode()) > MAX_TEXT_BYTES:
        raise ListError("list is too large (max 2 MB)")
    table = _rows(text.lstrip("﻿"))
    if not table:
        raise ListError("the list is empty")
    first = table[0]
    has_header = not any(normalize_phone(c) for c in first)
    if has_header:
        headers, data = first, table[1:]
    else:  # pasted rows without a header: the phone column is found by content
        width = max(len(r) for r in table)
        headers, data = [f"column_{i + 1}" for i in range(width)], table
    if len(set(headers)) != len(headers):
        raise ListError("column names must be unique")
    phone_col = phone_column or _pick(headers, PHONE_HEADERS)
    if phone_col is None and not has_header:
        phone_col = next((headers[i] for i in range(len(first)) if normalize_phone(first[i])), None)
    if phone_col is None or phone_col not in headers:
        raise ListError("could not find the phone number column")
    name_col = name_column if name_column in headers else _pick(headers, NAME_HEADERS)
    if name_col is None and not has_header:
        name_col = next(
            (
                h
                for i, h in enumerate(headers)
                if h != phone_col and i < len(first) and first[i] and not normalize_phone(first[i])
            ),
            None,
        )
    mapping = (
        column_map if column_map is not None else default_column_map(headers, phone_col, name_col)
    )
    for header, var in mapping.items():
        if header not in headers:
            raise ListError(f"unknown column: {header[:40]}")
        if not VARIABLE_NAME.fullmatch(var):
            raise ListError(f"invalid variable name: {var[:40]}")
    if len(set(mapping.values())) != len(mapping):
        raise ListError("two columns map to the same variable")
    if len(data) > max_rows:
        raise ListError(f"at most {max_rows} people per campaign")

    index = {h: i for i, h in enumerate(headers)}
    out = ParsedList(
        headers=headers, phone_column=phone_col, name_column=name_col, column_map=mapping
    )
    seen: set[str] = set()
    for n, row in enumerate(data, start=1):

        def cell(h: str, row: list[str] = row) -> str:
            i = index[h]
            return row[i] if i < len(row) else ""

        phone = normalize_phone(cell(phone_col))
        if phone is None:
            out.errors.append(RowError(n, "invalid_phone"))
            continue
        if phone in seen:
            out.errors.append(RowError(n, "duplicate"))
            continue
        seen.add(phone)
        name = cell(name_col)[:120] or None if name_col else None
        variables = {var: cell(h)[:200] for h, var in mapping.items() if cell(h)}
        out.rows.append(ParsedRow(n, phone, name, variables))
    return out
