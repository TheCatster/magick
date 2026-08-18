"""Read and write the Moxfield collection CSV format.

Observed header (Moxfield collection export, 2026):

    "Count","Tradelist Count","Name","Edition","Condition","Language","Foil",
    "Tags","Last Modified","Collector Number","Alter","Proxy","Purchase Price"

The same schema is what Moxfield's collection importer accepts, so the output
is written with exactly these columns, in this order, and nothing else.
"""

from __future__ import annotations

import csv
from typing import Iterable

from .csvio import parse_quantity, read_rows
from .errors import RowError
from .model import FINISH_ETCHED, FINISH_FOIL, FINISH_NONFOIL, CardKey, Entry

COLUMNS = (
    "Count",
    "Tradelist Count",
    "Name",
    "Edition",
    "Condition",
    "Language",
    "Foil",
    "Tags",
    "Last Modified",
    "Collector Number",
    "Alter",
    "Proxy",
    "Purchase Price",
)

#: Columns without which a row cannot be identified or counted.
REQUIRED_COLUMNS = ("Count", "Name", "Edition", "Collector Number", "Foil", "Language")

#: Optional columns: absent ones fall back to a default rather than failing.
OPTIONAL_COLUMNS = (
    "Tradelist Count",
    "Condition",
    "Tags",
    "Last Modified",
    "Alter",
    "Proxy",
    "Purchase Price",
)

FINISHES = {
    "": FINISH_NONFOIL,
    "normal": FINISH_NONFOIL,
    "nonfoil": FINISH_NONFOIL,
    "foil": FINISH_FOIL,
    "etched": FINISH_ETCHED,
    "etchedfoil": FINISH_ETCHED,
}


def read(path: str, default_condition: str) -> tuple[list[Entry], list[str]]:
    """Return one Entry per Moxfield row (unaggregated) plus any warnings."""
    entries: list[Entry] = []
    warnings: list[str] = []
    present = _present_columns(path)
    columns = REQUIRED_COLUMNS + tuple(c for c in OPTIONAL_COLUMNS if c in present)
    missing = [c for c in OPTIONAL_COLUMNS if c not in present]
    if missing:
        warnings.append(
            f"{path}: optional column(s) {', '.join(missing)} not present; "
            "defaults will be used"
        )

    for line, row in read_rows(path, columns):
        name = row["Name"]
        if not name:
            raise RowError(path, line, "column 'Name' is empty; card cannot be identified")
        edition = row["Edition"].lower()
        if not edition:
            raise RowError(
                path, line, f"column 'Edition' is empty for {name!r}; "
                "card identity cannot be established"
            )
        collector_number = row["Collector Number"].lower()
        if not collector_number:
            raise RowError(
                path, line, f"column 'Collector Number' is empty for {name!r}; "
                "card identity cannot be established"
            )
        language = row["Language"] or "English"
        count = parse_quantity(path, line, "Count", row["Count"])
        tradelist_raw = row.get("Tradelist Count", "")
        tradelist = (
            parse_quantity(path, line, "Tradelist Count", tradelist_raw)
            if tradelist_raw
            else 0
        )
        condition = row.get("Condition", "") or default_condition
        entries.append(
            Entry(
                key=CardKey(
                    set_code=edition,
                    collector_number=collector_number,
                    finish=_parse_finish(path, line, row["Foil"]),
                    language=language,
                ),
                name=name,
                count=count,
                tradelist_count=min(tradelist, count),
                conditions={condition: count} if count else {condition: 0},
                tags=_parse_tags(row.get("Tags", "")),
                last_modified=row.get("Last Modified", ""),
                alter=_parse_bool(row.get("Alter", "")),
                proxy=_parse_bool(row.get("Proxy", "")),
                purchase_price=row.get("Purchase Price", ""),
            )
        )
    return entries, warnings


def write(path: str, entries: Iterable[Entry]) -> int:
    """Write entries as a Moxfield-importable CSV. ``path`` of '-' means stdout."""
    import sys

    if path == "-":
        return _write_to(sys.stdout, entries)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        return _write_to(handle, entries)


def _write_to(handle, entries: Iterable[Entry]) -> int:
    # QUOTE_ALL and CRLF reproduce Moxfield's own export byte-for-byte in style.
    writer = csv.writer(handle, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    written = 0
    for entry in entries:
        writer.writerow(
            [
                entry.count,
                entry.tradelist_count,
                entry.name,
                entry.key.set_code,
                _condition_of(entry),
                entry.key.language,
                entry.key.finish,
                ",".join(entry.tags),
                entry.last_modified,
                entry.key.collector_number,
                "True" if entry.alter else "False",
                "True" if entry.proxy else "False",
                entry.purchase_price,
            ]
        )
        written += 1
    return written


def _condition_of(entry: Entry) -> str:
    if not entry.conditions:
        return ""
    # Most-copies wins; ties broken alphabetically so output is deterministic.
    return max(sorted(entry.conditions), key=lambda c: entry.conditions[c])


def _present_columns(path: str) -> set[str]:
    """Peek at the header so optional columns can be skipped when absent."""
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle), []) or []
    lowered = {h.strip().lower() for h in header}
    return {c for c in COLUMNS if c.lower() in lowered}


def _parse_finish(path: str, line: int, raw: str) -> str:
    token = raw.strip().lower()
    if token in FINISHES:
        return FINISHES[token]
    raise RowError(
        path,
        line,
        f"column 'Foil' has unrecognised value {raw!r}; "
        f"expected one of: (empty), foil, etched",
    )


def _parse_tags(raw: str) -> list[str]:
    return [tag.strip() for tag in raw.split(",") if tag.strip()]


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"true", "yes", "1"}
