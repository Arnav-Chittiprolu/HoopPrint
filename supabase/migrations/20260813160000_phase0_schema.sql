-- HoopPrint Phase 0 schema: profiles, clips pipeline tables, RLS, storage, profile trigger

-- Enums
create type public.source_type as enum ('individual', 'gameplay');
create type public.clip_type as enum ('shot', 'pass', 'drive');
create type public.clip_status as enum (
  'uploaded',
  'awaiting_bbox',
  'processing',
  'done',
  'failed'
);

-- Profiles (1:1 with auth.users)
create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Clips
create table public.clips (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  source_type public.source_type not null,
  clip_type public.clip_type not null,
  storage_path text not null,
  status public.clip_status not null default 'uploaded',
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index clips_user_id_idx on public.clips (user_id);
create index clips_status_idx on public.clips (status);

-- Gameplay single-player bbox (normalized 0–1)
create table public.player_boxes (
  id uuid primary key default gen_random_uuid(),
  clip_id uuid not null unique references public.clips (id) on delete cascade,
  x double precision not null check (x >= 0 and x <= 1),
  y double precision not null check (y >= 0 and y <= 1),
  w double precision not null check (w > 0 and w <= 1),
  h double precision not null check (h > 0 and h <= 1),
  created_at timestamptz not null default now()
);

-- Per-frame keypoints
create table public.keypoints (
  id uuid primary key default gen_random_uuid(),
  clip_id uuid not null references public.clips (id) on delete cascade,
  frame_index integer not null check (frame_index >= 0),
  keypoints jsonb not null,
  track_confidence double precision,
  created_at timestamptz not null default now(),
  unique (clip_id, frame_index)
);

create index keypoints_clip_id_idx on public.keypoints (clip_id);

-- Per-clip features
create table public.clip_features (
  id uuid primary key default gen_random_uuid(),
  clip_id uuid not null references public.clips (id) on delete cascade,
  feature_name text not null,
  value double precision not null,
  meta jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (clip_id, feature_name)
);

create index clip_features_clip_id_idx on public.clip_features (clip_id);

-- Aggregated user profile features
create table public.user_profiles_agg (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  feature_name text not null,
  value double precision not null,
  clip_count integer not null default 0 check (clip_count >= 0),
  updated_at timestamptz not null default now(),
  unique (user_id, feature_name)
);

create index user_profiles_agg_user_id_idx on public.user_profiles_agg (user_id);

-- Cached NBA players (seeded via nba_api in Phase 5)
create table public.nba_players (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  season text not null,
  feature_vector jsonb not null default '{}'::jsonb,
  raw_stats jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (name, season)
);

-- Comp results + LLM summary
create table public.comp_results (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  matches jsonb not null default '[]'::jsonb,
  summary text,
  created_at timestamptz not null default now()
);

create index comp_results_user_id_idx on public.comp_results (user_id);

-- updated_at helper
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger profiles_set_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();

create trigger clips_set_updated_at
  before update on public.clips
  for each row execute function public.set_updated_at();

-- Auto-create profile on signup
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (
    new.id,
    coalesce(new.raw_user_meta_data ->> 'display_name', split_part(new.email, '@', 1))
  );
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Ownership helper for clip-child tables
create or replace function public.owns_clip(target_clip_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.clips c
    where c.id = target_clip_id
      and c.user_id = auth.uid()
  );
$$;

-- RLS
alter table public.profiles enable row level security;
alter table public.clips enable row level security;
alter table public.player_boxes enable row level security;
alter table public.keypoints enable row level security;
alter table public.clip_features enable row level security;
alter table public.user_profiles_agg enable row level security;
alter table public.nba_players enable row level security;
alter table public.comp_results enable row level security;

-- profiles
create policy "Users can view own profile"
  on public.profiles for select
  using (auth.uid() = id);

create policy "Users can update own profile"
  on public.profiles for update
  using (auth.uid() = id)
  with check (auth.uid() = id);

-- clips
create policy "Users can view own clips"
  on public.clips for select
  using (auth.uid() = user_id);

create policy "Users can insert own clips"
  on public.clips for insert
  with check (auth.uid() = user_id);

create policy "Users can update own clips"
  on public.clips for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Users can delete own clips"
  on public.clips for delete
  using (auth.uid() = user_id);

-- player_boxes
create policy "Users can view own player boxes"
  on public.player_boxes for select
  using (public.owns_clip(clip_id));

create policy "Users can insert own player boxes"
  on public.player_boxes for insert
  with check (public.owns_clip(clip_id));

create policy "Users can update own player boxes"
  on public.player_boxes for update
  using (public.owns_clip(clip_id))
  with check (public.owns_clip(clip_id));

create policy "Users can delete own player boxes"
  on public.player_boxes for delete
  using (public.owns_clip(clip_id));

-- keypoints
create policy "Users can view own keypoints"
  on public.keypoints for select
  using (public.owns_clip(clip_id));

-- clip_features
create policy "Users can view own clip features"
  on public.clip_features for select
  using (public.owns_clip(clip_id));

-- user_profiles_agg
create policy "Users can view own aggregated profile"
  on public.user_profiles_agg for select
  using (auth.uid() = user_id);

-- nba_players (read-only for authenticated users; writes via service role)
create policy "Authenticated users can read nba players"
  on public.nba_players for select
  to authenticated
  using (true);

-- comp_results
create policy "Users can view own comp results"
  on public.comp_results for select
  using (auth.uid() = user_id);

-- Storage: private clips bucket
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'clips',
  'clips',
  false,
  52428800, -- 50MB
  array['video/mp4', 'video/quicktime']
)
on conflict (id) do nothing;

-- Paths: {user_id}/{clip_id}.mp4
create policy "Users can upload own clip files"
  on storage.objects for insert
  to authenticated
  with check (
    bucket_id = 'clips'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy "Users can read own clip files"
  on storage.objects for select
  to authenticated
  using (
    bucket_id = 'clips'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy "Users can update own clip files"
  on storage.objects for update
  to authenticated
  using (
    bucket_id = 'clips'
    and (storage.foldername(name))[1] = auth.uid()::text
  )
  with check (
    bucket_id = 'clips'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy "Users can delete own clip files"
  on storage.objects for delete
  to authenticated
  using (
    bucket_id = 'clips'
    and (storage.foldername(name))[1] = auth.uid()::text
  );
