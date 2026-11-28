"""The settings of Mode Pabrik (spec #442), apart from its adapter so the CLI names them
without importing an HTTP client."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

PABRIK_BASE_URL = "https://api.sea-lion.ai/v1"
PABRIK_MODEL = "aisingapore/Qwen-SEA-LION-v4.5-27B-IT"
API_KEY_ENV = "TRACEQ_PABRIK_API_KEY"
"""The environment variable holding the endpoint's key."""

StructuredOutput = Literal["json_schema", "tool"]
STRUCTURED_OUTPUTS: tuple[StructuredOutput, ...] = ("json_schema", "tool")

ThinkingParam = Literal["both", "enable_thinking", "thinking_mode", "none"]
THINKING_PARAMS: Mapping[ThinkingParam, Mapping[str, Any] | None] = {
    # Two chat-template conventions: Qwen3's ``enable_thinking`` and the SEA-LION reasoning
    # models' ``thinking_mode``; ``both`` sends the two, for a template that reads one of them.
    "both": {"enable_thinking": False, "thinking_mode": "off"},
    "enable_thinking": {"enable_thinking": False},
    "thinking_mode": {"thinking_mode": "off"},
    "none": None,
}
"""What each ``--thinking-param`` sends as ``chat_template_kwargs`` to ask thinking off."""
