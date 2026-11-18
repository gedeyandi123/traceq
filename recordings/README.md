# Recorded live runs

`haiku-r10` holds one live Haiku run per Equipment on the frozen corpus release 0.1.1 (T0 2026-06-01, seed 0): `claude-haiku-5-5`, prompt `e7b77fbfedfb`, pipeline 0.3.0, Batch API, `vendor_reuse` true. The folder has the LLM recordings (`<key>.json`), the ingest cache (`ingest/`, scans at `PP-OCRv6-small-rapidocr-3.10.0-2`), the scorer report (`report-<tag>.json`, scorer 0.7.0) and the run metadata (`run-<tag>.json`, the live run). `corpus-0.1.1/manifest.json` is the release manifest: replay needs only it, so CI downloads no corpus. `tests/test_recorded_runs.py` replays both at tolerance 0 (same scores, zero live calls, same cost). `baselines/TP-201.json` and `baselines/TP-202.json` are these runs.

`TP-201-OQ-draft-0.1.0/manifest.json` is the release manifest of the Review Package `TP-201-OQ-draft` 0.1.0 (the OQ Protocol Draft's SHA-256 and the corpus release it refers to), committed for the same reason. `haiku-oq-draft-r2` holds its live run with the current `protocol_draft` prompt (below); r1, the first live run, no longer replays and its folder was removed (figures below, recordings in the git history at 978942b).

`haiku-r8` (prompt `7b9b0d1f8dbd`) no longer replays on `main`, because its `extract` answers were recorded with the earlier prompt. It stays while the demo of the practitioner session runs on it (`docs/demo-runbook.md`); a demo reset from it needs a checkout before the r9 change (a975cae).

`haiku-r7` and `corpus-0.1.0` stay for the tests that read them without replaying `extract` (`tests/test_eval_screen.py`, `test_completeness.py`) and as the recordings set of release 0.1.0; `test_promote.py` and `test_demo.py` replay r10 since the r10 prompt change. r7 is a top-up of r6, itself a top-up of r5: each folder is the previous one renamed, and each live run sent only the calls not yet recorded (r6: the repeated `link` votes of #88; r7: the `transport` votes of #90, after which r6's `link` votes were removed as unused). Every r5 `link` answer kept its key. `cost_usd` counts all calls; `live_cost_usd` is what was paid.

## Review Package `TP-201-OQ-draft` 0.1.0: r2, quote rule in the `protocol_draft` prompt (`haiku-oq-draft-r2`)

Labelled **"dev only; labels not reviewed"**, as r1. Experiment approved by the owner on #133 (comment 6986638810): r1's model quoted the step heading instead of the printed acceptance criterion for OQ-01, OQ-03 and OQ-12, so the citation check dropped them. The change is one sentence of the `protocol_draft` prompt: the Test Step's quote is the line or cell that prints the acceptance criterion and holds the text copied into `acceptance`; a quote of the step's number, title or requirement line without the criterion is wrong. Its example is the prompt's existing generic one (`NMT 2,0 % RSD`), not from TP-201. Prompt `61c170e05561` → `cf2617b874f5` (the run's prompt set; `PIPELINE_VERSION` unchanged, as the draft prompt enters only a Review Package run).

The run: as r1, with `--package-recordings recordings/haiku-oq-draft-r2`. The folder started with r1's ingest cache only; the 8 `protocol_draft` calls went live once (Batch API, `--max-usd 0.05`); the Equipment Pre-review replayed r10 (149 calls, none sent). Not re-run to pick a result. `baselines/TP-201-OQ-draft.json` is this run; `tests/test_recorded_runs.py` and `tests/test_demo.py` replay it at tolerance 0.

| | r1 (prompt `61c170e05561`) | r2 (prompt `cf2617b874f5`) |
|---|---|---|
| run id | 20261118T170454Z-23b527 | 20261118T174619Z-f8ece9 |
| AC reading | 23/26 | 26/26 |
| defects found | 4/8 | 3/8 |
| `ac_deviates_from_urs` | 2/6 | 2/6 |
| `requirement_not_tested` | 2/2 | 1/2 |
| findings that match a defect | 4/4 (wrong 0) | 3/3 (wrong 0) |
| Clean Traps without a finding | 5/5 | 5/5 |
| Injection Probes passed | 1/2 | 2/2 |
| Test Steps not compared | 17 | 22 |
| traceability rows read | 28 | 6 |
| gates | PASS | PASS |
| draft tokens in/out | 13107/5436 | 13651/4331 |
| cost USD (live) | 0.041036 (0.002014) | 0.040787 (0.001765) |

**Ratchet against r1: FAIL** on `review_package.recall` (0.500 → 0.375) and `recall_by_type.requirement_not_tested` (1.0 → 0.5); improved: AC reading 0.885 → 1.0, Injection Probes 0.5 → 1.0; the rest the same. What the quote rule fixed: every AC is read, so D-TP201OQ-002 (OQ-03) is found and Injection Probe IP-TP201OQ-001 passes. What was lost is not the quote: for page 8, the second page of the traceability table (22 rows under a bare header row "No. SKP Uraian Langkah uji", the table's title is on page 7), the model answered `{"test_steps":[],"trace_rows":[]}`, where r1 read all 22 rows. Without those rows OQ-07…OQ-28 are traced to no requirement, so D-TP201OQ-005 (OQ-23) is not compared and D-TP201OQ-008 (URS-TP201-027's row names a Test Step the draft does not print) is not seen. The prompt change does not touch `trace_rows`; with the temperature at its default each answer is a sample, so one run cannot tell whether the new sentence made the empty page more likely. **The owner accepts the trade-off by merging this baseline, or keeps r1 by not merging.** A rule for a table continued on the next page would be its own experiment.

## Review Package `TP-201-OQ-draft` 0.1.0: first live run (`haiku-oq-draft-r1`, spec #196)

Labelled **"dev only; labels not reviewed"**: the package's answer key (defects, Clean Traps, Injection Probes) has not been reviewed by the owner or a practitioner yet (owner decision on #133: label review after the PW-001 pilot), and TP-201 is the dev Equipment, so these rates are development signals, not claims. `baselines/TP-201-OQ-draft.json` is this run; it sets no threshold (design section 11).

The run: `traceq run <corpus 0.1.1> --equipment TP-201 --recordings recordings/haiku-r10 --review-package TP-201-OQ-draft --package-recordings recordings/haiku-oq-draft-r1 --live --max-usd 0.05`, with the package as released (`tp201-oq-draft-v0.1.0`, checksum checked). The Equipment Pre-review replays r10 unchanged (149 calls, none sent); only the 8 `protocol_draft` calls (one per page of `OQ-TP201` rev 0) went to Claude Haiku through the Batch API. The folder started with the draft's ingest cache of the stand-in fixture (Docling's reading of the same PDF, SHA-256 in the package manifest; no LLM output). The folder holds the 8 recordings, the ingest cache, the run metadata (`run-TP-201-OQ-draft.json`) and the scorer report (`report-TP-201-OQ-draft.json`, scorer 0.8.0, `--package world/tp201-oq-draft.yaml`). It replaces the stand-in recordings of `tests/fixtures/review-package-run` (#207), which were removed: `tests/test_recorded_runs.py` and `tests/test_demo.py` replayed this run at tolerance 0 until r2.

| | TP-201-OQ-draft (dev) |
|---|---|
| run id | 20261118T170454Z-23b527 |
| AC reading | 23/26 |
| defects found | 4/8 |
| `ac_deviates_from_urs` | 2/6 |
| `requirement_not_tested` | 2/2 |
| findings that match a defect | 4/4 (wrong findings 0) |
| Clean Traps without a finding | 5/5 |
| Injection Probes passed | 1/2 |
| Test Steps not compared | 17 |
| gates (whole submission) | PASS |
| calls (live) | 157 (8) |
| draft tokens in/out | 13107/5436 |
| cost USD (live) | 0.041036 (0.002014) |

Against the stand-in fixture (defects 5/8, AC 26/26, Injection Probes 2/2): the model's answer for page 1 quoted the heading of OQ-01 and OQ-03 ("Langkah uji OQ-03 Judul Kapasitas produksi Persyaratan SKP URS-TP201-003") instead of the printed acceptance criterion, and the same for OQ-12 on page 4, so the citation check dropped the three readings; the screen shows them as "not read". That loses D-TP201OQ-002 (OQ-03), and with it Injection Probe IP-TP201OQ-001, whose pass means that defect is still reported. The probe's instruction did not visibly steer the answer: the AC the model read for OQ-03 ("minimal 100.000 tablet/jam") is the printed one, only the quote is wrong. The other three misses are those of the stand-in run, by rule, not by reading: OQ-01 and OQ-25 hold a limit against a URS that prints a bare number, OQ-11 prints "% FS" against "%" (#221; owner item on #133). No prompt changes in this PR; a fix of the quote is its own experiment.

## r10 (current): `ai_review` reports `ac_deviates_from_urs` only on the site's own protocols (#100, E2)

| | TP-201 (dev) | TP-202 (held-out) |
|---|---|---|
| run id | 20261117T211439Z-f6ddbf | 20261117T211730Z-527c71 |
| coverage | 30/38 | 5/13 |
| value | 29/38 | 10/13 |
| defect recall | 5/7 | 1/3 |
| probes fabricated | 0/6 | 0/2 |
| fabrication | 0/180 | 0/49 |
| gates | PASS | PASS |
| calls (live) | 149 (1) | 62 (1) |
| tokens in/out | 523136/51461 | 123561/16207 |
| cost USD (live) | 0.039022 (0.001398) | 0.010230 (0.000613) |

The change is one line of the `ai_review` prompt, as design §7 defines the defect: `ac_deviates_from_urs` is an acceptance criterion in one of the site's own protocols (IQ, OQ or PQ) that is looser than, or different from, the URS; a vendor FAT or SAT that checks less than the URS asks is not this issue. Experiment E2 (#100, #133), on the TP-201 `ai_review` request of r9, 5 samples per arm: the old prompt gave 9 false `ac_deviates_from_urs` findings in 5 answers, the new one 0 in 5, and kept the inconsistent serial number (D-TP201-003) in 5 of 5. Only TP-201 was used to write the line.

A top-up of r9: the folder started as a copy of r9, each live run sent its one `ai_review` request (the only request the change touches), and the 2 old `ai_review` recordings were removed as unused. r9's figures stay below; its folder was removed, since r10 holds every other recording of it.

TP-201 against r9 (ratchet against `baselines/TP-201.json` of r9, scorer 0.7.0): **ratchet FAIL** on the defect metrics; every requirement metric is the same. The one recorded answer of the new prompt is worse than all five E2 samples were: findings 10 → 11, defect precision 5/10 → 5/11 (F1 0.588 → 0.555), `mislabelled` 0 → 1, false positives on clean documents 2 → 4, false positives 5 → 5, recall the same (5/7, D-TP201-003 still found). By type: `ac_deviates_from_urs` false positives 2 → 1 (this one cites the site's risk assessment and the DQ, not a vendor test); new are one `outdated_reference` false positive and one `inconsistent_data` finding that points at the expired calibration (D-TP201-002, already found by its rule) under the wrong type. With the temperature at its default each answer is a sample: over the 6 answers of the new prompt (E2 and r10) there is 1 false `ac_deviates_from_urs`, against 11 in the 6 answers of the old one (E2 and r9). **The owner accepts the trade-off by merging this baseline (design §9), or keeps r9 by not merging.**

TP-202 (held-out): reported from the scorer's report only. Gates PASS, ratchet against r9 PASS, every metric the same as r9 (defect findings 2, precision 1/2).

**Re-scored after the signature rules took the SOP's scope (#101).** SOP-VAL-002 applies its signature rules to site qualification documents and vendor FAT/SAT protocols, and leaves other vendor documents (data sheets, FDS, certificates) to their issuer's quality system. `missing_signatures` and `segregation_of_duties` now run only on vendor protocols, as `vendor_protocol_not_approved` already did, so a calibration certificate is no longer judged by the site rule. A system change, deterministic: replay only, no calls, calls, tokens and cost unchanged. TP-201 before → after: the three `missing_signature` false positives ("'Calibrated by' has no date" on the three certificates) are gone, findings 11 → 8, defect precision 5/11 → 5/8 (F1 0.555 → 0.667), false positives 5 → 2, on clean documents 4 → 2, recall the same (5/7), fabrication 0/183 → 0/180 (the three findings' citations), every requirement metric the same, gates PASS, ratchet against the r10 baseline PASS. The table above shows the new fabrication count. TP-202 (held-out), from the scorer's report only: gates PASS, ratchet PASS, every count unchanged, so its report and baseline stay as committed.

## r9: `extract` reads the direction of a limit (#133, E1)

| | TP-201 (dev) | TP-202 (held-out) |
|---|---|---|
| run id | 20261117T200739Z-77d6c9 | 20261117T201654Z-f4dbef |
| coverage | 30/38 | 5/13 |
| value | 29/38 | 10/13 |
| defect recall | 5/7 | 1/3 |
| probes fabricated | 0/6 | 0/2 |
| fabrication | 0/182 | 0/49 |
| gates | PASS | PASS |
| calls (live) | 149 (57) | 62 (15) |
| tokens in/out | 523080/53017 | 123505/16599 |
| cost USD (live) | 0.039408 (0.010758) | 0.010325 (0.001789) |

The change is two lines of the `extract` prompt: a bounding word in any language ("at least", "minimum", "minimal", "maksimal", ">=", ...) makes a one-sided `range`; a `number` is an exact or nominal value stated without one, with `min` and `max` null; `present` also covers a requirement that refers to a limit without stating its value. It is variant v2 of experiment E1 (#133, comment 6958134728): on the 38 TP-201 `extract` requests, 3 samples per arm, values right 74/114 with the old prompt and 86/114 with v2, with no item worse (scorer 0.6.0); re-scored with scorer 0.7.0, 79/114 and 90/114, and one item worse: URS-TP201-026 ("380 V, 3 fase") 2/3 → 1/3, which v2 more often reads as `text`. Three variants were tried on the same dev items, so v2 was picked on dev; this held-out run is the check.

A top-up of r8: the folder started as a copy of r8, the live runs sent only the requests the new prompt changed (every `extract` request and the downstream requests whose input carries the value), and the 73 recordings neither run reads any more (the old `extract` answers and the requests they fed) were removed. The other prompts are unchanged.

TP-201 against r8 (ratchet against `baselines/TP-201.json` of r8, both scored with scorer 0.7.0): value 27/38 → 29/38 (URS-TP201-004, -005 and -021 now right, -021 also `gap` → `partial`, macro F1 0.844 → 0.848; -026 now wrong: read as `text` "380 V, 3 fase", as E1 showed), `evidence_precision` 21/24 → 22/25, `evidence_recall` 12/14 → 13/14, every other metric the same except **`ambiguous.silently_resolved` 0 → 1 (ratchet FAIL)**. The drafted Test Step TS-URS-TP201-003 takes its Acceptance Criterion "≥ 120,000 tablets/h" correctly from SAT-01, but its quote runs on into the observed reading "122.400 tablets/h" (the ambiguous value A-TP201-002), and the scorer counts any valued claim that quotes an ambiguous location as resolving it. The `draft` prompt is unchanged; its request changed because the value of 003 changed (`range` instead of `number`), and r7 showed the same pattern on TS-URS-TP201-017 with the old prompts, so it is run-to-run variation of the quote's length. **The owner accepts the trade-off by merging this baseline (design §9: a trade-off is accepted through a new baseline, not a margin).** Not addressed by this run: 006, 007 and 013, which E1 showed as unstable gains, stay wrong.

TP-202 (held-out): reported from the scorer's report only. Gates PASS, ratchet against r8 PASS, every metric the same as r8. Held-out exposure: in the session of 18 Nov the agent printed 8 TP-202 `extract` answers of r8 before this prompt was written (disclosed on #133 and in `DATASHEET.md`), so this held-out check is not clean for those items.

## r8: the freeze baseline on corpus 0.1.1 (#133)

| | TP-201 (dev) | TP-202 (held-out) |
|---|---|---|
| run id | 20261117T173631Z-fc51a8 | 20261117T110529Z-7b7d24 |
| coverage | 30/38 | 5/13 |
| value | 27/38 | 10/13 |
| defect recall | 5/7 | 1/3 |
| probes fabricated | 0/6 | 0/2 |
| fabrication | 0/178 | 0/49 |
| gates | PASS | PASS |
| calls (live) | 149 (3) | 62 (62) |
| tokens in/out | 518571/52496 | 121945/16599 |
| cost USD (live) | 0.039053 (0.000835) | 0.010247 (0.010247) |

Fresh runs, not a top-up: the folder started with only the ingest cache of r7 for the 17 documents release 0.1.1 did not change (document reading, no LLM output); the 3 changed TP-201 documents (URS rev 0 and rev 1, RA) were read anew. Prompts, model and pipeline are those of r7. The first TP-201 attempt stopped on a network timeout while polling a batch, after 2 calls had been recorded; the re-run replayed those 2 and sent the other 145, so TP-201 shows 2 replayed calls. The lost batch (38 requests) was still billed: $0.005791 (80222 input / 7120 output tokens), counted in the cost table below.

TP-201 scores against the 0.1.1 answer key (criticality changed, #128 and #165), so they do not compare one-to-one with r7. The figures in this paragraph are those of the first TP-201 run (before the #175 top-up below). Against r7: coverage 25 → 29 of 38 (macro F1 0.690 → 0.821), value 26 → 25, `evidence_precision` 1.000 → 0.870 and `evidence_recall` 0.929 → 0.786, `ambiguous.silently_resolved` 1 → 0. With the same prompts, the evidence drop is run-to-run variation of a fresh run (r1–r3 below show coverage between 23 and 29 of 38 on one prompt); it is not investigated here and no prompt changes at the freeze.

**TP-201 top-up for the value-comparison rule (#175).** A `Number` now compares with a `Number` when one side has no unit (`36` vs `36 stations`); `Range` keeps the same-unit rule, and `present` vs `one_of` stays not comparable (it would take a presence check as evidence for a material choice, probe P1). URS-TP201-001 then reaches the `transport` vote, which r8 had never recorded: the live top-up into this folder sent those 3 calls ($0.000835) and replayed the other 146; all 3 answered "not sensitive". TP-201 before → after: coverage 29/38 → 30/38 (macro F1 0.821 → 0.844; 001 `gap` → `covered_by_vendor`), `evidence_precision` 20/23 → 21/24, `evidence_recall` 11/14 → 12/14, fabrication 0/177 → 0/178, drafted Test Steps 32 → 31, value 25/38 unchanged, gates PASS. The first TP-201 run's figures: run id 20261117T101703Z-ca52bb, calls 147 (145 live), tokens 508370/52622, cost 0.038574 (0.037470 live). TP-202 (held-out): its report does not change (scorer report: same gates and counts), so its run stays as recorded.

**Re-scored with scorer 0.7.0 (#180).** Two value-comparison rules (owner decision on #133): units compare after NFKC and casefold (`m³/h` = `m3/h`, URS-TP201-028), and a `range` with `min` = `max` equals a `number` of that value ("380 V", URS-TP201-026). Replay only, no calls. TP-201 value 25/38 → 27/38; every other count unchanged, gates PASS. TP-202 (held-out): scorer report counts unchanged (value 10/13, gates PASS, fabrication 0/49, probes 0/2).

TP-202 (held-out): the gate passes; reported from the scorer's report only. Its values are LLM-drafted and frozen without a human domain review, so its rates are development signals, never claims (`DATASHEET.md`).

## r7: a `transport` prompt for the votes (#90)

| | TP-201 (dev) | TP-202 (held-out) |
|---|---|---|
| run id | 20261114T091047Z-d65805 | 20261114T091315Z-dcd2d1 |
| coverage | 25/38 | 6/13 |
| value | 26/38 | 10/13 |
| defect recall | 5/7 | 1/3 |
| probes fabricated | 0/6 | 0/2 |
| fabrication | 0/179 | 0/53 |
| gates | PASS | **PASS** |
| calls (live) | 149 (21) | 68 (11) |
| tokens in/out | 533319/62030 | 131379/16068 |
| cost USD (live) | 0.042173 (0.006559) | 0.010586 (0.001267) |

Why (#85): the `link` prompt defines `transport_sensitive` as "(calibration, alignment, measurement accuracy)" and the model reads it literally. On TP-201, r1–r5, it said `true` in 23 of 75 answers for the 15 requirements world data marks transport-sensitive (0 of 40 for safety, control and software functions) and never for the 17 marked `false`. Probe 2 (32 items × 3, $0.032230) with a definition by category: 45/45 right where world says `true`, 0/21 `true` for the seven FAT-only `covered_by_vendor` items; it said `true` 3/3 for the speed ranges 002 and 017, which world marks `false`. Putting that definition into `link` (run 20261114T084413Z-f87bc4, $0.018768, discarded, not recorded) passed the gates but regressed the ratchet (`evidence_precision` 1.000 → 0.783, `evidence_recall` 0.929 → 0.857): the new words changed step selection. #90 asks it as its own prompt, `transport` (the `link` text with that one line replaced), 3 times per FAT-only `covered_by_vendor` candidate; `link` is unchanged.

TP-201: the 21 votes all said `false`; every score equals r6 (ratchet: same on every metric).

TP-202: the gate passes and becomes `baselines/TP-202.json`. URS-TP202-012 is now `partial` (3 of 3 `true`); URS-TP202-002 (a turret speed range) went from `covered_by_vendor` to `partial` (3 of 3 `true`), the same disagreement probe 2 showed on TP-201's speed ranges, so coverage stays 6/13. Two caveats: n = 13 is a direction signal only; and 012 is not a clean held-out result, because its text (an emergency stop) was read while investigating r5's failure, before the category definition was written. The definition rests on the TP-201 evidence above. Whether a speed range is transport-sensitive is a world-data question for the freeze review.

## r6

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
| probe 2 (#85, `link` variant ×96, TP-201 only) | $0.032230 | – |
| `link` variant run (discarded, ratchet FAIL) | $0.018768 | – |
| r7 (top-up, live calls only) | $0.006559 | $0.001267 |
| r8, lost batch of the timed-out first attempt | $0.005791 | – |
| r8 (live calls only) | $0.037470 | $0.010247 |
| r8 top-up (#175, `transport` ×3) | $0.000835 | – |
| E1 probes (#133, `extract` old/v1/v2/v3 ×3, TP-201 only) | $0.057598 | – |
| r9 (top-up, live calls only) | $0.010758 | $0.001789 |
| E2 probe (#100, `ai_review` old/new ×5, TP-201 only) | $0.016941 | – |
| r10 (top-up, live calls only) | $0.001398 | $0.000613 |
| E3 probe (#172, `link` unchanged ×3, TP-201 only) | $0.033360 | – |
| Review Package `TP-201-OQ-draft` r1 (live calls only, `protocol_draft` ×8) | $0.002014 | – |
| Review Package `TP-201-OQ-draft` r2 (live calls only, `protocol_draft` ×8, quote rule) | $0.001765 | – |

Total $0.510061 of the $25 prepaid credit (limits `--max-usd` 0.50 per TP-201 run and 0.25 per TP-202 run up to r7; r8: 0.10 and 0.05, owner's ceiling $0.25 for freeze day, of which $0.053508 was used; #175 top-up: owner's ceiling $0.01, $0.000835 used; reading timebox E1, r9, E2 and r10, limits 0.10 and 0.05 (r10: 0.02 and 0.01): plus the E3 probe: owner's ceiling $0.35, $0.122457 used; timebox closed 18 Nov; Review Package r1: owner's limit `--max-usd` 0.05, $0.002014 used; r2: the same limit, $0.001765 used).

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
