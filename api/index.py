"""Vercel serverless entry point: exposes the ASTRA FastAPI app (API + frontend).

vercel.json rewrites every URL to this function as ``/api/index?__path=/<original>``
because the function itself only sees the rewritten path ``/api/index``. This
wrapper restores the original path (and the remaining query string) before the
request reaches FastAPI.
"""

import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.main import app as _astra  # noqa: E402

PATH_PARAM = "__path"


async def app(scope, receive, send):
    if scope.get("type") in ("http", "websocket"):
        pairs = parse_qsl(scope.get("query_string", b"").decode("latin-1"),
                          keep_blank_values=True)
        original = next((v for k, v in pairs if k == PATH_PARAM), None)
        if original is not None:
            path = "/" + original.lstrip("/")
            rest = [(k, v) for k, v in pairs if k != PATH_PARAM]
            scope = {**scope, "path": path, "raw_path": path.encode(),
                     "query_string": urlencode(rest).encode()}
    await _astra(scope, receive, send)
