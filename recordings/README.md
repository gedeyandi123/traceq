# Recorded live runs

Three live Haiku runs (#45) with the same prompt on corpus release 0.1.0 (T0 2026-06-01, seed 0): `claude-haiku-5-5`, prompt `aa1ff77e168f`, pipeline 0.3.0, Batch API, `vendor_reuse` true in every `run.json`. Each `haiku-r<n>` holds one run per Equipment: the LLM recordings (`<key>.json`), the ingest cache (`ingest/`), the scorer report (`report-<tag>.json`, scorer 0.5.0) and the run metadata (`run-<tag>.json`). Each run has its own folder because recordings are keyed by document, prompt and input, so a shared folder would replay run 1. `corpus-0.1.0/manifest.json` is the release manifest: replay needs only it, so CI downloads no corpus. `tests/test_recorded_runs.py` replays all six at tolerance 0 (same scores, zero live calls, same cost).

The dataset is not frozen: these runs are redone at the freeze. They measure run-to-run noise before a comparison rule is set (spec #29, user story 25); they are not a baseline.

## Cost

| Run | TP-201 (dev) | TP-202 (held-out) |
|---|---|---|
| r1 | $0.035300 | $0.009037 |
| r2 | $0.033902 | $0.008352 |
| r3 | $0.033866 | $0.008426 |

Total $0.128883 of the $25 prepaid credit (limits `--max-usd` 0.50 per TP-201 run and 0.25 per TP-202 run; upper-bound estimate before sending ≈ $0.35 per run pair).

## Noise

### TP-201 (dev)

| | 20261113T222445Z-4d6395 | 20261113T231958Z-c4bceb | 20261114T001513Z-4d2f3d |
|---|---|---|---|
| coverage | 24/38 | 23/38 | 29/38 |
| value | 24/38 | 23/38 | 25/38 |
| defect recall | 5/7 | 5/7 | 5/7 |
| defect findings matched | 5/11 | 5/10 | 5/11 |
| missing docs | 2/2 | 2/2 | 2/2 |
| probes fabricated | 0/6 | 0/6 | 0/6 |
| fabrication | 1/184 | 2/169 | 2/187 |
| gates | FAIL | FAIL | FAIL |
| vendor_reuse | True | True | True |
| calls (live) | 130 (130) | 130 (130) | 128 (128) |
| tokens in/out | 434729/54256 | 413309/52945 | 424889/50487 |
| cost USD | 0.035300 | 0.033902 | 0.033866 |

Items that change across runs: 15 of 94

- ambiguous A-TP201-001: {"asked": true, "silently_resolved": ["step TS-URS-TP201-017 acceptance"]} / {"asked": true, "silently_resolved": []} / {"asked": true, "silently_resolved": []}
- ambiguous A-TP201-002: {"asked": false, "silently_resolved": []} / {"asked": false, "silently_resolved": []} / {"asked": true, "silently_resolved": []}
- coverage URS-TP201-003: gap (expected partial) / gap (expected partial) / partial (ok)
- coverage URS-TP201-005: partial (expected covered_by_vendor) / partial (expected covered_by_vendor) / conflict (expected covered_by_vendor)
- coverage URS-TP201-009: conflict (ok) / conflict (ok) / gap (expected conflict)
- coverage URS-TP201-010: partial (expected covered_by_vendor) / partial (expected covered_by_vendor) / covered_by_vendor (ok)
- coverage URS-TP201-011: conflict (expected covered_by_vendor) / conflict (expected covered_by_vendor) / covered_by_vendor (ok)
- coverage URS-TP201-014: gap (expected partial) / gap (expected partial) / partial (ok)
- coverage URS-TP201-015: gap (expected partial) / gap (expected partial) / partial (ok)
- coverage URS-TP201-019: partial (expected covered_by_vendor) / gap (expected covered_by_vendor) / partial (expected covered_by_vendor)
- coverage URS-TP201-029: site_only (ok) / gap (expected site_only) / site_only (ok)
- coverage URS-TP201-032: site_only (expected gap) / site_only (expected gap) / gap (ok)
- defect false positives: 6 / 5 / 6
- value URS-TP201-010: wrong / wrong / ok
- value URS-TP201-011: ok / wrong / ok

### TP-202 (held-out)

| | 20261113T214025Z-2c5590 | 20261113T230021Z-37b062 | 20261113T235619Z-063c77 |
|---|---|---|---|
| coverage | 6/13 | 5/13 | 5/13 |
| value | 9/13 | 10/13 | 9/13 |
| defect recall | 1/3 | 0/3 | 0/3 |
| defect findings matched | 1/1 | 0/1 | 0/0 |
| missing docs | 2/2 | 2/2 | 2/2 |
| probes fabricated | 0/2 | 0/2 | 0/2 |
| fabrication | 0/48 | 0/40 | 0/37 |
| gates | PASS | PASS | PASS |
| vendor_reuse | True | True | True |
| calls (live) | 53 (53) | 56 (56) | 56 (56) |
| tokens in/out | 105302/15087 | 102474/12914 | 102174/13268 |
| cost USD | 0.009037 | 0.008352 | 0.008426 |

Items that change across runs: 8 of 34

- coverage URS-TP202-002: covered_by_vendor (ok) / gap (expected covered_by_vendor) / gap (expected covered_by_vendor)
- coverage URS-TP202-004: partial (ok) / gap (expected partial) / gap (expected partial)
- coverage URS-TP202-005: partial (expected covered_by_vendor) / gap (expected covered_by_vendor) / gap (expected covered_by_vendor)
- coverage URS-TP202-006: partial (expected covered_by_vendor) / gap (expected covered_by_vendor) / gap (expected covered_by_vendor)
- coverage URS-TP202-007: partial (expected covered_by_vendor) / covered_by_vendor (ok) / covered_by_vendor (ok)
- defect D-TP202-001 failed_result_no_deviation: found / missed / missed
- defect false positives: 0 / 1 / 0
- value URS-TP202-005: wrong / ok / wrong

TP-202 is held out: n = 13, one item is about 8 points, a direction signal only; no prompt change may be justified by a TP-202 item.

## Open: the `fabricated_citation` gate fails on every TP-201 run

The failures (1, 2, 2) are systematic, not noise: in all three runs `URS-TP201-009` cites `DS-TP201` p1 "Materials and finish SS 316L", and in r2 and r3 an AI Finding cites the SAT scan ("TACH-07 SW-03 122.400 tablets/h Lulus"). The system's own check passed each quote against its ingest text (Docling or OCR reading order: the first quote is verbatim in the ingest cache); the scorer matches against the rendered page text (pypdf), where table cells come in another order, at ratio 0.75–0.81 below the 0.9 floor. Whether the scorer's page text, the system's quoting, or the gate changes is an owner decision (gates and scoring rules). Until then no TP-201 run can become a baseline.

The calibration certificates no longer fail (#76): OCR joined the signature row and the stamp beside it into one line ("Calibrated by Markus Brandt Brandt CALIBRATED"), and a signature citation is now trimmed to the span from the printed role to the last printed field ("Calibrated by Markus Brandt"). The three TP-201 reports were re-scored for this; only those three citations per run changed, from `quote_not_found` to verified.
