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
