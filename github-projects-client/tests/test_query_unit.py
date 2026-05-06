"""Unit tests for expand_or_query() parser."""

from __future__ import annotations

import pytest

from github_projects_client.query import expand_or_query


# ---------------------------------------------------------------------------
# Passthrough (no OR, no parens)
# ---------------------------------------------------------------------------


class TestPassthrough:
    def test_plain_query(self):
        assert expand_or_query("is:issue") == ["is:issue"]

    def test_complex_plain_query(self):
        assert expand_or_query('is:issue -status:"🎉 Done"') == [
            'is:issue -status:"🎉 Done"'
        ]

    def test_empty_string(self):
        assert expand_or_query("") == [""]

    def test_whitespace_only(self):
        assert expand_or_query("   ") == ["   "]

    def test_or_inside_quotes_is_literal(self):
        q = 'title:"this OR that"'
        assert expand_or_query(q) == [q]

    def test_parens_inside_quotes_are_literal(self):
        q = 'title:"(hello) world"'
        assert expand_or_query(q) == [q]


# ---------------------------------------------------------------------------
# Simple OR with prefix
# ---------------------------------------------------------------------------


class TestSimpleOr:
    def test_two_branches_with_prefix(self):
        result = expand_or_query(
            'is:issue (milestone:"M4.2" -status:"🎉 Done") OR (-last-updated:7days)'
        )
        assert result == [
            'is:issue milestone:"M4.2" -status:"🎉 Done"',
            "is:issue -last-updated:7days",
        ]

    def test_two_branches_no_prefix(self):
        result = expand_or_query(
            '(is:issue milestone:"M4.2") OR (is:pr -last-updated:7days)'
        )
        assert result == [
            'is:issue milestone:"M4.2"',
            "is:pr -last-updated:7days",
        ]

    def test_three_branches(self):
        result = expand_or_query("is:issue (status:A) OR (status:B) OR (status:C)")
        assert result == [
            "is:issue status:A",
            "is:issue status:B",
            "is:issue status:C",
        ]

    def test_single_group_no_or_strips_parens(self):
        result = expand_or_query('is:issue (milestone:"M4.2")')
        assert result == ['is:issue milestone:"M4.2"']


# ---------------------------------------------------------------------------
# Multi-branch OR
# ---------------------------------------------------------------------------


class TestMultiBranch:
    def test_multi_word_prefix(self):
        result = expand_or_query(
            'is:issue -status:"🎉 Done" (milestone:"M4.1") OR (milestone:"M4.2")'
        )
        assert result == [
            'is:issue -status:"🎉 Done" milestone:"M4.1"',
            'is:issue -status:"🎉 Done" milestone:"M4.2"',
        ]

    def test_quoted_values_inside_groups(self):
        result = expand_or_query('(status:"🏗 In Progress") OR (status:"📋 Backlog")')
        assert result == [
            'status:"🏗 In Progress"',
            'status:"📋 Backlog"',
        ]


# ---------------------------------------------------------------------------
# OR/parens inside quotes (treated as literal)
# ---------------------------------------------------------------------------


class TestQuotedLiterals:
    def test_or_in_quoted_prefix(self):
        q = 'title:"error OR warning" (status:A) OR (status:B)'
        result = expand_or_query(q)
        assert result == [
            'title:"error OR warning" status:A',
            'title:"error OR warning" status:B',
        ]

    def test_parens_in_quoted_group(self):
        q = '(title:"(important)") OR (status:B)'
        result = expand_or_query(q)
        assert result == [
            'title:"(important)"',
            "status:B",
        ]


# ---------------------------------------------------------------------------
# Error conditions
# ---------------------------------------------------------------------------


class TestErrors:
    def test_unmatched_open_paren(self):
        with pytest.raises(ValueError, match="Unmatched opening parenthesis"):
            expand_or_query("(a b")

    def test_unmatched_close_paren(self):
        with pytest.raises(ValueError, match="Unexpected closing parenthesis"):
            expand_or_query("a) OR (b)")

    def test_nested_parens(self):
        with pytest.raises(ValueError, match="Nested parentheses"):
            expand_or_query("((a)) OR (b)")

    def test_trailing_terms(self):
        with pytest.raises(ValueError, match="Filter terms after the last group"):
            expand_or_query("(a) OR (b) extra")

    def test_or_without_parens(self):
        with pytest.raises(ValueError, match="OR requires parenthesized groups"):
            expand_or_query("a OR b")

    def test_empty_group(self):
        with pytest.raises(ValueError, match="Empty group"):
            expand_or_query("(a) OR ()")

    def test_or_inside_parens(self):
        with pytest.raises(ValueError, match="OR inside parentheses"):
            expand_or_query("(a OR b)")

    def test_or_at_start_without_parens(self):
        with pytest.raises(ValueError, match="OR requires parenthesized groups"):
            expand_or_query("OR something")

    def test_or_at_end_without_parens(self):
        with pytest.raises(ValueError, match="OR requires parenthesized groups"):
            expand_or_query("something OR")
