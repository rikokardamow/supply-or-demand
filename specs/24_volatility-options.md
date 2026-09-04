# Spec 24 — Volatility & Options Surface

> See `specs/00_TRADING_CONVENTIONS.md`'s **Verified core API** section for real function signatures, schema columns and series IDs before importing any name this spec guesses.

**Sources:** Bouchouev *Virtual Barrels* Ch. 12–13 (dealer negative gamma → downside momentum; CSOs priced under Bachelier/normal; virtual storage = long-dated CSO + delta hedge, exit before theta escalation; no-arbitrage bound on spread-vol decline; caution on correlation models); Newman (producer hedge flows); Mack (Greeks, collars/fences/three-ways/swaptions). Conventions: `specs/00_TRADING_CONVENTIONS.md`.

## Purpose
Surface, skew/positioning links, CSO analytics, virtual-storage strategy, hedge-structure pricers. Page `24_vol.py`.

## Data
Options settlements through the Spec 18 futures pipeline (extend both clients): `opt.<root>.<contract>.<strike>.<c|p>.settle`, `.oi`, `.volume`; CSO settlements `cso.cl.<pair>.<strike>.settle` (manual CSV if unavailable). Spec 18 unadjusted futures; Spec 10 `fred.dgs3mo`; Spec 14 options-inclusive COT; Spec 22 realised vol.

## Sessions

### Session A — pipeline extension + `core/vol.py` pricers
```python
def black76(F, K, T, r, sigma, cp) -> dict           # price, delta, gamma, vega, theta
def implied_vol_b76(price, F, K, T, r, cp) -> float
def bachelier(F, K, T, r, sigma_n, cp) -> dict       # d=(F-K)/(σ√T); C=e^{-rT}[(F-K)N(d)+σ√T n(d)]; σ_n in $/bbl
def implied_vol_bachelier(price, F, K, T, r, cp) -> float
def surface(chain, as_of) -> DataFrame               # per-expiry smile fit (cubic in delta); 10/25/50/75/90-delta vols; flag extrapolation
def skew_metrics(surface) -> DataFrame               # atm, rr25, bf25 per expiry
def vol_cone(realised, windows=(10,21,63,126,252)) -> DataFrame
```
- Tests: put–call parity ±1e-8; Bachelier ATM (F=K, T=1, r=0, σ_n=5) → 1.9947, delta 0.5; implied-vol round-trips ±1e-6; gamma > 0; extrapolation flagged not silent.
- DoD: [ ] options in lake (idempotent daily), [ ] pricers + tests, [ ] one option settle cross-checked against the exchange bulletin.

### Session B — dealer gamma, CSO, virtual storage (`core/cso.py`)
```python
def strike_concentration(chain, kind="p") -> DataFrame           # OI × Γ_b76 per strike, dealer short-put proxy
def dealer_gamma_profile(chain, F_grid) -> DataFrame              # aggregate −Γ·OI·size vs F; flag when spot is within $2 above peak negative-gamma strike
def cso_implied_normal_vol(cso_settles, spread_fwd, T) -> Series
def cso_term_structure(as_of) -> DataFrame
def local_vol_from_implied(sigma_n_term) -> Series                # (σ²(T2)T2 − σ²(T1)T1)/(T2−T1); negative = arbitrage violation, flagged never clipped
def storage_rent_from_cso(cso_price, storage_cost) -> Series
def virtual_storage_strategy(cso_chain, spread_path, exit_days_before_expiry=45, hedge_freq="weekly") -> BacktestResult   # via core.backtest
```
Strategy rule: buy the ≥9-month CSO when its implied normal vol is >10% below local-vol fair; Bachelier-delta hedge the calendar spread (weekly default; daily shown beside it); exit 45 days before expiry or at fair. Conditional-return table: next-5d return when spot sits just above peak negative gamma vs unconditional.
- Tests: local vol negative when σ(T2)²T2 < σ(T1)²T1 and flagged; Bachelier delta ∈ [0,1]; strategy backtest uses signal lagged ≥1 day.
- DoD: [ ] functions, [ ] tests, [ ] backtest card with regime fractionation.

### Session C — hedge structures + page (`core/structures.py`, `24_vol.py`)
`collar`, `fence`, `three_way`, `swaption`, `structure_pnl_grid`, `producer_hedge_flow_estimate(cot_pm_short_delta, put_oi_delta)`.
Theme additions: `iv_surface_heatmap`, `smile_chart`, `vol_cone_chart`, `gamma_profile_chart`, `term_structure_arbitrage_chart` (shaded violation), `payoff_grid_chart`.
Visualisation spec: surface + smiles; rr25/bf25 history and rr25-vs-MM-length scatter; cone; dealer gamma profile with price marker + conditional table; CSO implied vs local vol; virtual-storage equity daily vs weekly; structure explorer.
- DoD: [ ] page live, [ ] green.

## Definition of Done (spec)
- [ ] Options and CSO data flowing daily. [ ] Sessions A–C. [ ] Index + CHANGELOG.

## Session A opener
> Read NOTES.md, specs/00_TRADING_CONVENTIONS.md, specs/24_volatility-options.md and pipelines/futures/NOTES.md. Plan Session A: extend both futures clients to option chains and CSOs, then `core/vol.py` pricers with tests. Pure numpy/scipy — no QuantLib.
