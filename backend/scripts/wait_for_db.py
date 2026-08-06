"""Block until the database accepts connections.

Railway's private network (``*.railway.internal``) is IPv6-only and its DNS is
not resolvable for the first few seconds of a container's life. Running
``alembic upgrade head`` as the container's first action loses that race — the
deploy dies with "failed to resolve host" and then crash-loops, because every
restart lands in the same window.

Waiting here turns that hard failure into a few seconds of startup delay. A
genuinely wrong host or credential still fails, but after the timeout and with a
readable message rather than a SQLAlchemy traceback.
"""

from __future__ import annotations

import sys
import time

from sqlalchemy import create_engine, text

from app.config import get_settings

TIMEOUT_SECONDS = 90
RETRY_SECONDS = 2


def main() -> int:
    # get_settings() normalises postgres:// and postgresql:// onto the psycopg
    # driver, so this uses the exact URL Alembic and the app will use.
    url = get_settings().database_url

    # An unresolved Railway reference arrives verbatim, braces and all; one that
    # points at a missing variable arrives empty. Both die deep inside
    # SQLAlchemy's URL parser, so catch them here where the cause is obvious.
    if not url.strip():
        print(
            "DATABASE_URL is empty.\n"
            "In Railway this usually means a reference variable resolved to "
            "nothing — the service name matched but the variable it points at "
            "does not exist. Set DATABASE_URL on the backend *service* itself "
            "rather than in shared project variables, using the Variables tab's "
            "'Add Reference' button.",
            file=sys.stderr,
        )
        return 1

    if "${{" in url:
        print(
            "DATABASE_URL contains an unresolved variable reference:\n"
            f"  {url}\n"
            "The service name in the reference does not match any service in "
            "this Railway project. Re-add the variable with the Variables tab's "
            "'Add Reference' button so the name is filled in exactly.",
            file=sys.stderr,
        )
        return 1

    engine = create_engine(url, pool_pre_ping=True)
    deadline = time.monotonic() + TIMEOUT_SECONDS
    attempt = 0
    last_error: Exception | None = None

    try:
        while time.monotonic() < deadline:
            attempt += 1
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
            except Exception as exc:
                last_error = exc
                print(
                    f"Attempt {attempt}: database not ready "
                    f"({exc.__class__.__name__}); retrying in {RETRY_SECONDS}s.",
                    flush=True,
                )
                time.sleep(RETRY_SECONDS)
            else:
                print(f"Database reachable after {attempt} attempt(s).", flush=True)
                return 0
    finally:
        engine.dispose()

    print(
        f"Database unreachable after {TIMEOUT_SECONDS}s. Last error: {last_error}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
