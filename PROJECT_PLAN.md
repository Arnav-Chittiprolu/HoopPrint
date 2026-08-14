# HoopPrint — Project Plan

Basketball Skill Analyzer + NBA Player Comp

Full-stack web app: upload basketball footage → biomechanical features from pose → NBA player similarity → grounded LLM summary.

**Status:** Greenfield (empty repo). Build backend pipeline end-to-end before dashboard polish.

---

## 1. Product scope

### 1.1 What it does

1. User uploads a short clip (max ~15–20s, mp4).
2. User sets `source_type`: `individual` (solo drill) or `gameplay` (multi-person frame).
3. User sets `clip_type`: `shot` | `pass` | `drive`.
4. System extracts pose keypoints for **only the uploaded user**.
5. Pure functions compute biomechanical features.
6. Features aggregate across the user’s clips over time.
7. Cosine similarity / k-NN matches the user to real NBA players (`nba_api` data).
8. Gemini produces a short summary **only from provided numbers**.
9. Dashboard shows overlay, feature charts, comp card, writeup, history.

### 1.2 Hard constraints (never violate)

- **Single-player analysis only** — never track or analyze other people in frame.
- Gameplay: user draws **one** bbox once; CSRT (or similar) tracks that person only.
- Passing quality = user’s body mechanics only (not pass outcome / teammates / defenders).
- NBA comps come from **computed similarity**, never from the LLM.
- NBA stats come from **nba_api** (or another real source) — never fabricated.
- No action recognition beyond shot / pass / drive.
- No full-game analytics (score, possessions, team stats).
- If tracking confidence drops or box is lost for several frames → **skip segment**, do not extract garbage keypoints.

### 1.3 Explicit non-goals

- Multi-object tracking / defender recognition / “good pass decision” relative to court context
- Using an LLM to pick the NBA comp
- Fabricating stats or inventing game history in the summary
- Expanding feature set beyond the list in §5

---

## 2. Tech stack (free tier → scale path)

| Layer | Choice | Free now | Scale later |
|-------|--------|----------|-------------|
| Frontend | Next.js App Router + Tailwind | Vercel Hobby | Vercel Pro |
| Backend | FastAPI (Python) + MediaPipe + OpenCV | Render free (Docker; cold starts) | Render paid / larger CPU |
| Auth | Supabase Auth (email / magic link) | Supabase free | Supabase Pro |
| DB | PostgreSQL (Supabase) | Free 500MB | Pro |
| Storage | Supabase Storage (clips) | Free 1GB | Pro / S3 later if needed |
| Pose | MediaPipe Pose | Local/self-hosted | Same |
| Tracker | OpenCV CSRT + confidence gate | — | Same |
| NBA data | `nba_api` | Free, no key | Cache in DB |
| LLM | **Google Gemini Flash** (default) | Free API quota | Gemini paid **or** Anthropic/OpenAI via provider switch |

### 2.1 Why Gemini Flash

- Best free → paid path for grounded summaries.
- Same prompt works when upgrading quota.
- Thin `LLMProvider` interface so production can set `LLM_PROVIDER=anthropic|openai` without rewriting the pipeline.
- Groq is fine as a backup free provider; Ollama is local-only (not for cloud deploy).

### 2.2 Env vars (conceptual)

```
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
DATABASE_URL=
LLM_PROVIDER=gemini
GEMINI_API_KEY=
# later:
# ANTHROPIC_API_KEY=
# OPENAI_API_KEY=
```

---

## 3. Monorepo layout

```
HoopPrint/
  PROJECT_PLAN.md          # this file
  README.md
  frontend/                # Next.js (App Router)
  backend/
    app/
      api/                 # FastAPI routers
      services/            # pose, track, features, nba, llm, aggregate
      models/              # pydantic schemas
      db/                  # Supabase / SQL helpers
    tests/
      fixtures/            # sample clips + expected feature values
    Dockerfile
    requirements.txt
  supabase/
    migrations/            # SQL schema + RLS
  docker-compose.yml       # optional local helpers
```

---

## 4. Data model

### 4.1 Tables

| Table | Purpose |
|-------|---------|
| `profiles` | `id` FK → `auth.users`, display name, timestamps |
| `clips` | user_id, source_type, clip_type, storage_path, status, timestamps |
| `player_boxes` | clip_id, normalized bbox (x,y,w,h) — gameplay only |
| `keypoints` | clip_id, frame_index, keypoints JSONB, track_confidence |
| `clip_features` | clip_id, feature_name, value, meta JSONB |
| `user_profiles_agg` | user_id, feature_name, value, clip_count, updated_at |
| `nba_players` | name, season, feature_vector JSONB, raw_stats JSONB |
| `comp_results` | user_id, matches JSONB, summary text, created_at |

