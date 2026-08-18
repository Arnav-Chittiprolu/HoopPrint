# HoopPrint

HoopPrint is a basketball video-analysis application that turns repeated short clips into two separate outputs:

1. **Mechanics report** — pose-derived movement measurements from your own clips, such as release posture, relative hand height, body-relative early movement burst, and motion consistency.

2. **Playing-style profile** — a role-level summary built only from quality-checked shot, drive-like, and pass-like events across multiple clips. When evidence is sufficient, HoopPrint compares this profile with NBA role profiles derived from public tracking and shot-profile statistics.

HoopPrint does not claim that a user's joint angles match an NBA player's, that a clip predicts shooting percentage or NBA performance, or that a named NBA comparison is an exact player match.

Full phased plan: **[PROJECT_PLAN.md](./PROJECT_PLAN.md)**

## Limits

HoopPrint uses MediaPipe Pose landmarks from a single player. It does not directly track the ball, basket, defenders, teammates, pass target, contest level, shot result, dribble count, or full-game possession context.

Accordingly, HoopPrint:

- Does not measure true ball-release angle, ball arc, entry angle, shot distance, or shot make probability from pose alone.
- Does not infer assists, potential assists, pass completion, turnover risk, defender pressure, or basketball IQ from a one-player clip.
- Does not use pose mechanics such as elbow angle or release posture to compare a user with NBA shooting percentages or NBA player mechanics.
- Treats uploaded clip events as sampled evidence, not as full-game rates such as drives per game or passes per possession.

## How NBA role comparisons work

NBA comparisons are role resemblances, not biomechanical matches.

1. HoopPrint builds a user profile only from validated clip events.
2. It filters NBA candidates by broad position group and reported-height band.
3. It compares only role dimensions supported by evidence in the user's clips.
4. NBA inputs are public tracking and shot-profile statistics, normalized within a season and role cohort.
5. Mechanics measurements are never used in the NBA similarity score.
6. Named NBA examples appear only after sufficient repeated evidence and stability checks; otherwise HoopPrint shows an archetype only.

## Data provenance

NBA role-profile fields are sourced from public NBA statistics through cached `nba_api` data pulls. Each seed record stores its season, endpoint, source field, denominator, transformation version, and retrieval timestamp.

Because NBA.com data endpoints and fields can change, HoopPrint stores source snapshots and does not fabricate unavailable values.

Role-profile seed mapping (`python -m app.scripts.seed_nba_players`):

| Role dimension | NBA rate | Endpoints / fields |
|---|---|---|
| Catch readiness | Catch-and-shoot FGA / (C&S FGA + pull-up FGA) | `LeagueDashPtStats` CatchShoot + PullUpShot |
| Rim-pressure tendency | Drives / touches; paint-points share only if touches unavailable | `LeagueDashPtStats` Drives + Possessions; Scoring `PCT_PTS_PAINT` as documented proxy |
| Playmaking orientation | Potential assists / touches (else / passes) | `LeagueDashPtStats` Passing + Possessions |

Cohort percentiles are empirical ranks within position group after a minutes/GP filter. Legacy `style_vector` is no longer written.

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js (App Router) + Tailwind → Vercel |
| Backend | FastAPI → Render |
| Auth / DB / Storage | Supabase |
| LLM | Gemini Flash (optional narration) |

## Repo layout

```
frontend/     Next.js app
backend/      FastAPI app
supabase/     SQL migrations
PROJECT_PLAN.md
```

## Phase 0 setup

### 1. Supabase

