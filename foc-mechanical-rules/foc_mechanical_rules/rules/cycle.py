"""R-FC-012: recently-active items without a Cycle get the current cycle.

Canonical English rule:
foc-board-rules/field-completeness.md#r-fc-012-recently-active-items-without-a-cycle-get-the-current-cycle

This module is that rule's canonical implementation — see rules/assignee.py's
docstring for why the markdown and this module link back to each other.

GitHub has no change-history API for Projects v2 custom fields (only the
Status field gets a timeline event, ``ProjectV2ItemStatusChangedEvent`` —
confirmed by GraphQL schema introspection and by checking a real item's
timeline; ``IssueFieldChangedEvent`` and friends belong to a separate,
unrelated "Issue Fields" GitHub feature). So there's no way to ask GitHub
"was this item's Cycle field cleared after being set." To honor "don't
re-add a cycle a human removed," this rule checks its own mutation history
(``state.py``) instead: if it previously set Cycle to the current cycle on
this item and the item now has no cycle, that's the removal signal.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import requests
from github_projects_client import graphql_query, list_items, set_field_value

from ..github_api import FILOZ_ORG, PROJECT_NUMBER
from ..rule import ActionResult, Rule
from ..state import load_mutations

CURRENT_CYCLE_QUERY = """
query($org: String!, $number: Int!) {
  organization(login: $org) {
    projectV2(number: $number) {
      field(name: "Cycle") {
        ... on ProjectV2IterationField {
          configuration {
            iterations { title startDate duration }
          }
        }
      }
    }
  }
}
"""


def get_current_cycle_title(
    session: requests.Session,
    *,
    org: str,
    project_number: int,
    today: Optional[date] = None,
) -> Optional[str]:
    """Return the title of the iteration whose date range contains today.

    Returns None if today falls in a gap between iterations (no active cycle).
    """
    data = graphql_query(
        session, CURRENT_CYCLE_QUERY, {"org": org, "number": project_number}
    )
    field = ((data.get("organization") or {}).get("projectV2") or {}).get("field") or {}
    iterations = (field.get("configuration") or {}).get("iterations") or []

    today = today or date.today()
    for it in iterations:
        start = date.fromisoformat(it["startDate"])
        end = start + timedelta(days=it["duration"] - 1)
        if start <= today <= end:
            return it["title"]
    return None


class CycleRule(Rule):
    id = "R-FC-012"
    field_name = "cycle"
    doc_url = (
        "https://github.com/FilOzone/tpm-utils/blob/master/foc-board-rules/"
        "field-completeness.md#r-fc-012-recently-active-items-without-a-cycle-get-the-current-cycle"
    )

    def __init__(self, org: str = FILOZ_ORG, project_number: int = PROJECT_NUMBER):
        self.org = org
        self.project_number = project_number
        self._current_cycle: Optional[str] = None
        self._current_cycle_resolved = False

    def _resolve_current_cycle(self, session: requests.Session) -> Optional[str]:
        if not self._current_cycle_resolved:
            self._current_cycle = get_current_cycle_title(
                session, org=self.org, project_number=self.project_number
            )
            self._current_cycle_resolved = True
        return self._current_cycle

    def select(self, session: requests.Session) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            result = list_items(
                session,
                org=self.org,
                project_number=self.project_number,
                query='-status:"🎉 Done" no:cycle updated:>@today-3d',
                fields=["Repository", "Id", "Title", "url"],
                cursor=cursor,
            )
            items.extend(result["items"])
            if not result["has_more"]:
                break
            cursor = result["next_cursor"]
        return items

    def apply_one(
        self, session: requests.Session, item: Dict[str, Any], *, dry_run: bool
    ) -> ActionResult:
        repository = item.get("Repository", "")
        number = str(item.get("Id", ""))
        title = item.get("Title", "")
        item_ref = f"{repository}#{number}"

        current_cycle = self._resolve_current_cycle(session)
        if not current_cycle:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="error",
                reason="no active cycle for today (gap between iterations)",
            )

        previously_set_to_current = any(
            r.item == item_ref
            and r.field == self.field_name
            and r.new_value == current_cycle
            for r in load_mutations()
        )
        if previously_set_to_current:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="flagged",
                reason=(
                    f"{self.id} previously set Cycle to {current_cycle} on this item "
                    "and it's since been cleared -- not re-adding"
                ),
            )

        if dry_run:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="applied",
                reason="dry-run: would assign",
                old_value="",
                new_value=current_cycle,
            )

        result = set_field_value(
            session,
            org=self.org,
            project_number=self.project_number,
            item_ref=item_ref,
            field_name="Cycle",
            value=current_cycle,
        )
        if not result.get("success"):
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="error",
                reason=f"failed to set cycle: {result.get('error')}",
            )

        return ActionResult(
            item_ref=item_ref,
            title=title,
            status="applied",
            old_value=result.get("old_value", ""),
            new_value=current_cycle,
        )
