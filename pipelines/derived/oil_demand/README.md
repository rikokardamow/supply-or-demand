# GDP growth assumptions for the oil-demand scenario

`gdp_assumptions.csv` is the forward input to `pipelines/derived/oil_demand.py`. It is the
workbook's "User Input" column: **your** assumed real GDP growth, year on year, per block
per quarter. No connector supplies a GDP forecast and none is implied.

| Column | Meaning |
|---|---|
| `block` | `us`, `cn` or `ea` |
| `quarter` | quarter start, `yyyy-mm-dd` — must be after the last observed quarter |
| `gdp_yoy_pct` | assumed real GDP growth on a year earlier, in percent. Blank = no assumption |
| `author` | who set it |
| `as_of` | the date it was set |

The file ships with a header and no rows. With no rows, no scenario series is written.
Rows here become `derived.oil_demand.<block>.yoy.scenario` in the lake — never the observed
series. After editing, run `python -m pipelines.derived.oil_demand`.

Do not paste Bloomberg Economics' baseline here. It is licensed, and this file is tracked.
