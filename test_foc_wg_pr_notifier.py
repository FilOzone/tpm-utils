"""Regressions for cross-epic review routing and Slack previews."""

from unittest import TestCase
from unittest.mock import patch

from foc_wg_pr_notifier import collect_queue, render_queue, review_targets

REPO = "example/sdk"
ROOT = f"https://github.com/{REPO}"
MILESTONE = "https://www.notion.so/example-milestone"
EPIC_A = f"{ROOT}/issues/11"
EPIC_B = "https://github.com/example/curio/issues/12"


def candidate(number, epic, ticket, *, branch, base, requested_at):
    return {
        "pr": {
            "id": f"PR_{number}",
            "state": "OPEN",
            "isDraft": False,
            "title": f"Delivery change {number}",
            "url": f"{ROOT}/pull/{number}",
            "repository": {"nameWithOwner": REPO},
            "author": {"login": "author"},
            "reviewDecision": "REVIEW_REQUIRED",
            "reviewers": [
                {"kind": "user", "login": "engineer", "requestedAt": requested_at}
            ],
            "headRepository": {"nameWithOwner": REPO},
            "headRefName": branch,
            "baseRepository": {"nameWithOwner": REPO},
            "baseRefName": base,
        },
        "epic": {"url": epic, "title": "Epic"},
        "ticket": {
            "url": f"{ROOT}/issues/{ticket}",
            "title": f"Delivery ticket {ticket}",
        },
    }


class ReviewQueueTest(TestCase):
    @patch("foc_wg_pr_notifier.fetch_epic_candidates")
    def test_multiple_epics_deduplicate_prs_and_preserve_stack_order(self, fetch):
        first = candidate(
            41,
            EPIC_A,
            21,
            branch="first",
            base="main",
            requested_at="2026-11-17T12:00:00Z",
        )
        second = candidate(
            42,
            EPIC_B,
            22,
            branch="second",
            base="first",
            requested_at="2026-11-16T12:00:00Z",
        )
        fetch.side_effect = [
            [first],
            [second, dict(first, epic=second["epic"], ticket=second["ticket"])],
        ]
        projects = [
            {"title": "Bulk uploads", "url": MILESTONE, "epic_urls": [EPIC_A, EPIC_B]}
        ]
        queue, incomplete = collect_queue(None, projects, [])
        preview = render_queue(queue, {})[0]

        self.assertFalse(incomplete)
        self.assertEqual(fetch.call_count, 2)
        self.assertIn("2 unique PR(s)", preview)
        self.assertIn("*@engineer*", preview)
        self.assertEqual(preview.count("• <" + ROOT + "/pull/41"), 1)
        self.assertLess(
            preview.index("• <" + ROOT + "/pull/41"),
            preview.index("• <" + ROOT + "/pull/42"),
        )
        self.assertIn("Review after", preview)
        self.assertEqual(len(queue["PR_41"]["paths"]), 2)
        self.assertIn(EPIC_A, preview)
        self.assertIn(EPIC_B, preview)

    def test_only_explicit_rereview_survives_current_changes_requested(self):
        pr = candidate(
            41,
            EPIC_A,
            21,
            branch="first",
            base="main",
            requested_at="2026-11-17T12:00:00Z",
        )["pr"]
        pr.update(
            reviewDecision="CHANGES_REQUESTED",
            lastCommitAt="2026-11-17T11:00:00Z",
            lastChangesRequestedAt="2026-11-17T13:00:00Z",
            changesRequestedBy=["another-reviewer"],
        )
        self.assertEqual(review_targets(pr), [])
        pr["reviewers"].append(
            {
                "kind": "user",
                "login": "another-reviewer",
                "requestedAt": "2026-11-17T15:00:00Z",
            }
        )
        self.assertEqual(
            review_targets(pr),
            [(("user", "another-reviewer"), "2026-11-17T15:00:00Z")],
        )
