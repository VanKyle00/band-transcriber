-- Band Transcriber — initial schema.
-- One `jobs` table + a private `artifacts` storage bucket + a TTL cleanup job.
-- v1 is ephemeral/one-shot: rows and files auto-expire after 24h. The only change
-- needed to add accounts later is a `user_id` column + per-user RLS policies.

-- ---------------------------------------------------------------------------
-- jobs
-- ---------------------------------------------------------------------------
create table if not exists public.jobs (
    id          text primary key,                         -- random 12-hex id
    status      text not null default 'queued',           -- queued|processing|done|error
    stage       text,                                     -- downloading|separating|transcribing|done
    source_type text,                                     -- url|upload
    artifacts   jsonb,                                    -- { stems: [ { name, audio, midi, ... } ] }
    error       text,
    created_at  timestamptz not null default now(),
    expires_at  timestamptz
);

create index if not exists jobs_expires_at_idx on public.jobs (expires_at);

-- Lock the table down: RLS on, no anon policies. Only the service-role key
-- (used by Modal and the Next.js server) can read/write. Browsers poll status
-- through the Next.js API route, never Supabase directly.
alter table public.jobs enable row level security;

-- ---------------------------------------------------------------------------
-- storage bucket (private; access via signed URLs)
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('artifacts', 'artifacts', false)
on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- TTL cleanup: remove expired artifacts then their job rows.
-- Objects are stored under "<job_id>/<filename>", so we match on the first path segment.
-- ---------------------------------------------------------------------------
create or replace function public.cleanup_expired_jobs()
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    delete from storage.objects o
    using public.jobs j
    where j.expires_at < now()
      and o.bucket_id = 'artifacts'
      and split_part(o.name, '/', 1) = j.id;

    delete from public.jobs where expires_at < now();
end;
$$;

-- Schedule every 30 min. Requires the pg_cron extension (enable it in the
-- Supabase dashboard: Database -> Extensions -> pg_cron, or uncomment below).
-- create extension if not exists pg_cron;
-- select cron.schedule('cleanup-expired-jobs', '*/30 * * * *',
--                      $$ select public.cleanup_expired_jobs(); $$);
