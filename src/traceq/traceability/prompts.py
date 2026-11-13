"""Prompts of the traceability step. A change here is an eval experiment (CLAUDE.md): it
changes the prompt hash, so recordings no longer replay until the run is redone live.
Examples never come from the development Equipment."""

from __future__ import annotations

from traceq.ai import Prompt

SEGMENT = Prompt(
    name="segment",
    system=(
        "You read one page of a User Requirements Specification (URS) for pharmaceutical"
        " equipment. List every numbered requirement printed on the page.\n"
        "- id: the requirement number exactly as printed.\n"
        "- text: the requirement sentence exactly as printed.\n"
        "- quote: a verbatim excerpt of the page, at most 200 characters, that contains the"
        " requirement sentence. Copy characters exactly; never paraphrase or translate.\n"
        "Skip headings, revision history and approval blocks. If the page has no"
        " requirement, return an empty list."
    ),
    schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["requirements"],
        "properties": {
            "requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "text", "quote"],
                    "properties": {
                        "id": {"type": "string"},
                        "text": {"type": "string"},
                        "quote": {"type": "string"},
                    },
                },
            }
        },
    },
    max_tokens=16000,
)

EXTRACT = Prompt(
    name="extract",
    system=(
        "You extract the required value of one URS requirement for pharmaceutical"
        " equipment. Answer from the requirement and the page text only.\n"
        "kind:\n"
        "- range: a limit or interval; set min and/or max ('at least 5' has only min,"
        " 'at most 5' only max, '2-8' both).\n"
        "- number: one exact required number.\n"
        "- one_of: a required material, type or option; list the accepted texts in allowed,"
        " exactly as printed.\n"
        "- text: a required text value that is none of the above.\n"
        "- present: a feature or document that must exist, with no number.\n"
        "- none: the requirement states no value you can read with certainty.\n"
        "Numbers are plain JSON numbers: read the document's decimal and thousands"
        " separators (Indonesian documents write 1.000 for one thousand and 0,5 for one"
        " half). unit: a short English unit symbol such as mm, kN, rpm, min, bar or °C;"
        " null when there is none.\n"
        "quote: a verbatim excerpt of the page, at most 200 characters, that states the"
        " value with its numbers as printed. Copy characters exactly; never paraphrase."
        " If a value is ambiguous, answer kind none rather than guess."
    ),
    schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "min", "max", "number", "unit", "allowed", "text", "quote"],
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
            "quote": {"type": "string"},
        },
    },
    max_tokens=4000,
)

PROMPTS = (SEGMENT, EXTRACT)
