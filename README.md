# magick

Merge a **Helvault** CSV export and a **Moxfield** CSV export into a single,
accurately de-duplicated collection CSV that Moxfield can import.

Moxfield does not reliably de-duplicate collection entries: re-importing the same
scan leaves several rows for the same printing. `magick` collapses those rows
into one row per printing while **preserving the number of copies owned** — it
never simply throws duplicate rows away.

Pure Python standard library, no dependencies, fully offline.

---

## Input files

| File | Where it comes from | Notes |
| --- | --- | --- |
| Helvault CSV | Helvault Pro → export collection | scanned physical cards |
| Moxfield CSV | Moxfield → Collection → Export | the collection Moxfield already holds |

Both are read as UTF-8 (a UTF-8 BOM is stripped automatically), with LF or CRLF
line endings, quoted fields, and commas inside quoted values all handled.

## Installation

Nothing to install — Python 3.9+ is enough:

```bash
python3 -m magick --help
```

Optionally install it as a command:

```bash
pip install .
```

## CLI usage

```bash
python3 -m magick --helvault helvaultPro.csv --moxfield moxfield.csv --output collection.csv
```

Short flags: `-H` (Helvault), `-m` (Moxfield), `-o` (output). `-h` is reserved
for `--help`, so the Helvault input takes the upper-case `-H`.

| Option | Meaning |
| --- | --- |
| `-H`, `--helvault CSV` | Helvault export (env: `MAGICK_HELVAULT`) |
| `-m`, `--moxfield CSV` | Moxfield export (env: `MAGICK_MOXFIELD`) |
| `-o`, `--output CSV` | merged output; `-` writes to stdout (env: `MAGICK_OUTPUT`) |
| `-s`, `--strategy` | `sum` (default), `max`, `helvault`, `moxfield` (env: `MAGICK_STRATEGY`) |
| `--default-condition TEXT` | condition for cards Moxfield does not know (default `Near Mint`) |
| `--allow-unknown-extras` | ignore unrecognised Helvault `extras` values instead of failing |
| `-f`, `--force` | overwrite an existing output file |
| `-q`, `--quiet` | suppress the summary |

The CSV goes to the output file; the summary and all warnings go to **stderr**,
so `-o -` can be piped safely.

Exit codes: `0` success, `1` input/validation error (no output is written),
`2` command-line usage error.

Example run:

```
Reading Helvault collection...
Reading Moxfield collection...

Helvault: 3,884 rows -> 3,884 unique cards, 5,962 copies
Moxfield: 5,057 rows -> 4,804 unique cards, 7,115 copies

Merged collection (sum):
  5,260 unique cards
  13,077 total copies
  3,428 in both, 456 Helvault only, 1,376 Moxfield only

Wrote: collection.csv (5,260 rows)
```

---

## Card identity (what counts as "the same card")

A collection item is uniquely identified by **four** normalised fields:

```
set code + collector number + finish + language
```

| Field | Helvault column | Moxfield column | Normalisation |
| --- | --- | --- | --- |
| set code | `set_code` | `Edition` | trimmed, lower-cased |
| collector number | `collector_number` | `Collector Number` | trimmed, lower-cased (`187S` = `187s`) |
| finish | `extras` | `Foil` | `""` / `foil` / `etched` |
| language | `language` (`en`) | `Language` (`English`) | Scryfall code → Moxfield name |

Card **name is not part of the identity** — it is derived from set + collector
number, and it is only used for display and output. Nothing is ever merged on
name alone, so different printings of "Lightning Bolt" stay separate rows.

**Condition is deliberately not part of the identity**, because Helvault does
not record it; if it were, no Helvault row could ever merge with a Moxfield row.
When a Moxfield export lists the same printing in several conditions, they are
merged into one row using the condition with the most copies and a warning names
the card. (Verified against the author's real exports: 3,428 printings appear in
both files and **not one** had a conflicting card name, which confirms the key.)

Finish normalisation:

| Helvault `extras` | Moxfield `Foil` | Result |
| --- | --- | --- |
| *(empty)*, `nonfoil`, `normal` | *(empty)*, `normal`, `nonfoil` | `""` |
| `foil`, `/foil` | `foil` | `foil` |
| `etchedFoil`, `etched` | `etched`, `etchedFoil` | `etched` |

`extras` is treated as a `/`-separated token list, because real exports contain
a stray leading separator (`"/foil"`).

## Merge rules

```
normalize Helvault -> aggregate duplicates (always summed)
normalize Moxfield -> aggregate duplicates (always summed)
                   -> merge by card identity -> apply strategy
                   -> one row per card -> Moxfield CSV
```

* Duplicate rows **within one file** always describe extra physical copies and
  are always summed.
* For a card present in **both** files, `--strategy` decides:
  * `sum` *(default)* — the two files list different physical copies: `2 + 3 = 5`.
  * `max` — the files overlap (Moxfield was previously fed from Helvault):
    `max(2, 3) = 3`.
  * `helvault` / `moxfield` — that source is authoritative for shared cards.
* The output is always the **union** of both files. No strategy can make a card
  disappear: a card present in only one file always keeps its own count.
* A card whose final count is `0` is dropped and counted in the summary.

