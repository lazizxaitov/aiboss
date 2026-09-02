"""AI Business OS capability boundary exposed to the selected model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

CapabilityName = Literal[
    "business.query",
    "business.describe",
    "system.inspect",
    "ui.inspect",
    "code.search",
    "code.read",
    "code.edit",
    "tests.run",
    "dashboard.configure",
]


@dataclass(frozen=True, slots=True)
class AICapability:
    name: CapabilityName
    description: str
    access: Literal["read", "write"]
    arguments: dict[str, object] = field(default_factory=dict)


_CAPABILITIES: tuple[AICapability, ...] = (
    AICapability(
        "business.query",
        "Execute a safe read-only query against approved AI Business OS analytical views.",
        "read",
        arguments={
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "One SELECT statement over the published ai_* analytical views.",
                },
            },
            "required": ["sql"],
            "additionalProperties": False,
        },
    ),
    AICapability(
        "business.describe",
        "Describe the exact published fields and relationships for a requested business domain or view.",
        "read",
        arguments={
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "entity": {"type": "string"},
                "detail": {"type": "string", "enum": ["schema", "relationships"]},
            },
            "additionalProperties": False,
        },
    ),
    AICapability("system.inspect", "Inspect approved AI Business OS system state and service metadata.", "read"),
    AICapability("ui.inspect", "Inspect the current page, widget and visible UI context when supplied.", "read"),
    AICapability("code.search", "Search approved project source locations.", "read"),
    AICapability("code.read", "Read approved project source files.", "read"),
    AICapability("code.edit", "Edit project files only through a future explicit approval flow.", "write"),
    AICapability("tests.run", "Run project checks only through a future explicit approval flow.", "write"),
    AICapability("dashboard.configure", "Change dashboard configuration only through an approved action.", "write"),
)

BUSINESS_QUERY_CAPABILITY = "business.query"

_ROLE_CAPABILITIES: dict[str, tuple[CapabilityName, ...]] = {
    "business_analytics": ("business.query", "business.describe", "system.inspect", "ui.inspect"),
    "ai_chat": ("business.query", "business.describe", "system.inspect", "ui.inspect"),
    "system_action": ("business.query", "business.describe", "system.inspect", "ui.inspect", "dashboard.configure"),
    "communications": ("business.query", "business.describe", "system.inspect"),
    "system_developer": ("system.inspect", "ui.inspect", "code.search", "code.read"),
}


class AICapabilityRegistry:
    """Single source of truth for model-visible AI BOS permissions."""

    def for_role(self, role: str) -> list[AICapability]:
        allowed = set(_ROLE_CAPABILITIES.get(role, ()))
        return [capability for capability in _CAPABILITIES if capability.name in allowed]

    def describe(self, role: str) -> list[dict[str, object]]:
        return [asdict(capability) for capability in self.for_role(role)]


ai_capability_registry = AICapabilityRegistry()
