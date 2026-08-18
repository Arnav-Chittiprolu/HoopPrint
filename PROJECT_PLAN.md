# HoopPrint — Project Plan

Basketball playing-style analyzer + NBA **role-profile** match

Full-stack web app: upload clips over time → quality-checked clip events from pose → accumulate a **playing-style profile** → compare to **NBA role profiles** derived from public shot-type, driving, and passing statistics (cached via `nba_api`).

**Product claim (use everywhere):**

> **HoopPrint analyzes visible movement from your clips and builds a playing-style profile over time. When there is enough evidence, it compares that profile with NBA role profiles derived from public shot-type, driving, and passing statistics. It does not claim to identify your exact shooting form, predict outcomes, or measure NBA-caliber skill.**

**Status:** Phases 0–9 shipped (scaffold through deploy docs). **Phase 10** refactors the comp engine, data contracts, gates, and all user-facing copy to match the role-profile model below (supersedes the original five-slot style mapping in §5.6). Ship data model + gates first; update README and dashboard copy in the **same PR** as the new engine so legacy claims never appear alongside new scoring.

---

## 1. Product scope

### 1.1 What it does

**Two layers — always separate in UI, API, and scoring:**

1. **Mechanics report (video only)** — pose-derived movement measurements: release posture, elbow configuration, relative hand/release height, wrist-rise follow-through proxy, body-relative burst, and pass-motion descriptors. Shown with valid-clip/event counts, uncertainty, and quality badges. **Never** fed into NBA player matching.
2. **Playing-style / role profile (many clips over time)** — aggregated, **quality-checked clip events**. Each role dimension updates only when its action gate, pose-quality requirements, and event-confidence checks pass. Matched to NBA players on **public role statistics**, not joint angles.

**MediaPipe boundary:** Pose Landmarker estimates 2D/3D body landmarks only — not ball trajectory, possession events, hoop location, pass targets, or defender context. Every gate is an **inference with quality checks**, not a ground-truth basketball event.

**User flow:**

1. User fills a short **profile questionnaire** (height, position, hand, primary skill).
2. User uploads many short clips over time (max ~25s, mp4/mov, 50MB each).
3. User sets `source_type`: `individual` (solo drill) or `gameplay` (multi-person frame).
4. User sets `clip_type`: `shot` | `pass` | `drive`.
5. System extracts pose keypoints for **only the uploaded user**.
6. Pure functions compute **mechanics** features (§5.1–5.3) → mechanics card.
7. **Event gates** produce per-event records with gate decisions and rejection reasons (§5.6).
8. Valid events aggregate → **playing-style profile** with evidence tiers (§5.7).
9. NBA pool filtered by **broad position group + soft height band** (eligibility only; §5.8).
10. **Masked weighted percentile distance** on shared role dimensions only (§5.6).
11. Deterministic **why-this-match** + optional Gemini narration from stored evidence only.
12. Split recs: **mechanics_recs** (form/drill) vs **role_recs** (upload guidance, profile confidence).
13. Dashboard: overlay, mechanics panel, playing-style panel, NBA role resemblances (when established), disclosures, history.

**Evidence tiers (operational — see §5.7):**

| Tier | Requirements | UI may show | UI must not show |
|------|--------------|-------------|------------------|
| **Insufficient** | 0–2 valid events in dimension, or low quality | Mechanics observations + upload guidance | Archetype, NBA names, role-percentile claim |
| **Emerging** | ≥3 valid events; median event confidence ≥ 0.70 | Broad archetype + dimension trend | Named player comparison or ranking |
| **Established** | ≥5 valid events; ≥2 sessions when available; median confidence ≥ 0.75; bootstrap stability passes | Archetype, top 1–3 NBA **role resemblances**, why | “You play exactly like,” outcome predictions, mechanical equivalence |
| **Strong** | ≥10 valid events across sessions; stable under resampling | Specific role profile, trend history, named examples | NBA skill/athleticism claims, exact form match |

Named NBA examples require **Established** tier (not merely “5 clips uploaded”).

### 1.2 Hard constraints (never violate)

- **Single-player analysis only** — never track or analyze other people in frame.
- Gameplay: user draws **one** bbox once; CSRT (or similar) tracks that person only.
- **Two-layer separation:** mechanics (pose) and role match (NBA behavior stats) are parallel, **not interchangeable**.
- NBA examples = **public-stat role resemblances**; not biomechanical, skill-level, or outcome predictions.
- NBA comps come from **computed similarity**, never from the LLM and never from a “who do you play like?” answer.
- Questionnaire answers are **facts/context only** (filter cohort, calibrate pose). They do not pick the player.
- **Mechanics invariant:** no field from `MechanicsSummary` may be read by `build_role_vector()`, `normalize_role_vector()`, `calculate_role_similarity()`, or `select_nba_matches()`. Regression-test the role-scoring input schema for banned mechanics keys.
- **Do not map mechanics to outcomes:** release posture ≠ 3P%, elbow configuration ≠ FT%, burst ≠ drives/game without rate normalization.
- NBA numbers come from **`nba_api`** (cached seed with raw payload snapshots) — never fabricated. Store endpoint, field, denominator, season, `transform_version`, `fetched_at`.
- **Height + position filter eligibility only** — never >5–10% of final score as tie-breaker; never substitute for a role dimension.
- Only compare **role dimensions** with valid gated events; **mask** missing dimensions — never zero-fill.
- User upload counts are **sampled evidence**, not full-game rates (drives/game, pass rate, etc.).
- Compare **cohort percentiles** with documented reference populations; do not claim amateur “87th percentile” without a defined reference set (§5.6).
- **No ball, hoop, teammate, defender, or possession tracking** — disclose which inferences are therefore unavailable.
- No full-game analytics (score, possessions, team stats).
- If tracking confidence drops or box is lost → **skip segment**; low pose visibility → suppress event.
- **LLM:** may narrate deterministic stored evidence only; cannot select candidates, infer missing evidence, alter scores, or make performance claims.

