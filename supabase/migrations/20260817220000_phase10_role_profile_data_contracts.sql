-- Phase 10.1: Role-profile data contracts
-- Mechanics stay in clip_features / user_profiles_agg.
-- style_vector on nba_players remains read-only legacy until cutover (Phase 10.5).

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

create type public.role_dimension as enum (
  'catch_readiness',
  'rim_pressure',
  'playmaking'
);

create type public.role_dimension_status as enum (
  'not_observed',
  'insufficient',
  'emerging',
  'established',
  'suppressed_low_quality'
);

create type public.evidence_tier as enum (
  'insufficient',
  'emerging',
  'established',
  'strong'
);

create type public.comparison_mode as enum (
  'legacy_style',
  'role_profile_v1'
);

-- ---------------------------------------------------------------------------
-- clip_events — gated role events (one row per detected event attempt)
-- ---------------------------------------------------------------------------

create table public.clip_events (
  id uuid primary key default gen_random_uuid(),
  clip_id uuid not null references public.clips (id) on delete cascade,
  user_id uuid not null references public.profiles (id) on delete cascade,
  role_dimension public.role_dimension not null,
  event_index integer not null default 0 check (event_index >= 0),
  gate_passed boolean not null default false,
  rejection_reason text,
  signal_values jsonb not null default '{}'::jsonb,
  quality jsonb not null default '{}'::jsonb,
  fps double precision check (fps is null or fps > 0),
  burst_window_ms integer check (burst_window_ms is null or burst_window_ms > 0),
  event_confidence double precision check (
    event_confidence is null or (event_confidence >= 0 and event_confidence <= 1)
  ),
  session_date date,
  created_at timestamptz not null default now(),
  unique (clip_id, role_dimension, event_index)
);

create index clip_events_clip_id_idx on public.clip_events (clip_id);
create index clip_events_user_id_idx on public.clip_events (user_id);
create index clip_events_user_dimension_idx on public.clip_events (user_id, role_dimension);
create index clip_events_gate_passed_idx on public.clip_events (user_id, gate_passed)
  where gate_passed = true;

alter table public.clip_events enable row level security;

create policy "Users can view own clip events"
  on public.clip_events for select
  using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- user_role_profile — current aggregated role profile (one row per user)
-- ---------------------------------------------------------------------------

create table public.user_role_profile (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references public.profiles (id) on delete cascade,
  profile_version text not null default 'role_profile_v1',
  reference_population_version text,

  catch_readiness_value double precision,
  catch_readiness_percentile double precision,
  catch_readiness_event_count integer not null default 0 check (catch_readiness_event_count >= 0),
  catch_readiness_session_count integer not null default 0 check (catch_readiness_session_count >= 0),
  catch_readiness_confidence double precision,
  catch_readiness_stability double precision,
  catch_readiness_status public.role_dimension_status not null default 'not_observed',

  rim_pressure_value double precision,
  rim_pressure_percentile double precision,
  rim_pressure_event_count integer not null default 0 check (rim_pressure_event_count >= 0),
  rim_pressure_session_count integer not null default 0 check (rim_pressure_session_count >= 0),
  rim_pressure_confidence double precision,
  rim_pressure_stability double precision,
  rim_pressure_status public.role_dimension_status not null default 'not_observed',

  playmaking_value double precision,
  playmaking_percentile double precision,
  playmaking_event_count integer not null default 0 check (playmaking_event_count >= 0),
  playmaking_session_count integer not null default 0 check (playmaking_session_count >= 0),
  playmaking_confidence double precision,
  playmaking_stability double precision,
  playmaking_status public.role_dimension_status not null default 'not_observed',

  role_vector jsonb not null default '{}'::jsonb,
  active_dimensions jsonb not null default '[]'::jsonb,
  quality_summary jsonb not null default '{}'::jsonb,
  evidence_tier public.evidence_tier not null default 'insufficient',

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index user_role_profile_user_id_idx on public.user_role_profile (user_id);

create trigger user_role_profile_set_updated_at
  before update on public.user_role_profile
  for each row execute function public.set_updated_at();

alter table public.user_role_profile enable row level security;

create policy "Users can view own role profile"
  on public.user_role_profile for select
  using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- nba_players — role-profile seed lineage (style_vector legacy read-only)
-- ---------------------------------------------------------------------------

alter table public.nba_players
  add column if not exists season_type text not null default 'Regular Season',
  add column if not exists position_group text,
  add column if not exists minutes double precision,
  add column if not exists possessions double precision,
  add column if not exists catch_shoot_fga double precision,
  add column if not exists pull_up_fga double precision,
  add column if not exists catch_shoot_share double precision,
  add column if not exists drives double precision,
  add column if not exists touches double precision,
  add column if not exists drives_per_touch double precision,
  add column if not exists rim_attempt_share double precision,
  add column if not exists passes double precision,
  add column if not exists potential_assists double precision,
  add column if not exists passes_per_touch double precision,
  add column if not exists potential_assists_per_pass double precision,
  add column if not exists potential_assists_per_touch double precision,
  add column if not exists assist_pct double precision,
  add column if not exists role_vector jsonb not null default '{}'::jsonb,
  add column if not exists cohort_percentiles jsonb not null default '{}'::jsonb,
  add column if not exists raw_source jsonb not null default '{}'::jsonb,
  add column if not exists transform_version text,
  add column if not exists seeded_at timestamptz,
  add column if not exists meets_min_sample boolean not null default false;

-- Backfill position_group from legacy position column
update public.nba_players
set position_group = position
where position_group is null and position is not null;

create index if not exists nba_players_season_position_group_idx
  on public.nba_players (season, position_group);

comment on column public.nba_players.style_vector is
  'Legacy Phase 5 style slots — read-only after role_profile_v1 cutover.';
comment on column public.nba_players.role_vector is
  'Phase 10 role dimensions: catch_readiness, rim_pressure_tendency, playmaking_orientation.';
comment on column public.nba_players.raw_source is
  'Endpoint/field provenance per scalar; raw_stats retained for legacy seed payloads.';

-- ---------------------------------------------------------------------------
-- comp_results — auditable role-profile snapshots
-- ---------------------------------------------------------------------------

alter table public.comp_results
  add column if not exists user_role_profile_id uuid references public.user_role_profile (id) on delete set null,
  add column if not exists profile_version text,
  add column if not exists nba_seed_version text,
  add column if not exists comparison_mode public.comparison_mode not null default 'legacy_style',
  add column if not exists cohort_definition jsonb not null default '{}'::jsonb,
  add column if not exists active_dimensions jsonb not null default '[]'::jsonb,
  add column if not exists excluded_dimensions jsonb not null default '[]'::jsonb,
  add column if not exists dimension_contributions jsonb not null default '{}'::jsonb,
  add column if not exists candidate_results jsonb not null default '[]'::jsonb,
  add column if not exists archetype_result jsonb not null default '{}'::jsonb,
  add column if not exists evidence_tier public.evidence_tier,
  add column if not exists stability_metrics jsonb not null default '{}'::jsonb,
  add column if not exists disclosure_version text,
  add column if not exists mechanics_recs jsonb not null default '[]'::jsonb,
  add column if not exists role_recs jsonb not null default '[]'::jsonb;

create index if not exists comp_results_user_role_profile_id_idx
  on public.comp_results (user_role_profile_id);

create index if not exists comp_results_comparison_mode_idx
  on public.comp_results (comparison_mode);
