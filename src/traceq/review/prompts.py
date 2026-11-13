"""Prompts of the Pre-review step. A change here is an eval experiment (CLAUDE.md): it changes
the prompt hash, so recordings no longer replay until the run is redone live. Examples never
come from the development Equipment.

The model only reads and cites what a page prints; the rules in ``traceq.review.rules`` and
the comparison in ``traceq.review.missing`` decide."""

from __future__ import annotations

from typing import Any

from traceq.ai import Prompt

DOC_TYPES = (
    "urs",
    "risk_assessment",
    "datasheet",
    "functional_spec",
    "dq_report",
    "material_certificate",
    "calibration_certificate",
    "fat",
    "sat",
    "iq_protocol",
    "oq_protocol",
    "other",
)
"""Document type codes of submission schema version 1: a vocabulary, not a required list."""

STAGES = ("design", "FAT", "SAT", "IQ", "OQ")

SITE_RULES = (
    "signature_name_and_date",
    "vendor_protocol_approved_before_execution",
    "preparer_not_approver",
    "checker_not_approver",
    "performer_not_witness",
)
"""Rules a qualification SOP may state. A rule is applied only when the SOP states it."""

ROLES = ("prepared", "checked", "approved", "executed", "witnessed", "other")


def _object(required: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(required),
        "properties": required,
    }


def _list(item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": _object(item)}


_STR = {"type": "string"}
_QUOTE_RULE = (
    "quote: a verbatim excerpt of the page, at most 200 characters, holding what the item"
    " states. Copy characters exactly; never paraphrase or translate.\n"
)

RECORD = Prompt(
    name="record",
    system=(
        "You read one page of a qualification record for pharmaceutical equipment: a vendor"
        " FAT or SAT protocol and report, or a calibration certificate. Report only what the"
        ' page prints; leave a field empty ("") when the page leaves it blank.\n'
        "signatures: every row of a signature block (preparation, check, approval,"
        " execution, witness), also a row whose name, signature or date is blank."
        " role_printed: the role label exactly as printed; role: prepared, checked,"
        " approved, executed, witnessed or other; site: true when the person signs for the"
        " customer site rather than the vendor; name, date: as printed; signed: true when"
        " a signature (also an electronic one) is recorded.\n"
        "instruments: every measuring instrument whose calibration validity the page"
        " prints: id as printed, valid_until: the calibration due or expiry date exactly as"
        " printed.\n"
        "step_instruments: for each test step that names the instruments it used: step"
        " number and instrument ids as printed.\n"
        "deviations: every deviation recorded on the page: its id as printed and the step"
        " numbers it concerns. A section that says no deviation was recorded has none.\n"
        "calculations: every result the page computes from other printed numbers (mean,"
        " sum, difference, min, max, range): step number, operation, the inputs and the"
        " stated result exactly as printed.\n" + _QUOTE_RULE + "Return empty lists when the"
        " page has none."
    ),
    schema=_object(
        {
            "signatures": _list(
                {
                    "role_printed": _STR,
                    "role": {"type": "string", "enum": list(ROLES)},
                    "site": {"type": "boolean"},
                    "name": _STR,
                    "signed": {"type": "boolean"},
                    "date": _STR,
                    "quote": _STR,
                }
            ),
            "instruments": _list({"id": _STR, "valid_until": _STR, "quote": _STR}),
            "step_instruments": _list(
                {"step": _STR, "instruments": {"type": "array", "items": _STR}, "quote": _STR}
            ),
            "deviations": _list(
                {"id": _STR, "steps": {"type": "array", "items": _STR}, "quote": _STR}
            ),
            "calculations": _list(
                {
                    "step": _STR,
                    "operation": {
                        "type": "string",
                        "enum": ["mean", "sum", "difference", "min", "max", "range"],
                    },
                    "inputs": {"type": "array", "items": _STR},
                    "result": _STR,
                    "quote": _STR,
                }
            ),
        }
    ),
    max_tokens=16000,
)

REQUIRED = Prompt(
    name="required_documents",
    system=(
        "You read a site Validation Master Plan (VMP) for pharmaceutical equipment. List each"
        " annex that names the documents required for one equipment item.\n"
        "equipment: the equipment tag exactly as printed; page and quote: where the annex"
        " names it.\n"
        "rows: one per required document. doc_id, type_printed, stage_printed: the document"
        " number, document type and qualification stage exactly as printed (the VMP may be in"
        " Indonesian); type: the code of that document type, from the list given; stage: the"
        " code of the stage (design, FAT, SAT, IQ, OQ); page: the page that prints the row.\n"
        + _QUOTE_RULE
        + "Return an empty list when the document has no such annex."
    ),
    schema=_object(
        {
            "annexes": _list(
                {
                    "equipment": _STR,
                    "page": {"type": "integer"},
                    "quote": _STR,
                    "rows": _list(
                        {
                            "doc_id": _STR,
                            "type_printed": _STR,
                            "type": {"type": "string", "enum": list(DOC_TYPES)},
                            "stage_printed": _STR,
                            "stage": {"type": "string", "enum": list(STAGES)},
                            "page": {"type": "integer"},
                            "quote": _STR,
                        }
                    ),
                }
            )
        }
    ),
    max_tokens=8000,
)

RULES = Prompt(
    name="site_rules",
    system=(
        "You read a site's qualification SOP for pharmaceutical equipment (it may be in"
        " Indonesian). Report which of these rules it states, each with the page and a quote"
        " of the sentence that states it:\n"
        "- signature_name_and_date: every signature carries a name and a date.\n"
        "- vendor_protocol_approved_before_execution: the site checks and approves a vendor"
        " FAT/SAT protocol before it is executed.\n"
        "- preparer_not_approver: the person who prepares a document does not approve it.\n"
        "- checker_not_approver: the checker and the approver are different people.\n"
        "- performer_not_witness: the person who performs a test step is not its witness.\n"
        + _QUOTE_RULE
        + "List only rules the SOP states; return an empty list when it states none."
    ),
    schema=_object(
        {
            "rules": _list(
                {
                    "rule": {"type": "string", "enum": list(SITE_RULES)},
                    "page": {"type": "integer"},
                    "quote": _STR,
                }
            )
        }
    ),
    max_tokens=4000,
)

PROMPTS = (RECORD, REQUIRED, RULES)
