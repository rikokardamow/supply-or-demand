"""EU-27 gas balance by supply route: this repo's own model on Eurostat and GIE data.

What this page must not let a reader miss:

- **Routes are net imports.** Transit gas leaves and re-enters the EU (TAP through Albania,
  TurkStream through Serbia, gas to Switzerland), so gross imports double count. A negative
  route is gas the EU sends out.
- **The partner is where gas last came from, not always where it was produced.** Russian and
  Azeri gas share the south-east corridor and cannot be split.
- **A blank is a blank.** Months Eurostat publishes incompletely (all of 2020, March 2024)
  are left out, never treated as zero, and a year missing any month has no annual total.
- **The projection is an assumption, not a forecast.** It repeats each month of the previous
  year, scaled by the growth rates in `pipelines/derived/eu_gas/assumptions.csv`, which carry
  an author and a date.

Method: `core/eu_gas_balance.py`. Mapping: `pipelines/derived/eu_gas/routes.csv`.
"""

from __future__ import annotations

from views.render_streamlit import render
from views.sd import eu_gas_view

render(eu_gas_view())