### 1.3 Explicit non-goals

- Multi-object tracking / defender recognition / “good pass decision” relative to court context
- Using an LLM (or a questionnaire self-pick) to choose the NBA comp
- Fabricating stats, inventing game history, or generic coaching tips not tied to this user’s numbers
- Treating box-score shooting percentages as stand-ins for joint angles
- Implying one clip establishes season-long tendencies
- A naked “89% like Player X” without evidence tier, active dimensions, and comparison-pool disclosure
- Calling post-release wrist motion “shot arc” or implying ball-flight measurement from pose
- Claiming upload-frequency equals game-frequency for drives or passes
- Expanding pose feature set beyond §5.1–5.3 (mechanics module)

### 1.4 What we disclose to users

- MediaPipe Pose estimates **33 body landmarks** — not ball, basket, pass target, or contest level.
- Gameplay bbox = one person; no separation, teammate quality, or read quality.
- NBA public data = **on-court behavior over a season** (tracking/shot-profile stats), not joint kinematics.
- Short clips = **descriptive event measures** from uploads, not outcome prediction or NBA skill measurement.
- Named NBA comparisons appear only after **Established** evidence + stability checks; otherwise archetype only.

**Dashboard tagline:** *Understand your mechanics. Build your role profile.*

**Subheading:** *Upload short clips over time. HoopPrint analyzes visible movement and, when enough evidence is available, compares your playing-style profile with NBA role archetypes—not exact shooting form or future performance.*

### 1.5 What counts for the user

Mechanics (form) update whenever pose is good enough. **Playing-style / NBA role matching only uses clips that pass an action check.** A clip can still show form even if it does **not** count as role evidence.

**A clip counts toward role profile only if all of this is true:**

- You are clearly in frame (gameplay: the box stays on you)
- The camera is stable enough and video speed (FPS) is known (≥24)
- There are frames before and after the action
- The clip is tagged correctly (`shot` / `pass` / `drive`)
- The specific action check below passes

#### Catch readiness (shot clips)

- **Counts:** A catch or gather is visible (hands come together), then a shot release, in about **0.3–1.2 seconds**.
- **Does not count:** Form shooting with no catch; a shot that’s too slow or too instant to be a real catch-and-shoot; blurry arms; unknown video speed.
- **User sees:** “We used this clip as catch-and-shoot evidence” vs “Form measured, not used for role.”

#### Rim-pressure tendency (drive clips)

- **Counts:** A drive-like move with a clear hip burst in the first **~150–200 ms**.
- **Does not count:** Standing still, walking, a tiny step, lost tracking, unknown FPS.
- **Upload ≠ game rate:** Twenty drive clips means those uploads were drive-like — not that you drive twenty times a game.
- **User sees:** “Drive-like action detected” vs “Not enough movement to count as a drive.”

#### Playmaking orientation (pass clips)

- **Counts:** Clear pass-like arm releases. A *tendency* needs **at least 3 valid pass events** (across clips), not one wave of the arm.
- **Does not count:** A single pass sample (mechanics only). We cannot see who you passed to or if it was completed.
- **User sees:** “Pass-like action recorded” vs “Need more passing clips before this dimension is used.”

#### What to expect on the dashboard

| Situation | What counts | What they see |
|-----------|-------------|----------------|
| 1–2 valid actions of one type | Mechanics only | Form numbers + “upload more of this action” |
| 3–4 valid actions | That dimension starts counting | Archetype label, no NBA name |
| 5+ valid actions, stable, **≥2 different dimensions** | Role comparison allowed | Named NBA role resemblance + why |
| Gate failed | Nothing for role | Still see mechanics if pose worked |

**Never claimed from a clip:** make/miss, true ball arc, “you drive as often as Player X,” “you shoot like Steph.”


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
| `clip_events` | clip_id, event_type, gate_passed, rejection_reason, feature values, quality JSONB, fps, burst_window_ms — **Phase 10** |
| `user_profiles_agg` | user_id, feature_name, value, clip_count, updated_at — **mechanics agg only** |
| `user_role_profile` | per-dimension values, percentiles, event/session counts, confidence, stability, status enums, `active_dimensions`, `quality_summary`, `profile_version` — **Phase 10** (§4.4) |
| `nba_players` | player_id, season, position_group, height, rate fields, `role_vector`, `cohort_percentiles`, `raw_source`, `transform_version`, `seeded_at` — **Phase 10** (§4.5) |
| `comp_results` | auditable snapshot: `user_role_profile_id`, cohort definition, dimension contributions, archetype, candidates, evidence tier, stability metrics, `disclosure_version`, split recs — **Phase 10** (§4.6) |

### 4.4 `user_role_profile` (Phase 10)

Store raw evidence, aggregates, and status **per dimension** — do not overwrite without versioning.

Key fields per dimension (`catch_readiness`, `rim_pressure`, `playmaking`):

- `*_value`, `*_percentile` (only when reference population documented)
- `*_event_count`, `*_session_count`
- `*_confidence`, `*_stability`
- `*_status`: `not_observed` | `insufficient` | `emerging` | `established` | `suppressed_low_quality`

Plus: `profile_version`, `reference_population_version`, `active_dimensions` JSONB, `quality_summary` JSONB, timestamps.

Evidence variables (computed): `dimension_event_count`, `dimension_session_count`, `median_event_confidence`, `event_confidence_iqr`, `dimension_stability_score`, `active_feature_count`, `cohort_size`, `nba_stat_sample_reliability`.

### 4.5 `nba_players` seed lineage (Phase 10)

Do not store only `role_vector`. Persist:

