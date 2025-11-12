from typing import List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator

ActionType = Literal[
    "navigate",
    "fill",
    "click",
    "wait_for_selector",
    "assert_title",
    "wait",
    "select",
    "press_key"  # Added for keyboard interactions
]

class Action(BaseModel):
    type: ActionType
    selector: Optional[str] = None
    value: Optional[Union[str, int]] = None
    timeout_ms: Optional[int] = 30000
    
    @field_validator('value', mode='before')
    @classmethod
    def convert_value_to_string(cls, v):
        """Convert integer values to strings for consistency."""
        if v is not None and isinstance(v, int):
            return str(v)
        return v

class Plan(BaseModel):
    actions: List[Action] = Field(default_factory=list)
