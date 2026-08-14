# HoopPrint — Project Plan

Basketball Skill Analyzer + NBA Player Comp

Full-stack web app: upload basketball footage → biomechanical features from pose → profile questionnaire (height, position, role) → style-space NBA comps from tracking/shot mix (not box-score proxies) → grounded LLM summary.

**Status:** Greenfield (empty repo). Build backend pipeline end-to-end before dashboard polish.

---

## 1. Product scope

### 1.1 What it does

1. User fills a short **profile questionnaire** (height, position, hand, primary skill).
2. User uploads a short clip (max ~15–20s, mp4).
3. User sets `source_type`: `individual` (solo drill) or `gameplay` (multi-person frame).
4. User sets `clip_type`: `shot` | `pass` | `drive`.
5. System extracts pose keypoints for **only the uploaded user**.
6. Pure functions compute biomechanical features (mechanics card).
7. Features aggregate across the user’s clips over time.
8. Questionnaire + pose fuse into a **style vector**; NBA pool is filtered by height/position; cosine / k-NN vs cached `nba_api` **tracking / shot-profile / bio** (style card).
9. Gemini produces a short summary **only from provided numbers**.
10. Dashboard shows overlay, feature charts, mechanics + style comps, writeup, history.

### 1.2 Hard constraints (never violate)

- **Single-player analysis only** — never track or analyze other people in frame.
- Gameplay: user draws **one** bbox once; CSRT (or similar) tracks that person only.
- Passing quality = user’s body mechanics only (not pass outcome / teammates / defenders).
- NBA comps come from **computed similarity**, never from the LLM and never from a “who do you play like?” answer.
- Questionnaire answers are **facts/context only** (calibrate, filter, extra vector slots). They do not pick the player.
- Do **not** map pose features 1:1 onto box-score outcomes (e.g. `release_angle` ≠ 3P%, `elbow_angle` ≠ FT%). Those are different quantities.
- NBA numbers come from **`nba_api`** (or another real source) — never fabricated. Prefer tracking, shot-profile, and bio over FG%/3P%/FT% as similarity inputs.
- Height from the form is stored in inches and also as **`height_z` vs average adult male** (~69 in, SD ~3 in): short / average / tall on that scale. Use it to scale pose (absolute release height ≈ stated height × `release_height_ratio`) and to filter the NBA pool. Height does not override clip mechanics.
- Only compare categories the user has evidence for (shot clips → shooting style; no drive clips → do not use drive stats).
- No action recognition beyond shot / pass / drive.
- No full-game analytics (score, possessions, team stats).
- If tracking confidence drops or box is lost for several frames → **skip segment**, do not extract garbage keypoints.

### 1.3 Explicit non-goals

- Multi-object tracking / defender recognition / “good pass decision” relative to court context
- Using an LLM (or a questionnaire self-pick) to choose the NBA comp
- Fabricating stats or inventing game history in the summary
- Treating box-score shooting percentages as stand-ins for joint angles
- Expanding pose feature set beyond the list in §5.1–5.3

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
      services/            # pose, track, features, style, nba, llm, aggregate
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
| `profiles` | `id` FK → `auth.users`, display name, questionnaire fields (§5.5), timestamps |
| `clips` | user_id, source_type, clip_type, storage_path, status, timestamps |
| `player_boxes` | clip_id, normalized bbox (x,y,w,h) — gameplay only |
| `keypoints` | clip_id, frame_index, keypoints JSONB, track_confidence |
| `clip_features` | clip_id, feature_name, value, meta JSONB — **pose mechanics only** |
| `user_profiles_agg` | user_id, feature_name, value, clip_count, updated_at — pose mechanics agg |
| `nba_players` | name, season, position, height_in, style_vector JSONB, raw_stats JSONB |
| `comp_results` | user_id, matches JSONB (overall + per-category), summary text, created_at |

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
- Weight later comps by `clip_count` and average `track_confidence` per category.

### 5.5 Profile questionnaire (facts only)

Short onboarding / settings form. **Do not** ask “which NBA player are you like?”

