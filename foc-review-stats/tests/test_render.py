"""Unit tests for output rendering."""

from foc_review_stats.render import (
    HTML_SHADE_HIGH,
    HTML_SHADE_LOW,
    render_html,
    render_markdown,
)
from foc_review_stats.stats import Aggregate


def _contributors(markdown: str) -> list[str]:
    rows = [
        line
        for line in markdown.splitlines()
        if line.startswith("| ") and not line.startswith("| Contributor ")
    ]
    return [row.split("|")[1].strip() for row in rows]


def test_markdown_sorts_by_reviews_then_prs_then_name():
    agg = Aggregate()
    agg.authored.update({"newperson": 4, "rjan90": 2, "rvagg": 2, "sgtpooki": 1})
    agg.reviewed.update({"newperson": 5, "rjan90": 1, "rvagg": 3, "sgtpooki": 1})
    names = {
        "newperson": "Ada New",
        "rjan90": "Phi-rjan",
        "rvagg": "Rod Vagg",
        "sgtpooki": "Russell Dempsey",
    }

    out = render_markdown(agg, names, "2026-05-12", 3)

    assert _contributors(out) == [
        "Ada New",
        "Rod Vagg",
        "Phi-rjan",
        "Russell Dempsey",
    ]


def test_html_shades_ratio_below_and_above_one_only():
    agg = Aggregate()
    agg.authored.update({"low": 2, "even": 1, "high": 1, "none": 0})
    agg.reviewed.update({"low": 1, "even": 1, "high": 2, "none": 1})
    names = {"low": "Low", "even": "Even", "high": "High", "none": "None"}

    out = render_html(
        agg,
        names,
        "2026-05-12",
        3,
    )
    ratio_lines = {
        value: next(line for line in out.splitlines() if f">{value}</td>" in line)
        for value in ["0.50", "1.00", "2.00", "-"]
    }

    assert HTML_SHADE_LOW in ratio_lines["0.50"]
    assert "background-color" not in ratio_lines["1.00"]
    assert HTML_SHADE_HIGH in ratio_lines["2.00"]
    assert "background-color" not in ratio_lines["-"]
