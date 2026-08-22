"""R-FC-012 / R-FC-013: keep an item's Cycle pointed at the current iteration.

Canonical English rules:
- foc-board-rules/field-completeness.md#r-fc-012-recently-active-items-without-a-cycle-get-the-current-cycle
- foc-board-rules/field-completeness.md#r-fc-013-open-items-in-a-past-cycle-should-move-to-the-current-cycle

This module is that rule's canonical implementation — see rules/assignee.py's
docstring for why the markdown and this module link back to each other.

The "don't re-add/re-move a cycle a human undid" guards rely on the mutation
log (see mutation_log.py and README.md's "Mutation log" section for why
that's necessary and how it works) rather than anything GitHub-provided.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import requests
from github_projects_client import graphql_query, list_items, set_field_value

from ..github_api import FILOZ_ORG, PROJECT_NUMBER
from ..mutation_log import MutationLog
from ..rule import ActionResult, Rule

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


def _fetch_iterations(
    session: requests.Session, *, org: str, project_number: int
) -> List[Dict[str, Any]]:
    data = graphql_query(
        session, CURRENT_CYCLE_QUERY, {"org": org, "number": project_number}
    )
    field = ((data.get("organization") or {}).get("projectV2") or {}).get("field") or {}
    return (field.get("configuration") or {}).get("iterations") or []


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
    iterations = _fetch_iterations(session, org=org, project_number=project_number)

    today = today or date.today()
    for it in iterations:
        start = date.fromisoformat(it["startDate"])
        end = start + timedelta(days=it["duration"] - 1)
        if start <= today <= end:
            return it["title"]
    return None


def get_current_and_past_cycle_titles(
    session: requests.Session,
    *,
    org: str,
    project_number: int,
    today: Optional[date] = None,
) -> tuple[Optional[str], set[str]]:
    """Return (current cycle title, set of past cycle titles).

    A cycle is "past" if its date range ended before today. The current
    cycle (if any) is never included in the past set, even on a boundary.
    """
    iterations = _fetch_iterations(session, org=org, project_number=project_number)

    today = today or date.today()
    current: Optional[str] = None
    past: set[str] = set()
    for it in iterations:
        start = date.fromisoformat(it["startDate"])
        end = start + timedelta(days=it["duration"] - 1)
        if start <= today <= end:
            current = it["title"]
        elif end < today:
            past.add(it["title"])
    return current, past


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
        self,
        session: requests.Session,
        item: Dict[str, Any],
        *,
        dry_run: bool,
        mutation_log: MutationLog,
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
            m.field == self.field_name and m.new_value == current_cycle
            for m in mutation_log.for_item(item_ref)
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


class PastCycleRule(Rule):
    id = "R-FC-013"
    field_name = "cycle"
    doc_url = (
        "https://github.com/FilOzone/tpm-utils/blob/master/foc-board-rules/"
        "field-completeness.md#r-fc-013-open-items-in-a-past-cycle-should-move-to-the-current-cycle"
    )

    def __init__(self, org: str = FILOZ_ORG, project_number: int = PROJECT_NUMBER):
        self.org = org
        self.project_number = project_number
        self._current_cycle: Optional[str] = None
        self._past_cycles: Optional[set] = None
        self._resolved = False

    def _resolve(self, session: requests.Session) -> tuple[Optional[str], set]:
        if not self._resolved:
            self._current_cycle, self._past_cycles = get_current_and_past_cycle_titles(
                session, org=self.org, project_number=self.project_number
            )
            self._resolved = True
        return self._current_cycle, self._past_cycles or set()

    def select(self, session: requests.Session) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            result = list_items(
                session,
                org=self.org,
                project_number=self.project_number,
                query='-status:"🎉 Done" has:cycle',
                fields=["Repository", "Id", "Title", "url", "Cycle"],
                cursor=cursor,
            )
            items.extend(result["items"])
            if not result["has_more"]:
                break
            cursor = result["next_cursor"]
        return items

    def apply_one(
        self,
        session: requests.Session,
        item: Dict[str, Any],
        *,
        dry_run: bool,
        mutation_log: MutationLog,
    ) -> ActionResult:
        repository = item.get("Repository", "")
        number = str(item.get("Id", ""))
        title = item.get("Title", "")
        item_ref = f"{repository}#{number}"
        item_cycle = item.get("Cycle", "")

        current_cycle, past_cycles = self._resolve(session)
        if not current_cycle:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="error",
                reason="no active cycle for today (gap between iterations)",
            )

        if item_cycle == current_cycle:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="skipped",
                reason="already in the current cycle",
            )

        if item_cycle not in past_cycles:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="skipped",
                reason=f"cycle '{item_cycle}' is not a past iteration (future or unknown)",
            )

        reverted_by_human = any(
            m.rule == self.id
            and m.field == self.field_name
            and m.old_value == item_cycle
            for m in mutation_log.for_item(item_ref)
        )
        if reverted_by_human:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="flagged",
                reason=(
                    f"{self.id} previously moved this item off cycle '{item_cycle}' "
                    "and a human has since moved it back -- not re-applying"
                ),
            )

        if dry_run:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="applied",
                reason="dry-run: would move",
                old_value=item_cycle,
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
            old_value=item_cycle,
            new_value=current_cycle,
        )
