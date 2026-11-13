"""Prompts of the drafting step. A change here is an eval experiment (CLAUDE.md): it changes
the prompt hash, so recordings no longer replay until the run is redone live. Examples never
come from the development Equipment."""

from __future__ import annotations

from traceq.ai import Prompt

DRAFT = Prompt(
    name="draft",
    system=(
        "You draft one IQ/OQ Test Step for one URS requirement of pharmaceutical equipment."
        " You get the requirement with its verified value and Coverage class, the vendor"
        " Evidence linked to it with why it does not prove the requirement, and the pages of"
        " the source documents.\n"
        "description: what the step verifies, one sentence.\n"
        "method: how to perform it, executable at the site; test the upper and lower limits"
        " or the worst case where the requirement has them.\n"
        "instrument: the measuring instrument to use; null when the step measures nothing.\n"
        "acceptance: the Acceptance Criterion, only when a source page prints it. kind:"
        " range (min and/or max), number, one_of (accepted texts in allowed, exactly as"
        " printed), text, present (a feature that must exist), or none. Numbers are plain"
        " JSON numbers (Indonesian documents write 1.000 for one thousand and 0,5 for one"
        " half); unit: a short English unit symbol such as mm, kN, rpm or °C.\n"
        "acceptance_source: where the AC is printed: doc and rev of one of the given"
        " sources, the page number and a verbatim quote, at most 200 characters, that"
        " states the AC with its numbers as printed. Copy characters exactly.\n"
        "Never invent, round or tighten a limit. If no source prints an AC for this"
        " requirement, answer kind none and acceptance_source null: a human sets it."
    ),
    schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["description", "method", "instrument", "acceptance", "acceptance_source"],
        "properties": {
            "description": {"type": "string"},
            "method": {"type": "string"},
            "instrument": {"type": ["string", "null"]},
            "acceptance": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "min", "max", "number", "unit", "allowed", "text"],
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["range", "number", "one_of", "text", "present", "none"],
                    },
                    "min": {"type": ["number", "null"]},
                    "max": {"type": ["number", "null"]},
                    "number": {"type": ["number", "null"]},
                    "unit": {"type": ["string", "null"]},
                    "allowed": {"type": "array", "items": {"type": "string"}},
                    "text": {"type": ["string", "null"]},
                },
            },
            "acceptance_source": {
                "type": ["object", "null"],
                "additionalProperties": False,
                "required": ["doc", "rev", "page", "quote"],
                "properties": {
                    "doc": {"type": "string"},
                    "rev": {"type": "integer"},
                    "page": {"type": "integer"},
                    "quote": {"type": "string"},
                },
            },
        },
    },
    max_tokens=4000,
)

PROMPTS = (DRAFT,)
