-- Spec 32 Session 3 (security review): make every serving.* view enforce RLS.
--
-- A Postgres view executes with its OWNER's privileges by default, and RLS is not
-- enforced against a table's owner -- so these six views were reading their base tables
-- with row-level security switched off, while `grant select ... to anon, authenticated`
-- and the Data API exposed them publicly.
--
-- Nothing leaks today, because every base policy is `for select ... using (true)`: the
-- view path and the table path return identical rows. The problem is what happens next.
-- Spec 32 §4 plans an `authenticated` policy of the shape
-- `using (tier = 'desk' or series_id in (select id from serving.public_series))`. The
-- day that lands on serving.seasonal, serving.seasonal_v would still serve every row to
-- anon -- and it would not look like a bug, because the policy it bypasses would be
-- sitting right there in the schema looking correct.
--
-- `security_invoker = true` makes the view run as the *caller*, so base-table RLS
-- applies. Fixing it now, while the two paths are equivalent, costs nothing and cannot
-- change behaviour; fixing it later means noticing the leak first.
alter view serving.seasonal_v set (security_invoker = true);
alter view serving.wpsr_latest_v set (security_invoker = true);
alter view serving.vessel_latest_v set (security_invoker = true);
alter view serving.grp_components_v set (security_invoker = true);
alter view serving.spreads_v set (security_invoker = true);
alter view serving.latest_publish_v set (security_invoker = true);
