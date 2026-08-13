# models/tool_response.py

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResponse:
    success: bool
    tool_name: str
    data: Any = None
    error: str | None = None
    execution_time_ms: float | None = None