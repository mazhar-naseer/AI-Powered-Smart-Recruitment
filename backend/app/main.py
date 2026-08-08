import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api import router
from app.ats_api import router as ats_router
from app.saas_api import router as saas_router
from app.oauth_api import router as oauth_router
from app.governance_api import router as governance_router
from app.config import get_settings
from app.database import Base, engine
from app.first_admin import ensure_first_admin
from app.logging_config import (
    configure_logging,
    get_logger,
    get_request_id,
    reset_request_id,
    set_request_id,
)

settings = get_settings()
configure_logging()
logger = get_logger("app.request")

# Above this, a request is worth looking at even though it succeeded. Resume
# analysis is the slow path and runs off-request, so a slow endpoint here means
# a query or an upstream call, not the scorer.
SLOW_REQUEST_SECONDS = 3.0


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Starting %s in %s environment", settings.app_name, settings.environment)
    # Storage roots are created by the local backend when it is the one selected;
    # creating them here would put directories on disk even in Cloudinary mode.
    Base.metadata.create_all(engine)
    # After create_all: the seed needs the users table to exist.
    ensure_first_admin(settings)
    logger.info(
        "Startup complete (inline_background_jobs=%s, email_verification_enabled=%s)",
        settings.inline_background_jobs,
        settings.email_verification_enabled,
    )
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Content-Disposition",
        "Content-Length",
        "Content-Type",
    ],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Log every request once, and bind its id for everything it calls.

    This is what guarantees each endpoint produces a log line without 83 route
    bodies having to log for themselves. Endpoints add their own records only
    where the detail is domain-specific.
    """
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    token = set_request_id(request_id)
    started = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            # The exception handlers below build the response, but they run
            # outside the middleware, so this is the only place that sees the
            # failure with the request's timing still in scope.
            logger.exception(
                "%s %s failed after %.3fs",
                request.method,
                request.url.path,
                time.perf_counter() - started,
            )
            raise

        elapsed = time.perf_counter() - started
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # 5xx is a defect, 4xx is usually the caller's, 2xx is routine.
        if response.status_code >= 500:
            level = logging.ERROR
        elif response.status_code >= 400:
            level = logging.WARNING
        else:
            level = logging.INFO
        logger.log(
            level,
            "%s %s -> %s in %.3fs",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
        if response.status_code < 400 and elapsed >= SLOW_REQUEST_SECONDS:
            logger.warning(
                "Slow request: %s %s took %.3fs", request.method, request.url.path, elapsed
            )
        return response
    finally:
        # Always unbind: ContextVars are reused across requests on the same
        # worker, so a leaked id would mislabel later log lines.
        reset_request_id(token)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Field names only. Values can carry passwords and resume contents, and
    # exc.errors() includes the rejected input.
    logger.warning(
        "Validation failed for %s %s on fields %s",
        request.method,
        request.url.path,
        [".".join(str(part) for part in error.get("loc", ())) for error in exc.errors()],
    )
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder(
            {
                "success": False,
                "message": "Validation failed",
                "error": {"code": "VALIDATION_ERROR", "details": exc.errors()},
                "request_id": get_request_id(),
            }
        ),
    )


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    """Record deliberate 4xx/5xx aborts without changing what the client reads.

    ``detail`` is kept exactly as FastAPI's default handler returns it, because
    both the frontend error reader and the test suite index into it. The envelope
    keys are added alongside it so an aborted request carries the same
    ``success``/``message``/``request_id`` fields as a successful one.
    """
    if exc.status_code >= 500:
        logger.error("%s %s aborted: %s", request.method, request.url.path, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(
            {
                "detail": exc.detail,
                "success": False,
                "message": exc.detail if isinstance(exc.detail, str) else "Request failed",
                "error": {"code": f"HTTP_{exc.status_code}", "details": exc.detail},
                "request_id": get_request_id(),
            }
        ),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """Last resort for a bug in an endpoint.

    Logged with a stack trace; the client gets the request id and nothing else.
    An exception message can name a table, a column, or a file path, which is
    detail an unauthenticated caller should not receive.
    """
    logger.exception("Unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "An internal error occurred. Please try again.",
            "error": {"code": "INTERNAL_ERROR", "request_id": get_request_id()},
            "request_id": get_request_id(),
        },
    )


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/ready")
def ready():
    """Readiness depends on the database, so check it rather than assume it."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Readiness check failed: database is unreachable")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ready"}


app.include_router(router)
app.include_router(ats_router)
app.include_router(saas_router)
app.include_router(oauth_router)
app.include_router(governance_router)
