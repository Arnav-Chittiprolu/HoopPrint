-- Phase 5: style-space NBA comps — extend nba_players for full roster seed

alter table public.nba_players
  add column if not exists player_id bigint,
  add column if not exists position text,
  add column if not exists height_in double precision,
  add column if not exists style_vector jsonb not null default '{}'::jsonb;

-- Prefer style_vector going forward; copy any legacy feature_vector rows
do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'nba_players'
      and column_name = 'feature_vector'
  ) then
    execute $sql$
      update public.nba_players
      set style_vector = feature_vector
      where coalesce(style_vector, '{}'::jsonb) = '{}'::jsonb
        and coalesce(feature_vector, '{}'::jsonb) <> '{}'::jsonb
    $sql$;
    execute 'alter table public.nba_players drop column feature_vector';
  end if;
end $$;

alter table public.nba_players drop constraint if exists nba_players_name_season_key;

create unique index if not exists nba_players_player_id_season_uidx
  on public.nba_players (player_id, season)
  where player_id is not null;

create index if not exists nba_players_season_position_idx
  on public.nba_players (season, position);

create index if not exists nba_players_season_height_idx
  on public.nba_players (season, height_in);
