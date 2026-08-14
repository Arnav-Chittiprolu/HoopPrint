"""Debug Supabase JWT verification — run: python scripts/test_auth.py <access_token>"""
from __future__ import annotations

import sys

from app.auth import _decode_supabase_jwt, _decode_with_jwks, _verify_with_supabase_auth
from app.config import get_settings


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_auth.py <access_token>")
        return 1

    token = sys.argv[1]
    settings = get_settings()
    print("anon configured:", bool(settings.supabase_anon_key))
    print("url configured:", bool(settings.supabase_url))

    for name, fn in [
        ("supabase_auth", lambda: _verify_with_supabase_auth(token, settings)),
        ("jwks", lambda: _decode_with_jwks(token, settings)),
        ("full", lambda: _decode_supabase_jwt(token, settings)),
    ]:
        try:
            result = fn()
            print(f"{name}: OK sub={result.get('sub')}")
        except Exception as exc:
            print(f"{name}: FAIL {type(exc).__name__}: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
