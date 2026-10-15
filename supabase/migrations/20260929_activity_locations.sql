-- Log User Location (spec: log_user_location.md, section 9).
-- Minimal profiles and activities tables are included because activity_locations depends on them.

create table if not exists public.profiles (
  id               uuid primary key references auth.users(id) on delete cascade,
  location_consent boolean not null default false,
  created_at       timestamptz not null default now()
);

create table if not exists public.activities (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  type          text not null check (type in ('run', 'walk', 'cycle')),
  status        text not null default 'in_progress'
                check (status in ('in_progress', 'ended', 'cancelled')),
  started_at    timestamptz not null default now(),
  ended_at      timestamptz,
  point_count   integer not null default 0,
  last_point_at timestamptz
);

create index if not exists activities_user_idx on public.activities (user_id);

create table if not exists public.activity_locations (
  id                  bigint generated always as identity primary key,
  activity_id         uuid not null references public.activities(id) on delete cascade,
  user_id             uuid not null references auth.users(id) on delete cascade,
  client_point_id     uuid not null,
  recorded_at         timestamptz not null,
  received_at         timestamptz not null default now(),
  latitude            double precision not null,
  longitude           double precision not null,
  accuracy_m          real not null,
  altitude_m          real,
  altitude_accuracy_m real,
  speed_mps           real,
  heading_deg         real,
  source              text not null check (source in ('phone_gps', 'watch_gps', 'band', 'import')),
  flagged             boolean not null default false,
  flag_reason         text,
  unique (activity_id, client_point_id)
);

create index if not exists activity_locations_activity_time_idx
  on public.activity_locations (activity_id, recorded_at);

-- Row Level Security: users see and write only their own rows.
alter table public.profiles enable row level security;
alter table public.activities enable row level security;
alter table public.activity_locations enable row level security;

create policy "profiles own read"   on public.profiles for select using (auth.uid() = id);
create policy "profiles own update" on public.profiles for update using (auth.uid() = id);

create policy "activities own read"   on public.activities for select using (auth.uid() = user_id);
create policy "activities own insert" on public.activities for insert with check (auth.uid() = user_id);
create policy "activities own update" on public.activities for update using (auth.uid() = user_id);

create policy "locations own read"   on public.activity_locations for select using (auth.uid() = user_id);
create policy "locations own insert" on public.activity_locations for insert with check (auth.uid() = user_id);
-- No update or delete policy: location rows are immutable.

-- Insert a batch and update the activity summary in one transaction.
-- security invoker: runs as the caller, so RLS still applies.
create or replace function public.insert_activity_locations(p_activity_id uuid, p_points jsonb)
returns integer
language plpgsql
security invoker
set search_path = public
as $$
declare
  inserted integer;
begin
  if not exists (
    select 1 from activities
    where id = p_activity_id and user_id = auth.uid() and status = 'in_progress'
  ) then
    raise exception 'activity_not_active' using errcode = 'P0001';
  end if;

  with ins as (
    insert into activity_locations (
      activity_id, user_id, client_point_id, recorded_at, received_at,
      latitude, longitude, accuracy_m, altitude_m, altitude_accuracy_m,
      speed_mps, heading_deg, source, flagged, flag_reason
    )
    select
      p_activity_id, auth.uid(), p.client_point_id, p.recorded_at, p.received_at,
      p.latitude, p.longitude, p.accuracy_m, p.altitude_m, p.altitude_accuracy_m,
      p.speed_mps, p.heading_deg, p.source, p.flagged, p.flag_reason
    from jsonb_to_recordset(p_points) as p(
      client_point_id uuid, recorded_at timestamptz, received_at timestamptz,
      latitude double precision, longitude double precision, accuracy_m real,
      altitude_m real, altitude_accuracy_m real, speed_mps real, heading_deg real,
      source text, flagged boolean, flag_reason text
    )
    on conflict (activity_id, client_point_id) do nothing
    returning recorded_at
  )
  update activities a
  set point_count   = a.point_count + (select count(*) from ins),
      last_point_at = greatest(a.last_point_at, (select max(recorded_at) from ins))
  where a.id = p_activity_id
  returning (select count(*) from ins) into inserted;

  return inserted;
end;
$$;