### 4.2 Clip status machine

`uploaded` → `awaiting_bbox` (gameplay only) → `processing` → `done` | `failed`

### 4.3 RLS

Every user-owned row: `auth.uid() = user_id` (or ownership via `clips.user_id`). Service role used only on the FastAPI backend for processing.

---

## 5. Feature set (do not expand)

Each feature is a **pure function**: `keypoints[] → float`. Unit-test each against ≥1 manually verified clip before moving on.

### 5.1 Shooting (`clip_type = shot`)

- Release angle (forearm at release frame)
- Elbow angle at release
- Release height relative to standing height
- Shot arc estimate (wrist keypoint trajectory post-release)

### 5.2 Passing (`clip_type = pass`)

- Arm extension at release (elbow angle)
- Release point consistency across passes in the clip
- Decision speed: frames between “ball reaches hands” proxy and “release” proxy

### 5.3 Driving (`clip_type = drive`)

- First-step burst: hip keypoint displacement in first ~5 frames of movement
- Change-of-direction angle (when applicable)

### 5.4 Aggregation

- Pool **individual + gameplay** clips together by feature / category once features exist.
- Recompute `user_profiles_agg` whenever a clip finishes successfully.

---

## 6. Core pipeline

```
Upload → Storage + clips row
  → [gameplay: bbox + CSRT track + confidence skip]
  → MediaPipe Pose (sampled frames; crop if gameplay)
  → Feature functions
  → Aggregate user profile
  → Cosine similarity vs nba_players
  → Gemini grounded summary
  → Persist comp_results
```

**Rule:** verify each stage on **individual** clips first (no tracker), then add gameplay.

---

## 7. Phased build plan

Do not start a phase until the previous phase’s **exit criteria** pass.

---

### Phase 0 — Project scaffold

**Goal:** Empty repo becomes a runnable shell with auth and DB, no pipeline yet.

#### 0.1 Repo + tooling

- [x] Init git, root README pointing at this plan
- [x] `frontend/` Next.js App Router + Tailwind
- [x] `backend/` FastAPI + `requirements.txt` + Dockerfile
- [x] `.env.example` for frontend and backend
- [x] Basic CI optional (lint only) — skip if slowing MVP

#### 0.2 Supabase project

- [x] Create free Supabase project *(manual — see README)*
- [x] Write migrations for all tables in §4
- [x] Enable RLS policies *(in migration SQL)*
- [x] Create Storage bucket `clips` (private; signed URLs) *(in migration SQL)*
- [x] Enable Auth (email magic link and/or email+password) *(manual in Supabase dashboard)*

#### 0.3 Auth wiring

- [x] Frontend: Supabase client, login/signup, protected routes
- [x] Backend: verify JWT from Supabase on protected API routes
- [x] `profiles` row created on first signup (trigger or API)

#### 0.4 Health checks

- [x] `GET /health` on FastAPI
- [x] Frontend loads and can sign in against Supabase

**Exit criteria:** Two users can sign up; each sees only their empty dashboard shell; no clip processing yet. ✓

---

### Phase 1 — Upload + storage

**Goal:** Authenticated users can upload a clip; metadata lands in Postgres; file in Storage.

#### 1.1 API

- [x] `POST /clips` — multipart file + `source_type` + `clip_type`
- [x] Validate: mp4, max duration ~20s, max file size
- [x] Upload to Supabase Storage; insert `clips` row (`status=uploaded` or `awaiting_bbox`)
- [x] `GET /clips` — list current user’s clips
- [x] `GET /clips/{id}` — metadata

#### 1.2 Frontend (minimal)

- [x] Upload form (file + source_type + clip_type)
- [x] Clip list with status

**Exit criteria:** Upload an individual shot clip; row + storage object exist; list shows it.

---

### Phase 2 — Pose extraction (individual only)

**Goal:** MediaPipe Pose runs on an individual clip and stores keypoints.

#### 2.1 Service

- [x] Download clip from Storage (or stream)
- [x] Sample every 2nd–3rd frame
- [x] Run MediaPipe Pose on full frame
- [x] Persist `keypoints` rows (JSONB + frame_index)
- [x] Set clip `status=processing` → `done` / `failed`

#### 2.2 API / CLI

