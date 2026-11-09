# FiberDoc AI - evaluation results

Run: 2026-11-09 19:54 UTC

| Metric | Value |
|---|---|
| Documents | 10 |
| Rule checks | 46 |
| **Accuracy** | **65%** (30/46) |
| Recall (planted defects found) | 21% |
| Precision (flags that were real) | 100% |
| False positives / false negatives | 0 / 15 |
| Inconclusive (LLM error) | 1 |
| Document-type accuracy | 60% |
| Ungrounded evidence quotes | 0 |

## Per case

| Case | Type | Result | Wrong checks | Seconds |
|---|---|---|---|---|
| clean_pdf | pdf | PASS | - | 348.8 |
| only_qa_014_pdf | pdf | PASS | - | 435.1 |
| only_dsn_011_pdf | pdf | PASS | - | 436.4 |
| only_dsn_003_pdf | pdf | PASS | - | 365.2 |
| only_con_007_pdf | pdf | PASS | - | 308.6 |
| only_prm_002_pdf | pdf | FAIL | PRM-002 (expected flag, got error) | 290.5 |
| depth_exactly_36_pdf | pdf | FAIL | - | 2.0 |
| all_defects_pdf | pdf | FAIL | QA-014 (expected flag, got ok), DSN-011 (expected flag, got ok), DSN-003 (expected flag, got ok), CON-007 (expected flag, got ok), PRM-002 (expected flag, got ok) | 2.2 |
| all_defects_docx | docx | FAIL | QA-014 (expected flag, got ok), DSN-011 (expected flag, got ok), DSN-003 (expected flag, got ok), CON-007 (expected flag, got ok), PRM-002 (expected flag, got ok) | 0.1 |
| all_defects_xlsx | xlsx | FAIL | QA-014 (expected flag, got ok), DSN-011 (expected flag, got ok), DSN-003 (expected flag, got ok), CON-007 (expected flag, got ok), PRM-002 (expected flag, got ok) | 0.1 |

Synthetic documents and demo rules only. Semantic (LLM) rules can vary between runs.
