"""Aggregation and merging: the core logic, independent of the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from .model import CardKey, Entry, sort_key

#: How copy counts from the two sources are combined for a card present in both.
STRATEGIES: dict[str, Callable[[int, int], int]] = {
    # Both files describe distinct physical copies: add them up. (Default.)
    "sum": lambda helvault, moxfield: helvault + moxfield,
    # The files overlap (e.g. Moxfield was previously fed from Helvault): keep
    # the larger of the two rather than double counting.
    "max": max,
    # One source is authoritative for shared cards; the other only contributes
    # cards it alone knows about.
    "helvault": lambda helvault, moxfield: helvault,
    "moxfield": lambda helvault, moxfield: moxfield,
}
DEFAULT_STRATEGY = "sum"


@dataclass
class SourceStats:
    rows: int = 0
    unique: int = 0
    copies: int = 0


@dataclass
class MergeResult:
    entries: list[Entry]
    helvault: SourceStats
    moxfield: SourceStats
    unique_cards: int = 0
    total_copies: int = 0
    only_helvault: int = 0
    only_moxfield: int = 0
    in_both: int = 0
    #: Cards present in both sources with the *same* count in each - a strong
    #: signal that the two exports describe the same physical cards.
    identical_in_both: int = 0
    dropped_zero: int = 0
    warnings: list[str] = field(default_factory=list)


def aggregate(entries: Iterable[Entry]) -> dict[CardKey, Entry]:
    """Collapse duplicate rows *within one source*.

    Repeated rows always describe additional physical copies, so counts are
    summed here regardless of the cross-source strategy.
    """
    result: dict[CardKey, Entry] = {}
    for entry in entries:
        existing = result.get(entry.key)
        if existing is None:
            result[entry.key] = Entry(
                key=entry.key,
                name=entry.name,
                count=entry.count,
                tradelist_count=entry.tradelist_count,
                conditions=dict(entry.conditions),
                tags=list(entry.tags),
                last_modified=entry.last_modified,
                alter=entry.alter,
                proxy=entry.proxy,
                purchase_price=entry.purchase_price,
            )
            continue
        existing.count += entry.count
        existing.tradelist_count += entry.tradelist_count
        for condition, copies in entry.conditions.items():
            existing.conditions[condition] = existing.conditions.get(condition, 0) + copies
        for tag in entry.tags:
            if tag not in existing.tags:
                existing.tags.append(tag)
        existing.last_modified = max(existing.last_modified, entry.last_modified)
        existing.alter = existing.alter or entry.alter
        existing.proxy = existing.proxy or entry.proxy
        existing.purchase_price = existing.purchase_price or entry.purchase_price
    return result


def merge(
    helvault_rows: Iterable[Entry],
    moxfield_rows: Iterable[Entry],
    strategy: str = DEFAULT_STRATEGY,
    default_condition: str = "Near Mint",
) -> MergeResult:
    """Merge two sources into one collection, one Entry per CardKey.

    Metadata precedence: Moxfield wins for every field it populates, Helvault
    fills only what Moxfield does not know (i.e. cards Moxfield never had).
    """
    if strategy not in STRATEGIES:
        raise ValueError(
            f"unknown strategy {strategy!r}; expected one of: "
            f"{', '.join(sorted(STRATEGIES))}"
        )
    combine = STRATEGIES[strategy]

    helvault_rows = list(helvault_rows)
    moxfield_rows = list(moxfield_rows)
    helvault = aggregate(helvault_rows)
    moxfield = aggregate(moxfield_rows)

    result = MergeResult(
        entries=[],
        helvault=_stats(helvault_rows, helvault),
        moxfield=_stats(moxfield_rows, moxfield),
    )

    for key in list(helvault) + [k for k in moxfield if k not in helvault]:
        h = helvault.get(key)
        m = moxfield.get(key)
        if h is not None and m is not None:
            result.in_both += 1
            if h.count == m.count:
                result.identical_in_both += 1
        elif h is not None:
            result.only_helvault += 1
        else:
            result.only_moxfield += 1

        # The strategy only decides how to reconcile a card *both* sources
        # know about. A card present in one source alone always keeps its own
        # count, so no strategy can make a card disappear.
        if h is None:
            count, tradelist = m.count, m.tradelist_count
        elif m is None:
            count, tradelist = h.count, h.tradelist_count
        else:
            count = combine(h.count, m.count)
            tradelist = combine(h.tradelist_count, m.tradelist_count)
        conditions = dict(m.conditions) if m else {}
        if m is not None and len(conditions) > 1:
            result.warnings.append(
                f"{(m.name)} ({key.describe()}): Moxfield lists several conditions "
                f"({', '.join(sorted(conditions))}); they are merged into one row "
                f"using {max(sorted(conditions), key=lambda c: conditions[c])!r}"
            )
        if not conditions:
            conditions = {default_condition: count}

        if count == 0:
            result.dropped_zero += 1
            continue

        result.entries.append(
            Entry(
                key=key,
                # Moxfield's own spelling wins; Helvault names cards Moxfield
                # has never seen.
                name=(m.name if m else h.name),
                count=count,
                tradelist_count=min(tradelist, count),
                conditions=conditions,
                tags=list(m.tags) if m else [],
                last_modified=m.last_modified if m else "",
                alter=m.alter if m else False,
                proxy=m.proxy if m else False,
                # Helvault's estimated_price is a market estimate, not a price
                # paid, so it is never written into Purchase Price.
                purchase_price=m.purchase_price if m else "",
            )
        )

    result.entries.sort(key=sort_key)
    result.unique_cards = len(result.entries)
    result.total_copies = sum(entry.count for entry in result.entries)
    return result


def _stats(rows: list[Entry], aggregated: dict[CardKey, Entry]) -> SourceStats:
    return SourceStats(
        rows=len(rows),
        unique=len(aggregated),
        copies=sum(entry.count for entry in aggregated.values()),
    )
