"""EU ETS allowance balance and auction prices: this repo's own model on public data.

What this page must not let a reader miss:

- **The price is an auction clearing price** (EEX primary auctions, one a day), not a
  continuous market price. No futures settlement is used.
- **The surplus is an annual flow**: supply (free allocation plus auctions) minus what must
  be surrendered. It is not the Total Number of Allowances in Circulation, and the Market
  Stability Reserve is outside it.
- **The latest registry year may be incomplete.** It is extracted soon after the reporting
  deadline. A year that falls short of the prior year's reporting count is left out of
  the balance.
- **Shipping counts at its legislated phase-in** (40% of 2024 emissions, 70% of 2025, 100%
  from 2026), from a committed and cited file.
- **The projection is an assumption, not a forecast.**
"""

from __future__ import annotations

from views.render_streamlit import render
from views.sd import eu_carbon_view

render(eu_carbon_view())
