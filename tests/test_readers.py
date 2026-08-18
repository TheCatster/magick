"""Parsing, normalisation and input validation."""

from __future__ import annotations

import unittest

from magick import helvault, moxfield
from magick.errors import InputError, RowError
from magick.model import CardKey
from tests.helpers import TempDir, fixture, helvault_csv, moxfield_csv, write_csv


class HelvaultReaderTest(unittest.TestCase):
    def read(self, *rows, **kw):
        with TempDir() as tmp:
            return helvault.read(helvault_csv(tmp, *rows), **kw)[0]

    def test_identity_is_case_and_whitespace_insensitive(self):
        rows = self.read(
            '"161","","en","Lightning Bolt","1","2ED"',
            '" 161 ","","EN"," Lightning Bolt ","1"," 2ed "',
        )
        self.assertEqual(rows[0].key, CardKey("2ed", "161", "", "English"))
        self.assertEqual(rows[0].key, rows[1].key)

    def test_finish_normalisation(self):
        rows = self.read(
            '"1","","en","A","1","xxx"',
            '"2","foil","en","A","1","xxx"',
            '"3","etchedFoil","en","A","1","xxx"',
            '"4","/foil","en","A","1","xxx"',
            '"5","nonfoil","en","A","1","xxx"',
        )
        self.assertEqual([r.key.finish for r in rows], ["", "foil", "etched", "foil", ""])

    def test_language_codes_map_to_moxfield_names(self):
        rows = self.read(
            '"1","","en","A","1","xxx"',
            '"2","","fr","A","1","xxx"',
            '"3","","zhs","A","1","xxx"',
            '"4","","Japanese","A","1","xxx"',
        )
        self.assertEqual(
            [r.key.language for r in rows],
            ["English", "French", "Chinese Simplified", "Japanese"],
        )

    def test_unknown_language_is_fatal(self):
        with self.assertRaises(RowError) as ctx:
            self.read('"1","","elvish","A","1","xxx"')
        self.assertIn("'language'", str(ctx.exception))
        self.assertIn("elvish", str(ctx.exception))

    def test_unknown_extras_is_fatal_unless_allowed(self):
        with self.assertRaises(RowError) as ctx:
            self.read('"1","serialized","en","A","1","xxx"')
        self.assertIn("--allow-unknown-extras", str(ctx.exception))

        with TempDir() as tmp:
            path = helvault_csv(tmp, '"1","serialized/foil","en","A","1","xxx"')
            rows, warnings = helvault.read(path, allow_unknown_extras=True)
        self.assertEqual(rows[0].key.finish, "foil")
        self.assertEqual(len(warnings), 1)
        self.assertIn("serialized", warnings[0])

    def test_missing_identity_fields_are_fatal(self):
        for row, column in (
            ('"161","","en","","1","2ed"', "name"),
            ('"161","","en","A","1",""', "set_code"),
            ('"","","en","A","1","2ed"', "collector_number"),
        ):
            with self.subTest(column=column), self.assertRaises(RowError) as ctx:
                self.read(row)
            self.assertIn(column, str(ctx.exception))

    def test_invalid_quantities_are_fatal(self):
        for value, expected in (("two", "non-numeric"), ("-1", "negative"), ("", "empty")):
            with self.subTest(value=value), self.assertRaises(RowError) as ctx:
                self.read(f'"161","","en","A","{value}","2ed"')
            self.assertIn(expected, str(ctx.exception))
            self.assertIn("h.csv:2", str(ctx.exception))  # file and line reported

    def test_bom_and_crlf_fixture(self):
        rows, _ = helvault.read(fixture("helvault_bom_crlf.csv"))
        self.assertEqual(len(rows), 7)
        self.assertIn("Juzám Djinn", [r.name for r in rows])
        self.assertEqual(rows[0].key, CardKey("2ed", "161", "", "English"))

    def test_missing_required_column(self):
        with TempDir() as tmp:
            path = write_csv(tmp, "h.csv", "name,set_code,quantity\n\"A\",\"2ed\",\"1\"\n")
            with self.assertRaises(InputError) as ctx:
                helvault.read(path)
        message = str(ctx.exception)
        self.assertIn("missing required column", message)
        self.assertIn("collector_number", message)
        self.assertIn("extras", message)

    def test_missing_file(self):
        with self.assertRaises(InputError) as ctx:
            helvault.read("/nonexistent/nope.csv")
        self.assertIn("does not exist", str(ctx.exception))

    def test_empty_file(self):
        with TempDir() as tmp:
            with self.assertRaises(InputError) as ctx:
                helvault.read(write_csv(tmp, "h.csv", ""))
        self.assertIn("empty", str(ctx.exception))

    def test_malformed_row_with_too_many_fields(self):
        with TempDir() as tmp:
            with self.assertRaises(RowError) as ctx:
                helvault.read(helvault_csv(tmp, '"161","","en","A","1","2ed","boom"'))
        self.assertIn("malformed", str(ctx.exception))

    def test_broken_quoting_fails_loudly_rather_than_silently(self):
        with TempDir() as tmp:
            path = write_csv(
                tmp,
                "h.csv",
                'collector_number,extras,language,name,quantity,set_code\n'
                '"161","","en","Unclosed,"1","2ed"\n',
            )
            with self.assertRaises((InputError, RowError)) as ctx:
                helvault.read(path)
        self.assertIn("h.csv", str(ctx.exception))

    def test_blank_lines_are_skipped(self):
        rows = self.read('"161","","en","A","1","2ed"', "", '"162","","en","B","1","2ed"')
        self.assertEqual(len(rows), 2)


class MoxfieldReaderTest(unittest.TestCase):
    def read(self, *rows, condition="Near Mint"):
        with TempDir() as tmp:
            return moxfield.read(moxfield_csv(tmp, *rows), condition)

    def test_quoted_commas_inside_names_survive(self):
        rows, _ = self.read(
            '"1","1","Sol Ring, the Ringening // Sol","cmr","Near Mint","English",'
            '"etched","cube,edh","","472","False","False",""'
        )
        self.assertEqual(rows[0].name, "Sol Ring, the Ringening // Sol")
        self.assertEqual(rows[0].tags, ["cube", "edh"])

    def test_unknown_foil_value_is_fatal(self):
        with self.assertRaises(RowError) as ctx:
            self.read(
                '"1","1","A","2ed","Near Mint","English","glitter","","","161",'
                '"False","False",""'
            )
        self.assertIn("'Foil'", str(ctx.exception))

    def test_optional_columns_may_be_absent(self):
        with TempDir() as tmp:
            path = write_csv(
                tmp,
                "m.csv",
                "Count,Name,Edition,Collector Number,Foil,Language\r\n"
                '"2","Lightning Bolt","2ed","161","","English"\r\n',
            )
            rows, warnings = moxfield.read(path, "Lightly Played")
        self.assertEqual(rows[0].count, 2)
        self.assertEqual(rows[0].conditions, {"Lightly Played": 2})
        self.assertTrue(any("Condition" in w for w in warnings))

    def test_missing_required_column(self):
        with TempDir() as tmp:
            path = write_csv(tmp, "m.csv", 'Count,Name,Edition\r\n"1","A","2ed"\r\n')
            with self.assertRaises(InputError) as ctx:
                moxfield.read(path, "Near Mint")
        self.assertIn("Collector Number", str(ctx.exception))

    def test_invalid_count_is_fatal(self):
        with self.assertRaises(RowError) as ctx:
            self.read(
                '"many","1","A","2ed","Near Mint","English","","","","161",'
                '"False","False",""'
            )
        self.assertIn("'Count'", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
