-- Phase 4: profile questionnaire fields for style/comp calibration

do $$ begin
  create type public.player_position as enum ('guard', 'wing', 'forward', 'center');
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.dominant_hand as enum ('left', 'right');
exception when duplicate_object then null;
end $$;

do $$ begin
  create type public.primary_skill as enum ('shot', 'pass', 'drive');
exception when duplicate_object then null;
end $$;

alter table public.profiles
  add column if not exists height_in double precision;

alter table public.profiles
  drop constraint if exists profiles_height_in_check;

alter table public.profiles
  add constraint profiles_height_in_check
  check (height_in is null or (height_in >= 48 and height_in <= 96));

alter table public.profiles
  add column if not exists height_z double precision;

alter table public.profiles
  add column if not exists "position" public.player_position;

alter table public.profiles
  add column if not exists dominant_hand public.dominant_hand;

alter table public.profiles
  add column if not exists primary_skill public.primary_skill;

comment on column public.profiles.height_in is 'Stated height in inches';
comment on column public.profiles.height_z is '(height_in - 69) / 3 vs average adult male (~5''9", SD ~3 in)';
