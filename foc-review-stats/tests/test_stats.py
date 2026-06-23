"""Unit tests for aggregation logic."""

from foc_review_stats.render import render_markdown
from foc_review_stats.stats import Aggregate, aggregate, is_bot, top_given, top_received


def _pr(
    author_login,
    reviewer_logins=(),
    bot_author=False,
    bot_reviewers=(),
    created_at="2026-03-10T12:00:00Z",
    review_created_at="2026-03-10T12:00:00Z",
):
    review_times = (
        review_created_at
        if isinstance(review_created_at, list)
        else [review_created_at] * len(reviewer_logins)
    )
    return {
        "createdAt": created_at,
        "author": {
            "__typename": "Bot" if bot_author else "User",
            "login": author_login,
        },
        "reviews": {
            "nodes": [
                {
                    "createdAt": review_times[i],
                    "author": {
                        "__typename": "Bot" if login in bot_reviewers else "User",
                        "login": login,
                    },
                    "state": "APPROVED",
                }
                for i, login in enumerate(reviewer_logins)
            ]
        },
    }


def test_is_bot_detects_graphql_bot_type():
    assert is_bot({"__typename": "Bot", "login": "dependabot"}, set())


def test_is_bot_detects_ignored_logins():
    assert is_bot({"__typename": "User", "login": "FilOzzy"}, {"filozzy"})


def test_is_bot_passes_real_user():
    assert not is_bot({"__typename": "User", "login": "rvagg"}, set())


def test_is_bot_treats_missing_actor_as_bot():
    assert is_bot(None, set())


def test_aggregate_counts_authored_and_reviewed():
    prs = [
        _pr("rvagg", reviewer_logins=["hugomrdias"]),
        _pr("rvagg", reviewer_logins=["hugomrdias", "juliangruber"]),
        _pr("hugomrdias", reviewer_logins=["rvagg"]),
    ]
    agg = aggregate(prs, ignored_lower=set())
    assert agg.authored["rvagg"] == 2
    assert agg.authored["hugomrdias"] == 1
    assert agg.reviewed["hugomrdias"] == 2
    assert agg.reviewed["juliangruber"] == 1
    assert agg.reviewed["rvagg"] == 1


def test_aggregate_skips_self_review():
    prs = [_pr("rvagg", reviewer_logins=["rvagg", "hugomrdias"])]
    agg = aggregate(prs, ignored_lower=set())
    assert agg.reviewed["rvagg"] == 0
    assert agg.reviewed["hugomrdias"] == 1


def test_aggregate_dedupes_repeated_reviewers_on_same_pr():
    prs = [_pr("rvagg", reviewer_logins=["hugomrdias", "hugomrdias", "hugomrdias"])]
    agg = aggregate(prs, ignored_lower=set())
    assert agg.reviewed["hugomrdias"] == 1


def test_aggregate_skips_bot_author_prs_entirely():
    prs = [
        _pr("dependabot", reviewer_logins=["rvagg"], bot_author=True),
        _pr("rvagg", reviewer_logins=["hugomrdias"]),
    ]
    agg = aggregate(prs, ignored_lower=set())
    assert "dependabot" not in agg.authored
    assert agg.reviewed.get("rvagg", 0) == 0
    assert agg.authored["rvagg"] == 1


def test_aggregate_honours_ignored_list_for_author_and_reviewer():
    prs = [
        _pr("magik6k", reviewer_logins=["rvagg"]),
        _pr("rvagg", reviewer_logins=["magik6k", "hugomrdias"]),
    ]
    agg = aggregate(prs, ignored_lower={"magik6k"})
    assert "magik6k" not in agg.authored
    assert agg.reviewed.get("magik6k", 0) == 0
    assert agg.reviewed["hugomrdias"] == 1


