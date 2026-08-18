"""Command line interface. Parsing/merging live in the other modules."""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__, helvault, moxfield
from .errors import MagickError
from .merge import DEFAULT_STRATEGY, STRATEGIES, MergeResult, merge

EXIT_OK = 0
EXIT_ERROR = 1  # argparse itself exits 2 on usage errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="magick",
        description=(
            "Merge a Helvault CSV export and a Moxfield CSV export into one "
            "de-duplicated, Moxfield-importable collection CSV."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Cards are identified by set code + collector number + finish + "
            "language.\nEvery option can also be supplied as an environment "
            "variable (MAGICK_HELVAULT,\nMAGICK_MOXFIELD, MAGICK_OUTPUT, "
            "MAGICK_STRATEGY), which is handy inside Docker."
        ),
    )
    # -h is argparse's help flag, so the Helvault input takes -H.
    parser.add_argument(
        "-H",
        "--helvault",
        metavar="CSV",
        default=os.environ.get("MAGICK_HELVAULT"),
        help="path to the Helvault CSV export",
    )
    parser.add_argument(
        "-m",
        "--moxfield",
        metavar="CSV",
        default=os.environ.get("MAGICK_MOXFIELD"),
        help="path to the Moxfield CSV export",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="CSV",
        default=os.environ.get("MAGICK_OUTPUT"),
        help="path for the merged CSV ('-' writes to stdout)",
    )
    parser.add_argument(
        "-s",
        "--strategy",
        choices=sorted(STRATEGIES),
        default=os.environ.get("MAGICK_STRATEGY", DEFAULT_STRATEGY),
        help=(
            "how to combine counts for a card present in both files: "
            "sum (default, both files list distinct physical copies), "
            "max, helvault, or moxfield"
        ),
    )
    parser.add_argument(
        "--default-condition",
        metavar="TEXT",
        default=os.environ.get("MAGICK_DEFAULT_CONDITION", "Near Mint"),
        help="condition for cards Moxfield does not know (default: %(default)s)",
    )
    parser.add_argument(
        "--allow-unknown-extras",
        action="store_true",
        help="treat unrecognised Helvault 'extras' values as non-finish decorations "
        "instead of failing",
    )
    parser.add_argument(
        "-f", "--force", action="store_true", help="overwrite an existing output file"
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress the summary")
    parser.add_argument("--version", action="version", version=f"magick {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    for name in ("helvault", "moxfield", "output"):
        if not getattr(args, name):
            parser.error(
                f"--{name} is required (or set MAGICK_{name.upper()})"
            )

    log = (lambda *a: None) if args.quiet else _log
    try:
        if (
            args.output != "-"
            and os.path.exists(args.output)
            and not args.force
        ):
            raise MagickError(
                f"{args.output}: output file already exists; pass --force to overwrite"
            )

        log("Reading Helvault collection...")
        helvault_rows, warnings = helvault.read(args.helvault, args.allow_unknown_extras)
        log("Reading Moxfield collection...")
        moxfield_rows, more = moxfield.read(args.moxfield, args.default_condition)
        warnings.extend(more)

        result = merge(
            helvault_rows,
            moxfield_rows,
            strategy=args.strategy,
            default_condition=args.default_condition,
        )
        warnings.extend(result.warnings)

        written = moxfield.write(args.output, result.entries)
    except MagickError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if not args.quiet:
        _summary(result, args, written)
    return EXIT_OK


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def _summary(result: MergeResult, args, written: int) -> None:
    out = sys.stderr
    n = lambda value: f"{value:,}"
    print(file=out)
    print(
        f"Helvault: {n(result.helvault.rows)} rows -> "
        f"{n(result.helvault.unique)} unique cards, "
        f"{n(result.helvault.copies)} copies",
        file=out,
    )
    print(
        f"Moxfield: {n(result.moxfield.rows)} rows -> "
        f"{n(result.moxfield.unique)} unique cards, "
        f"{n(result.moxfield.copies)} copies",
        file=out,
    )
    print(file=out)
    print(f"Merged collection ({args.strategy}):", file=out)
    print(f"  {n(result.unique_cards)} unique cards", file=out)
    print(f"  {n(result.total_copies)} total copies", file=out)
    print(
        f"  {n(result.in_both)} in both, {n(result.only_helvault)} Helvault only, "
        f"{n(result.only_moxfield)} Moxfield only",
        file=out,
    )
    if result.dropped_zero:
        print(f"  {n(result.dropped_zero)} card(s) dropped with a count of 0", file=out)
    _overlap_advice(result, args, out)
    print(file=out)
    print(f"Wrote: {args.output} ({n(written)} rows)", file=out)


def _overlap_advice(result: MergeResult, args, out) -> None:
    """Warn when 'sum' is very likely to double count the same physical cards."""
    if args.strategy != "sum" or result.in_both < 20:
        return
    ratio = result.identical_in_both / result.in_both
    if ratio < 0.75:
        return
    print(file=out)
    print(
        f"NOTE: {result.identical_in_both:,} of {result.in_both:,} shared cards "
        f"({ratio:.0%}) have the *same* count in both files.",
        file=out,
    )
    print(
        "      That usually means the Moxfield collection was already imported "
        "from Helvault,",
        file=out,
    )
    print(
        "      in which case --strategy sum double counts them. Compare with "
        "--strategy max.",
        file=out,
    )
