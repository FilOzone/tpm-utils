from foc_mechanical_rules.rule import ActionResult, Rule, RuleRun
from foc_mechanical_rules.runner import render_summary


class _FakeRule(Rule):
    id = "R-TEST-001"
    field_name = "Status"
    doc_url = "https://example.com/R-TEST-001"


def test_render_summary_links_item_ref_to_github_issue():
    rule = _FakeRule()
    run = RuleRun(
        rule_id=rule.id,
        results=[
            ActionResult(
                item_ref="FilOzone/foc-observer#104",
                title="Some PR",
                status="applied",
                old_value="Todo",
                new_value="In Review",
            )
        ],
    )

    summary = render_summary([rule], [run])

    assert (
        "[`FilOzone/foc-observer#104`](https://github.com/FilOzone/foc-observer/issues/104)"
        in summary
    )


def test_render_summary_leaves_unparseable_item_ref_as_code():
    rule = _FakeRule()
    run = RuleRun(
        rule_id=rule.id,
        results=[
            ActionResult(
                item_ref="not-a-valid-ref",
                title="Weird item",
                status="flagged",
            )
        ],
    )

    summary = render_summary([rule], [run])

    assert "`not-a-valid-ref`" in summary
    assert "](https://github.com" not in summary
