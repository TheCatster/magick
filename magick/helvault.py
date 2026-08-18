"""Read and normalise a Helvault CSV export.

Observed header (Helvault Pro, 2026):

    cmc,collector_number,color_identity,colors,estimated_price,extras,language,
    mana_cost,name,oracle_id,quantity,rarity,scryfall_id,set_code,set_name,type_line

Only the columns below are required; everything else is ignored.
"""

from __future__ import annotations

from .csvio import parse_quantity, read_rows
from .errors import RowError
from .model import FINISH_ETCHED, FINISH_FOIL, FINISH_NONFOIL, CardKey, Entry

REQUIRED_COLUMNS = (
    "name",
    "set_code",
    "collector_number",
    "quantity",
    "extras",
    "language",
)

#: Scryfall language codes -> the language names Moxfield writes in its export.
LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ja": "Japanese",
    "ko": "Korean",
    "ru": "Russian",
    "zhs": "Chinese Simplified",
    "zht": "Chinese Traditional",
    "he": "Hebrew",
    "la": "Latin",
    "grc": "Ancient Greek",
    "ar": "Arabic",
    "sa": "Sanskrit",
    "ph": "Phyrexian",
}
_LANGUAGE_NAMES = {name.lower(): name for name in LANGUAGES.values()}

#: Tokens Helvault puts in "extras" that describe the finish of the card.
FINISH_TOKENS = {
    "foil": FINISH_FOIL,
    "etchedfoil": FINISH_ETCHED,
    "etched": FINISH_ETCHED,
    "nonfoil": FINISH_NONFOIL,
    "normal": FINISH_NONFOIL,
}


def read(path: str, allow_unknown_extras: bool = False) -> tuple[list[Entry], list[str]]:
    """Return one Entry per Helvault row (unaggregated) plus any warnings."""
    entries: list[Entry] = []
    warnings: list[str] = []
    for line, row in read_rows(path, REQUIRED_COLUMNS):
        name = row["name"]
        if not name:
            raise RowError(path, line, "column 'name' is empty; card cannot be identified")
        set_code = row["set_code"].lower()
        if not set_code:
            raise RowError(
                path, line, f"column 'set_code' is empty for {name!r}; "
                "card identity cannot be established"
            )
        collector_number = row["collector_number"].lower()
        if not collector_number:
            raise RowError(
                path, line, f"column 'collector_number' is empty for {name!r}; "
                "card identity cannot be established"
            )
        finish = _parse_finish(path, line, row["extras"], allow_unknown_extras, warnings)
        quantity = parse_quantity(path, line, "quantity", row["quantity"])
        entries.append(
            Entry(
                key=CardKey(
                    set_code=set_code,
                    collector_number=collector_number,
                    finish=finish,
                    language=_parse_language(path, line, row["language"]),
                ),
                name=name,
                count=quantity,
                # Helvault has no tradelist concept; newly scanned copies inherit
                # the "available for trade" convention Moxfield exports use.
                tradelist_count=quantity,
            )
        )
    return entries, warnings


def _parse_language(path: str, line: int, raw: str) -> str:
    text = raw.strip()
    if not text:
        raise RowError(path, line, "column 'language' is empty; expected e.g. 'en'")
    if text.lower() in LANGUAGES:
        return LANGUAGES[text.lower()]
    if text.lower() in _LANGUAGE_NAMES:  # tolerate a full name
        return _LANGUAGE_NAMES[text.lower()]
    raise RowError(
        path,
        line,
        f"column 'language' has unrecognised value {raw!r}. "
        f"Known codes: {', '.join(sorted(LANGUAGES))}",
    )


def _parse_finish(
    path: str, line: int, raw: str, allow_unknown: bool, warnings: list[str]
) -> str:
    """Map Helvault's 'extras' column to a Moxfield finish.

    The column is a '/'-separated token list and may carry a stray leading
    separator (an actual export contains "/foil"), so tokens are split and
    empties dropped rather than the whole string being matched.
    """
    finish = FINISH_NONFOIL
    for token in (part.strip().lower() for part in raw.split("/")):
        if not token:
            continue
        if token in FINISH_TOKENS:
            resolved = FINISH_TOKENS[token]
            if resolved:
                finish = resolved
        elif allow_unknown:
            warnings.append(
                f"{path}:{line}: ignoring unrecognised 'extras' value {token!r} "
                "(treated as a non-finish decoration)"
            )
        else:
            raise RowError(
                path,
                line,
                f"column 'extras' has unrecognised value {token!r}; it may change "
                f"the card's finish. Known values: {', '.join(sorted(FINISH_TOKENS))}. "
                "Re-run with --allow-unknown-extras to ignore it.",
            )
    return finish
