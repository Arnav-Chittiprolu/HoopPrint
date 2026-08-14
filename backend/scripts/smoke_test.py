"""Smoke test Supabase + backend integration (reads secrets from backend/.env)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def request_json(url: str, headers: dict[str, str], method: str = "GET", body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw) if raw else {"error": exc.reason}
        except json.JSONDecodeError:
            payload = {"error": raw or exc.reason}
        return exc.code, payload


def main() -> int:
    env = load_env(ENV_PATH)
    supabase_url = env["SUPABASE_URL"].rstrip("/")
    jwt_secret = env.get("SUPABASE_JWT_SECRET", "")
    service_key = env.get("SUPABASE_SERVICE_ROLE_KEY", "")
    anon_key = os.environ.get(
        "SUPABASE_ANON_KEY",
        "sb_publishable_yhyCyv1HWZcgcA_pu-o1Dg_mTNPOy5u",
    )

    results: list[tuple[str, str]] = []

    # Backend health
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5) as resp:
            health = json.loads(resp.read().decode())
        results.append(("backend_health", "ok" if health.get("status") == "ok" else "fail"))
    except Exception as exc:  # noqa: BLE001
        results.append(("backend_health", f"fail: {exc}"))

    # Frontend home
    try:
        with urllib.request.urlopen("http://127.0.0.1:3000/", timeout=5) as resp:
            results.append(("frontend_home", "ok" if resp.status == 200 else f"http {resp.status}"))
    except Exception as exc:  # noqa: BLE001
        results.append(("frontend_home", f"fail: {exc}"))

    # Profiles table (anon)
    status, payload = request_json(
        f"{supabase_url}/rest/v1/profiles?select=id&limit=1",
        {
            "apikey": anon_key,
            "Authorization": f"Bearer {anon_key}",
        },
    )
    results.append(("profiles_table_anon", "ok" if status == 200 else f"http {status}: {payload}"))

    # Profiles + storage via service role (server-side only)
    if service_key:
        status, payload = request_json(
            f"{supabase_url}/rest/v1/profiles?select=id,display_name&limit=5",
            {
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
            },
        )
        count = len(payload) if isinstance(payload, list) else 0
        results.append(("profiles_rows", f"ok ({count} rows)" if status == 200 else f"http {status}"))

        status, payload = request_json(
            f"{supabase_url}/storage/v1/bucket/clips",
            {
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
            },
        )
        results.append(
            (
                "clips_bucket",
                "ok" if status == 200 and isinstance(payload, dict) else f"http {status}: {payload}",
            )
        )

    # JWT config present
    results.append(("jwt_secret_configured", "ok" if jwt_secret else "missing"))

    # /me without token should 401
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/me", timeout=5) as resp:
            results.append(("me_unauth", f"unexpected {resp.status}"))
    except urllib.error.HTTPError as exc:
        results.append(("me_unauth", "ok (401)" if exc.code == 401 else f"http {exc.code}"))

    print(json.dumps(dict(results), indent=2))
    failed = [k for k, v in results if v.startswith("fail") or "http 4" in v or "http 5" in v or v == "missing"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
