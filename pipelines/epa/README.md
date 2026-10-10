# EPA Renewable Fuel Standard reference tables

Read on 2026-10-10 from public EPA and Federal Register text.

| File | Content | Sources |
|---|---|---|
| `volume_targets.csv` | billion RINs by year and category | 2023 final rule (FR doc 2023-13462) for 2023-2025 advanced and total; 2024 cellulosic waiver (FR doc 2025-11153); 2026-27 final rule (FR doc 2026-06275) and the EPA page "Final Renewable Fuel Standards for 2026 and 2027" |
| `percentage_standards.csv` | fraction of gasoline plus diesel | 2023 rule Table I.A.2-1; 2024 cellulosic waiver; 2026-27 rule, 40 CFR 80.1405(a) Table 1 |

Each row's `source` carries the exact URL. 2026-27 volumes are EPA's total applicable volumes
(including reallocated small-refinery exemptions), the basis of that rule's percentages.

Known gaps: BBD volumes for 2023-2025 (published in gallons, not RINs), the 2023 supplemental
standard, and years before 2023. See `reference.py`.

To add a year: open the final rule on epa.gov or govinfo.gov, add one row per category to
both CSVs with `status=final`, the exact URL in `source` and today's date in `as_of`, then run
`pytest tests/test_epa_reference.py`.
