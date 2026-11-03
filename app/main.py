"""CNPJ/CEP lookup service: consumes BrasilAPI, caches in SQLite, exposes its own REST API."""
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from . import db, service
from .client import BrasilAPIClient
from .errors import NotFoundUpstream, UpstreamError
from .validators import is_valid_cep, is_valid_cnpj, normalize_cep, normalize_cnpj

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cnpj_service.api")

DB_PATH = os.getenv("DB_PATH", "lookups.db")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "86400"))
BRASILAPI_BASE_URL = os.getenv("BRASILAPI_BASE_URL", "https://brasilapi.com.br/api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect(DB_PATH).close()  # make sure the table exists
    app.state.client = BrasilAPIClient(base_url=BRASILAPI_BASE_URL)
    yield
    app.state.client.close()


app = FastAPI(title="CNPJ Lookup Service", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    log.info(
        "%s %s -> %d (%.0f ms)",
        request.method, request.url.path, response.status_code, (time.perf_counter() - started) * 1000,
    )
    return response


@app.exception_handler(UpstreamError)
async def upstream_error_handler(request: Request, exc: UpstreamError):
    """Translate upstream failures into clear status codes for our own clients."""
    if isinstance(exc, NotFoundUpstream):
        status, detail = 404, "Not found"
    elif exc.status_code == 429:
        status, detail = 503, "Upstream rate limit reached, try again shortly"
    elif exc.status_code == 504:
        status, detail = 504, "Upstream timed out"
    else:
        status, detail = 502, "Upstream service error"
    log.error("upstream failure on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=status, content={"detail": detail})


def get_conn():
    conn = db.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def get_client(request: Request) -> BrasilAPIClient:
    return request.app.state.client


def _envelope(result: service.LookupResult) -> dict:
    return {"source": result.source, "fetched_at": result.fetched_at.isoformat(), "data": result.payload}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/company/{cnpj:path}")
def get_company(cnpj: str, conn=Depends(get_conn), client: BrasilAPIClient = Depends(get_client)):
    if not is_valid_cnpj(cnpj):
        raise HTTPException(status_code=422, detail="Invalid CNPJ (wrong format or check digits)")
    key = normalize_cnpj(cnpj)
    return _envelope(service.get_or_fetch(conn, "cnpj", key, client.get_cnpj, CACHE_TTL_SECONDS))


@app.get("/companies")
def list_companies(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn=Depends(get_conn),
):
    rows = db.list_kind(conn, "cnpj", limit=limit, offset=offset)
    items = [
        {
            "cnpj": r["key"],
            "razao_social": r["payload"].get("razao_social"),
            "uf": r["payload"].get("uf"),
            "municipio": r["payload"].get("municipio"),
            "fetched_at": r["fetched_at"].isoformat(),
        }
        for r in rows
    ]
    return {"count": len(items), "limit": limit, "offset": offset, "items": items}


@app.get("/cep/{cep}")
def get_cep(cep: str, conn=Depends(get_conn), client: BrasilAPIClient = Depends(get_client)):
    if not is_valid_cep(cep):
        raise HTTPException(status_code=422, detail="Invalid CEP (must have 8 digits)")
    key = normalize_cep(cep)
    return _envelope(service.get_or_fetch(conn, "cep", key, client.get_cep, CACHE_TTL_SECONDS))
