# models/tool_request.py

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolRequest:
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)