> **Which strategy?** If your Moxfield collection was built by importing earlier
> Helvault exports, `sum` will double count. The summary prints a NOTE when a
> large share of shared cards have *identical* counts in both files, which is a
> strong sign of exactly that; compare the totals with `--strategy max` before
> importing.

## Metadata precedence

Moxfield wins for everything it populates; Helvault fills only the gaps.

| Output column | Source |
| --- | --- |
| `Count` | merged per strategy |
| `Tradelist Count` | merged per strategy, then clamped to `Count`. Helvault has no tradelist concept, so its copies are treated as tradeable (matching how Moxfield exports look after a plain import). |
| `Name` | Moxfield's spelling; Helvault's for cards Moxfield never had |
| `Edition`, `Collector Number`, `Foil`, `Language` | the normalised identity |
| `Condition` | Moxfield; otherwise `--default-condition` (`Near Mint`) |
| `Tags` | Moxfield only (union over duplicate rows) |
| `Last Modified` | latest Moxfield value; empty for Helvault-only cards |
| `Alter`, `Proxy` | Moxfield (`True` if any duplicate row said so), else `False` |
| `Purchase Price` | Moxfield only — Helvault's `estimated_price` is a *market estimate*, not a price paid, and is never written here |

Rows are sorted by name, set, collector number, finish, language, so two runs on
the same inputs produce byte-identical output.

## Output format

Exactly the Moxfield collection-export schema — same columns, same order, no
extra columns, all fields quoted, CRLF line endings:

```
"Count","Tradelist Count","Name","Edition","Condition","Language","Foil","Tags","Last Modified","Collector Number","Alter","Proxy","Purchase Price"
"7","7","Lightning Bolt","2ed","Near Mint","English","","","2025-02-02 10:00:00.000000","161","False","False",""
```

The result can be fed straight back into `magick` as a Moxfield input.

## Validation

Processing stops with a clear, file-and-line-scoped error (and **no output
file**) when:

* an input file is missing, empty, a directory, or unreadable;
* a required column is missing (the message lists which, and what was found);
* a row has more fields than the header (malformed CSV);
* a quantity is empty, non-numeric, or negative;
* a card's name, set code, or collector number is empty;
* a Helvault `language` code is unrecognised;
* a Helvault `extras` value is unrecognised (unless `--allow-unknown-extras`);
* a Moxfield `Foil` value is not one of `""` / `foil` / `etched`;
* the output file already exists and `--force` was not given.

Warnings (non-fatal, on stderr) cover ignored `extras` values, absent optional
Moxfield columns, and printings merged across differing conditions.

## Important CSV schema assumptions

These are derived from real 2026 exports, not guessed. If either tool changes
its format, this section is what to re-check.

**Helvault** — header:
`cmc, collector_number, color_identity, colors, estimated_price, extras,
language, mana_cost, name, oracle_id, quantity, rarity, scryfall_id, set_code,
set_name, type_line`

1. Required: `name`, `set_code`, `collector_number`, `quantity`, `extras`,
   `language`. All other columns are ignored.
2. `quantity` is the number of physical copies as a whole number.
3. `extras` carries the finish, `/`-separated, possibly with a leading `/`.
4. `language` is a Scryfall language code (`en`, `fr`, …); a full English name is
   also accepted.
5. `set_code` is a Scryfall set code and matches Moxfield's `Edition`.
6. `oracle_id` is often empty (175 of 3,884 rows in the sample export) and
   `scryfall_id` identifies a printing that Moxfield does not export, so
   **neither is used for identity**.
7. Helvault records no condition, tags, prices paid, alters or proxies.

**Moxfield** — header:
`"Count","Tradelist Count","Name","Edition","Condition","Language","Foil","Tags",
"Last Modified","Collector Number","Alter","Proxy","Purchase Price"`

1. Required: `Count`, `Name`, `Edition`, `Collector Number`, `Foil`, `Language`.
   The rest are optional; if absent, defaults are used and a warning is printed.
2. `Foil` is `""`, `foil` or `etched`.
3. `Language` is an English language name (`English`, `Japanese`, …) and is
   passed through unchanged, including values not in the mapping table.
4. `Tags` is a comma-separated list inside one quoted field.
5. `Tradelist Count` never exceeds `Count`.
6. This same schema is what Moxfield's collection importer accepts.

## Testing

```bash
python3 -m unittest discover -s tests -t .
```

47 tests over small fixture CSVs in `tests/fixtures/`, covering aggregation
within each source, cross-source merging, single-source cards, printing
separation, identifier normalisation, malformed CSV, missing columns, invalid
quantities, UTF-8 BOM/CRLF input, every strategy, exit codes, and that the
output schema is Moxfield-compatible and round-trips.

## Docker

```bash
docker build -t magick .
docker run --rm -v "$PWD:/data" magick \
  --helvault helvaultPro.csv --moxfield moxfield.csv --output collection.csv
```

Or with environment variables:

```bash
docker run --rm -v "$PWD:/data" \
  -e MAGICK_HELVAULT=helvaultPro.csv \
  -e MAGICK_MOXFIELD=moxfield.csv \
  -e MAGICK_OUTPUT=collection.csv \
  -e MAGICK_STRATEGY=max \
  magick
```

The container reads and writes only inside `/data`, needs no network, and never
prompts for input.
