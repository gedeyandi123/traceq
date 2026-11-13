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

_VALUE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "min", "max", "number", "unit", "text", "present"],
    "properties": {
        "kind": {"type": "string", "enum": ["range", "number", "text", "present", "none"]},
        "min": {"type": ["number", "null"]},
        "max": {"type": ["number", "null"]},
        "number": {"type": ["number", "null"]},
        "unit": {"type": ["string", "null"]},
        "text": {"type": ["string", "null"]},
        "present": {"type": ["boolean", "null"]},
    },
}
_DATE = {
    "type": ["object", "null"],
    "additionalProperties": False,
    "required": ["date", "quote"],
    "properties": {"date": {"type": "string"}, "quote": {"type": "string"}},
}
_VALUE_RULES = (
    "value: the value as normalised data.\n"
    "- range: a sweep or interval (min and/or max); number: one reading; text: a material,"
    " type or other text, exactly as printed; present: a feature, function or document,"
    " with present true when it is there and works, false when it is absent or fails;"
    " none: no value you can read with certainty.\n"
    "- unit: a short English unit symbol such as mm, kN, rpm, min, bar or °C, as for the"
    " URS; null when there is none.\n"
)

FACTS = Prompt(
    name="facts",
    system=(
        "You read one page of a vendor document for pharmaceutical equipment: a FAT or SAT"
        " protocol and report, a datasheet or a certificate. Report only what the page"
        " prints.\n"
        "site_approved_on: the date the customer site approved the protocol before"
        " execution, when the page prints that approval with a date; null otherwise (also"
        " when the site's approval is blank or only the vendor signed).\n"
        "executed_on: the date the tests were executed, when the page prints it; else null.\n"
        "For both: date exactly as printed, and a quote that holds it.\n"
        "steps: every test step on the page. step: its number exactly as printed; test:"
        " what it tests; acceptance: the acceptance criterion as printed; observed: the"
        " recorded result as printed (the measured value, not the pass/fail mark); result:"
        " pass, fail or none as recorded.\n"
        "rows: every design or certified value on a datasheet or certificate. name: the row"
        " label as printed; printed: the value as printed.\n"
        + _VALUE_RULES
        + "quote: a verbatim excerpt of the page, at most 200 characters, holding the step"
        " number and its observed result, or the row label and its value. Copy characters"
        " exactly; never paraphrase or translate. If the page has none, return empty lists."
    ),
    schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["site_approved_on", "executed_on", "steps", "rows"],
        "properties": {
            "site_approved_on": _DATE,
            "executed_on": _DATE,
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "step",
                        "test",
                        "acceptance",
                        "observed",
                        "result",
                        "value",
                        "quote",
                    ],
                    "properties": {
                        "step": {"type": "string"},
                        "test": {"type": "string"},
                        "acceptance": {"type": "string"},
                        "observed": {"type": "string"},
                        "result": {"type": "string", "enum": ["pass", "fail", "none"]},
                        "value": _VALUE,
                        "quote": {"type": "string"},
                    },
                },
            },
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "printed", "value", "quote"],
                    "properties": {
                        "name": {"type": "string"},
                        "printed": {"type": "string"},
                        "value": _VALUE,
                        "quote": {"type": "string"},
                    },
                },
            },
        },
    },
    max_tokens=16000,
)

LINK = Prompt(
    name="link",
    system=(
        "You trace one URS requirement for pharmaceutical equipment to vendor Evidence. You"
        " get the requirement and lists of vendor test steps and design values, each with an"
        " id.\n"
        "steps: ids of the test steps whose result tests what the requirement asks. A step"
        " that checks something else (another part, a document about a different property)"
        " is not Evidence.\n"
        "rows: ids of the design or certified values that state what the requirement asks"
        " about (the same parameter, material or feature).\n"
        "site_only: true when the vendor cannot test the requirement because it depends on"
        " the site (utility connections, the production room, plant systems).\n"
        "transport_sensitive: true when transport or installation can change the result, so"
        " a factory test alone does not prove it (calibration, alignment, measurement"
        " accuracy).\n"
        "Use only the ids given; return empty lists when nothing fits."
    ),
    schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["steps", "rows", "site_only", "transport_sensitive"],
        "properties": {
            "steps": {"type": "array", "items": {"type": "string"}},
            "rows": {"type": "array", "items": {"type": "string"}},
            "site_only": {"type": "boolean"},
            "transport_sensitive": {"type": "boolean"},
        },
    },
    max_tokens=2000,
)

PROMPTS = (SEGMENT, EXTRACT, FACTS, LINK)
