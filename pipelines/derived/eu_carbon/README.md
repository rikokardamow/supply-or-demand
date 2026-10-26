# EU carbon balance — the committed model files

This repo's own EU ETS allowance balance on public data. A Bloomberg Intelligence EUA
calculator served as a layout example only.

    python -m pipelines.carbon.pull
    python -m pipelines.derived.eu_carbon

## The balance

    supply      = free allocation (registry) + auctioned volume (EEX, EUA and EUAA)
    to surrender = combustion + industry + aviation emissions + shipping × phase-in
    surplus     = supply − to surrender            (an annual flow)

The cumulative surplus is a running sum of those flows from 2020, the first EEX year. It is not
the Total Number of Allowances in Circulation. Banked allowances from before 2020 and the
Market Stability Reserve's intake are outside it. A TNAC reference file from the Commission's
annual communications is the obvious next step.

## `assumptions.csv`

`line, year, yoy_pct, author, as_of, note`, annual. Lines are the four emission sectors, free
allocation and auctioned volume. The projection starts after the last complete registry year,
and its cumulative surplus continues from the last observed one. The committed file is a
**persistence baseline** (0%, `persistence baseline (default)`, 2026-10-26). It ignores the cap's legislated
decline, so replace it with your own view.

## What the 2026-10-26 run shows (public data)

- Verified emissions, EU ETS without GB: 1,734 Mt (2013) → 1,150 Mt (2023) → 1,185 Mt (2024,
  including 90 Mt of shipping before its phase-in).
- Annual surplus: +53 Mt (2020), then deficits each year: −208, −310, −68, −18 Mt (2021–2024).
- Volume-weighted auction price: €24.52 (2020), €83.25 (2023), €64.75 (2024), €78.43 (2026 to
  date).
- 2025 is still being reported (account counts well short of 2024's) and is left out of the
  balance.
