-- Spec 32 correction: serving.flows' primary key must include `mode`.
--
-- The schema as drafted keyed on (source, from_node, to_node, ts, period), leaving
-- `mode` a plain nullable column. That cannot represent a corridor served by more than
-- one transport mode at the same timestamp -- which is the ordinary case for inter-PADD
-- crude movements, not an edge case.
--
-- Measured on the real lake 2026-09-09: of 126,751 flows rows, 32,420 sat in a duplicate
-- key group under the old key, and 13,687 of those 13,700 groups differed only by
-- `mode`. PADD1 -> PADD2 in February 1986, for instance, genuinely carries both a
-- pipeline movement (0 MBBL) and a tanker/barge movement (23 MBBL). Publishing under the
-- old key silently discarded ~15% of the data and left which mode survived to chance.
--
-- `mode` is never null in the lake (checked across all 126,751 rows, five distinct
-- values: grid_interchange, nomination, pipeline, rail, tanker_barge), so promoting it
-- to a key column is safe.
--
-- The table is truncated first: rows already written under the old key carry an
-- arbitrary surviving mode per corridor, and the next publish rewrites all of them.
truncate table serving.flows;

alter table serving.flows drop constraint flows_pkey;
alter table serving.flows alter column mode set not null;
alter table serving.flows add primary key (source, from_node, to_node, ts, period, mode);
