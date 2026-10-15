-- Sign up / create profile (spec: spec.md).
-- Run after 20260929_activity_locations.sql, which creates public.profiles.
--
-- Supabase Auth creates the auth.users row on sign-up. The trigger below creates the
-- matching profiles row in the same transaction, so either both exist or neither does.

alter table public.profiles
  add column if not exists display_name text not null
    check (char_length(display_name) between 2 and 40),
  add column if not exists email text not null;

-- Emails are unique ignoring case (auth.users also enforces this).
create unique index if not exists profiles_email_lower_key on public.profiles (lower(email));

-- security definer: runs as the table owner, because the new user has no session yet.
-- The check constraint above still applies, so bad metadata sent straight to Supabase
-- fails the whole sign-up instead of creating a half-valid profile.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, display_name, email, location_consent)
  values (
    new.id,
    btrim(new.raw_user_meta_data ->> 'display_name'),
    lower(new.email),
    coalesce((new.raw_user_meta_data ->> 'location_consent')::boolean, false)
  );
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