- Raw numerators/denominators: `catch_shoot_fga`, `pull_up_fga`, `catch_shoot_share`, `drives`, `touches`, `drives_per_touch`, `rim_attempt_share` (restricted-area proxy — see §5.6), `passes`, `potential_assists`, `passes_per_touch`, `potential_assists_per_pass`, `assist_pct`
- `role_vector` JSONB, `cohort_percentiles` JSONB
- `raw_source` JSONB: endpoint name, params, field names, season, season_type, `fetched_at`
- `transform_version`, minimum minutes/possessions eligibility flags

`nba_api` maps NBA.com endpoints that can change without notice — cache raw payloads and version every transform.

### 4.6 `comp_results` audit snapshot (Phase 10)

Persist so historical results remain explainable after seed or algorithm changes:

- `user_role_profile_id`, `profile_version`, `nba_seed_version`
- `cohort_definition`, `active_dimensions`, `excluded_dimensions`
- `dimension_contributions`, `candidate_results`, `archetype_result`
- `evidence_tier`, `stability_metrics`, `disclosure_version`
- `mechanics_recs`, `role_recs` (separate arrays)
- `comparison_mode: "role_profile_v1"` on API responses

### 4.2 Clip status machine

`uploaded` → `awaiting_bbox` (gameplay only) → `processing` → `done` | `failed`

### 4.3 RLS

Every user-owned row: `auth.uid() = user_id` (or ownership via `clips.user_id`). Service role used only on the FastAPI backend for processing.

---

## 5. Feature set

**Mechanics module (§5.1–5.3):** fixed list — do not expand. Used for the **mechanics card only**; not inputs to NBA role matching (§5.6).

Each mechanics feature is a **pure function**: `keypoints[] → float`. Unit-test each against ≥1 manually verified clip.

### 5.1 Shooting (`clip_type = shot`) — mechanics only

- Release posture / release angle (forearm at estimated release frame)
- Elbow configuration at release
- Relative hand/release height (wrist height vs standing-body proxy in frame)
- **Wrist-rise follow-through proxy** (post-release wrist keypoint motion — **not** ball arc, apex, launch trajectory, or entry angle)

Do **not** label wrist motion as “shot arc.” Without ball tracking, true arc is unknowable.

### 5.2 Passing (`clip_type = pass`) — mechanics only

- Pass release extension (elbow angle at release)
- Release-point consistency across pass events in the clip
- Post-gather release latency (frames between catch/gather proxy and release — **only when gather proxy is reliable**)

### 5.3 Driving (`clip_type = drive`) — mechanics only

- Early body-relative burst: hip displacement in **`burst_window_ms = 150–200 ms`** (not a fixed frame count — store clip FPS alongside feature)
- Change-of-direction descriptor (when applicable)

Minimum FPS for time-based features: 24 or 30; suppress if unknown or below threshold.

### 5.4 Aggregation

**Mechanics (existing):**

- Pool **individual + gameplay** clips together by feature / category once features exist.
- Recompute `user_profiles_agg` whenever a clip finishes successfully.
- Weight display by `clip_count` and average `track_confidence` per category.

**Role profile (Phase 10):**

- Do **not** aggregate clips directly into role vector — create **`clip_events`** first.
- Only **gated valid events** contribute to each role dimension (§5.6).
- Median aggregation; IQR/MAD for variability; session count; bootstrap stability (§5.7).
- Recompute `user_role_profile` after each new valid event batch.
- `primary_skill` = **tie-breaker** only (≤5–10% of final score when top-2 within ε).

### 5.5 Profile questionnaire (facts only)

Short onboarding / settings form. **Do not** ask “which NBA player are you like?”

