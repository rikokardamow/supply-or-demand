/**
 * Row types for Supabase's `serving` schema (Spec 32 §2).
 *
 * Spec 33 §3 calls for `supabase gen types typescript`. That CLI path needs either
 * Docker (for `--db-url`, which shells out to a container) or a personal access token
 * (for `--project-id`); neither exists on this machine, so these were generated from a
 * real `information_schema.columns` query against the live database on 2026-09-09 --
 * accurate to the deployed schema, not hand-guessed. Regenerate with the CLI once Docker
 * or an access token is available, and prefer that over editing this by hand.
 *
 * Nullability mirrors the database exactly. Note that every column of a *view* is
 * nullable as far as Postgres is concerned, even where the underlying table's column is
 * NOT NULL -- Postgres does not propagate the constraint through a view. That is why
 * `SeasonalRow.doy` is `number | null` while `serving.seasonal.doy` is `not null`.
 */

/** `serving.series_long` -- scalar time series, mirrors core.schemas.ts_long. */
export type SeriesLongRow = {
  series_id: string;
  ts: string;
  value: number | null;
  unit: string | null;
  geo: string | null;
  freq: string | null;
  source: string;
  revision_date: string | null;
};

/** `serving.seasonal_v` -- one row per series per day-of-year. 2020 is excluded from
 * the band by `core.seasonal`; `current` is null for days that have not happened yet. */
export type SeasonalRow = {
  series_id: string | null;
  doy: number | null;
  band_min: number | null;
  band_max: number | null;
  median: number | null;
  current: number | null;
  prior: number | null;
  years: number | null;
  unit: string | null;
};

/** `serving.wpsr_latest_v` -- the WPSR at-a-glance table for the most recent week.
 * `wow` is an absolute change in the line's own unit; the other two are percentages. */
export type WpsrLineRow = {
  week_ending: string | null;
  line: string | null;
  label: string | null;
  unit: string | null;
  value: number | null;
  wow: number | null;
  yoy_pct: number | null;
  vs_median_pct: number | null;
  line_order: number | null;
};

/** `serving.flows` -- directional flows. `period` is the measured cadence
 * ('hourly' | 'daily' | 'monthly'), and `mode` is part of the primary key. */
export type FlowRow = {
  source: string;
  from_node: string;
  to_node: string;
  ts: string;
  period: string;
  value: number | null;
  unit: string | null;
  mode: string;
};

/** `serving.latest_publish_v` -- provenance. `as_of` is the *data's* own as-of, which is
 * what a staleness badge must read; `published_at` is merely when the publish ran. */
export type PublishLogRow = {
  table_name: string | null;
  as_of: string | null;
  source_note: string | null;
  published_at: string | null;
};

/** `serving.curve_settles` -- contract-coded futures settles. */
export type CurveSettleRow = {
  root: string;
  trade_date: string;
  contract: string;
  expiry: string | null;
  settle: number | null;
  oi: number | null;
  source: string | null;
};

/** `serving.spreads_v` -- calendar spreads, front minus back (positive = backwardation). */
export type SpreadRow = {
  root: string | null;
  trade_date: string | null;
  legs: string | null;
  value: number | null;
};
