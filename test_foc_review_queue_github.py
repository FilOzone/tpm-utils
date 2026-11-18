"""Regression checks for following the native GitHub links across repositories."""

import unittest
from unittest.mock import Mock

from foc_review_queue_github import GitHubQueueError, fetch_epic_candidates


def page(nodes, cursor=None, *, backwards=False):
    more, position = (
        ("hasPreviousPage", "startCursor")
        if backwards
        else ("hasNextPage", "endCursor")
    )
    return {"nodes": nodes, "pageInfo": {more: bool(cursor), position: cursor}}


def issue(identifier, repo, number=1):
    return {
        "id": identifier,
        "title": identifier,
        "url": f"https://github.com/{repo}/issues/{number}",
    }


def pull(identifier, repo, number=2, *, draft=False):
    return {
        "id": identifier,
        "url": f"https://github.com/{repo}/pull/{number}",
        "state": "OPEN",
        "isDraft": draft,
    }


class TestGitHubQueue(unittest.TestCase):
    def session(self, *responses):
        session = Mock()
        session.post.side_effect = [Mock(**{"json.return_value": r}) for r in responses]
        return session

    def test_cross_repo_nested_links_and_paginated_review_requests(self):
        epic = dict(issue("epic", "one/first"), body="## Tasks\n- [ ] #12")
        child = issue("child", "one/first", 2)
        nested = issue("nested", "two/second")
        other = issue("other", "three/third")
        direct = pull("direct", "one/first")
        queued = pull("queued", "two/second")
        draft = pull("draft", "two/second", 3, draft=True)
        reviewer = {"__typename": "User", "login": "person"}
        team = {"__typename": "Team", "combinedSlug": "two/maintainers"}
        wanted_at = "2026-11-18T11:00:00Z"
        oldest_at = "2026-11-17T10:00:00Z"

        def node(**fields):
            return {"data": {"node": fields}}

        session = self.session(
            {"data": {"repository": {"issue": epic}}},
            node(
                subIssues=page([child], "child-page"),
                closedByPullRequestsReferences=page([direct]),
            ),
            node(subIssues=page([other])),
            node(
                subIssues=page([nested]),
                closedByPullRequestsReferences=page([]),
            ),
            node(
                subIssues=page([]),
                closedByPullRequestsReferences=page([draft], "pull-page"),
            ),
            node(closedByPullRequestsReferences=page([queued])),
            node(
                **queued,
                reviewRequests=page([{"requestedReviewer": reviewer}], "request-page"),
                reviewEvents=page(
                    [{"createdAt": wanted_at, "requestedReviewer": reviewer}],
                    "event-page",
                    backwards=True,
                ),
                latestOpinionatedReviews=page([]),
                readyEvents=page([]),
                commits=page([]),
            ),
            node(reviewRequests=page([{"requestedReviewer": team}])),
            node(
                reviewEvents=page(
                    [
                        {"createdAt": oldest_at, "requestedReviewer": team},
                        {"createdAt": oldest_at, "requestedReviewer": reviewer},
                    ],
                    backwards=True,
                )
            ),
            node(subIssues=page([]), closedByPullRequestsReferences=page([queued])),
        )
        diagnostics = []
        candidates = fetch_epic_candidates(
            session, epic["url"], diagnostics=diagnostics
        )

        self.assertEqual(
            [entry["ticket"]["url"] for entry in candidates],
            [nested["url"], other["url"]],
        )
        self.assertTrue(
            all(entry["epic"]["url"] == epic["url"] for entry in candidates)
        )
        self.assertIs(candidates[0]["pr"], candidates[1]["pr"])
        self.assertEqual(
            candidates[0]["pr"]["reviewers"],
            [
                {"kind": "user", "login": "person", "requestedAt": wanted_at},
                {"kind": "team", "login": "two/maintainers", "requestedAt": oldest_at},
            ],
        )
        self.assertEqual(len(diagnostics), 1)
        self.assertIn(direct["url"], diagnostics[0])
        variables = [
            call.kwargs["json"]["variables"] for call in session.post.call_args_list
        ]
        self.assertEqual(variables[2]["childrenAfter"], "child-page")
        self.assertEqual(variables[5]["pullsAfter"], "pull-page")
        self.assertEqual(variables[7]["requestsAfter"], "request-page")
        self.assertEqual(variables[8]["eventsBefore"], "event-page")

    def test_checklist_without_native_links_is_reported(self):
        epic = dict(issue("epic", "one/first"), body="## Sub-issues / PRs\n- [ ] #12")
        session = self.session(
            {"data": {"repository": {"issue": epic}}},
            {
                "data": {
                    "node": {
                        "subIssues": page([]),
                        "closedByPullRequestsReferences": page([]),
                    }
                }
            },
        )
        diagnostics = []
        self.assertEqual(
            fetch_epic_candidates(session, epic["url"], diagnostics=diagnostics), []
        )
        self.assertIn("checklist entries", diagnostics[0])
        self.assertEqual(session.post.call_count, 2)

    def test_graphql_partial_result_does_not_look_like_an_empty_queue(self):
        epic = issue("epic", "one/first")
        session = self.session(
            {
                "data": {"repository": {"issue": epic}},
                "errors": [{"message": "Access denied"}],
            }
        )
        with self.assertRaisesRegex(GitHubQueueError, "Access denied"):
            fetch_epic_candidates(session, epic["url"])
