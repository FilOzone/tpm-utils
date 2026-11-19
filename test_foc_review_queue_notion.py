from unittest import TestCase
from unittest.mock import Mock

from foc_review_queue_notion import fetch_projects


def text(value, href=None):
    return {"plain_text": value, "href": href}


def project(title, stage, epics):
    return {
        "url": f"https://notion.so/{title}",
        "properties": {
            "Name": {"title": [text(title)]},
            "Workstream": {"select": {"name": "Product"}},
            "Delivery stage": {"select": {"name": stage} if stage else None},
            "GitHub epics": {"type": "rich_text", "rich_text": epics},
        },
    }


def response(results, next_cursor=None):
    return Mock(
        status_code=200,
        json=Mock(
            return_value={
                "results": results,
                "has_more": next_cursor is not None,
                "next_cursor": next_cursor,
            }
        ),
    )


class NotionProjectTests(TestCase):
    def test_fetches_multiple_issues_across_pages_and_reports_bad_links(self):
        sdk_issue = "https://github.com/filozone/synapse-sdk/issues/1082"
        curio_issue = "https://github.com/filecoin-project/curio/issues/1001"
        sdk_milestone = "https://github.com/filozone/synapse-sdk/milestone/1"
        session = Mock()
        session.post.side_effect = [
            response(
                [
                    project(
                        "Multi",
                        "Implementation",
                        [
                            text("SDK epic", sdk_issue),
                            text("\n"),
                            text("Milestone", sdk_milestone),
                            text("\n"),
                            text("Curio epic", curio_issue),
                            text("\n"),
                            text(
                                "https://github.com/FilOzone/Synapse-SDK/issues/1082/#task"
                            ),
                        ],
                    ),
                    project("Completed", "Engineering complete", []),
                ],
                next_cursor="page-two",
            ),
            response([project("Legacy", None, [])]),
        ]

        projects, diagnostics = fetch_projects(session)

        self.assertEqual([row["title"] for row in projects], ["Multi", "Legacy"])
        self.assertEqual(projects[0]["epic_urls"], [sdk_issue, curio_issue])
        self.assertEqual(len(diagnostics), 2)
        self.assertIn("line 2 is not a GitHub issue link", diagnostics[0])
        self.assertIn("add at least one epic", diagnostics[1])
        self.assertEqual(
            session.post.call_args.kwargs["json"]["start_cursor"], "page-two"
        )