| Field | Values | Role |
|-------|--------|------|
| `height_in` | inches | Absolute size; calibrate pose |
| `height_z` | computed | `(height_in − 69) / 3` vs **US adult male** (~5'9", SD ~3 in). Profile display / “tall for a man” only. |
| `height_z_nba` | computed at comp time | `(height_in − NBA mean) / SD` — **not** the US male scale. League mean ~78 in (6'6"); with a stated position use that role’s NBA mean (guard ~75", wing ~78", forward ~80.5", center ~83"). Used for **height band filter** only in role matching. |
| `position` | `guard` \| `wing` \| `forward` \| `center` | **Filter** NBA pool (eligibility); choose NBA position mean for `height_z_nba` band |
| `dominant_hand` | `left` \| `right` | Which wrist/elbow to use for release/pass **mechanics** |
| `primary_skill` | `shot` \| `pass` \| `drive` | Tie-break among close role matches; suggest which clip type to upload next |

Store `height_in` / `height_z` (US male) on `profiles`. Recompute `height_z` whenever `height_in` changes. Do **not** treat US male average as NBA average.

**Height × video:** pose does not know real height. `release_height_ratio` is wrist height / standing-body height **in the frame**. With stated height:

`approx_release_height_in ≈ height_in × release_height_ratio`

Same ratio on a 5'10" user vs a 6'8" user is a different physical profile. Scale `first_step_burst` by body size (displacement in body-lengths), not raw pixels. Height **filters** the NBA pool (height band + position) using **`height_z_nba`**; it does **not** invent shooting/driving/passing mechanics — clips do.

### 5.6 Role profile space (how NBA comps actually work)

**Principle:** Compare **behavioral role resemblance**, not biomechanical clone. Mechanics (§5.1–5.3) and role matching are **parallel outputs** — never fuse release posture, wrist-rise proxy, or burst into the NBA vector.

**Why the pivot:** (1) mechanics proxies saturate on short clips, (2) height-filtered pools can be tiny, (3) mapping joint angles to shot mix produces false precision and repeated comps. Role profiles use **rate-normalized NBA tracking stats** and **gated amateur event evidence** — weaker claims, honest ones.

#### Layer A — Mechanics card (video only)

Pose features from §5.1–5.3 + history. Title: **Your mechanics**. Subtitle: *Pose-derived movement observations from your uploaded clips. These measurements are personal to your video setup and are not used for NBA comparisons.*

Badges: valid clip count, view quality, estimate confidence, **Ball not tracked**. Never: “NBA-caliber form,” “your arc,” “shooting percentage potential.”

#### Layer B — Playing-style profile (canonical Phase 10 table)

| Role dimension | What activates it | User-side evidence | NBA comparison fields | Interpretation boundary | Min display threshold |
|---|---|---|---|---|---|
| **Catch readiness** | Shot-like action with reliable catch/gather proxy + release-frame estimate; valid FPS, pose visibility, enough pre/post frames | Median catch/gather-to-release time across valid events; variability; event count | Catch-and-shoot attempt share; pull-up attempt share — **documented numerators, denominators, season, cohort** | Quick-trigger / received-shot role signal; **not** accuracy, decision quality, or self-creation | **Emerging:** 3 valid events → archetype; **Established:** 5+ stable events → player examples |
| **Rim-pressure tendency** | Drive-like event with sufficient hip displacement in time-normalized window; no severe tracking/camera failure | Count of **validated drive-like uploads**; early body-relative burst; optional COD descriptor | Drives per touch or per 100 possessions; **documented restricted-area / rim-attempt-share proxy** where sourced | Upload history reflects **detected drive-like motions**, not full-game drive rate, possession usage, athleticism, or finishing | Same as above |
| **Playmaking orientation** | ≥3 valid pass-like events (prefer gameplay); latency only when gather proxy reliable | Validated pass-event count; optional post-gather release latency; mechanics consistency stays in mechanics panel | Passes per touch; potential assists per pass/touch; AST% **secondary only** | **No** pass target, completion, assist, turnover, read quality, or potential-assist inference from one-player crop | Same as above |

**Allowed user phrasing:** *“Your uploaded clips contain repeated drive-like actions with above-median early movement burst.”*

**Not allowed:** *“You drive as often as Player X.”* NBA drives are tracking-defined (touch beginning ≥20 ft from hoop, ending within 10 ft while dribbling, excluding fast breaks) — body-only clips without hoop/ball do not prove that definition.

#### Valid event requirements (gates)

A valid event needs **all** of:

- Sufficient pose-landmark visibility
- Stable bbox/identity in gameplay mode
- Enough frames before and after estimated event
- Known or reliably inferred frame rate
- Low camera motion or compensation strategy
- Task/action classification with adequate confidence
- Event-specific validity (e.g. minimum hip displacement for drive measure)

| Gate | Rule | If fail |
|------|------|---------|
| Catch readiness | Shot + detectable catch/gather proxy before release | Mechanics only; event rejected with reason |
| Rim pressure | Drive-like sequence + burst in 150–200 ms window | Mechanics only; excluded from rim bucket |
| Playmaking | ≥3 valid pass-like events (not 2) | Mechanics sample only |
| Tracking / visibility | Confidence above threshold | Skip frames / suppress event |
| FPS | ≥24/30 for time-based catch-readiness | Suppress time-based role signal |
| Saturation | Median across events, not max per clip | Prevents one hot clip dominating |

#### 5.6.1 Role-vector contract

**User role vector** — role-dimension evidence only:

```ts
type UserRoleVector = {
  catch_readiness?: number;        // latent score from valid shot events
  rim_pressure_tendency?: number;  // latent score from valid drive events
  playmaking_orientation?: number; // latent score from valid pass events
}
```

**Mechanics summary** — separate, never read by role scoring:

```ts
type MechanicsSummary = {
  release_angle_deg?: SummaryStat;
  elbow_angle_deg?: SummaryStat;
  relative_release_height?: SummaryStat;
  wrist_rise_proxy?: SummaryStat;
  first_step_burst_body_lengths?: SummaryStat;
  pass_release_extension_deg?: SummaryStat;
  release_point_consistency?: SummaryStat;
}
```

**NBA role vector** — cohort percentiles with provenance per scalar:

```ts
type NbaRoleVector = {
  catch_readiness: number;
  rim_pressure_tendency: number;
  playmaking_orientation: number;
}
```

Persist per field: `raw_value`, `raw_numerator`, `raw_denominator`, `season`, `season_type`, `endpoint_name`, `endpoint_params`, `field_name`, `transformation_version`, `cohort_definition`, `percentile`, `sample_reliability`, `fetched_at`.

**Deprecated (Phase 5 — do not extend):** five-slot `style_vector`, mechanics→style bridges, league min-max on drives/game, `%FGA at rim` without sourced definition.

Use **“restricted-area attempt share or documented rim-attempt-share proxy, where available”** — never bare `%FGA at rim` in code or copy without stored zone definition and denominator.

#### 5.6.2 Masked weighted percentile distance

1. Filter NBA pool: broad position cohort, soft height band, minimum minutes/possessions, sufficient denominators (§5.8).
2. NBA stats → **within-cohort percentiles** (empirical CDF / rank; not league min-max).
3. User gated evidence → amateur reference percentile **only when reference population is documented**; otherwise show raw medians + “building baseline” — do not fake NBA-scale percentiles.
4. Compare only dimensions present on both sides (**mask**, never zero-fill).

\[
d(u,p)= \sqrt{ \frac{ \sum_{j \in M} w_j q_{u,j} q_{p,j} (z_{u,j}-z_{p,j})^2 }{ \sum_{j \in M} w_j q_{u,j} q_{p,j} } }
\]

- \(M\): dimensions with user valid events
- \(w_j\): predeclared weights
- \(q_{u,j}\), \(q_{p,j}\): user evidence confidence; NBA stat reliability (minutes/touches/attempts)
- \(z\): percentile → clipped normal score (not raw 0–1)

**Display separately:**

- **Similarity:** “Role resemblance” (High / Medium / Low within evidence set)
- **Confidence:** “Evidence strength” (Insufficient / Emerging / Established / Strong)

Never a naked “89% like Player X.” Prefer: *Role-profile proximity: Strong · Evidence strength: Established · Match confidence: 76/100* (with tooltip definitions).

Require **≥2 active role dimensions** + **Established** tier before named overall match. If player identity unstable but archetype stable → show archetype, suppress names.

#### Archetypes (deterministic — not LLM-generated)

Examples: `quick-trigger perimeter role`, `rim-pressure guard/wing`, `pass-oriented connector`, `balanced developing profile`. Mapped from role-vector bands; require Emerging tier minimum.

#### UI copy rules

- **Playing-style panel title:** *Your playing-style profile* — *Built from quality-checked events. Describes role tendencies, not skill level or outcomes.*
- **NBA panel title:** *NBA role resemblances* — *Similar public role-stat profiles within your comparison pool. Not shared mechanics, skill, or performance.*
- Always show: comparison pool sentence, season, active/excluded dimensions, evidence tier.
- Gemini narrates stored `why` only — never selects candidates.

Document exact field ← `nba_api` mapping in README + `nba_seed.py` with provenance.

### 5.7 Evidence system and stability

**Stability (computable — not manual judgment):**

1. Aggregate role scores from all valid events.
2. Bootstrap-resample valid events 200–500×.
3. Recompute role vector and top-\(k\) candidates.
4. Store: score SD, 80%/95% CI, top-3 overlap rate, archetype agreement rate.

```text
stable = (
  event_count >= 5
  AND bootstrap_dimension_sd <= 0.12
  AND top_3_overlap_rate >= 0.60
  AND active_role_dimensions >= 2
)
```

If bootstrap fails stability → suppress named players; show archetype + “keep building your profile.”

### 5.8 Height and position policy

**Position:** user-reported; broad groups (`guard`, `wing`, `forward`, `center`); widen to adjacent group only when cohort too small — **with UI disclosure**.

**Height:** soft eligibility band; default ±3 in; expand to ±5 in only for minimum viable pool; **≤5–10% tie-breaker max**; never a role dimension.

| Stage | Position cohort | Height rule | Use |
|---|---|---|---|
| 1 | Same broad group | ±3 in | Default |
| 2 | Same broad group | ±5 in | Pool too small |
| 3 | Adjacent broad group | ±4–5 in | Disclosure required |
| 4 | — | — | Archetype only; no named match |

Results must show: *“Comparison pool: guards and wings within 5 inches of your reported height, using [season] public NBA role statistics.”*

### 5.9 Recommendations (mechanics vs role — never conflate)

**Mechanics rec (allowed):** cite feature value, uncertainty, valid clip count, video limits, drill/recording instruction. **No NBA player reference** in match context.

Example: *“Across six valid shot clips, your estimated release posture varied more than your personal baseline. Film a side-view stationary shooting drill.”*

**Mechanics rec (forbidden):** *“Raise your release angle to become more like Player X.”*

**Role rec (allowed):** which dimensions have evidence, which upload types improve confidence, what NBA profile describes at role level. **No outcome claims.**

Example: *“Your evidence is most consistent with a quick-trigger, off-ball shooting orientation. Upload more gameplay clips with catches before shots.”*

**Role rec (forbidden):** *“Take more catch-and-shoot threes because you match Player X.”*

### 5.10 Wording contract (plan ↔ product)

| Avoid | Use instead |
|---|---|
| “Release angle, elbow, arc, burst, pass form” | Release posture, elbow configuration, relative release height, wrist-rise proxy, body-relative burst, pass-motion descriptors |
| “Gated visible actions” | Quality-checked, validated clip events |
| “Drive frequency + burst” | Repeated validated drive-like event evidence + early body-relative burst; uploads ≠ game frequency |
| “Pass rate, decision speed” | Repeated valid pass-event evidence + optional post-gather release timing |
| “%FGA at rim” | Documented restricted-area / rim-attempt-share proxy, where available |
| “C&S vs pull-up mix” | Catch-and-shoot and pull-up attempt shares with documented numerator, denominator, season, cohort |
| “5+ clips, stable signal” | 5+ valid events, preferably 2+ sessions, defined confidence + bootstrap stability |
| “NBA comps = role resemblance” | NBA examples are public-stat role resemblances; not biomechanical, skill, or outcome predictions |

---

## 6. Core pipeline

```
Questionnaire → profiles (height, position, primary_skill)
Upload (many clips over time) → Storage + clips row
  → [gameplay: bbox + CSRT track + confidence skip]
  → MediaPipe Pose (sampled frames; crop if gameplay)
  → Mechanics features (§5.1–5.3) → user_profiles_agg
  → Event gates → clip_events (pass/fail + rejection reason)
  → Aggregate valid events → user_role_profile + evidence tier + stability
  → Filter NBA pool (§5.8 staged cohort)
  → Masked weighted percentile distance (§5.6.2)
  → Archetype OR NBA role resemblances (§5.7 tiers)
  → Why breakdown (deterministic) + optional Gemini narration
  → mechanics_recs + role_recs (separate)
  → Persist comp_results (versioned audit snapshot)
```

**Rule:** verify each stage on **individual** clips first (no tracker), then add gameplay.
`nba_api` is a **seed/cache** pipeline with raw payload storage — not a live call per upload.

**Implementation note:** Phases 5–8 currently use legacy five-slot `style_vector`. Phase 10 replaces scoring, data contracts, and all user-facing copy; **disable legacy engine** from writing production `comp_results` at cutover (internal feature-flag only if retained temporarily).

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

### Phase 5 — NBA player database + comp engine *(legacy — superseded by Phase 10)*

**Goal:** Real comps from real tracking/shot-profile/bio; no hardcoding of “you are like X”; no joint-angle ↔ shooting-% mapping.

**Shipped (legacy):** Five-slot `style_vector` with cosine similarity; mechanics proxies (`release_angle`, `shot_arc`, etc.) incorrectly bridged into style slots. Known issues: saturation, tiny height-filtered pools, repeated comps. **Do not extend this model** — Phase 10 replaces it per §5.6.

#### 5.1 Seed pipeline

- [x] Script using `nba_api` to pull **all** current NBA players (full roster, not a curated subset)
- [x] Store position, listed `height_in`, `raw_stats` (tracking, shot dashboard, bio — not used as fake pose)
- [x] Build `style_vector` on the old five slots *(legacy)*
- [x] Document mapping in README *(to be rewritten in Phase 10)*

#### 5.2 Similarity *(legacy)*

- [x] Build user style vector from questionnaire + pose agg
- [x] Filter pool: same `position` and height band
- [x] Cosine on style vectors; size term; `primary_skill` weight
- [x] Return top 1–3 overall + per-category matches
- [x] Persist `comp_results`

#### 5.3 API

- [x] `POST /me/comp` or auto-run after agg update (require questionnaire height + position)
- [x] `GET /me/comp` — latest matches + scores (mechanics vs style clearly labeled)

**Exit criteria (legacy):** Same inputs → same top matches; no LLM involved; short guard ≠ tall center.

---

### Phase 6 — Why-this-match explanation + personalized recs (Gemini)

**Goal:** Every **role match** must answer: (1) *why this player resembles your playing style*, (2) *what should I do next that is specific to me*. Mechanics recs stay separate from role recs. LLM never chooses the match.

#### 6.1 Deterministic “why this match” (required; no LLM)

Attach a `why` object on each archetype / role match before any LLM call:

- Filter: `position`, `height_in` vs NBA listed height, band width
- Score terms: masked percentile distance on **role dimensions** (§5.6), not mechanics
- Dimension overlap: for each active role dim, user percentile, NBA percentile, gap, contribution rank
- Evidence: gated clip counts per dimension; which dimensions omitted; overall confidence
- Explicit label: **role resemblance**, not identical motion / not joint-angle match

Same inputs → same `why`. Unit-test: `why` must never cite `release_angle` ↔ 3P% or `elbow_angle` ↔ FT%.

#### 6.2 Personalized recs from data (not generic tips)

Build a rec candidate list **from numbers**, then let Gemini phrase only those candidates.

Sources:

| Signal | How it becomes a rec |
|--------|----------------------|
| **Mechanics** (separate section) | e.g. low `shot_arc` on n shot clips → follow-through drill citing those values |
| User role dim vs **this match** | largest percentile gaps on catch-readiness / rim-pressure / playmaking |
| User vs **position cohort** | percentile of user’s role signals among seeded players at same `position` + height band |
| Missing evidence | “Upload 3+ gated drive clips to score rim pressure” — not fake drive advice |

Each rec: `target`, `current_value`, `reference`, `action`, `because`. Cap 3. Drop recs requiring dimensions with no gated clips.

**Phase 10 update:** Split rec output into `mechanics_recs` and `role_recs` in `comp_results.matches`.

#### 6.3 Provider abstraction

- [x] `LLMProvider` interface: `generate(prompt) → str`
- [x] `GeminiProvider` (default)
- [x] Stub hooks for Anthropic / OpenAI (env-switched, not required for MVP)

#### 6.4 Prompt template

Must include:

- Questionnaire context (`height_in`, `position`, primary skill)
- User **mechanics** values + clip counts (separate block)
- User **role profile** + per-dimension clip counts + confidence
- Matched player role stats + `why` breakdown from §6.1
- Ranked rec candidates from §6.2
- Explicit instruction: *Role match = playing-style resemblance from visible actions vs NBA tracking data. Mechanics = form from video only. Do not conflate them. Do not invent statistics or say the user’s elbow angle equals a shooting percentage.*

Ask for structured output:

1. **Why this match** — 1–2 short paragraphs walking through filter + top overlapping / differing slots
2. **Personalized next steps** — 2–3 bullets, each citing a candidate’s `current_value` / `reference`

#### 6.5 Output + storage

- [x] Persist `why` + `recommendations` JSON on `comp_results.matches` (usable even if LLM fails)
- [x] Store Gemini narration on `comp_results.summary` (or split `explanation` / `recs_text`)
- [x] Fail closed if LLM returns empty / errors (comp + why + numeric recs still valid)

**Exit criteria:** Same match always produces the same `why` JSON; summary only mentions numbers in the prompt; changing `shot_arc` or height changes both the explanation and the rec list in a smoke test; a user with only shot clips never gets drive drills.

---

### Phase 7 — Gameplay path (bbox + tracking)

**Goal:** Multi-person footage works with single-object tracking only.

#### 7.1 First frame + bbox

- [x] `GET /clips/{id}/first-frame` → JPEG
- [x] Frontend: draw rectangle on first frame
- [x] `POST /clips/{id}/bbox` → save `player_boxes`, kick processing

#### 7.2 Tracker

- [x] Init OpenCV CSRT (or similar) with bbox
- [x] Track frame-to-frame
- [x] Confidence / lost-box check: if low for N consecutive frames → skip those frames
- [x] Never invent a second tracked person

#### 7.3 Pose on crop

- [x] Crop (or mask) to tracked box before MediaPipe
- [x] Store `track_confidence` with keypoints
- [x] Reuse Phases 3–6 unchanged downstream

**Exit criteria:** One gameplay clip with manual bbox produces keypoints only for the boxed player; when tracker is intentionally lost, skipped frames have no keypoints (or are marked skipped).

---

### Phase 8 — Dashboard UI

**Goal:** Polished per-user results — only after Phases 1–7 work via API.

#### 8.1 Results page

- [x] Video + keypoint overlay visualization
- [x] Feature breakdown charts (**mechanics** from video)
- [x] NBA comp card *(legacy copy — Phase 10: role profile + archetype / named match)*
- [x] **Why this match** — filter + dimension gaps from Phase 6 `why` JSON, plus Gemini narration
- [x] **Personalized recs** — mechanics + role recs with this user’s values
- [x] Mechanics summary (pose features; not claimed as NBA joint angles)
- [x] LLM writeup (explanation + recs; hide gracefully if summary is null)

**Phase 10 UI updates (ship with engine — same PR):**

- [ ] Tagline: *Understand your mechanics. Build your role profile.* + subheading (§1.4)
- [ ] Per-clip “counts / doesn’t count” copy from §1.5 (catch-and-shoot evidence vs form-only; drive-like vs not a drive; pass recorded vs need more)
- [ ] **Your mechanics** panel — separate from playing-style; badges: valid clips, view quality, confidence, “Ball not tracked”
- [ ] **Your playing-style profile** panel — dimension cards with microcopy from §5.6
- [ ] **NBA role resemblances** panel — pool disclosure, season, evidence tier, excluded dimensions
- [ ] Low-evidence state: *Keep building your profile* (§5.6) — no weak NBA name
- [ ] Remove legacy “style vector,” cosine %, mechanics-driven NBA copy

#### 8.2 History

- [x] Chart / list of how aggregated features change as clips are added

#### 8.3 UX polish

- [x] Status polling while `processing`
- [x] Clear errors for failed clips / lost tracking
- [x] Mobile-usable upload + bbox
- [x] Profile questionnaire (height, position, role) before first comp

**Exit criteria:** Full happy path in browser for individual and gameplay, without using API clients manually. ✓

---

### Phase 9 — Hardening + deploy

**Goal:** Free-tier production deploy with documented limits and scale path.

#### 9.1 Hardening

- [x] Clip size/duration enforcement
- [x] Idempotent reprocess
- [x] Structured logging for pose/track failures
- [x] Rate-limit expensive process endpoint per user (simple)

#### 9.2 Deploy

- [x] Frontend → Vercel *(config + README; deploy from your account)*
- [x] Backend → Render (Docker with MediaPipe + OpenCV) *(Dockerfile + `render.yaml`)*
- [x] Production Supabase env vars *(documented)*
- [x] Gemini API key on Render *(documented)*

#### 9.3 Docs

- [x] README: setup, env, local run, deploy
- [x] Free-tier limits (Render cold starts, Supabase pauses, Gemini quota)
- [x] Scale checklist: paid Render CPU → Supabase Pro → Gemini paid or Claude/OpenAI via `LLM_PROVIDER`

**Exit criteria:** Signup → upload → results works locally; production URLs after you set env on Vercel/Render. ✓

---

### Phase 10 — Role-profile pivot *(current priority)*

**Goal:** Replace legacy cosine matching with honest role-profile comps per §5.6–5.10. Data contracts and gates **before** scoring; README + dashboard copy in the **same PR** as engine cutover.

**Implement in this order:**

#### 10.1 Data contracts + migration *(first)* ✓

- [x] `clip_events` table — `supabase/migrations/20260817220000_phase10_role_profile_data_contracts.sql`
- [x] `user_role_profile` with per-dimension status enums (§4.4)
- [x] `nba_players` provenance fields + rate columns (§4.5)
- [x] `comp_results` audit snapshot fields (§4.6)
- [x] `profile_version`, `nba_seed_version`, `transform_version`, `reference_population_version` constants — `backend/app/services/role_profile/constants.py`
- [x] Pydantic contracts + DB mappers — `backend/app/models/role_profile.py`, `backend/app/services/role_profile/db.py`
- [x] Supabase client stubs — `insert_clip_events`, `upsert_user_role_profile`, extended `insert_comp_result`
- [x] Unit tests — `backend/tests/test_role_profile_contracts.py`
- [x] Migration plan from legacy `style_vector`; keep read-only until cutover (SQL comments + `comparison_mode` default `legacy_style`)

**Apply migration:** run `supabase/migrations/20260817220000_phase10_role_profile_data_contracts.sql` in Supabase SQL Editor (or `supabase db push` if linked).

#### 10.2 Gates + event records *(before aggregation)* ✓

- [x] Per-event records: `clip_events` with gate decision, `rejection_reason`, signal values, quality metadata
- [x] Catch/gather-to-release gate (FPS-aware, 0.3–1.2s) — `role_profile/gates.py`
- [x] Drive-like gate (`burst_window_ms` 150–200, time-normalized hip burst)
- [x] Pass gate: one record per elbow peak; extension + visibility checks
- [x] Wired into `clip_processor` after mechanics extraction (persists on process; fails open on DB error)
- [x] Gate tests — `tests/test_role_profile_gates.py` (18 tests with contracts)

**Rejection reasons:** `low_track_confidence`, `low_pose_visibility`, `missing_fps`, `no_catch_proxy`, `catch_timing_out_of_range`, `insufficient_pre_post_window`, `no_drive_onset`, `insufficient_hip_displacement`, `no_pass_release`, `no_release_frame`

**Note:** Playmaking **dimension** needs ≥3 valid events across uploads (Phase 10.3). Single pass clip may record events that fail or pass individually.

#### 10.3 Aggregation + confidence ✓

- [x] Median aggregation; IQR/MAD variability; session count — `role_profile/aggregate.py`
- [x] Bootstrap stability of dimension latents (SD, 80% CI, band agreement; `stable` if n≥5 and SD≤0.12)
- [x] Evidence tier + per-dimension status (`not_observed` → `established` / `suppressed_low_quality`)
- [x] Role vector from gated latents only (no mechanics keys; percentiles stay null until a reference population exists)
- [x] Wired into `clip_processor` after `clip_events` persist → upsert `user_role_profile`
- [x] Tests — `tests/test_role_profile_aggregate.py`

**Named NBA matches still wait for Phase 10.5.** Overall `established` / `strong` requires **≥2 active dimensions**. One deep dimension stays `emerging` at the profile level.

#### 10.4 Re-seed NBA data ✓

- [x] Cache **raw endpoint payloads** per player (`raw_stats` + `raw_source` provenance)
- [x] Derive rates from documented numerators/denominators (drives/touch, C&S share, passes/touch, potential assists/touch) — `role_profile/nba_transform.py`
- [x] Rim proxy: drives/touch when touches exist; otherwise documented `PCT_PTS_PAINT` paint-points share (not unsourced `%FGA at rim`)
- [x] Cohort percentiles after eligibility filter (minutes/GP minimum)
- [x] Deprecate `style_vector` writes (seed stores `{}`)

Re-seed after deploy: `cd backend && PYTHONPATH=. python -m app.scripts.seed_nba_players`. Comp also hydrates role vectors in memory from cached `raw_stats` if `role_vector` is empty.

#### 10.5 Scoring + comp engine (§5.6.1–5.6.2) ✓

- [x] `build_role_vector()` — banned mechanics keys; schema regression tests
- [x] Masked weighted distance; no zero-fill
- [x] Staged height/position pool (§5.8)
- [x] Deterministic archetypes from role-vector bands
- [x] Named matches only at **Established** + stability
- [x] `comparison_mode: "role_profile_v1"` on API responses
- [x] Split `mechanics_recs` vs `role_recs`
- [x] **Disable legacy engine** from production `comp_results` (`POST /me/comp` → `run_role_comp`)

#### 10.6 Frontend + README *(same PR as 10.5)* ✓

- [x] README opening, Limits, How NBA comparisons work, Data provenance (see README template in repo)
- [x] Dashboard copy per §5.6, §1.4, Phase 8 checklist
- [x] Remove all legacy style-vector / cosine / form-match language from dashboard + landing

#### 10.7 Tests *(non-negotiable regressions)*

```text
test_role_vector_excludes_release_angle ✓
test_role_vector_excludes_elbow_angle ✓
test_role_vector_excludes_release_height ✓
test_role_vector_excludes_wrist_rise_proxy ✓
test_role_vector_excludes_pass_release_extension ✓
test_role_vector_excludes_release_consistency ✓
test_no_valid_action_means_no_role_dimension ✓
test_low_pose_visibility_suppresses_event ✓
test_missing_fps_suppresses_time_based_catch_readiness ✓
test_insufficient_events_returns_archetype_or_no_comp_not_player_name ✓
test_named_matches_require_established_evidence ✓
test_active_dimensions_are_masked_not_zero_filled ✓
test_height_and_position_only_filter_or_tiebreak_not_primary_similarity ✓
test_nba_seed_requires_provenance_and_denominator ✓
test_identical_role_vectors_rank_identically_regardless_of_mechanics ✓
test_missing_dimension_not_penalized_as_zero ✓
test_seed_version_change_creates_new_comp_result_not_mutating_old ✓
test_pool_below_minimum_suppresses_named_match ✓
```

**Exit criteria:** Mechanics update every processed clip; role profile updates only from valid events; named NBA examples only at Established + stability; UI never implies form match or game-frequency equivalence; every named comparison traceable to gated events → aggregates → NBA source fields → cohort → deterministic score.

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
| GET | `/me/comp` | Role profile + archetype/matches + mechanics + why + recs + confidence |
| POST | `/me/comp` | Recompute role profile + matches + why + recs + summary |

All except `/health` require Supabase JWT.

---

## 9. Testing strategy

| Layer | What |
|-------|------|
| Unit | Mechanics pure functions; clip gate accept/reject (all conditions in §5.6) |
| Integration | Pose → mechanics → clip_events → role profile |
| Comp | Masked distance; identical role vectors → identical ranks regardless of mechanics |
| Regression | Banned mechanics keys in role module; `why` never maps mechanics ↔ box score |
| Stability | Bootstrap SD, top-3 overlap, archetype agreement |
| Seed | Provenance + denominator required; raw payload round-trip |
| LLM | Separate mechanics/role blocks; no candidate selection; no performance claims |
| Manual | 5+ valid events → Emerging archetype → Established named match; low-evidence suppresses names |

**Build rule:** Phase 10 ships data contracts + gates + scoring + copy together. Legacy `style_vector` must not write user-facing comps after cutover.

---

## 10. Suggested milestone order (summary)

| Phase | Name | Depends on |
|-------|------|------------|
| 0 | Scaffold + Auth + Schema | — |
| 1 | Upload + Storage | 0 |
| 2 | Pose (individual) | 1 |
| 3 | Features + unit tests | 2 |
| 4 | Aggregation + questionnaire | 3 |
| 5 | NBA seed + comp engine *(legacy)* | 4 |
| 6 | Why-this-match + personalized recs (Gemini) | 5 |
| 7 | Gameplay bbox + CSRT | 2–6 |
| 8 | Dashboard UI | 1–7 |
| 9 | Harden + deploy (free) | 8 |
| **10** | **Role-profile pivot** | **5–9** |

---

## 11. Scale-up path (when leaving free tier)

1. **Render paid** — eliminate cold starts; more CPU/RAM for MediaPipe.
2. **Supabase Pro** — no inactivity pause; more storage for clips.
3. **LLM** — raise Gemini tier, or set `LLM_PROVIDER=anthropic` / `openai` with the same prompt.
4. **Optional later** — async job queue (Redis/RQ) if processing blocks HTTP; CDN for video; separate worker dyno.

Architecture stays the same; only ops and keys change.