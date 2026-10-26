"""Atlantic LNG: where US LNG goes, and where Europe's LNG comes from.

What this page must not let a reader miss:

- **Two statistics describe the same cargoes, and they disagree.** EU member states record
  about two-thirds of the LNG the US reports shipping to the EU, a stable ratio, with a
  growing "origin not specified" share. The UK and the US agree closely. Both sides are shown;
  neither is corrected.
- **Europe here is the EU-27 plus the UK, and only LNG from outside Europe counts.**
  Re-exports between European terminals are not new supply.
- **The global view is what countries report to JODI, and gaps are named.** Russia does
  not report its LNG exports. Taiwan files zeros for its imports, and those are treated as
  unreported. Thailand, Bangladesh, Pakistan and Singapore do not report at all. A month
  counts only when its reporters cover 98% of typical volume.
"""

from __future__ import annotations

from views.render_streamlit import render
from views.sd import lng_view

render(lng_view())
