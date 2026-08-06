"""Block until the database accepts connections.

Railway's private network (``*.railway.internal``) is IPv6-only and its DNS is
not resolvable for the first few seconds of a container's life. Running
``alembic upgrade head`` as the container's first action loses that race — the
deploy dies with "failed to resolve host" and then crash-loops, because every
restart lands in the same window.

Waiting here turns that hard failure into a few seconds of startup delay. Three
attempts are made, each capped at a 60-second connection timeout. A genuinely
wrong host or credential still fails, but with a readable message rather than a
SQLAlchemy traceback.
"""

from __future__ import annotations

import sys
import time

from sqlalchemy import create_engine, text

from app.config import get_settings

MAX_ATTEMPTS = 3
CONNECT_TIMEOUT_SECONDS = 60
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
            "In Railway this means a reference variable resolved to nothing — "
            "the service name matched but the variable it points at does not "
            "exist. Railway's Postgres template exposes DATABASE_PRIVATE_URL "
            "and (only once public access is enabled) DATABASE_PUBLIC_URL. "
            "There is no plain DATABASE_URL to reference. Set:\n"
            "  DATABASE_URL=${{ Postgres.DATABASE_PRIVATE_URL }}",
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

    # connect_timeout caps each individual attempt. Without it a black-holed
    # host hangs on the TCP handshake until the kernel gives up, which is far
    # longer than 60s and would stall the deploy rather than fail it.
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )
    last_error: Exception | None = None

    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
            except Exception as exc:
                last_error = exc
                print(
                    f"Attempt {attempt}/{MAX_ATTEMPTS}: database not ready "
                    f"({exc.__class__.__name__}).",
                    flush=True,
                )
                if attempt < MAX_ATTEMPTS:
                    time.sleep(RETRY_SECONDS)
            else:
                print(f"Database reachable after {attempt} attempt(s).", flush=True)
                return 0
    finally:
        engine.dispose()

    print(
        f"Database unreachable after {MAX_ATTEMPTS} attempts "
        f"({CONNECT_TIMEOUT_SECONDS}s timeout each). Last error: {last_error}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
