# HoopPrint — basketball clips that become a role profile

# HoopPrint

Basketball clip analysis that separates how you move from how you play.

Upload short shot, pass, and drive clips. HoopPrint quality-checks the action, measures mechanics from pose, and — when enough events pass — matches a playing-style profile to NBA role resemblances. Height is body plausibility, not a style slot. A named comparison is not a claim that you shoot like them.

Next.js · FastAPI · Supabase · MediaPipe · Tailwind · Gemini

**Status:** prototype · **Platform:** local + Vercel / Render · **Clips:** mp4 / mov, ~25s, 50MB

---

# HoopPrint — footage in, role profile out

> [!NOTE]
> Two reports, never mixed. **Mechanics** come from MediaPipe pose on your clips. **NBA names** come from quality-checked shot / pass / drive events compared to public tracking stats. Elbow angle never ranks you against Cade. A 6'6" profile never names Wembanyama.

## Contents

- [What it is](#what-it-is)
- [How it works](#how-it-works)
- [Features](#features)
- [Getting started](#getting-started)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Design system](#design-system)
- [Deploy](#deploy)
- [Roadmap](#roadmap)
- [Limits](#limits)
- [Acknowledgements](#acknowledgements)

## What it is

HoopPrint is a web app that turns repeated short clips into two separate outputs:

1. **Mechanics report** — pose-derived measurements from your own footage (release posture, relative hand height, body-relative burst, motion consistency).
2. **Playing-style profile** — a role-level summary built only from quality-checked catch-and-shoot / pull-up, drive-like, and pass-like events. When evidence is **Established** (~5 valid events), it names NBA role comps.

It does **not** claim that your joint angles match an NBA player's, that a clip predicts shooting percentage or NBA performance, or that a named comparison is an exact player match.

The product surface is two tabs after login:

- **Clips** — profile, upload, and clip list.
- **Analysis** — playing-style profile, physical context, primary comps, style-only references, and a re-run card.

## How it works

```
  you ── upload clip ──►  ┌─────────────────┐
                          │  FastAPI + pose │  MediaPipe on a single player
                          │  (MediaPipe)    │  optional gameplay box + track
                          └────────┬────────┘
                                   │ keypoints · clip features
              ┌────────────────────┼────────────────────┐
              ▼                                         ▼
        ┌───────────┐                             ┌───────────┐
        │ mechanics │                             │   gates   │
        │  report   │                             │ shot/pass │
        │  (pose)   │                             │  /drive   │
        └───────────┘                             └─────┬─────┘
                                                        │ valid events only
                                                  ┌─────▼─────┐
                                                  │ role vec  │
                                                  │ catch ·   │
                                                  │ rim ·     │
                                                  │ playmake  │
                                                  └─────┬─────┘
                                                        │ 72% role / 16% body
                                                  ┌─────▼─────┐
                                                  │ NBA names │
                                                  │  or style │
                                                  │   -only   │
                                                  └───────────┘
```

1. **You record the action** — tag shot, pass, or drive. Solo drills process immediately. Gameplay asks you to box yourself; only that person is tracked.
2. **Pose runs on the crop** — MediaPipe writes keypoints. Mechanics come from those landmarks. Role matching never reads them.
3. **Events have to pass a gate** — form shooting, missing catches, sparse tracks, and clips that start on the action do not count toward NBA comparison.
4. **The role vector is three numbers** — catch readiness, rim-pressure tendency, playmaking orientation. Missing dimensions are masked, not zero-filled.
5. **Rank is role-first** — 72% role resemblance, 16% body plausibility, 7% sample confidence, 5% listed position. Height bands: 0–5" primary, 5–7" primary only on high resemblance, 7–9" style-only, **>9" excluded**.

NBA inputs are public tracking and shot-profile statistics (`nba_api`), stored with season, endpoint, source field, and transform version. Cohort percentiles are empirical ranks within position group after a minutes / GP filter.

### Role-profile seed mapping

`python -m app.scripts.seed_nba_players`

| Role dimension | NBA rate | Endpoints / fields |
|---|---|---|
| Catch readiness | Catch-and-shoot FGA / (C&S FGA + pull-up FGA) | `LeagueDashPtStats` CatchShoot + PullUpShot |
| Rim-pressure tendency | Drives / touches; paint-points share only if touches unavailable | `LeagueDashPtStats` Drives + Possessions; Scoring `PCT_PTS_PAINT` as documented proxy |
| Playmaking orientation | Potential assists / touches (else / passes) | `LeagueDashPtStats` Passing + Possessions |

## Features

**Clips**

- Shot / Pass / Drive segmented upload with a dropzone. mp4 or mov, ~25s, 50MB.
- Individual drills auto-process. Gameplay: draw a full-body box, then track.
- Compact clip list with Processed / Processing / Error; expand for overlay, type change, retry, delete.
- Progress toward Established (about 5 quality-checked clips).
- Process is rate-limited to **6 / 15 min** per user. Retry is idempotent if that clip is already running.

**Analysis**

- Playing-style profile with an evidence badge (Building / Established).
- Physical context copy — height shapes which NBA bodies are realistic, not how you play.
- Primary comps (style + body plausible) vs style-only (size mismatch, for learning).
- Dual bars: orange = you, gray = them. Why-this-match is computed JSON, not model invention.
- Optional Gemini writeup that narrates stored JSON only — it does not pick names.

**Account**

- Email + password via Supabase Auth.
- Setup wizard: name, height (ft/in), position, dominant hand, primary skill.
- Incomplete profiles cannot reach the dashboard.

## Getting started

### Prerequisites

- Node.js 18+ and npm.
- Python 3.11+ (backend venv).
- A [Supabase](https://supabase.com) project with Email auth.
- Optional: `GEMINI_API_KEY` for narration.

### 1. Supabase

1. Create a free project.
2. Enable Email auth. For local dev, turn **OFF** “Confirm email” so signup logs you in immediately and avoids the tiny built-in email quota.
3. Run every file in [`supabase/migrations/`](./supabase/migrations/) in the SQL Editor, in filename order.
4. From **Project Settings → API**, copy Project URL, `anon` key, `service_role` key, and JWT secret.

### 2. Frontend

```bash
cd frontend
cp .env.example .env.local
# NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, NEXT_PUBLIC_API_DIRECT_URL
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
# SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET, SUPABASE_SERVICE_ROLE_KEY
# optional: GEMINI_API_KEY
MPLCONFIGDIR=/tmp/mpl MEDIAPIPE_DISABLE_GPU=1 .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Do **not** pass `--reload` — MediaPipe can kill the reloader. Restart uvicorn after Python changes.

- Health: `GET http://127.0.0.1:8000/health`
- First pose run downloads `pose_landmarker_lite.task` into `backend/models/`
- Seed NBA rows once: `cd backend && PYTHONPATH=. python -m app.scripts.seed_nba_players`

### Email rate limit

Supabase’s built-in sender is tiny on the free tier.

1. Auth → Providers → Email → turn **OFF** “Confirm email”.
2. Or Auth → Users → **Add user** (auto-confirm), then sign in at `/login`.

[↑ back to top](#contents)

## Architecture

Two clients, one API, one database:

```
┌─────────────────────────────────────────────────────────────┐
│                     Next.js (App Router)                     │
│   /  /login  /signup  /setup                                 │
│   /dashboard (Clips)   /dashboard/analysis                   │
└──────────────────────────▲──────────────────────────────────┘
                           │ Bearer + cookies (Supabase Auth)
              ┌────────────┴────────────┐
              │                         │
       ┌──────┴──────┐           ┌──────┴──────┐
       │   FastAPI   │           │  Supabase   │
       │  :8000      │           │ Auth · DB   │
       │ clips/comp  │◄──────────│ Storage     │
       │ profile     │  service  │ `clips`     │
       └──────▲──────┘  role     └─────────────┘
              │
       MediaPipe Pose · optional CSRT track · Gemini (optional)
```

- **Auth** — Supabase email/password. Middleware sends incomplete profiles to `/setup`.
- **Clips plane** — upload to Storage, pose job, keypoints, overlay video, clip features.
- **Role plane** — event gates → aggregate role vector → masked percentile distance vs NBA `role_vector` → named / style-only / archetype.
- **Mechanics plane** — aggregated pose features + history. Never an input to `POST /me/comp`.

## Project structure

```
frontend/                    Next.js 16 + Tailwind
  src/app/
    page.tsx                 landing
    login/ signup/ setup/    auth + profile onboarding
    dashboard/page.tsx       Clips (profile · upload · list)
    dashboard/analysis/      Role analysis + mechanics
  src/components/            clip list, upload, comps, bbox picker
  src/lib/                   API client, Supabase, profile helpers

backend/                    FastAPI
  app/api/                   clips, profile, comp, health
  app/services/
    pose_extraction.py       MediaPipe
    track.py                 gameplay box follow
    features/                shot / pass / drive mechanics
    role_profile/            gates, aggregate, pool, score, named, why
    llm.py                   optional Gemini narration
  app/scripts/               process_clip, seed_nba_players, extract_pose
  tests/                     gates, score, regressions, pose, track

supabase/migrations/         schema, profile, role-profile contracts, bbox start
design-system/hoopprint/     UI tokens / page notes
```

[↑ back to top](#contents)

## Design system

Light zinc canvas, orange wordmark (`#C2410C`), black CTAs, white cards. Clips is a three-column dashboard; Analysis is a report plus a sticky run-settings card. Tokens and page notes live in [`design-system/hoopprint/`](./design-system/hoopprint/).

## Deploy

Public URLs need Vercel + Render. Env stays in each dashboard — never commit `.env`.

### Backend → Render

1. New **Web Service**, connect the repo.
2. Docker: [`backend/Dockerfile`](./backend/Dockerfile), context `backend/` (or Blueprint [`render.yaml`](./render.yaml)).
3. Health check: `/health`.
4. Env (same names as [`backend/.env.example`](./backend/.env.example)): `ENVIRONMENT=production`, Supabase keys, `CORS_ORIGINS=https://YOUR_VERCEL_APP.vercel.app`, optional `GEMINI_API_KEY`.
5. Copy the `onrender.com` URL after first deploy.

Free Render sleeps when idle; the first request can take ~30–60s. Stay under 50MB so pose does not OOM on 512MB.

### Frontend → Vercel

1. Import the repo, **Root Directory** `frontend`.
2. Env: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_DIRECT_URL=https://YOUR_RENDER_SERVICE.onrender.com`.
3. Add the Vercel origin to Render `CORS_ORIGINS` and to Supabase Auth redirect URLs.

### Production Supabase

- Same project as local is fine for MVP.
- Storage bucket `clips` stays **50MB** on the free plan.
- Run all SQL in `supabase/migrations/` on a new project.
- Seed NBA rows once from the backend.

### Free-tier limits

| Service | What you will hit |
|---------|-------------------|
| Render free | Cold starts, 512MB RAM, sleeps when idle |
| Supabase free | Pauses after inactivity; **50MB** upload cap; Auth email quota |
| Gemini free | Daily token quota; app fails closed (why / recs JSON still saved) |
| Vercel Hobby | Fine for this Next.js app |

## Roadmap

**Shipped** — clip upload and pose, gameplay bbox + track, mechanics aggregation, gated role events, provenance-backed NBA seed, role-first named comps with height as body plausibility, profile setup, Clips / Analysis UI.

**Next**

1. **Basketball action detection.** Use pose, ball, and court tracking to detect dribbles, drives, shots, passes, cuts, screens, rebounds, and defensive movement from uploaded clips.
2. **ML role-profile model.** Aggregate those actions into an interpretable playing-style profile — on-ball creation, rim pressure, catch-and-shoot, off-ball movement, playmaking, interior activity, and defense — then classify users into probabilistic basketball archetypes.
3. **Learned NBA ranking.** Match the user’s role profile to NBA role data with a similarity model, while keeping height, wingspan, and standing reach as a separate body-plausibility layer for realistic primary comps and clearly labeled style-only references.

Nearer-term: paid Render / more RAM so 4K clips do not starve MediaPipe, a stronger event mix so rim-pressure actually ranks, a job queue if process stays on the HTTP worker, and overlay / bbox polish on smaller screens.

[↑ back to top](#contents)

## Limits

HoopPrint uses MediaPipe Pose landmarks from a **single player**. It does not directly track the ball, basket, defenders, teammates, pass target, contest level, shot result, dribble count, or full-game possession context.

Accordingly, HoopPrint:

- Does not measure true ball-release angle, ball arc, entry angle, shot distance, or make probability from pose alone.
- Does not infer assists, pass completion, turnover risk, defender pressure, or basketball IQ from a one-player clip.
- Does not use pose mechanics to compare a user with NBA shooting percentages or NBA player mechanics.
- Treats uploaded clip events as sampled evidence, not as full-game rates such as drives per game.

## Acknowledgements

- [MediaPipe](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker) — pose landmarks.
- [`nba_api`](https://github.com/swar/nba_api) — public NBA tracking and scoring endpoints.
- Supabase, Next.js, FastAPI, Tailwind.
