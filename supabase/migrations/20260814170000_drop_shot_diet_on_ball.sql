-- Drop shot_diet / on_ball questionnaire fields (removed from product)

alter table public.profiles drop column if exists shot_diet;
alter table public.profiles drop column if exists on_ball;

drop type if exists public.shot_diet;
drop type if exists public.on_ball_role;
