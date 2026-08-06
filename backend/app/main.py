import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import router
from app.ats_api import router as ats_router
from app.saas_api import router as saas_router
from app.oauth_api import router as oauth_router
from app.governance_api import router as governance_router
from app.config import get_settings
from app.database import Base, engine

settings = get_settings()
logging.basicConfig(
    level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.resume_storage_path.mkdir(parents=True, exist_ok=True)
    settings.avatar_storage_path.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    yield


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
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    logging.getLogger("api").info(
        "%s %s %s %.3fs",
        request.method,
        request.url.path,
        response.status_code,
        time.perf_counter() - started,
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder(
            {
                "success": False,
                "message": "Validation failed",
                "error": {"code": "VALIDATION_ERROR", "details": exc.errors()},
                "request_id": request.headers.get("X-Request-ID"),
            }
        ),
    )


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/ready")
def ready():
    return {"status": "ready"}


app.include_router(router)
app.include_router(ats_router)
app.include_router(saas_router)
app.include_router(oauth_router)
app.include_router(governance_router)
