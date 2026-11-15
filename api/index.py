"""Vercel serverless entry point: exposes the ASTRA FastAPI app (API + frontend)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.main import app as _astra  # noqa: E402

_logged = 0


async def app(scope, receive, send):
    # TEMPORARY diagnostics: log what path/headers Vercel passes through.
    global _logged
    if scope.get("type") == "http" and _logged < 5:
        _logged += 1
        hdrs = {k.decode(): v.decode()[:120] for k, v in scope.get("headers", [])
                if k.decode().startswith(("x-", "forwarded"))}
        print(f"ASTRA-DIAG path={scope.get('path')!r} raw={scope.get('raw_path')!r} "
              f"root={scope.get('root_path')!r} qs={scope.get('query_string')!r} hdrs={hdrs}",
              flush=True)
    await _astra(scope, receive, send)
