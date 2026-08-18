"""Shared CSV reading. Handles BOM, CRLF, quoting and reports errors by file/row."""

from __future__ import annotations

import csv
import os
from typing import Iterator

from .errors import InputError, RowError


def read_rows(
    path: str, required_columns: tuple[str, ...]
) -> Iterator[tuple[int, dict[str, str]]]:
    """Yield ``(line_number, row)`` with header names normalised to canonical case.

    ``encoding="utf-8-sig"`` transparently strips a UTF-8 BOM; ``newline=""``
    lets the csv module handle both CRLF and LF line endings, including
    newlines inside quoted fields.
    """
    if not os.path.exists(path):
        raise InputError(f"{path}: file does not exist")
    if os.path.isdir(path):
        raise InputError(f"{path}: is a directory, expected a CSV file")

    try:
        handle = open(path, "r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise InputError(f"{path}: cannot open file ({exc.strerror})") from exc

    with handle:
        reader = csv.reader(handle)
        try:
            header = next(reader, None)
        except (csv.Error, UnicodeDecodeError) as exc:
            raise InputError(f"{path}: cannot parse CSV header ({exc})") from exc
        if header is None:
            raise InputError(f"{path}: file is empty, expected a CSV header row")

        canonical = _map_header(path, header, required_columns)

        for line, values in _iter_rows(path, reader):
            if len(values) > len(header):
                raise RowError(
                    path,
                    line,
                    f"row has {len(values)} fields but the header has "
                    f"{len(header)}; the file looks malformed",
                )
            row = {name: "" for name in canonical.values()}
            for index, name in canonical.items():
                if index < len(values):
                    row[name] = values[index].strip()
            yield line, row


def _iter_rows(path: str, reader) -> Iterator[tuple[int, list[str]]]:
    while True:
        try:
            values = next(reader)
        except StopIteration:
            return
        except (csv.Error, UnicodeDecodeError) as exc:
            raise InputError(f"{path}: cannot parse CSV ({exc})") from exc
        if not values or all(value.strip() == "" for value in values):
            continue  # blank separator line
        yield reader.line_num, values


def _map_header(
    path: str, header: list[str], required_columns: tuple[str, ...]
) -> dict[int, str]:
    """Map column index -> canonical column name, matching case-insensitively."""
    seen: dict[str, int] = {}
    for index, raw in enumerate(header):
        seen.setdefault(raw.strip().lower(), index)

    missing = [name for name in required_columns if name.lower() not in seen]
    if missing:
        raise InputError(
            f"{path}: missing required column(s): {', '.join(missing)}. "
            f"Found: {', '.join(h.strip() for h in header) or '(none)'}"
        )
    return {seen[name.lower()]: name for name in required_columns}


def parse_quantity(path: str, line: int, column: str, raw: str) -> int:
    """Parse a copy count. Anything that is not a non-negative integer is fatal."""
    text = raw.strip()
    if text == "":
        raise RowError(path, line, f"column {column!r} is empty; expected a whole number")
    try:
        value = int(text)
    except ValueError:
        raise RowError(
            path, line, f"column {column!r} has non-numeric quantity {raw!r}"
        ) from None
    if value < 0:
        raise RowError(path, line, f"column {column!r} has negative quantity {raw!r}")
    return value
