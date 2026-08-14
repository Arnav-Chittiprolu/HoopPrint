# Test fixtures

Place a short individual basketball clip here for local integration tests:

- `sample_shot.mp4` — solo shooting clip, ≤25s, mp4

The file is gitignored (see repo root `.gitignore`). Unit tests generate a tiny synthetic video automatically.

Run pose smoke test:

```bash
cd backend
PYTHONPATH=. pytest tests/test_pose_extraction.py -v
```

Process a real uploaded clip via CLI (uses `backend/.env`):

```bash
cd backend
PYTHONPATH=. python -m app.scripts.process_clip <clip-uuid>
```
