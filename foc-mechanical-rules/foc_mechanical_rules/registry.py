"""Registry of every mechanical rule this runner enforces.

Add a new rule here as it's ready, alongside its entry in foc-board-rules/.
"""

from __future__ import annotations

from typing import List

from .rule import Rule
from .rules.assignee import AssigneeRule
from .rules.cycle import CycleRule


def default_rules() -> List[Rule]:
    return [AssigneeRule(), CycleRule()]