- [x] `POST /clips/{id}/process` (or auto-kick after upload for individual)
- [x] CLI script: `python -m app.scripts.process_clip <clip_id>` for debugging
- [x] `GET /clips/{id}/keypoints` for inspection

#### 2.3 Tests / fixtures

- [x] Commit or document one short fixture clip path for local use
- [x] Smoke test: processing produces N frames of keypoints

**Exit criteria:** One real individual clip yields inspectable keypoints JSON end-to-end via API/CLI.

---

### Phase 3 — Feature extraction (pure functions)

**Goal:** Deterministic features from keypoints; unit tests green.

#### 3.1 Shared helpers

- [ ] Angle between joints, distance, standing height proxy, release-frame heuristics
- [ ] Document assumptions (which landmark indices, units)

#### 3.2 Shot features

- [ ] `release_angle`, `elbow_angle_at_release`, `release_height_ratio`, `shot_arc`
- [ ] Unit tests with manually verified expected ranges for fixture clip

#### 3.3 Pass features

- [ ] `arm_extension_at_release`, `release_point_consistency`, `decision_speed`
- [ ] Unit tests

#### 3.4 Drive features

- [ ] `first_step_burst`, `change_of_direction_angle`
- [ ] Unit tests

#### 3.5 Persistence

- [ ] Write `clip_features` after successful extraction
- [ ] Wire into process pipeline after pose

**Exit criteria:** Each feature function has ≥1 unit test; processing an individual shot/pass/drive writes `clip_features`.

---

### Phase 4 — Multi-clip aggregation

**Goal:** User profile is the average (or agreed aggregate) of features across clips.

#### 4.1 Logic

- [ ] Aggregate by `feature_name` across all successful clips for user
- [ ] Pool individual + gameplay once features exist
- [ ] Upsert `user_profiles_agg` after each successful clip
- [ ] Store `clip_count` and `updated_at`

#### 4.2 API

- [ ] `GET /me/profile` — aggregated feature vector
- [ ] `GET /me/history` — time series of agg values (or per-clip feature history)

**Exit criteria:** Two shot clips with different release angles → agg reflects both; history endpoint returns change over time.

---

### Phase 5 — NBA player database + comp engine

**Goal:** Real comps from real stats; no hardcoding of “you are like X”.

#### 5.1 Seed pipeline

- [ ] Script using `nba_api` to pull ~20–30 well-known current players
- [ ] Map available stats → normalized feature dimensions that align with user vector
- [ ] Store `nba_players.feature_vector` + `raw_stats`
- [ ] Document mapping (which NBA stat ↔ which user feature / proxy)

#### 5.2 Similarity

- [ ] Normalize user agg vector to same dimensions
- [ ] Cosine similarity (and/or k-NN distance)
- [ ] Return top 1–3 with scores
- [ ] Persist `comp_results` (matches JSON; summary filled in Phase 6)

#### 5.3 API

- [ ] `POST /me/comp` or auto-run after agg update
- [ ] `GET /me/comp` — latest matches + scores

**Exit criteria:** Same user vector always returns same top matches; scores change when agg changes; no LLM involved.

---

### Phase 6 — Grounded LLM summary (Gemini)

**Goal:** 2–3 paragraph explanation + 2–3 tips, strictly grounded in numbers.

#### 6.1 Provider abstraction

- [ ] `LLMProvider` interface: `generate(prompt) → str`
- [ ] `GeminiProvider` (default)
- [ ] Stub hooks for Anthropic / OpenAI (env-switched, not required for MVP)

#### 6.2 Prompt template

Must include:

- User computed feature values
- Matched player real stat values
- Similarity score(s)
- Explicit instruction: *Only reference the numeric values provided below. Do not invent statistics, game history, or claims not present in this data.*

#### 6.3 Output + storage

- [ ] Parse/store summary on `comp_results`
- [ ] Fail closed if LLM returns empty / errors (comp still valid without summary)

**Exit criteria:** Summary mentions only numbers present in the prompt; changing a feature changes the advice accordingly in a smoke test.

---

### Phase 7 — Gameplay path (bbox + tracking)

**Goal:** Multi-person footage works with single-object tracking only.

#### 7.1 First frame + bbox

- [ ] `GET /clips/{id}/first-frame` → JPEG
- [ ] Frontend: draw rectangle on first frame
- [ ] `POST /clips/{id}/bbox` → save `player_boxes`, kick processing

#### 7.2 Tracker

- [ ] Init OpenCV CSRT (or similar) with bbox
- [ ] Track frame-to-frame
- [ ] Confidence / lost-box check: if low for N consecutive frames → skip those frames
- [ ] Never invent a second tracked person

