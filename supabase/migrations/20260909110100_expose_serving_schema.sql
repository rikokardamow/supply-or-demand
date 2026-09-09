-- Expose the serving schema on the Data API (PostgREST), alongside the default
-- public schema, so supabase-js can query serving.* from the Next.js UI (Spec 33).
-- See https://supabase.com/docs/guides/api/using-custom-schemas.
alter role authenticator set pgrst.db_schemas = 'public, serving';
notify pgrst, 'reload config';
