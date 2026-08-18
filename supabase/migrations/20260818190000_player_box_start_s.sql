-- Gameplay bbox start time (seconds into the clip)
alter table public.player_boxes
  add column if not exists start_s double precision not null default 0
  check (start_s >= 0);