def test_aggregate_in_scope_filter_drops_external_authors():
    prs = [
        _pr("rvagg", reviewer_logins=["hugomrdias", "someouterperson"]),
        _pr("someouterperson", reviewer_logins=["rvagg"]),
    ]
    agg = aggregate(prs, ignored_lower=set(), in_scope_lower={"rvagg", "hugomrdias"})
    assert agg.authored["rvagg"] == 1
    assert "someouterperson" not in agg.authored
    assert agg.reviewed["hugomrdias"] == 1
    assert agg.reviewed.get("someouterperson", 0) == 0
    assert agg.reviewed.get("rvagg", 0) == 0


def test_aggregate_no_in_scope_means_no_filter():
    prs = [_pr("someouterperson", reviewer_logins=["rvagg"])]
    agg = aggregate(prs, ignored_lower=set(), in_scope_lower=None)
    assert agg.authored["someouterperson"] == 1
    assert agg.reviewed["rvagg"] == 1


def test_aggregate_empty_in_scope_filters_out_everyone():
    prs = [_pr("rvagg", reviewer_logins=["hugomrdias"])]
    agg = aggregate(prs, ignored_lower=set(), in_scope_lower=set())
    assert agg.authored == {}
    assert agg.reviewed == {}


def test_aggregate_window_counts_reviews_on_prs_created_before_window():
    prs = [
        _pr(
            "rvagg",
            reviewer_logins=["hugomrdias"],
            created_at="2026-02-20T12:00:00Z",
            review_created_at="2026-03-05T12:00:00Z",
        )
    ]

    agg = aggregate(
        prs,
        ignored_lower=set(),
        since_iso="2026-03-01T00:00:00Z",
        until_iso="2026-04-01T00:00:00Z",
    )

    assert agg.authored.get("rvagg", 0) == 0
    assert agg.reviewed["hugomrdias"] == 1
    assert agg.matrix["hugomrdias"]["rvagg"] == 1
    assert "rvagg" in agg.logins


def test_aggregate_window_filters_reviews_after_until():
    prs = [
        _pr(
            "rvagg",
            reviewer_logins=["hugomrdias"],
            created_at="2026-03-10T12:00:00Z",
            review_created_at="2026-04-01T00:00:00Z",
        )
    ]

    agg = aggregate(
        prs,
        ignored_lower=set(),
        since_iso="2026-03-01T00:00:00Z",
        until_iso="2026-04-01T00:00:00Z",
    )

    assert agg.authored["rvagg"] == 1
    assert agg.reviewed.get("hugomrdias", 0) == 0


def test_aggregate_window_dedupes_reviewer_with_in_window_review():
    prs = [
        _pr(
            "rvagg",
            reviewer_logins=["hugomrdias", "hugomrdias", "hugomrdias"],
            review_created_at=[
                "2026-02-28T12:00:00Z",
                "2026-03-05T12:00:00Z",
                "2026-03-06T12:00:00Z",
            ],
        )
    ]

    agg = aggregate(
        prs,
        ignored_lower=set(),
        since_iso="2026-03-01T00:00:00Z",
        until_iso="2026-04-01T00:00:00Z",
    )

    assert agg.reviewed["hugomrdias"] == 1


def test_top_received_and_given_are_sorted_descending():
    prs = [
        _pr("rvagg", reviewer_logins=["hugomrdias"]),
        _pr("rvagg", reviewer_logins=["hugomrdias", "juliangruber"]),
        _pr("rvagg", reviewer_logins=["juliangruber"]),
    ]
    agg = aggregate(prs, ignored_lower=set())
    rec = top_received("rvagg", agg.matrix, n=3)
    assert rec == [("hugomrdias", 2), ("juliangruber", 2)] or rec == [
        ("juliangruber", 2),
        ("hugomrdias", 2),
    ]
    given = top_given("hugomrdias", agg.matrix, n=3)
    assert given == [("rvagg", 2)]


def test_markdown_heading_describes_bounded_activity_window():
    out = render_markdown(Aggregate(), {}, "2026-03-01", 3, until="2026-03-31")
    assert out.splitlines()[0] == (
        "FOC review stats (activity from 2026-03-01 through 2026-03-31)"
    )
