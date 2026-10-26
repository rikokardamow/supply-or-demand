"""UK gas balance by route and the call on LNG: this repo's own model on DESNZ data.

What this page must not let a reader miss:

- **The UK balances on LNG.** With little storage, the useful forward number is not a fill
  level. It is how much LNG the UK must import once production, Norway and the continent are
  counted.
- **Routes are net.** IUK and BBL flow both ways, and the UK exports to Ireland and the
  continent. A negative route is gas leaving the UK.
- **Sector demand starts in January 2023.** DESNZ marks earlier months not available.
- **The projection is an assumption, not a forecast**: the same month a year earlier, scaled
  by `pipelines/derived/uk_gas/assumptions.csv`, which carries an author and a date.

Method: `core/uk_gas_balance.py`. Mapping: `pipelines/derived/uk_gas/routes.csv`.
"""

from __future__ import annotations

from views.render_streamlit import render
from views.sd import uk_gas_view

render(uk_gas_view())
