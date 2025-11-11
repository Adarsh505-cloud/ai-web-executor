from typing import List, Literal, Optional
from pydantic import BaseModel, Field

ActionType = Literal[
    "navigate",
    "fill",
    "click",
    "wait_for_selector",
    "assert_title"
]

class Action(BaseModel):
    type: ActionType
    selector: Optional[str] = None
    value: Optional[str] = None
    timeout_ms: Optional[int] = 10000

class Plan(BaseModel):
    actions: List[Action] = Field(default_factory=list)
