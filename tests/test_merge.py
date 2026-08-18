"""Core merge behaviour, verified on the fixture exports."""

from __future__ import annotations

import unittest

from magick import helvault, moxfield
from magick.merge import aggregate, merge
from magick.model import CardKey
from tests.helpers import fixture

BOLT = CardKey("2ed", "161", "", "English")
BOLT_FOIL = CardKey("2ed", "161", "foil", "English")
BOLT_ALPHA = CardKey("lea", "161", "", "English")
SOL_RING = CardKey("cmr", "472", "etched", "English")
FOREST_FR = CardKey("eoe", "88", "", "French")
COUNTERSPELL = CardKey("tmp", "63", "foil", "English")
LOTUS = CardKey("lea", "232", "", "English")


def load(helvault_name="helvault_basic.csv", moxfield_name="moxfield_basic.csv", **kw):
    h, _ = helvault.read(fixture(helvault_name))
    m, _ = moxfield.read(fixture(moxfield_name), "Near Mint")
    return merge(h, m, **kw)


class MergeTest(unittest.TestCase):
    def setUp(self):
        self.result = load()
        self.by_key = {entry.key: entry for entry in self.result.entries}

    def test_duplicate_rows_within_helvault_are_aggregated(self):
        h, _ = helvault.read(fixture("helvault_basic.csv"))
        self.assertEqual(len(h), 7)  # rows as written
        self.assertEqual(aggregate(h)[BOLT].count, 3)  # 2 + 1

    def test_duplicate_rows_within_moxfield_are_aggregated(self):
        m, _ = moxfield.read(fixture("moxfield_basic.csv"), "Near Mint")
        self.assertEqual(len(m), 6)
        self.assertEqual(aggregate(m)[BOLT].count, 4)  # 3 + 1

    def test_card_in_both_sources_sums_quantities(self):
        self.assertEqual(self.by_key[BOLT].count, 7)  # helvault 3 + moxfield 4

    def test_card_only_in_helvault_is_kept(self):
        self.assertEqual(self.by_key[FOREST_FR].count, 4)
        self.assertEqual(self.by_key[BOLT_ALPHA].count, 1)

    def test_card_only_in_moxfield_is_kept(self):
        self.assertEqual(self.by_key[LOTUS].count, 1)

    def test_output_is_the_union_of_both_sources(self):
        self.assertEqual(
            set(self.by_key),
            {BOLT, BOLT_FOIL, BOLT_ALPHA, SOL_RING, FOREST_FR, COUNTERSPELL, LOTUS},
        )
        self.assertEqual(self.result.unique_cards, 7)
        self.assertEqual(self.result.total_copies, 7 + 2 + 1 + 3 + 4 + 3 + 1)

    def test_different_printings_are_not_merged(self):
        # Same name, different finish / set / language stay separate rows.
        self.assertEqual(self.by_key[BOLT_FOIL].count, 2)  # 1 + 1
        self.assertEqual(self.by_key[BOLT].count, 7)
        self.assertEqual(self.by_key[BOLT_ALPHA].count, 1)
        self.assertNotIn(CardKey("eoe", "88", "", "English"), self.by_key)

    def test_equivalent_identifiers_normalise(self):
        # Helvault 'etchedFoil' == Moxfield 'etched'; a stray '/foil' is foil;
        # 'fr' == 'French'; set codes and collector numbers fold to lower case.
        self.assertEqual(self.by_key[SOL_RING].count, 3)  # 2 + 1
        self.assertEqual(self.by_key[COUNTERSPELL].count, 3)  # 1 + 2
        self.assertEqual(self.by_key[FOREST_FR].key.language, "French")

    def test_moxfield_metadata_takes_precedence(self):
        sol = self.by_key[SOL_RING]
        self.assertEqual(sol.tags, ["cube", "edh"])
        self.assertEqual(sol.purchase_price, "24.99")
        self.assertEqual(sol.last_modified, "2025-03-03 10:00:00.000000")
        # Latest of the two duplicate Moxfield rows wins.
        self.assertEqual(self.by_key[BOLT].last_modified, "2025-02-02 10:00:00.000000")

    def test_helvault_only_cards_get_default_condition_and_no_invented_metadata(self):
        forest = self.by_key[FOREST_FR]
        self.assertEqual(forest.conditions, {"Near Mint": 4})
        self.assertEqual(forest.purchase_price, "")  # never taken from estimated_price
        self.assertEqual(forest.last_modified, "")

    def test_tradelist_count_never_exceeds_count(self):
        for entry in self.result.entries:
            self.assertLessEqual(entry.tradelist_count, entry.count, entry.name)
        # Moxfield had 1 copy with tradelist 0; Helvault adds 2 tradeable copies.
        self.assertEqual(self.by_key[SOL_RING].tradelist_count, 2)

    def test_statistics(self):
        self.assertEqual(self.result.helvault.rows, 7)
        self.assertEqual(self.result.helvault.unique, 6)
        self.assertEqual(self.result.helvault.copies, 12)
        self.assertEqual(self.result.moxfield.rows, 6)
        self.assertEqual(self.result.moxfield.unique, 5)
        self.assertEqual(self.result.moxfield.copies, 9)
        self.assertEqual(self.result.in_both, 4)
        self.assertEqual(self.result.only_helvault, 2)
        self.assertEqual(self.result.only_moxfield, 1)


class StrategyTest(unittest.TestCase):
    def by_key(self, strategy):
        return {e.key: e for e in load(strategy=strategy).entries}

    def test_max_keeps_the_larger_side(self):
        entries = self.by_key("max")
        self.assertEqual(entries[BOLT].count, 4)  # max(3, 4)
        self.assertEqual(entries[FOREST_FR].count, 4)  # helvault only, untouched
        self.assertEqual(entries[LOTUS].count, 1)  # moxfield only, untouched

    def test_source_preferring_strategies(self):
        self.assertEqual(self.by_key("helvault")[BOLT].count, 3)
        self.assertEqual(self.by_key("moxfield")[BOLT].count, 4)
        # Cards the preferred source lacks are still kept, with their own count.
        self.assertEqual(self.by_key("helvault")[LOTUS].count, 1)
        self.assertEqual(self.by_key("moxfield")[FOREST_FR].count, 4)

    def test_unknown_strategy_is_rejected(self):
        with self.assertRaises(ValueError):
            load(strategy="average")


class ZeroQuantityTest(unittest.TestCase):
    def test_zero_count_cards_are_dropped_and_reported(self):
        from magick.model import Entry

        result = merge(
            [Entry(key=BOLT, name="Lightning Bolt", count=0)],
            [Entry(key=LOTUS, name="Black Lotus", count=1)],
        )
        self.assertEqual(result.dropped_zero, 1)
        self.assertEqual([e.key for e in result.entries], [LOTUS])


if __name__ == "__main__":
    unittest.main()
