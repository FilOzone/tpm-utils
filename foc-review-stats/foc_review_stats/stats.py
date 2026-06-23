"""PR authorship and review aggregation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable


def is_bot(actor: dict[str, Any] | None, ignored_lower: set[str]) -> bool:
    """Treat GitHub Bot accounts and configured-ignored logins as bots."""
    if not actor:
        return True
    if actor.get("__typename") == "Bot":
        return True
    login = (actor.get("login") or "").lower()
    return login in ignored_lower


@dataclass
class Aggregate:
    """Aggregated counts derived from a window of PRs.

    All login keys are normalised to lowercase. Use a separate display-name map
    to render output.
    """

    authored: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    reviewed: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    matrix: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )

    @property
    def logins(self) -> set[str]:
        authors_with_reviews = {
            author for by_author in self.matrix.values() for author in by_author
        }
        return set(self.authored) | set(self.reviewed) | authors_with_reviews


def aggregate(
    prs: Iterable[dict[str, Any]],
    ignored_lower: set[str],
    in_scope_lower: set[str] | None = None,
    since_iso: str | None = None,
    until_iso: str | None = None,
) -> Aggregate:
    """Walk a sequence of PR nodes (as returned by github.fetch_repo_prs).

    Skips PRs by bot or ignored authors entirely. Each reviewer is counted once
    per PR regardless of how many in-window review events they submitted.
    Self-reviews are ignored.

    When since_iso/until_iso are provided, PR authorship is counted only when
    the PR creation timestamp is inside the half-open window
    [since_iso, until_iso), and reviews are counted only when the review
    timestamp is inside that same window.

    `in_scope_lower` controls team filtering:
      - `None`: no team filter, every non-bot, non-ignored login is counted.
      - empty set: filter on, but nobody is in scope -> nothing is counted.
      - non-empty set: only those logins are counted on either side.
    """
    agg = Aggregate()

    def in_scope(login: str) -> bool:
        return in_scope_lower is None or login in in_scope_lower

    def in_window(timestamp: str | None) -> bool:
        if since_iso is None and until_iso is None:
            return True
        if not timestamp:
            return False
        if since_iso is not None and timestamp < since_iso:
            return False
        if until_iso is not None and timestamp >= until_iso:
            return False
        return True

    for pr in prs:
        author = pr.get("author")
        if is_bot(author, ignored_lower):
            continue
        a_key = (author.get("login") or "").lower()
        if not a_key or not in_scope(a_key):
            continue
        if in_window(pr.get("createdAt")):
            agg.authored[a_key] += 1

        distinct_reviewers: set[str] = set()
        reviews = (pr.get("reviews") or {}).get("nodes") or []
        for review in reviews:
            if not in_window(review.get("createdAt")):
                continue
            ra = review.get("author")
            if is_bot(ra, ignored_lower):
                continue
            r_key = (ra.get("login") or "").lower()
            if not r_key or r_key == a_key or not in_scope(r_key):
                continue
            distinct_reviewers.add(r_key)

        for r_key in distinct_reviewers:
            agg.reviewed[r_key] += 1
            agg.matrix[r_key][a_key] += 1

    return agg


def top_received(
    login: str, matrix: dict[str, dict[str, int]], n: int
) -> list[tuple[str, int]]:
    """Top N reviewers (by count) of the given login's PRs."""
    pairs: list[tuple[str, int]] = []
    for reviewer, by_author in matrix.items():
        count = by_author.get(login, 0)
        if count > 0:
            pairs.append((reviewer, count))
    pairs.sort(key=lambda x: (-x[1], x[0]))
    return pairs[:n]


def top_given(
    login: str, matrix: dict[str, dict[str, int]], n: int
) -> list[tuple[str, int]]:
    """Top N authors (by count) whose PRs the given login reviewed."""
    pairs = [(a, c) for a, c in matrix.get(login, {}).items() if c > 0]
    pairs.sort(key=lambda x: (-x[1], x[0]))
    return pairs[:n]
