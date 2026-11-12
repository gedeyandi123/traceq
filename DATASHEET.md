# Datasheet: TraceQ synthetic qualification dataset

Format: [Datasheets for Datasets](https://arxiv.org/abs/1803.09010) (Gebru et al.). Sections marked _TBD_ are filled in as v0 is built. Design rationale: [`docs/design/synthetic-dataset.md`](docs/design/synthetic-dataset.md).

## Motivation

- **Purpose:** drive the TraceQ demo and its evals: extraction accuracy, citation groundedness, missing-document recall, Coverage classification, Pre-review precision/recall, and drafted Test Step quality.
- **Creator:** the TraceQ project maintainer.
- **Funding:** none.

## Composition

- **Instances:** documents of a fictional oral solid dose plant (URS, Vendor Documents, FAT/SAT, Protocols, Execution records, reports, monitoring data), plus a structured answer key.
- **Counts:** _TBD (v0)._
- **Labels:** answer key derived from the same world data as the documents: requirement values, citations, Coverage class, required documents, planted defects, OCR bounding boxes.
- **Splits:** dev = all Equipment except TP-202; held-out test = TP-202.
- **Real data:** none. Every plant, vendor, person, and serial number is fictional. A CI denylist blocks real equipment vendor names and other protected terms.
- **Known noise:** deliberate, documented in the defect manifest. Ambiguous values are labelled "ask for confirmation".

## Collection process

- World data for TP-201 and PW-001 is copied from cited public sources (regulation, pharmacopoeia, literature) with verbatim quotes, or recorded as a site decision with a written rationale. Quotes are checked automatically against the source page. Site decisions record who drafted them; those drafted by an LLM are signed off by the owner or a practitioner before freeze. Other Equipment may be LLM-drafted, then human-edited and frozen.
- Documents are rendered deterministically (Typst) from world data and a T0 date; scans are produced by a controlled degrader with a seed.

## Preprocessing

None on the answer key. Values are stored normalised; documents keep locale-specific number and date formats.

## Uses

- **Intended:** evaluating document-understanding and drafting systems for equipment qualification; demos.
- **Not intended:** any real GMP decision. The dataset is not a qualification template and has not been reviewed as regulatory guidance.
- **Judge caveat:** drafted Test Step scores use an LLM judge (Claude Haiku) for three of six criteria. A real on-premises deployment must use a local judge.

## Distribution

- Rendered corpus: GitHub Release asset per dataset version; release bytes are canonical.
- Licence: CC BY 4.0 ([`LICENSE-DATA`](LICENSE-DATA)). Code: Apache-2.0 ([`LICENSE`](LICENSE)).

## Maintenance

- Versioning: SemVer, see [`CHANGELOG.md`](CHANGELOG.md).
- Answer-key changes: separate PR with written rationale, decision-table reference, and CHANGELOG entry; never combined with prompt changes.
- Issues: GitHub issues on this repository.