#### 7.3 Pose on crop

- [ ] Crop (or mask) to tracked box before MediaPipe
- [ ] Store `track_confidence` with keypoints
- [ ] Reuse Phases 3–6 unchanged downstream

**Exit criteria:** One gameplay clip with manual bbox produces keypoints only for the boxed player; when tracker is intentionally lost, skipped frames have no keypoints (or are marked skipped).

---

### Phase 8 — Dashboard UI

**Goal:** Polished per-user results — only after Phases 1–7 work via API.

#### 8.1 Results page

- [ ] Video + keypoint overlay visualization
- [ ] Feature breakdown charts
- [ ] NBA comp card (name, score, key overlapping stats)
- [ ] LLM writeup

#### 8.2 History

- [ ] Chart / list of how aggregated features change as clips are added

#### 8.3 UX polish

- [ ] Status polling while `processing`
- [ ] Clear errors for failed clips / lost tracking
- [ ] Mobile-usable upload + bbox

**Exit criteria:** Full happy path in browser for individual and gameplay, without using API clients manually.

---

### Phase 9 — Hardening + deploy

**Goal:** Free-tier production deploy with documented limits and scale path.

#### 9.1 Hardening

- [ ] Clip size/duration enforcement
- [ ] Idempotent reprocess
- [ ] Structured logging for pose/track failures
- [ ] Rate-limit expensive process endpoint per user (simple)

#### 9.2 Deploy

- [ ] Frontend → Vercel
- [ ] Backend → Render (Docker with MediaPipe + OpenCV)
- [ ] Production Supabase env vars
- [ ] Gemini API key on Render

#### 9.3 Docs

- [ ] README: setup, env, local run, deploy
- [ ] Free-tier limits (Render cold starts, Supabase pauses, Gemini quota)
- [ ] Scale checklist: paid Render CPU → Supabase Pro → Gemini paid or Claude/OpenAI via `LLM_PROVIDER`

**Exit criteria:** Public URLs work for signup → upload → results on free tiers.

---

## 8. API surface (target)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | Public |
| POST | `/clips` | Upload |
| GET | `/clips` | List mine |
| GET | `/clips/{id}` | Detail |
| GET | `/clips/{id}/first-frame` | Gameplay |
| POST | `/clips/{id}/bbox` | Gameplay |
| POST | `/clips/{id}/process` | Kick / retry |
| GET | `/clips/{id}/keypoints` | Debug / overlay |
| GET | `/clips/{id}/features` | Per-clip features |
| GET | `/me/profile` | Aggregated features |
| GET | `/me/history` | Feature trends |
| GET | `/me/comp` | Matches + summary |
| POST | `/me/comp` | Recompute matches + summary |

All except `/health` require Supabase JWT.

---

## 9. Testing strategy

| Layer | What |
|-------|------|
| Unit | Every feature pure function + angle helpers |
| Integration | Process one fixture individual clip through pose → features → agg |
| Comp | Fixed nba_players seed → known cosine ordering for a synthetic user vector |
| LLM | Prompt snapshot test (string contains required fields); optional live Gemini smoke (skipped in CI without key) |
| Manual | One individual + one gameplay clip before Phase 8 UI |

**Build rule from brief:** Do not build the frontend dashboard until the backend pipeline works on CLI/API for at least one full example of each `source_type`.

---

## 10. Suggested milestone order (summary)

| Phase | Name | Depends on |
|-------|------|------------|
| 0 | Scaffold + Auth + Schema | — |
| 1 | Upload + Storage | 0 |
| 2 | Pose (individual) | 1 |
| 3 | Features + unit tests | 2 |
| 4 | Aggregation | 3 |
| 5 | NBA seed + cosine comp | 4 |
| 6 | Gemini grounded summary | 5 |
| 7 | Gameplay bbox + CSRT | 2–6 |
| 8 | Dashboard UI | 1–7 |
| 9 | Harden + deploy (free) | 8 |

---

## 11. Scale-up path (when leaving free tier)

1. **Render paid** — eliminate cold starts; more CPU/RAM for MediaPipe.
2. **Supabase Pro** — no inactivity pause; more storage for clips.
3. **LLM** — raise Gemini tier, or set `LLM_PROVIDER=anthropic` / `openai` with the same prompt.
4. **Optional later** — async job queue (Redis/RQ) if processing blocks HTTP; CDN for video; separate worker dyno.

Architecture stays the same; only ops and keys change.