| Field | Values | Role |
|-------|--------|------|
| `height_in` | inches | Absolute size; calibrate pose |
| `height_z` | computed | `(height_in − 69) / 3` vs **US adult male** (~5'9", SD ~3 in). Profile display / “tall for a man” only. |
| `height_z_nba` | computed at comp time | `(height_in − NBA mean) / SD` — **not** the US male scale. League mean ~78 in (6'6"); with a stated position use that role’s NBA mean (guard ~75", wing ~78", forward ~80.5", center ~83"). Drives style `size` + height band. |
| `position` | `guard` \| `wing` \| `forward` \| `center` | Filter NBA pool + choose NBA position mean for `height_z_nba` |
| `dominant_hand` | `left` \| `right` | Which wrist/elbow to use for release/pass features |
| `primary_skill` | `shot` \| `pass` \| `drive` | Weight that category higher in ranking |

Store `height_in` / `height_z` (US male) on `profiles`. Recompute `height_z` whenever `height_in` changes. Do **not** treat US male average as NBA average.

**Height × video:** pose does not know real height. `release_height_ratio` is wrist height / standing-body height **in the frame**. With stated height:

`approx_release_height_in ≈ height_in × release_height_ratio`

Same ratio on a 5'10" user vs a 6'8" user is a different physical profile. Scale `first_step_burst` by body size (displacement in body-lengths), not raw pixels. Height **filters** the NBA pool (height band + position) using **`height_z_nba`**; it does **not** invent shooting/driving/passing mechanics — clips do.

### 5.6 Style space (how comps actually work)

Do **not** cosine pose joints against FG%/3P%/FT%. Build two related outputs:

1. **Mechanics card** — pose features from §5.1–5.3 (and user history). No NBA joint angles exist in `nba_api`; do not pretend they do.
2. **Style card** — shared slots both sides can fill honestly:

| Style slot | From user (video + form) | From NBA (`nba_api`) |
|------------|--------------------------|----------------------|
| Size | `height_z_nba` (vs NBA / position mean) | listed height on same NBA z scale |
| Perimeter vs rim | `shot_arc` / `release_angle` (if shot clips exist) | %FGA from 3 / mid / rim, avg shot distance |
| Creation | `decision_speed` (if pass clips exist) | pull-up vs catch-and-shoot, unassisted % |
| Drive burst | `first_step_burst`, COD (if drive clips exist) | drives/game, speed, %FGA at rim |
| Passing | arm extension / consistency (if pass clips exist) | AST%, potential assists / passes (tracking) |

**Fusion / ranking**

```
eligible NBA players = same position AND listed height within band of user height_in
                     (band wider if height_z_nba is extreme vs NBA/position mean)

score = w_style * cosine(style_user, style_nba)
      + w_size  * similarity(height_in, NBA height_in)
      + primary_skill bonus if that player's profile matches primary_skill

w_style weights for shooting/passing/driving = 0 if that category has no successful clips
```

Category comps allowed: “jumper like X, driver like Y” when the user has evidence in more than one category. Overall name is optional and must be explained as **play-style**, not identical motion.

Document the exact slot ← field mapping in code comments + README when Phase 5 lands. Prefer NBA **tracking / shot dashboard / bio** over shooting percentages.

---

## 6. Core pipeline

```
Questionnaire → profiles (height_z, position, role)
Upload → Storage + clips row
  → [gameplay: bbox + CSRT track + confidence skip]
  → MediaPipe Pose (sampled frames; crop if gameplay)
  → Feature functions (mechanics) + height calibration
  → Aggregate user profile
  → Style vector (form + pose) → filter NBA pool → cosine vs nba_players.style_vector
  → Gemini grounded summary
  → Persist comp_results
```

**Rule:** verify each stage on **individual** clips first (no tracker), then add gameplay.
`nba_api` is a **seed/cache** pipeline, not a live call per upload.

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

- [x] Angle between joints, distance, standing height proxy, release-frame heuristics
- [x] Document assumptions (which landmark indices, units)
- [x] Use `profiles.dominant_hand` to pick left vs right wrist/elbow when present; default right

#### 3.2 Shot features

- [x] `release_angle`, `elbow_angle_at_release`, `release_height_ratio`, `shot_arc`
- [x] If `height_in` is set, also store `approx_release_height_in` in feature `meta` (height × ratio)
- [x] Unit tests with manually verified expected ranges for fixture clip

#### 3.3 Pass features

- [x] `arm_extension_at_release`, `release_point_consistency`, `decision_speed`
- [x] Unit tests

#### 3.4 Drive features

- [x] `first_step_burst`, `change_of_direction_angle`
- [x] Scale first-step displacement in body-lengths (not raw pixels) when standing-height proxy / `height_in` exists
- [x] Unit tests

#### 3.5 Persistence

- [x] Write `clip_features` after successful extraction
- [x] Wire into process pipeline after pose

**Exit criteria:** Each feature function has ≥1 unit test; processing an individual shot/pass/drive writes `clip_features`.

---

### Phase 4 — Multi-clip aggregation + profile questionnaire

**Goal:** User profile is the average of pose features across clips, plus stored questionnaire context.

#### 4.1 Logic

- [x] Aggregate by `feature_name` across all successful clips for user
- [x] Pool individual + gameplay once features exist
- [x] Upsert `user_profiles_agg` after each successful clip
- [x] Store `clip_count` and `updated_at`

#### 4.2 Questionnaire

- [x] Migration: add questionnaire columns on `profiles` (§5.5)
- [x] Compute `height_z = (height_in − 69) / 3` on write
- [x] `GET` / `PATCH /me/profile` — display name + questionnaire
- [x] Frontend: short onboarding form (required before first comp; optional before upload)

#### 4.3 API

- [x] `GET /me/profile` — questionnaire + aggregated feature vector
- [x] `GET /me/history` — time series of agg values (or per-clip feature history)

**Exit criteria:** Two shot clips with different release angles → agg reflects both; history endpoint returns change over time; user can save height/position and `height_z` is stored.

---

### Phase 5 — NBA player database + style-space comp engine

**Goal:** Real comps from real tracking/shot-profile/bio; no hardcoding of “you are like X”; no joint-angle ↔ shooting-% mapping.

#### 5.1 Seed pipeline

- [x] Script using `nba_api` to pull **all** current NBA players (full roster, not a curated subset)
- [x] Store position, listed `height_in`, `raw_stats` (tracking, shot dashboard, bio — not used as fake pose)
- [x] Build `style_vector` on the shared slots in §5.6 (size, perimeter vs rim, creation, drive, passing)
- [x] Document mapping (which NBA field fills which style slot) in README

#### 5.2 Similarity

- [x] Build user style vector from questionnaire + pose agg (skip slots with no clip evidence)
- [x] Filter pool: same `position` and listed height within band of `height_in` (use `height_z` to explain short vs tall vs average man)
- [x] Cosine on style vectors; optional size term; `primary_skill` weight
- [x] Return top 1–3 overall **and** per-category matches when that category has clips
- [x] Persist `comp_results` (matches JSON; summary filled in Phase 6)

#### 5.3 API

- [x] `POST /me/comp` or auto-run after agg update (require questionnaire height + position)
- [x] `GET /me/comp` — latest matches + scores (mechanics vs style clearly labeled)

**Exit criteria:** Same inputs always return same top matches; changing height/position or agg changes scores; no LLM involved; a synthetic short guard does not match a much taller center.

---

### Phase 6 — Grounded LLM summary (Gemini)

**Goal:** 2–3 paragraph explanation + 2–3 tips, strictly grounded in numbers.

#### 6.1 Provider abstraction

- [ ] `LLMProvider` interface: `generate(prompt) → str`
- [ ] `GeminiProvider` (default)
- [ ] Stub hooks for Anthropic / OpenAI (env-switched, not required for MVP)

#### 6.2 Prompt template

Must include:

- Questionnaire context (`height_in`, `height_z` interpretation, position, primary skill)
- User computed pose feature values (mechanics)
- Matched player real tracking / shot-profile / bio values (style)
- Similarity score(s) and whether the match is style vs mechanics
- Explicit instruction: *Only reference the numeric values provided below. Do not invent statistics, game history, or claims not present in this data. Do not say the user’s elbow angle equals a shooting percentage.*

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
- [ ] Feature breakdown charts (mechanics from video)
- [ ] NBA **style** comp card (name, score, overlapping shot mix / tracking / height)
- [ ] Mechanics summary (pose features; not claimed as NBA joint angles)
- [ ] LLM writeup

#### 8.2 History

- [ ] Chart / list of how aggregated features change as clips are added

#### 8.3 UX polish

- [ ] Status polling while `processing`
- [ ] Clear errors for failed clips / lost tracking
- [ ] Mobile-usable upload + bbox
- [ ] Profile questionnaire (height, position, role) before first comp

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
| GET | `/me/profile` | Questionnaire + aggregated pose features |
| PATCH | `/me/profile` | Update questionnaire / display name |
| GET | `/me/history` | Feature trends |
| GET | `/me/comp` | Style + category matches + summary |
| POST | `/me/comp` | Recompute matches + summary |

All except `/health` require Supabase JWT.

---

## 9. Testing strategy

| Layer | What |
|-------|------|
| Unit | Every feature pure function + angle helpers |
| Integration | Process one fixture individual clip through pose → features → agg |
| Comp | Filtered NBA seed + known ordering for a synthetic short guard vs tall center; no 3P%↔release_angle mapping |
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
| 4 | Aggregation + questionnaire | 3 |
| 5 | NBA seed + style-space comp | 4 |
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