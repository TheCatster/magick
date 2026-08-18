"""Shared test helpers."""

from __future__ import annotations

import csv
import os
import tempfile

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

HELVAULT_HEADER = (
    "collector_number,extras,language,name,quantity,set_code"
)
MOXFIELD_HEADER = (
    '"Count","Tradelist Count","Name","Edition","Condition","Language","Foil",'
    '"Tags","Last Modified","Collector Number","Alter","Proxy","Purchase Price"'
)


def fixture(name: str) -> str:
    return os.path.join(FIXTURES, name)


def write_csv(directory: str, name: str, text: str) -> str:
    """Write raw CSV text verbatim (so tests can craft malformed input)."""
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path


def helvault_csv(directory: str, *rows: str, name: str = "h.csv") -> str:
    return write_csv(directory, name, "\n".join((HELVAULT_HEADER, *rows)) + "\n")


def moxfield_csv(directory: str, *rows: str, name: str = "m.csv") -> str:
    return write_csv(directory, name, "\r\n".join((MOXFIELD_HEADER, *rows)) + "\r\n")


def read_output(path: str) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def counts_by_card(rows: list[dict[str, str]]) -> dict[tuple[str, ...], int]:
    return {
        (r["Name"], r["Edition"], r["Collector Number"], r["Foil"], r["Language"]): int(
            r["Count"]
        )
        for r in rows
    }


class TempDir(tempfile.TemporaryDirectory):
    pass
