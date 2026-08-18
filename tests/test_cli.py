"""End-to-end CLI behaviour and Moxfield output compatibility."""

from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout

from magick import moxfield
from magick.cli import main
from tests.helpers import TempDir, counts_by_card, fixture, read_output


def _read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
    except SystemExit as exc:  # argparse exits 2 on usage errors
        code = exc.code
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def merge_fixtures(self, tmp, *extra):
        output = os.path.join(tmp, "collection.csv")
        code, out, err = run(
            "-H", fixture("helvault_basic.csv"),
            "-m", fixture("moxfield_basic.csv"),
            "-o", output, *extra,
        )
        return code, output, out, err

    def test_end_to_end_writes_expected_collection(self):
        with TempDir() as tmp:
            code, output, _, err = self.merge_fixtures(tmp)
            self.assertEqual(code, 0, err)
            rows = read_output(output)
        self.assertEqual(
            counts_by_card(rows),
            {
                ("Black Lotus", "lea", "232", "", "English"): 1,
                ("Counterspell", "tmp", "63", "foil", "English"): 3,
                ("Forest", "eoe", "88", "", "French"): 4,
                ("Lightning Bolt", "2ed", "161", "", "English"): 7,
                ("Lightning Bolt", "2ed", "161", "foil", "English"): 2,
                ("Lightning Bolt", "lea", "161", "", "English"): 1,
                ("Sol Ring, the Ringening // Sol", "cmr", "472", "etched", "English"): 3,
            },
        )
        self.assertIn("7 unique cards", err)
        self.assertIn("21 total copies", err)

    def test_output_schema_is_moxfield_compatible(self):
        with TempDir() as tmp:
            _, output, _, _ = self.merge_fixtures(tmp)
            with open(output, encoding="utf-8", newline="") as handle:
                header = handle.readline()
            rows = read_output(output)
        expected = ",".join(f'"{c}"' for c in moxfield.COLUMNS)
        self.assertEqual(header, expected + "\r\n")  # exact columns, exact order
        for row in rows:
            self.assertEqual(tuple(row), moxfield.COLUMNS)  # no extra columns
            self.assertIn(row["Foil"], ("", "foil", "etched"))
            self.assertIn(row["Alter"], ("True", "False"))
            self.assertIn(row["Proxy"], ("True", "False"))
            self.assertTrue(row["Condition"])
            self.assertGreaterEqual(int(row["Count"]), 1)
            self.assertLessEqual(int(row["Tradelist Count"]), int(row["Count"]))

    def test_output_can_be_read_back_as_a_moxfield_export(self):
        """The result round-trips: re-reading it yields the same collection."""
        with TempDir() as tmp:
            _, output, _, _ = self.merge_fixtures(tmp)
            reread, warnings = moxfield.read(output, "Near Mint")
            original = read_output(output)
        self.assertEqual(warnings, [])
        self.assertEqual(len(reread), len(original))
        self.assertEqual(sum(e.count for e in reread), 21)

    def test_utf8_bom_input_is_handled(self):
        with TempDir() as tmp:
            output = os.path.join(tmp, "out.csv")
            code, _, err = run(
                "-H", fixture("helvault_bom_crlf.csv"),
                "-m", fixture("moxfield_basic.csv"),
                "-o", output,
            )
            self.assertEqual(code, 0, err)
            rows = read_output(output)
        names = [r["Name"] for r in rows]
        self.assertIn("Juzám Djinn", names)
        self.assertNotIn("﻿", "".join(names))

    def test_strategy_max(self):
        with TempDir() as tmp:
            _, output, _, _ = self.merge_fixtures(tmp, "--strategy", "max")
            counts = counts_by_card(read_output(output))
        self.assertEqual(counts[("Lightning Bolt", "2ed", "161", "", "English")], 4)
        self.assertEqual(len(counts), 7)  # union is preserved under every strategy

    def test_stdout_output(self):
        code, out, err = run(
            "-H", fixture("helvault_basic.csv"),
            "-m", fixture("moxfield_basic.csv"),
            "-o", "-",
        )
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith('"Count","Tradelist Count"'))
        self.assertEqual(len(out.strip().splitlines()), 8)  # header + 7 cards

    def test_quiet_suppresses_summary_but_not_errors(self):
        with TempDir() as tmp:
            _, _, out, err = self.merge_fixtures(tmp, "--quiet")
            self.assertEqual(err, "")
            self.assertEqual(out, "")

    def test_existing_output_is_not_clobbered_without_force(self):
        with TempDir() as tmp:
            output = os.path.join(tmp, "collection.csv")
            with open(output, "w") as handle:
                handle.write("precious\n")
            code, _, err = run(
                "-H", fixture("helvault_basic.csv"),
                "-m", fixture("moxfield_basic.csv"),
                "-o", output,
            )
            self.assertEqual(code, 1)
            self.assertIn("--force", err)
            self.assertEqual(_read(output), "precious\n")

            code, _, _ = run(
                "-H", fixture("helvault_basic.csv"),
                "-m", fixture("moxfield_basic.csv"),
                "-o", output, "--force",
            )
            self.assertEqual(code, 0)
            self.assertNotEqual(_read(output), "precious\n")

    def test_missing_input_file_exits_nonzero_with_actionable_error(self):
        with TempDir() as tmp:
            code, _, err = run(
                "-H", "/nope/helvault.csv",
                "-m", fixture("moxfield_basic.csv"),
                "-o", os.path.join(tmp, "out.csv"),
            )
        self.assertEqual(code, 1)
        self.assertIn("/nope/helvault.csv", err)
        self.assertIn("does not exist", err)

    def test_no_output_is_written_when_input_is_invalid(self):
        with TempDir() as tmp:
            output = os.path.join(tmp, "out.csv")
            code, _, err = run(
                "-H", fixture("moxfield_basic.csv"),  # wrong file on purpose
                "-m", fixture("moxfield_basic.csv"),
                "-o", output,
            )
        self.assertEqual(code, 1)
        self.assertIn("missing required column", err)
        self.assertFalse(os.path.exists(output))

    def test_missing_arguments_exit_with_usage_error(self):
        code, _, _ = run("-H", fixture("helvault_basic.csv"))
        self.assertEqual(code, 2)

    def test_environment_variables_supply_defaults(self):
        with TempDir() as tmp:
            output = os.path.join(tmp, "out.csv")
            os.environ.update(
                MAGICK_HELVAULT=fixture("helvault_basic.csv"),
                MAGICK_MOXFIELD=fixture("moxfield_basic.csv"),
                MAGICK_OUTPUT=output,
                MAGICK_STRATEGY="max",
            )
            try:
                code, _, err = run()
            finally:
                for name in ("MAGICK_HELVAULT", "MAGICK_MOXFIELD", "MAGICK_OUTPUT",
                             "MAGICK_STRATEGY"):
                    os.environ.pop(name, None)
            self.assertEqual(code, 0, err)
            self.assertIn("(max)", err)
            self.assertTrue(os.path.exists(output))


if __name__ == "__main__":
    unittest.main()