1. Create a free project at [supabase.com](https://supabase.com).
2. Enable Email auth (Authentication → Providers → Email).
   - **Local dev:** turn **OFF** “Confirm email” so signup logs you in immediately and avoids Supabase’s tiny built-in email quota (~2 emails/hour on free tier).
3. Run migrations in the SQL Editor (in order):
   - [`supabase/migrations/20260813160000_phase0_schema.sql`](./supabase/migrations/20260813160000_phase0_schema.sql)
   - … subsequent phase migrations …
   - [`supabase/migrations/20260817220000_phase10_role_profile_data_contracts.sql`](./supabase/migrations/20260817220000_phase10_role_profile_data_contracts.sql) *(Phase 10.1 — role-profile tables)*
4. Copy keys from **Project Settings → API**:
   - Project URL
   - `anon` public key
   - `service_role` key (backend only)
   - JWT Secret (Settings → API → JWT Settings)

### 2. Frontend

```bash
cd frontend
cp .env.example .env.local
# fill NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_API_DIRECT_URL
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### 3. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# fill SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET, SUPABASE_SERVICE_ROLE_KEY
# optional: GEMINI_API_KEY
MPLCONFIGDIR=/tmp/mpl MEDIAPIPE_DISABLE_GPU=1 uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- Public health: `GET http://localhost:8000/health`
- Protected smoke: `GET http://localhost:8000/me` with `Authorization: Bearer <supabase_access_token>`

### Phase 0 exit criteria

- [x] Two users can sign up
- [x] Each user sees only their empty dashboard shell
- [x] No clip processing yet (starts in Phase 1)

### Troubleshooting: “email rate limit exceeded”

Supabase’s **built-in email sender** has a very low rate limit on the free tier. Each signup with “Confirm email” ON sends a mail and counts toward that limit (including failed retries).

**Fix for development:**

1. Supabase Dashboard → **Authentication** → **Providers** → **Email**
2. Turn **OFF** “Confirm email”
3. Wait ~15–60 minutes for the rate limit to reset, then sign up again

**Immediate workaround:** Supabase Dashboard → **Authentication** → **Users** → **Add user** (email + password, auto-confirm). Then sign in at `/login`.

## Local run (current)

1. Start backend (no `--reload` — MediaPipe can kill the reloader):

```bash
cd backend
MPLCONFIGDIR=/tmp/mpl MEDIAPIPE_DISABLE_GPU=1 .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

2. Start frontend: `cd frontend && npm run dev`
3. Open [http://localhost:3000](http://localhost:3000) → sign in → dashboard.

Clips: mp4/mov, max **25s** and **50MB**. Gameplay: draw a box, then process. Idempotent Retry will not start a second job if that clip is already running. Process is rate-limited to **6 / 15 min** per user.

## Deploy (free tier)

Public URLs need your Vercel + Render accounts. Config is in-repo; env values stay in each dashboard (never commit `.env`).

### Backend → Render

1. New **Web Service**, connect this GitHub repo.
2. Use Docker: Dockerfile `backend/Dockerfile`, context `backend/` (or Blueprint [`render.yaml`](./render.yaml)).
3. Health check: `/health`.
4. Set env vars (same names as [`backend/.env.example`](./backend/.env.example)):
   - `ENVIRONMENT=production`
   - `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`
   - `CORS_ORIGINS=https://YOUR_VERCEL_APP.vercel.app` (comma-separate preview URLs if needed)
   - `GEMINI_API_KEY` and `GEMINI_MODEL=gemini-2.5-flash` (optional; comps still work without narration)
5. After first deploy, copy the `onrender.com` URL.

Free Render will **spin down** after idle; the first request can take ~30–60s. Pose on a 512MB instance can still OOM on huge files — stay under 50MB.

### Frontend → Vercel

1. Import the repo, **Root Directory** `frontend`.
2. Env:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `NEXT_PUBLIC_API_DIRECT_URL=https://YOUR_RENDER_SERVICE.onrender.com`
3. Redeploy after the Render URL is known.
4. Add the Vercel origin to Render `CORS_ORIGINS`.

### Production Supabase

- Same project as local is fine for MVP.
- Auth → URL configuration: add `https://YOUR_VERCEL_APP.vercel.app` to Site URL / Redirect URLs.
- Storage bucket `clips` stays **50MB** on the free plan (global file-size cap).
- Run all SQL in `supabase/migrations/` if this is a new project.
- Seed NBA rows once: `cd backend && PYTHONPATH=. python -m app.scripts.seed_nba_players`

## Free-tier limits

| Service | What you will hit |
|---------|-------------------|
| Render free | Cold starts, 512MB RAM, sleeps when idle |
| Supabase free | Pauses after inactivity; **50MB** upload cap; Auth email quota |
| Gemini free | Daily token quota; app fails closed (why/recs JSON still saved) |
| Vercel Hobby | Fine for this Next.js app |

## Scale checklist

1. **Render paid** — no sleep, more RAM/CPU for MediaPipe.
2. **Supabase Pro** — no pause; raise storage if clip volume grows.
3. **LLM** — paid Gemini, or `LLM_PROVIDER=anthropic` / `openai` with the same prompt.
4. Later: job queue if process blocks HTTP; CDN for overlay video.

## What's next

**Phase 10** (current priority): role-profile pivot — data contracts, event gates, provenance-backed NBA seed, masked percentile scoring, dashboard/README copy, disable legacy engine. See PROJECT_PLAN.md §Phase 10.

### Phase 9 — Hardening + deploy

### Phase 8 — Dashboard UI

Results-first dashboard: mechanics panel, playing-style profile (Phase 10), NBA role resemblances when evidence is established, split recs, Gemini narration (optional), overlay, history, touch bbox.

### Phase 7 — Gameplay bbox + tracking

Upload as **gameplay** → draw a box around yourself on the first frame → CSRT (or template fallback) tracks that person only → pose on the crop → same features/comps as individual clips.

- `GET /clips/{id}/first-frame`
- `POST /clips/{id}/bbox`
- Lost track for 5 frames → skip pose on those frames (no second person)

### Phase 6 — Why this match + personalized recs

After `POST /me/comp`, each match includes a computed `why` (filter + dimension gaps + evidence tier). Recs split into **mechanics_recs** and **role_recs** (Phase 10). Gemini narrates stored JSON only — it does not select candidates or make performance claims.

- Set `GEMINI_API_KEY` in `backend/.env` (optional — why/recs still save if unset)
- Dashboard shows why, next steps, and writeup when available

### Phase 5 — NBA comps *(legacy — replaced by Phase 10 role profile)*

Full-roster seed from `nba_api` now writes `role_vector` + provenance. Cosine `style_vector` matching is disabled on `POST /me/comp`.

- Seed (once per season, after role-profile columns exist): `cd backend && PYTHONPATH=. python -m app.scripts.seed_nba_players`
- API: `POST /me/comp`, `GET /me/comp` — `comparison_mode: "role_profile_v1"`

Pose mechanics are returned separately and must **not** feed role matching.
### Phase 4 — Aggregation + profile questionnaire

- After each successful clip, features average into `user_profiles_agg`
- Dashboard **Your profile** form: height → `height_z`, position, hand, primary skill
- `GET` / `PATCH /me/profile`, `GET /me/history`
- Run migration: `supabase/migrations/20260814160000_phase4_profile_questionnaire.sql` in the Supabase SQL Editor

### Phase 3 — Feature extraction

Pose keypoints → deterministic shot / pass / drive features in `clip_features`.

- Inspect: `GET /clips/{id}/features`
- Reprocess a clip to write features: `POST /clips/{id}/process` or CLI
- Units and landmark assumptions: `backend/app/services/features/geometry.py`

### Phase 2 — Pose extraction (individual)

MediaPipe Pose on individual clips → `keypoints` rows in Postgres.

- Auto-processes after upload for `source_type=individual`
- Manual retry: `POST /clips/{id}/process`
- Inspect: `GET /clips/{id}/keypoints`
- CLI: `cd backend && PYTHONPATH=. python -m app.scripts.process_clip <clip_id>`
- First run downloads `pose_landmarker_lite.task` into `backend/models/`

### Phase 1 — Upload clips

Dashboard upload form → `POST /clips` → Supabase Storage + `clips` row.

- mp4/mov, max ~25s, 50MB
- Individual clips → status `uploaded`
- Gameplay clips → status `awaiting_bbox` (bbox UI in Phase 7)
