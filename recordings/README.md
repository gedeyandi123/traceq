# Recorded live runs

`haiku-r6` holds one live Haiku run per Equipment on corpus release 0.1.0 (T0 2026-06-01, seed 0): `claude-haiku-5-5`, prompt `cbd88f90a040`, pipeline 0.3.0, Batch API, `vendor_reuse` true. The folder has the LLM recordings (`<key>.json`), the ingest cache (`ingest/`, scans at `PP-OCRv6-small-rapidocr-3.10.0-2`), the scorer report (`report-<tag>.json`, scorer 0.6.0) and the run metadata (`run-<tag>.json`, the live run). `corpus-0.1.0/manifest.json` is the release manifest: replay needs only it, so CI downloads no corpus. `tests/test_recorded_runs.py` replays both at tolerance 0 (same scores, zero live calls, same cost). `baselines/TP-201.json` is this TP-201 run.

r6 is a top-up of r5: the folder is r5's (renamed), and the live run sent only the calls r5 had not recorded, the `transport_sensitive` votes of #88 (a repeated request has its own key, so every r5 answer kept its key). Its `cost_usd` counts all calls; `live_cost_usd` is what was paid.

The dataset is not frozen (freeze 2026-11-25): the baseline is redone at the freeze.

## r6 (current): `transport_sensitive` votes (#88)

| | TP-201 (dev) | TP-202 (held-out) |
|---|---|---|
| run id | 20261114T081401Z-b8a6c4 | 20261114T081635Z-ee9c8f |
| coverage | 25/38 | 6/13 |
| value | 26/38 | 10/13 |
| defect recall | 5/7 | 1/3 |
| probes fabricated | 0/6 | 0/2 |
| fabrication | 0/179 | 0/51 |
| gates | PASS | FAIL (`unsafe_covered_by_vendor`: 1) |
| calls (live) | 142 (14) | 63 (6) |
| tokens in/out | 498419/60817 | 120210/15261 |
| cost USD (live) | 0.040125 (0.004510) | 0.009826 (0.000507) |

Why (#85): URS-TP201-036 was `covered_by_vendor` in r4 and `partial` in r5 with the same Evidence and the same `link` prompt; only the model's `transport_sensitive` bit differed. A probe sent r5's `link` request 10 times per item: 036 said `false` 3/10; the seven items expected `covered_by_vendor` from FAT alone said `false` 70/70; 016 said `true` 10/10. A prompt that defaulted to `true` fixed 036 but turned four covered items `true` 10/10, so it was dropped. With #88 a FAT-only `covered_by_vendor` asks the same request until there are 3 answers, and any `true` applies condition 4. On the probe's rate that puts 036 near 0.3^3 ≈ 3 % per run; 3/10 is a small sample, so the bound is loose. Probe cost $0.058814 (180 calls, not recorded).

TP-201: the 14 votes (7 items × 2) all said `false`, so every score equals r5's (ratchet: same on every metric). r5 had answered 036 `true`, so this run asks it no votes; the fix's evidence on 036 is the probe and the unit tests.

**TP-202 still has no baseline.** Its one run fails the same gate on URS-TP202-012, and the votes do not change it: the item said `false` in 3 of 3 answers, so it is a consistent judgement, not the noise #88 handles. Reported as it is and not re-run; no change is justified by a TP-202 item.

## r5

| | TP-201 (dev) | TP-202 (held-out) |
|---|---|---|
| run id | 20261114T024517Z-4a9ed2 | 20261114T042443Z-4e5583 |
| coverage | 25/38 | 6/13 |
| value | 26/38 | 10/13 |
| defect recall | 5/7 | 1/3 |
| defect findings matched | 5/10 | 1/2 |
| missing docs | 2/2 | 2/2 |
| probes fabricated | 0/6 | 0/2 |
| fabrication | 0/179 | 0/51 |
| gates | PASS | FAIL (`unsafe_covered_by_vendor`: 1) |
| calls (live) | 128 (128) | 57 (57) |
| tokens in/out | 431979/56064 | 111960/14883 |
| cost USD | 0.035615 | 0.009319 |

The prompt change from r1–r3 is one sentence of the `facts` prompt: a datasheet row is quoted by its value's own cell, not joined to its row label. Docling had put `SS 316L` in the row of the heading `Materials and finish`, so the old quote "Materials and finish SS 316L" was not printed (the last `fabricated_citation` failure of r1–r3). Together with #76 (signature quotes) and #78 (uncertain OCR readings) the TP-201 gate passes.

**TP-202 has no baseline.** Its gate fails on `unsafe_covered_by_vendor` (URS-TP202-012 claimed `covered_by_vendor`, expected `partial`). The same gate failed once on TP-201 in the r4 experiment (URS-TP201-036) and passed in the other six runs, so it is investigated on TP-201 (dev) only; no prompt change may be justified by a TP-202 item. TP-202 is not re-run until then (re-running until it passes would pick the result).

**SAT correction (left as is, owner decision).** The SAT scan prints a struck-through value next to its correction (`121.400 tablets/h` struck, `122.400 tablets/h` written). The scorer's page text (pypdf) keeps both, so a quote that skips the struck value can fall below the 0.9 ratio. The shorter quotes of r5 do not hit it; if a later run does, the scorer's handling of struck text is a scoring-rule change for the owner.

## Cost

| Run | TP-201 (dev) | TP-202 (held-out) |
|---|---|---|
| r1 | $0.035300 | $0.009037 |
| r2 | $0.033902 | $0.008352 |
| r3 | $0.033866 | $0.008426 |
| r4 (experiment, not kept) | $0.033010 | – |
| r5 | $0.035615 | $0.009319 |
| probe (#85, `link` ×180, TP-201 only) | $0.058814 | – |
| r6 (top-up, live calls only) | $0.004510 | $0.000507 |

Total $0.270658 of the $25 prepaid credit (limits `--max-usd` 0.50 per TP-201 run and 0.25 per TP-202 run).

r4 (20261114T014948Z-568dc2) also shortened the `record` prompt's quotes. It failed the gate (`fabricated_citation` 4, `unsafe_covered_by_vendor` 1, probes fabricated 1/6), dropped every calibration fact (its quote lost the due date), and did not stop the stamp text; that change was reverted and the recordings were not kept.

## Noise (r1–r3, previous prompt)

r1–r3 ran prompt `aa1ff77e168f` (#45) and no longer replay after the `facts` change; their recordings were removed and stay in the git history (last at commit 8523555). Scores below are as last re-scored there (scorer 0.6.0, with #76 and #78). They measured run-to-run noise before a comparison rule is set (spec #29, user story 25).

### r1–r3, TP-201 (dev)

| | 20261113T222445Z-4d6395 | 20261113T231958Z-c4bceb | 20261114T001513Z-4d2f3d |
|---|---|---|---|
| coverage | 24/38 | 23/38 | 29/38 |
| value | 24/38 | 23/38 | 25/38 |
| defect recall | 5/7 | 5/7 | 5/7 |
| defect findings matched | 5/10 | 5/9 | 5/10 |
| missing docs | 2/2 | 2/2 | 2/2 |
| probes fabricated | 0/6 | 0/6 | 0/6 |
| fabrication | 1/182 | 1/166 | 1/184 |
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
- defect false positives: 5 / 4 / 5
- value URS-TP201-010: wrong / wrong / ok
- value URS-TP201-011: ok / wrong / ok

### r1–r3, TP-202 (held-out)

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
