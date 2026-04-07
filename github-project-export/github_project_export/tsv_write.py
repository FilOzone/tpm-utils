"""Write UTF-8 TSV rows to a text stream."""

from __future__ import annotations

import csv
import io
from typing import Iterable, List, TextIO


def write_tsv(headers: List[str], rows: Iterable[List[str]], stream: TextIO) -> None:
    """Write header + data rows as TSV (tab-delimited, Unix newlines)."""
    writer = csv.writer(
        stream,
        delimiter="\t",
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)


def tsv_to_string(headers: List[str], rows: Iterable[List[str]]) -> str:
    buf = io.StringIO()
    write_tsv(headers, rows, buf)
    return buf.getvalue()
