# derived.rin — implied Renewable Fuel Standard mandate

`pipelines/derived/rin.py` turns the EIA STEO non-renewable gasoline and distillate demand
(`steo.mgtcpusx_p.*`, `steo.dftcpus_p.*`) and EPA's committed percentage standards
(`pipelines/epa/percentage_standards.csv`) into an implied mandate in billions of RINs, one
value per month and category. The arithmetic is `core/rin.py`.

Run by hand after a STEO pull: `python -m pipelines.derived.rin`. It is not scheduled.

## Series ids

    derived.rin.mandate.<category>.<observed|projected>.<final|proposed>

Unit `billion RINs`, monthly, US. The label pair says what the number rests on:

- `projected` if either demand input for the month is a STEO projection, else `observed`.
- `final` or `proposed` from the `status` of the EPA standard used.

## Rules

- Observed beats projected where a month sits under both STEO labels.
- The denominator is the `_P` (non-renewable) pair, never the headline series.
- Days come from each month's own calendar length.
- A month missing a demand input, or a year with no standard, writes no row.

No licensed workbook figure appears here or in the tests; all demand numbers in the tests
are synthetic.

## Checked against the workbook (2026-10-26)

Compared month by month against the workbook's `Implied Mandate` row on its `RIN Balance`
sheet (total category), January 2023 to December 2027: sixty months. Also compared were
its `RVO Percentage Standards` block, four categories over five years, and the fuel-demand
lines beneath the mandate. The comparison script lives outside the repo. As with
`hormuz/README.md`, no workbook figure is printed here. Reproduce it from
`data/manual/bloomberg/849726237.xlsx`.

**The arithmetic is the same.** In every month the workbook's mandate is its fuel demand times
the `Renewable Fuel` percentage standard, which is `core/rin.py`'s formula.

**The denominator is the same quantity, built differently.** The workbook takes STEO motor
gasoline plus distillate, then subtracts ethanol blended and other renewables. This port reads
STEO's non-renewable pair (`MGTCPUSX_P` + `DFTCPUS_P`) directly. In every historical month
(2023–2025) the two agree to within half a per cent, and the residual is STEO's revisions
between the workbook's vintage and this one.

**Then the workbook makes two adjustments this port deliberately does not:**

1. **An Alaska exclusion** (Alaska is outside the RFS obligation unless it opts in), prorated
   from annual EIA AEO values.
2. **An "adjusted-to-actual" reconciliation**, a per-year percentage that scales STEO demand
   to EPA's reported obligated volumes. It is the analyst's calibration rather than a published
   series.

Together these put the workbook's monthly mandate slightly *below* this port's: by at most about one
and a half per cent in every month of 2024–2025. In 2023 the workbook applies a further
adjustment of its own to the mandate line, and the two still agree within the same band.

**Where the two diverge, and why:**

- **2026 onward is a vintage difference, not an error.** The workbook was last reviewed
  19 March 2026. From March 2026 it marks months `Scenario` and uses its own demand baseline;
  for 2027 it has no STEO component lines at all. This port uses the October 2026 STEO,
  observed to July 2026 and projected after. Gaps of a few per cent in 2026–2027 are two
  forecasts disagreeing and should be read that way.
- **Percentage standards: 17 of 20 year-category cells match EPA's published figures exactly.**
  The five that differ are **2025, 2026 and 2027 cellulosic, plus 2027 biomass-based diesel
  and 2027 advanced**. The `total` standard matches in every year. All five pre-date EPA's
  final rule of 1 April 2026 (FR doc 2026-06275), which waived part of the 2025 cellulosic
  volume and set the 2026–2027 standards. The workbook's own note says its 2026–27 standards
  are "calculated from SRE reallocation assumptions", which is an analyst scenario. **This port
  follows the final rule**, and `pipelines/epa/percentage_standards.csv` cites it row by row.
  The disagreement is deliberate.

**What this port does not reproduce, by design:** the Alaska exclusion, the reconciliation
factor and the SRE-reallocated standards. Each is a judgement, not a published number. If one
is wanted, it belongs in a committed, dated assumptions file with an author, as with
`hormuz/flow_share.csv`, never inherited silently from the workbook.
