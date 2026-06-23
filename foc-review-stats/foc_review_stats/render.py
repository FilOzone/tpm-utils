"""Output renderers: text, markdown, html."""

from __future__ import annotations

import html
from typing import Callable

from foc_review_stats.stats import Aggregate, top_given, top_received


HTML_SHADE_LOW = "#fce4e4"  # very light red, ratio < 1
HTML_SHADE_HIGH = "#e6f4ea"  # very light green, ratio > 1

Row = tuple[str, str, int, int, str, str, str]


def _ratio_str(created: int, reviewed: int) -> str:
    if created == 0:
        return "-"
    return f"{reviewed / created:.2f}"


def _build_rows(
    agg: Aggregate,
    names: dict[str, str],
    top_n: int,
    contributor_order: list[str] | None = None,
    sort_by: str = "contributor",
) -> list[Row]:
    """Return rows with login plus display-ready output fields."""

    def fmt_pairs(pairs: list[tuple[str, int]]) -> str:
        if not pairs:
            return "-"
        return ", ".join(f"{names.get(login, login)}({n})" for login, n in pairs)

    rows = []
    for login in sorted(agg.logins):
        created = agg.authored.get(login, 0)
        reviewed = agg.reviewed.get(login, 0)
        rows.append(
            (
                login,
                names.get(login, login),
                created,
                reviewed,
                _ratio_str(created, reviewed),
                fmt_pairs(top_received(login, agg.matrix, top_n)),
                fmt_pairs(top_given(login, agg.matrix, top_n)),
            )
        )

    if sort_by == "reviews":
        rows.sort(key=lambda r: (-r[3], -r[2], r[1].casefold()))
    else:
        order = {login.lower(): i for i, login in enumerate(contributor_order or [])}
        rows.sort(key=lambda r: (order.get(r[0], len(order)), r[1].casefold()))
    return rows


def _display_rows(rows: list[Row]) -> list[tuple[str, int, int, str, str, str]]:
    return [
        (name, prs, reviews, ratio, by, for_)
        for _, name, prs, reviews, ratio, by, for_ in rows
    ]


def _format_table(
    rows: list[tuple], headers: list[str], aligns: list[str] | None = None
) -> str:
    cols = list(zip(*([headers] + rows)))
    widths = [max(len(str(c)) for c in col) for col in cols]
    aligns = aligns or ["<"] * len(headers)

    def fmt(row: tuple) -> str:
        return "  ".join(f"{str(v):{aligns[i]}{widths[i]}}" for i, v in enumerate(row))

    out = [fmt(headers), "  ".join("-" * w for w in widths)]
    out.extend(fmt(r) for r in rows)
    return "\n".join(out)


def render_text(
    agg: Aggregate,
    names: dict[str, str],
    since: str,
    top_n: int,
    contributor_order: list[str] | None = None,
    sort_by: str = "contributor",
) -> str:
    rows = _display_rows(_build_rows(agg, names, top_n, contributor_order, sort_by))
    headers = [
        "Contributor",
        "PRs",
        "Reviews",
        "Rev/PR",
        f"Reviewed by (top {top_n})",
        f"Reviewed for (top {top_n})",
    ]
    aligns = ["<", ">", ">", ">", "<", "<"]
    lines = [
        f"FOC review stats: PRs created since {since}",
        "",
        _format_table(rows, headers, aligns),
        "",
    ]
    return "\n".join(lines)


def render_markdown(
    agg: Aggregate,
    names: dict[str, str],
    since: str,
    top_n: int,
    contributor_order: list[str] | None = None,
    sort_by: str = "contributor",
) -> str:
    rows = _display_rows(_build_rows(agg, names, top_n, contributor_order, sort_by))
    headers = [
        "Contributor",
        "PRs",
        "Reviews",
        "Rev/PR",
        f"Reviewed by (top {top_n})",
        f"Reviewed for (top {top_n})",
    ]
    out = [
        f"FOC review stats (PRs created since {since})",
        "",
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for row in rows:
        out.append("| " + " | ".join(str(v) for v in row) + " |")
    out.append("")
    return "\n".join(out)


def render_html(
    agg: Aggregate,
    names: dict[str, str],
    since: str,
    top_n: int,
    contributor_order: list[str] | None = None,
    sort_by: str = "contributor",
) -> str:
    rows = _display_rows(_build_rows(agg, names, top_n, contributor_order, sort_by))

    def shade(ratio: str) -> str:
        if ratio == "-":
            return ""
        try:
            v = float(ratio)
        except ValueError:
            return ""
        if v < 1:
            return f"background-color:{HTML_SHADE_LOW};"
        if v > 1:
            return f"background-color:{HTML_SHADE_HIGH};"
        return ""

    cell = "padding:4px 8px; border:1px solid #ccc;"
    header_cell = cell + "background-color:#f0f0f0; font-weight:bold;"

    def esc(value: object) -> str:
        return html.escape(str(value), quote=True)

    lines: list[str] = []
    lines.append('<meta charset="utf-8">')
    lines.append(f"<h2>FOC review stats (PRs created since {esc(since)})</h2>")
    lines.append(
        '<table style="border-collapse:collapse; '
        'font-family:Arial, sans-serif; font-size:11pt;">'
    )
    lines.append("  <thead><tr>")
    for h in [
        "Contributor",
        "PRs",
        "Reviews",
        "Rev/PR",
        f"Reviewed by (top {top_n})",
        f"Reviewed for (top {top_n})",
    ]:
        lines.append(f'    <th style="{header_cell}">{esc(h)}</th>')
    lines.append("  </tr></thead>")
    lines.append("  <tbody>")
    for name, prs, reviews, ratio, by, for_ in rows:
        ratio_style = cell + "text-align:right;" + shade(ratio)
        num_style = cell + "text-align:right;"
        lines.append("    <tr>")
        lines.append(f'      <td style="{cell}">{esc(name)}</td>')
        lines.append(f'      <td style="{num_style}">{esc(prs)}</td>')
        lines.append(f'      <td style="{num_style}">{esc(reviews)}</td>')
        lines.append(f'      <td style="{ratio_style}">{esc(ratio)}</td>')
        lines.append(f'      <td style="{cell}">{esc(by)}</td>')
        lines.append(f'      <td style="{cell}">{esc(for_)}</td>')
        lines.append("    </tr>")
    lines.append("  </tbody>")
    lines.append("</table>")
    return "\n".join(lines)


RENDERERS: dict[
    str, Callable[[Aggregate, dict[str, str], str, int, list[str] | None, str], str]
] = {
    "text": render_text,
    "md": render_markdown,
    "html": render_html,
}
