"""Canonical representation of a collection item, shared by both sources."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Finish is part of card identity. These are the only values Moxfield's
#: "Foil" column accepts: empty (non-foil), "foil", "etched".
FINISH_NONFOIL = ""
FINISH_FOIL = "foil"
FINISH_ETCHED = "etched"
FINISHES = (FINISH_NONFOIL, FINISH_FOIL, FINISH_ETCHED)


@dataclass(frozen=True)
class CardKey:
    """Identity of one distinct physical printing.

    Two rows describe the same stack of cards if and only if all four fields
    match. Deliberately excluded: card name (derived from set + collector
    number), condition (Helvault cannot express it), and tags/prices/alters.
    """

    set_code: str
    collector_number: str
    finish: str
    language: str

    def describe(self) -> str:
        finish = self.finish or "nonfoil"
        return (
            f"{self.set_code.upper()} #{self.collector_number} "
            f"[{finish}, {self.language}]"
        )


@dataclass
class Entry:
    """Aggregated copies of one CardKey, plus the metadata seen alongside them."""

    key: CardKey
    name: str
    count: int
    tradelist_count: int = 0
    #: condition -> number of copies carrying it. Empty when the source
    #: (Helvault) does not record condition at all.
    conditions: dict[str, int] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    last_modified: str = ""
    alter: bool = False
    proxy: bool = False
    purchase_price: str = ""


_NUM_CHUNK = re.compile(r"(\d+)")


def sort_key(entry: Entry) -> tuple:
    """Deterministic, human-friendly output ordering."""
    parts = tuple(
        int(chunk) if chunk.isdigit() else chunk
        for chunk in _NUM_CHUNK.split(entry.key.collector_number)
        if chunk
    )
    # int/str are not mutually comparable, so tag each part with its type.
    collector = tuple((0, p, "") if isinstance(p, int) else (1, 0, p) for p in parts)
    return (
        entry.name.lower(),
        entry.key.set_code,
        collector,
        entry.key.finish,
        entry.key.language,
    )
