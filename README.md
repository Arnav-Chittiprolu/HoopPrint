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

Phase 2 — MediaPipe pose extraction on individual clips (see PROJECT_PLAN.md).

### Phase 1 — Upload clips

Dashboard upload form → `POST /clips` → Supabase Storage + `clips` row.

- mp4/mov, max ~20s, 50MB
- Individual clips → status `uploaded`
- Gameplay clips → status `awaiting_bbox` (bbox UI in Phase 7)
