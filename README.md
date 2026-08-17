# HoopPrint

Basketball skill analyzer + NBA player comp.

Upload short footage → pose features → cosine similarity vs real NBA stats → Gemini grounded summary.

Full phased plan: **[PROJECT_PLAN.md](./PROJECT_PLAN.md)**

## Stack (Phase 0)

| Layer | Tech |
|-------|------|
| Frontend | Next.js (App Router) + Tailwind → Vercel |
| Backend | FastAPI → Render |
| Auth / DB / Storage | Supabase |
| LLM (later) | Gemini Flash |

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
3. Run the migration SQL in the SQL Editor:
   - [`supabase/migrations/20260813160000_phase0_schema.sql`](./supabase/migrations/20260813160000_phase0_schema.sql)
4. Copy keys from **Project Settings → API**:
   - Project URL
   - `anon` public key
   - `service_role` key (backend only)
   - JWT Secret (Settings → API → JWT Settings)

### 2. Frontend

```bash
cd frontend
cp .env.example .env.local
# fill NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_API_URL
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
# fill SUPABASE_URL, SUPABASE_JWT_SECRET, SUPABASE_SERVICE_ROLE_KEY
uvicorn app.main:app --reload --port 8000
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

## What’s next

Phase 8 — Dashboard polish (charts, history, mobile bbox).

### Phase 7 — Gameplay bbox + tracking

Upload as **gameplay** → draw a box around yourself on the first frame → CSRT (or template fallback) tracks that person only → pose on the crop → same features/comps as individual clips.

- `GET /clips/{id}/first-frame`
- `POST /clips/{id}/bbox`
- Lost track for 5 frames → skip pose on those frames (no second person)

### Phase 6 — Why this match + personalized recs

After `POST /me/comp`, each match includes a computed `why` (filter + score terms + slot gaps). Recs come from your pose vs this match and the NBA position cohort. Gemini narrates those JSON blobs only.

- Set `GEMINI_API_KEY` in `backend/.env` (optional — why/recs still save if unset)
- Dashboard **NBA style comps** shows why, next steps, and writeup

### Phase 5 — NBA style-space comps

Full-roster seed from `nba_api` → `nba_players.style_vector` → cosine comps filtered by height/position.

- Migration: `supabase/migrations/20260814180000_phase5_nba_style.sql`
- Seed (once per season): `cd backend && PYTHONPATH=. python -m app.scripts.seed_nba_players`
- API: `POST /me/comp`, `GET /me/comp`
- Dashboard: **NBA style comps** panel

**Style slot ← field mapping**

| Style slot | User | NBA (`nba_api` cache) |
|------------|------|------------------------|
| `size` | `height_z_nba` vs NBA/position mean (not US male `height_z`) | listed height on same NBA z scale |
| `perimeter_vs_rim` | `release_angle`, `shot_arc` | Scoring: `PCT_FGA_3PT`, `1 - PCT_PTS_PAINT` |
| `creation` | `decision_speed` | `PCT_UAST_FGM` + pull-up FGA share vs catch-and-shoot |
| `drive_burst` | `first_step_burst`, COD | tracking Drives + `AVG_SPEED_OFF` (league min-max) |
| `passing` | arm extension / consistency | `AST_PCT` + potential assists / passes |

Pose mechanics are returned separately and are **not** treated as FG%/3P%/FT%.

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
