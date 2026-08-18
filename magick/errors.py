"""Error types. Every message must name the file (and row/column) at fault."""

from __future__ import annotations


class MagickError(Exception):
    """Base class for all errors that should be reported to the user, not traced."""


class InputError(MagickError):
    """A problem with an input file: missing, unreadable, or structurally invalid."""


class RowError(MagickError):
    """A problem with one row of an input file."""

    def __init__(self, path: str, line: int, message: str) -> None:
        super().__init__(f"{path}:{line}: {message}")
        self.path = path
        self.line = line
