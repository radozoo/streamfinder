-- ============================================================================
--  Streamfinder — cross-device favourites
-- ----------------------------------------------------------------------------
--  Run ONCE in the shared Supabase project (the one the lunch app uses):
--    dashboard → SQL Editor → New query → paste → Run.
--  Re-running is safe: every statement is create-if-not-exists or or-replace.
--
--  WHY THIS DIFFERS FROM public.favorites, which it is modelled on.
--
--  The lunch app's favourites are SHARED and PUBLIC on purpose — the count per
--  restaurant is the whole feature — so identity is a typed name and RLS lets
--  anyone read the table. Streamfinder's favourites are the opposite: a private
--  watchlist on a public website. Two consequences:
--
--    1. Identity is a random secret generated in the browser, not a name.
--       A name-keyed list on a public site means anyone who types "Rado" owns
--       Rado's list.
--
--    2. The table has RLS on and NO policies, so the anon key cannot touch it
--       at all — not even SELECT. A `using (true)` read policy would let anyone
--       dump every list in one request, which would make the secret pointless:
--       it would guard writes while the data stayed public. Access goes only
--       through the security-definer functions below, which check the key
--       first. This is the same posture `public.suggestions` already uses for
--       its submit code.
--
--  WHY csfd_id AND NOT A FOREIGN KEY. The catalog is a static build on GitHub
--  Pages; titles do not exist as rows in Supabase, so there is nothing to
--  reference. ČSFD's own id is the stable identifier — the site's local
--  Postgres SERIAL is reassigned whenever the database is rebuilt, which would
--  silently repoint saved favourites at different films.
-- ============================================================================

create table if not exists public.streamfinder_favs (
  id         uuid primary key default gen_random_uuid(),
  list_key   text   not null,                  -- the visitor's secret; identity for this list
  csfd_id    bigint not null,                  -- ČSFD title id (no FK: catalog is static)
  created_at timestamptz not null default now(),
  unique (list_key, csfd_id)                   -- one row per title per list → idempotent add
);

-- Every query is "give me one list", so the key leads the index.
create index if not exists streamfinder_favs_list_key_idx
  on public.streamfinder_favs (list_key, created_at desc);

alter table public.streamfinder_favs enable row level security;
-- Deliberately no policies. See the header: the anon key must not read this table.
drop policy if exists "streamfinder_favs_read"   on public.streamfinder_favs;
drop policy if exists "streamfinder_favs_insert" on public.streamfinder_favs;
drop policy if exists "streamfinder_favs_delete" on public.streamfinder_favs;

-- ---------- Key validation ---------------------------------------------------
-- The client generates 128+ bits of entropy. Enforcing a floor here stops a
-- short or empty key from ever creating a list: without it, a bug that passes
-- '' would file everyone's favourites under one guessable identity.
create or replace function public.sf_key_ok(p_key text)
returns boolean
language sql
immutable
as $$
  select p_key is not null and length(p_key) between 20 and 128;
$$;

-- ---------- Read -------------------------------------------------------------
-- Returns the whole list, newest first — the order the Oblíbené page shows.
create or replace function public.sf_favs_list(p_key text)
returns table (csfd_id bigint, created_at timestamptz)
language plpgsql
security definer
set search_path = public
as $$
begin
  if not sf_key_ok(p_key) then
    raise exception 'invalid list key' using errcode = '22023';
  end if;
  return query
    select f.csfd_id, f.created_at
    from streamfinder_favs f
    where f.list_key = p_key
    order by f.created_at desc;
end;
$$;

-- ---------- Write ------------------------------------------------------------
-- Add and remove are separate calls rather than one toggle: the client already
-- knows the intended end state, and a toggle would flip twice if a request were
-- retried after a timeout.
create or replace function public.sf_favs_add(p_key text, p_csfd_id bigint)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if not sf_key_ok(p_key) then
    raise exception 'invalid list key' using errcode = '22023';
  end if;
  insert into streamfinder_favs (list_key, csfd_id)
  values (p_key, p_csfd_id)
  on conflict (list_key, csfd_id) do nothing;   -- two tabs must not error
end;
$$;

create or replace function public.sf_favs_remove(p_key text, p_csfd_id bigint)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if not sf_key_ok(p_key) then
    raise exception 'invalid list key' using errcode = '22023';
  end if;
  delete from streamfinder_favs where list_key = p_key and csfd_id = p_csfd_id;
end;
$$;

-- Merge a device's existing local favourites into the list, then hand back the
-- union. This is what runs when a second device joins: the phone's offline
-- hearts must survive being linked, so the two sides merge instead of one
-- overwriting the other.
create or replace function public.sf_favs_merge(p_key text, p_csfd_ids bigint[])
returns table (csfd_id bigint, created_at timestamptz)
language plpgsql
security definer
set search_path = public
as $$
begin
  if not sf_key_ok(p_key) then
    raise exception 'invalid list key' using errcode = '22023';
  end if;
  -- `on conflict do nothing` WITHOUT a column list, unlike everywhere else in this
  -- file. `returns table (csfd_id …)` declares an OUT variable of that name, and a
  -- conflict target naming the column is then ambiguous against it (42702) — which
  -- `#variable_conflict use_column` does not fix, because inference is resolved by
  -- the SQL parser, not by plpgsql name resolution. Omitting the target covers any
  -- constraint on the table, which here is the one we want.
  insert into streamfinder_favs (list_key, csfd_id)
  select p_key, unnest(coalesce(p_csfd_ids, '{}'::bigint[]))
  on conflict do nothing;
  return query
    select f.csfd_id, f.created_at
    from streamfinder_favs f
    where f.list_key = p_key
    order by f.created_at desc;
end;
$$;

grant execute on function public.sf_favs_list(text)            to anon, authenticated;
grant execute on function public.sf_favs_add(text, bigint)     to anon, authenticated;
grant execute on function public.sf_favs_remove(text, bigint)  to anon, authenticated;
grant execute on function public.sf_favs_merge(text, bigint[]) to anon, authenticated;

-- sf_key_ok is a helper for the definers above; the client has no reason to call it.
revoke execute on function public.sf_key_ok(text) from anon, authenticated;
