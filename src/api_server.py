#!/usr/bin/env python3
"""API Server pour MCP-Claude-mem-local - Interface dynamique temps réel"""

import hashlib
import logging
import math
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urlparse
from uuid import UUID

import asyncpg
import httpx
from dotenv import load_dotenv
from fastapi import Body, FastAPI, Query, Request, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

load_dotenv()

# Configure secure logging (no secrets)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DATABASE = os.getenv("PG_DATABASE", "claude_memory")
PG_USER = os.getenv("PG_USER", "claude")
PG_PASSWORD = os.getenv("PG_PASSWORD")
if not PG_PASSWORD:
    raise RuntimeError("PG_PASSWORD environment variable is required. Set it in .env file.")

# Security: Validate OLLAMA_HOST to prevent SSRF
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
_parsed_ollama = urlparse(OLLAMA_HOST)
ALLOWED_OLLAMA_HOSTS = {"localhost", "127.0.0.1"}
if _parsed_ollama.hostname not in ALLOWED_OLLAMA_HOSTS:
    raise RuntimeError(f"OLLAMA_HOST must be localhost or 127.0.0.1 for security. Got: {_parsed_ollama.hostname}")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

# User isolation
USER_ID = os.getenv("USER_ID", "default")

# Security: Proxy trust (only trust X-Forwarded-For when behind a reverse proxy)
TRUST_PROXY = os.getenv("TRUST_PROXY", "false").lower() == "true"

# Security: API Key authentication
API_KEY = os.getenv("API_KEY")
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "true").lower() == "true"
if REQUIRE_AUTH and not API_KEY:
    raise RuntimeError(
        "API_KEY must be set when REQUIRE_AUTH=true. "
        "Generate one with: openssl rand -hex 32"
    )
API_KEY_HEADER = "X-API-Key"

# Security: Rate limiting configuration
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))  # requests per minute
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # window in seconds

# Simple in-memory rate limiter (capped to prevent memory exhaustion)
_rate_limit_store: dict[str, list[float]] = {}
_MAX_TRACKED_IPS = 10000


def get_client_ip(request: Request) -> str:
    """Get client IP from request (only trust X-Forwarded-For behind a proxy)"""
    if TRUST_PROXY:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(client_ip: str) -> bool:
    """Check if client has exceeded rate limit"""
    import time
    current_time = time.time()

    # Evict all entries if store exceeds cap (prevent memory exhaustion)
    if len(_rate_limit_store) > _MAX_TRACKED_IPS:
        _rate_limit_store.clear()

    if client_ip not in _rate_limit_store:
        _rate_limit_store[client_ip] = []

    # Clean old entries
    _rate_limit_store[client_ip] = [
        t for t in _rate_limit_store[client_ip]
        if current_time - t < RATE_LIMIT_WINDOW
    ]

    if len(_rate_limit_store[client_ip]) >= RATE_LIMIT_REQUESTS:
        return False

    _rate_limit_store[client_ip].append(current_time)
    return True


async def verify_api_key(
    request: Request,
    x_api_key: str = Header(None, alias="X-API-Key")
) -> None:
    """Verify API key if configured"""
    # Skip auth for web interface root page only
    if request.url.path == "/":
        return

    if API_KEY:
        if not x_api_key:
            raise HTTPException(status_code=401, detail="API key required")
        # Constant-time comparison to prevent timing attacks
        if not secrets.compare_digest(x_api_key, API_KEY):
            logger.warning(f"Invalid API key attempt from {get_client_ip(request)}")
            raise HTTPException(status_code=401, detail="Invalid API key")

pool = None


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # CSP for all paths (unsafe-inline required for embedded HTML template)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware"""
    async def dispatch(self, request: Request, call_next):
        client_ip = get_client_ip(request)
        if not check_rate_limit(client_ip):
            logger.warning(f"Rate limit exceeded for {client_ip}")
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."}
            )
        return await call_next(request)


async def _init_connection(conn):
    """Set RLS session variable on each new connection."""
    # SET does not support $1 parameters in PostgreSQL; sanitize and interpolate
    safe_id = USER_ID.replace("'", "''")
    await conn.execute(f"SET app.current_user_id = '{safe_id}'")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    global pool
    pool = await asyncpg.create_pool(
        host=PG_HOST, port=PG_PORT, database=PG_DATABASE,
        user=PG_USER, password=PG_PASSWORD,
        min_size=2, max_size=10, command_timeout=30,
        init=_init_connection,
    )
    logger.info(f"Connected to PostgreSQL: {PG_DATABASE}")
    yield
    await pool.close()
    logger.info("Database connection closed")


app = FastAPI(
    title="MCP-Claude-mem-local API",
    lifespan=lifespan,
    docs_url=None if os.getenv("DISABLE_DOCS") else "/docs",  # Disable in production
    redoc_url=None if os.getenv("DISABLE_DOCS") else "/redoc"
)

# Add security middlewares
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)


# Global exception handler - don't expose internal errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions securely"""
    # Log the actual error for debugging
    logger.error(f"Unhandled exception on {request.url.path}: {type(exc).__name__}")

    # Return generic error to client (don't expose internals)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again later."}
    )


# Security: Restrict CORS to localhost only
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(",")
for _origin in ALLOWED_ORIGINS:
    _parsed = urlparse(_origin.strip())
    if not _parsed.scheme or not _parsed.hostname:
        raise RuntimeError(f"Invalid ALLOWED_ORIGINS entry: '{_origin}'. Must be a valid URL.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    allow_credentials=False,
)


@app.get("/api/stats")
async def get_stats(request: Request, _: None = Depends(verify_api_key)):
    """Statistiques globales des mémoires"""
    _uf = "(user_id = $1 OR user_id IS NULL)"
    async with pool.acquire() as conn:
        total = await conn.fetchval(f"SELECT COUNT(*) FROM memories WHERE {_uf}", USER_ID)
        by_category = await conn.fetch(
            f"SELECT category, COUNT(*) as count FROM memories WHERE {_uf} GROUP BY category ORDER BY count DESC",
            USER_ID
        )
        by_project = await conn.fetch(
            f"SELECT project_context, COUNT(*) as count FROM memories "
            f"WHERE project_context IS NOT NULL AND {_uf} GROUP BY project_context ORDER BY count DESC",
            USER_ID
        )
        total_prompts = await conn.fetchval(
            f"SELECT COUNT(*) FROM user_prompts WHERE {_uf}", USER_ID
        )
        recent = await conn.fetchval(
            f"SELECT COUNT(*) FROM memories WHERE created_at > NOW() - INTERVAL '7 days' AND {_uf}",
            USER_ID
        )

    return {
        "total_memories": total,
        "total_prompts": total_prompts,
        "recent_week": recent,
        "by_category": [{"category": r["category"], "count": r["count"]} for r in by_category],
        "by_project": [{"project": r["project_context"], "count": r["count"]} for r in by_project]
    }


@app.get("/api/memories")
async def get_memories(
    request: Request,
    category: str = Query(None, description="Filtrer par catégorie", max_length=50),
    project: str = Query(None, description="Filtrer par projet", max_length=200),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _: None = Depends(verify_api_key)
):
    """Liste des mémoires avec filtres"""
    query = """
        SELECT id, content, summary, category, tags, project_context,
               importance_score, created_at, access_count
        FROM memories
        WHERE (user_id = $5 OR user_id IS NULL)
          AND ($1::text IS NULL OR category = $1)
          AND ($2::text IS NULL OR project_context = $2)
        ORDER BY created_at DESC
        LIMIT $3 OFFSET $4
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, category, project, limit, offset, USER_ID)

    return {
        "memories": [
            {
                "id": str(r["id"]),
                "content": r["content"],
                "summary": r["summary"],
                "category": r["category"],
                "tags": r["tags"] or [],
                "project": r["project_context"],
                "importance": r["importance_score"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "access_count": r["access_count"]
            }
            for r in rows
        ],
        "count": len(rows)
    }


MAX_BULK_DELETE = 500


def _parse_uuid(raw: str) -> UUID:
    """Valide un identifiant de memoire, sinon 400."""
    try:
        return UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid memory id")


async def _delete_memory_ids(ids: list[UUID]) -> int:
    """Supprime les memoires appartenant a l'utilisateur courant. Retourne le nombre supprime."""
    async with pool.acquire() as conn:
        deleted = await conn.fetch(
            "DELETE FROM memories WHERE id = ANY($1::uuid[]) "
            "AND (user_id = $2 OR user_id IS NULL) RETURNING id",
            ids, USER_ID
        )
    return len(deleted)


@app.delete("/api/memories/{memory_id}")
async def delete_memory(
    request: Request,
    memory_id: str,
    _: None = Depends(verify_api_key)
):
    """Supprime une memoire par son ID."""
    mem_id = _parse_uuid(memory_id)
    deleted = await _delete_memory_ids([mem_id])
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Memory not found")
    logger.info(f"Deleted memory {mem_id}")
    return {"deleted": deleted, "ids": [str(mem_id)]}


@app.post("/api/memories/bulk-delete")
async def bulk_delete_memories(
    request: Request,
    ids: list[str] = Body(..., embed=True),
    _: None = Depends(verify_api_key)
):
    """Supprime plusieurs memoires en une fois."""
    if not ids:
        raise HTTPException(status_code=400, detail="No memory id provided")
    if len(ids) > MAX_BULK_DELETE:
        raise HTTPException(
            status_code=400,
            detail=f"Too many ids (max {MAX_BULK_DELETE})"
        )
    mem_ids = [_parse_uuid(i) for i in ids]
    deleted = await _delete_memory_ids(mem_ids)
    logger.info(f"Bulk deleted {deleted}/{len(mem_ids)} memories")
    return {"deleted": deleted, "requested": len(mem_ids)}


@app.get("/api/search")
async def search_memories(
    request: Request,
    q: str = Query(..., min_length=2, max_length=500, description="Requête de recherche"),
    limit: int = Query(10, ge=1, le=50),
    _: None = Depends(verify_api_key)
):
    """Recherche vectorielle dans les mémoires"""
    # Générer l'embedding de la requête
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{OLLAMA_HOST}/api/embeddings",
            json={"model": EMBEDDING_MODEL, "prompt": q}
        )
        response.raise_for_status()
        embedding = response.json()["embedding"]

    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    query = """
        SELECT id, content, summary, category, tags, project_context,
               importance_score, created_at, access_count,
               1 - (embedding <=> $1::vector) as similarity
        FROM memories
        WHERE 1 - (embedding <=> $1::vector) >= 0.3
          AND (user_id = $3 OR user_id IS NULL)
        ORDER BY (1 - (embedding <=> $1::vector)) * importance_score DESC
        LIMIT $2
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, embedding_str, limit, USER_ID)

    return {
        "query": q,
        "results": [
            {
                "id": str(r["id"]),
                "content": r["content"],
                "summary": r["summary"],
                "category": r["category"],
                "tags": r["tags"] or [],
                "project": r["project_context"],
                "importance": r["importance_score"],
                "similarity": round(r["similarity"], 3),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
        "count": len(rows)
    }


GRAPH_KNN = 3              # voisins semantiques retenus par memoire
GRAPH_EDGE_MIN = 0.78      # cosinus minimum pour tracer un lien
GRAPH_DUP_THRESHOLD = 0.92 # cosinus au-dela duquel deux memoires sont quasi-identiques
GRAPH_ACTR_DECAY = 0.5


def _actr_fallback(access_count: int, age_days: float, importance: float) -> float:
    """Approximation ACT-R quand actr_activation n'est pas encore calculee."""
    n = max(1, access_count or 0)
    t = max(0.5, age_days)
    return math.log(n * t ** (-GRAPH_ACTR_DECAY)) + 2.0 * (importance or 0.5)


@app.get("/api/graph")
async def get_graph(
    request: Request,
    limit: int = Query(5000, ge=1, le=20000),
    include_forgotten: bool = Query(True),
    _: None = Depends(verify_api_key)
):
    """Noeuds de l'atlas memoire (projets -> categories -> memoires).

    Les liens semantiques ne sont pas calcules ici : ils sont couteux et
    n'ont de sens qu'une fois un projet deplie (voir /api/graph/edges).
    """
    query = """
        SELECT id, content, summary, category, tags, project_context,
               importance_score, memory_status, access_count, actr_activation,
               created_at, last_accessed_at
        FROM memories
        WHERE (user_id = $1 OR user_id IS NULL)
          AND ($3::bool OR COALESCE(memory_status, 'active') <> 'forgotten')
        ORDER BY created_at DESC
        LIMIT $2
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, USER_ID, limit, include_forgotten)

    now = datetime.now(timezone.utc)
    memories = []
    for r in rows:
        last = r["last_accessed_at"] or r["created_at"]
        age = int((now - last).total_seconds() // 86400) if last else 0
        importance = float(r["importance_score"] or 0.5)
        access = int(r["access_count"] or 0)
        act = r["actr_activation"]
        act = float(act) if act is not None else _actr_fallback(access, age, importance)
        content = (r["content"] or "")[:520]
        memories.append({
            "i": str(r["id"]),
            "c": r["category"] or "sans catégorie",
            "p": r["project_context"] or "sans projet",
            "s": (r["summary"] or content)[:130],
            "t": content,
            "g": list(r["tags"] or [])[:8],
            "imp": round(importance, 3),
            "st": r["memory_status"] or "active",
            "n": access,
            "age": max(0, age),
            "act": round(act, 3),
            "d": last.date().isoformat() if last else "",
        })

    return {
        "memories": memories,
        "edges": [],
        "categories": sorted({m["c"] for m in memories}),
        "projects": sorted({m["p"] for m in memories}),
        "dupThreshold": GRAPH_DUP_THRESHOLD,
        "generated": now.date().isoformat(),
        "count": len(memories),
    }


@app.get("/api/graph/edges")
async def get_graph_edges(
    request: Request,
    project: str = Query(..., max_length=200, description="Projet deplie"),
    knn: int = Query(GRAPH_KNN, ge=1, le=8),
    min_similarity: float = Query(GRAPH_EDGE_MIN, ge=0.0, le=1.0),
    _: None = Depends(verify_api_key)
):
    """Voisins semantiques des memoires d'un projet, cherches dans tout le corpus.

    Restreindre la source a un projet garde le calcul court tout en laissant
    apparaitre les quasi-doublons inter-projets.
    """
    query = """
        SELECT src.id AS a, nb.id AS b, 1 - (src.embedding <=> nb.embedding) AS sim
        FROM memories src
        CROSS JOIN LATERAL (
            SELECT x.id, x.embedding
            FROM memories x
            WHERE x.id <> src.id
              AND x.embedding IS NOT NULL
              AND (x.user_id = $1 OR x.user_id IS NULL)
            ORDER BY x.embedding <=> src.embedding
            LIMIT $3
        ) nb
        WHERE src.project_context = $2
          AND src.embedding IS NOT NULL
          AND (src.user_id = $1 OR src.user_id IS NULL)
          AND 1 - (src.embedding <=> nb.embedding) >= $4
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, USER_ID, project, knn, min_similarity)

    # Dedoublonnage des paires (a,b) / (b,a)
    seen: dict[tuple[str, str], float] = {}
    for r in rows:
        a, b = str(r["a"]), str(r["b"])
        key = (a, b) if a < b else (b, a)
        sim = round(float(r["sim"]), 4)
        if sim > seen.get(key, 0.0):
            seen[key] = sim

    edges = [{"a": a, "b": b, "s": sim} for (a, b), sim in seen.items()]
    return {
        "project": project,
        "edges": edges,
        "dupThreshold": GRAPH_DUP_THRESHOLD,
        "count": len(edges),
    }


@app.get("/api/prompts")
async def get_prompts(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    _: None = Depends(verify_api_key)
):
    """Liste des prompts utilisateur"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, prompt_text, prompt_number, created_at, project_context FROM user_prompts "
            "WHERE (user_id = $2 OR user_id IS NULL) "
            "ORDER BY created_at DESC LIMIT $1", limit, USER_ID
        )

    return {
        "prompts": [
            {
                "id": str(r["id"]),
                "text": r["prompt_text"],
                "number": r["prompt_number"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "project": r["project_context"]
            }
            for r in rows
        ],
        "count": len(rows)
    }


@app.get("/", response_class=HTMLResponse)
async def serve_viewer():
    """Sert l'interface web dynamique"""
    return HTML_TEMPLATE.replace("__API_KEY__", API_KEY or "")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SYNAPTIC-MEM</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Nunito:ital,wght@0,300;0,400;0,600;0,700;1,400&family=Open+Sans:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
            /* Marque Zenika (indépendant du thème) */
            --z-red: #EE2238; --z-raspberry: #BF1D67;
            --z-gradient: linear-gradient(135deg, #EE2238 0%, #BF1D67 100%);
            --g-yellow: linear-gradient(135deg, #F4C042 0%, #EB8581 100%);
            --g-blue: linear-gradient(135deg, #4CA8E7 0%, #4F8DF5 100%);
            --g-violet: linear-gradient(135deg, #A188EF 0%, #7C86E9 100%);
            --g-mint: linear-gradient(135deg, #00EB84 0%, #00E3EC 100%);
            --red-soft: rgba(238,34,56,0.14); --red-strong: rgba(238,34,56,0.28); --red-border: rgba(238,34,56,0.45);
            --font-body: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            --font-caption: 'Open Sans', 'Nunito', sans-serif;
            /* Thème clair (défaut) */
            --bg: #FFFFFF; --surface: #F7F7F8; --surface-2: #FFFFFF; --hover: rgba(0,0,0,0.05);
            --border: rgba(0,0,0,0.10); --border-strong: rgba(0,0,0,0.16);
            --text: #1E1E1E; --text-strong: #000000; --text-muted: #5f6368; --text-dim: #9aa0a6;
            --input-bg: #FFFFFF; --shadow: rgba(0,0,0,0.16);
        }
        :root[data-theme="dark"] {
            --bg: #1c1c1f; --surface: #232327; --surface-2: #26262a; --hover: rgba(255,255,255,0.07);
            --border: rgba(255,255,255,0.10); --border-strong: rgba(255,255,255,0.18);
            --text: #F3F3F3; --text-strong: #FFFFFF; --text-muted: #B7B7B7; --text-dim: #8a8a8f;
            --input-bg: #26262a; --shadow: rgba(0,0,0,0.6);
        }
        button, input, select, textarea { font-family: var(--font-body); }
        body { font-family: var(--font-body); background: var(--bg); color: var(--text); min-height: 100vh; padding: 20px; transition: background 0.25s, color 0.25s; }
        .container { max-width: 1400px; margin: 0 auto; }
        /* Bandeau haut unique : titre · onglets · outils de l'onglet actif · réglages */
        /* Tout tient sur une seule ligne : c'est le champ de recherche qui absorbe la contrainte */
        .topbar { display: flex; align-items: center; gap: 16px; margin-bottom: 14px; flex-wrap: nowrap; width: 100vw; margin-left: calc(50% - 50vw); padding: 0 20px; }
        h1 { flex: 0 0 auto; white-space: nowrap; font-weight: 700; letter-spacing: -0.01em; background: var(--z-gradient); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.1em; }
        h1::after { content: ""; display: block; width: 64px; height: 3px; margin: 6px auto 0; border-radius: 2px; background: var(--z-gradient); }
        .topbar .tabs { margin-bottom: 0; flex: 0 0 auto; }
        .topbar-tools { display: flex; align-items: center; gap: 10px; flex: 1 1 auto; min-width: 0; }
        .topbar-tools .refresh-btn { flex: 0 0 auto; white-space: nowrap; }
        .topbar-tools[hidden] { display: none; }
        .topbar-tools[hidden] ~ .topbar-end { margin-left: auto; }
        .topbar-end { display: flex; align-items: center; gap: 10px; flex: 0 0 auto; }
        .settings-btn { flex: 0 0 auto; background: transparent; border: none; color: var(--text-muted); cursor: pointer; font-size: 1.25em; line-height: 1; padding: 6px 8px; border-radius: 8px; }
        .settings-btn:hover { color: var(--z-red); background: var(--hover); }
        .settings-btn[aria-expanded="true"] { color: var(--z-red); background: var(--red-soft); }
        /* Barre d'état : passée en pop-over ancré sous l'icône réglages */
        .settings-pop { position: fixed; top: 62px; right: 20px; z-index: 1100; width: min(680px, calc(100vw - 40px)); display: none; }
        .settings-pop.open { display: block; }
        /* Fond opaque : la modale ne doit pas laisser voir l'atlas au travers */
        .settings-pop .status-bar { margin-bottom: 0; background: linear-gradient(rgba(0,196,106,0.12), rgba(0,196,106,0.12)), var(--surface-2); box-shadow: 0 18px 46px var(--shadow); }
        .settings-backdrop { position: fixed; inset: 0; z-index: 1090; display: none; }
        .settings-backdrop.open { display: block; }
        @media (max-width: 1000px) {
            .topbar { flex-wrap: wrap; gap: 12px; }
            h1 { font-size: 1.7em; }
        }
        .subtitle { text-align: center; color: var(--text-muted); margin-bottom: 20px; }
        .status-bar { background: rgba(0,196,106,0.12); border: 1px solid rgba(0,196,106,0.55); border-radius: 8px; padding: 10px 15px; margin-bottom: 20px; display: flex; align-items: center; gap: 10px; justify-content: space-between; min-height: 44px; }
        .status-left { display: flex; align-items: center; gap: 10px; min-width: 350px; }
        .status-dot { width: 10px; height: 10px; min-width: 10px; min-height: 10px; max-width: 10px; max-height: 10px; background: #00C46A; border-radius: 50%; flex-shrink: 0; }
        .status-dot.loading { background: var(--z-red); animation: blink 0.5s ease-in-out infinite; }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        #statusText { min-width: 300px; }
        .header-actions { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
        .theme-toggle { background: var(--surface); border: 1px solid var(--border-strong); color: var(--text); padding: 7px 11px; border-radius: 8px; cursor: pointer; font-size: 1.05em; line-height: 1; }
        .theme-toggle:hover { border-color: var(--z-red); }
        .refresh-btn { background: var(--z-gradient); border: none; color: #fff; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; }
        .refresh-btn:hover { filter: brightness(1.08); }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab-btn { padding: 12px 24px; border: none; border-radius: 8px 8px 0 0; background: var(--surface); color: var(--text-muted); cursor: pointer; font-size: 1em; transition: all 0.25s; }
        .tab-btn:hover { color: var(--text); }
        .tab-btn.active { background: var(--z-gradient); color: #fff; font-weight: 600; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 15px; margin-bottom: 30px; min-height: 90px; }
        .stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; text-align: center; min-height: 80px; }
        .stat-value { font-size: 2em; font-weight: 700; color: var(--z-red); }
        .stat-card:nth-child(2) .stat-value { color: #2E90DC; }
        .stat-card:nth-child(3) .stat-value { color: #00B468; }
        .stat-card:nth-child(4) .stat-value { color: #E0A21C; }
        .stat-card:nth-child(5) .stat-value { color: #8B6CE0; }
        .stat-card:nth-child(6) .stat-value { color: #E06A66; }
        .stat-card:nth-child(7) .stat-value { color: #4F8DF5; }
        .stat-card:nth-child(8) .stat-value { color: #16B8C0; }
        .stat-label { color: var(--text-muted); font-size: 0.9em; }
        .controls { display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap; align-items: center; }
        .search-box { flex: 1; min-width: 250px; padding: 12px 20px; border: 1px solid var(--border-strong); border-radius: 25px; background: var(--input-bg); color: var(--text); font-size: 1em; }
        .search-box:focus { outline: none; border-color: var(--z-red); }
        .search-btn { background: var(--z-gradient); border: none; color: #fff; padding: 12px 24px; border-radius: 25px; cursor: pointer; font-weight: 600; }
        .search-btn:hover { filter: brightness(1.08); }
        .filters { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 15px; min-height: 36px; align-items: center; }
        .filter-btn { padding: 6px 14px; border: 1px solid var(--border-strong); border-radius: 20px; background: transparent; color: var(--text); cursor: pointer; font-size: 0.85em; transition: all 0.2s; }
        .filter-btn:hover { border-color: var(--z-red); }
        .filter-btn.active { background: var(--z-gradient); border-color: transparent; color: #fff; }
        .project-btn { padding: 6px 14px; border: 1px solid var(--red-border); border-radius: 20px; background: transparent; color: var(--z-red); cursor: pointer; font-size: 0.85em; }
        .project-btn:hover, .project-btn.active { background: var(--red-soft); }
        .project-select { padding: 6px 12px; border: 1px solid var(--red-border); border-radius: 8px; background: var(--input-bg); color: var(--text); cursor: pointer; font-size: 0.9em; min-width: 220px; }
        .project-select:focus { outline: none; border-color: var(--z-red); }
        .project-select option { background: var(--surface-2); color: var(--text); }
        .project-combo { position: relative; display: inline-block; }
        .project-search { padding: 6px 12px; border: 1px solid var(--border-strong); border-radius: 8px; background: var(--input-bg); color: var(--text); font-size: 0.9em; min-width: 240px; }
        .project-search:focus { outline: none; border-color: var(--z-red); }
        .project-search::placeholder { color: var(--text-dim); }
        .project-list { position: absolute; top: 100%; left: 0; right: 0; z-index: 100; margin-top: 4px; background: var(--surface-2); border: 1px solid var(--border-strong); border-radius: 8px; max-height: 320px; overflow-y: auto; display: none; box-shadow: 0 8px 24px var(--shadow); }
        .project-list.open { display: block; }
        .project-item { padding: 7px 12px; cursor: pointer; color: var(--text); font-size: 0.88em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .project-item:hover, .project-item.active { background: var(--red-soft); }
        .project-item.kb-active { background: var(--red-strong); outline: 1px solid var(--z-red); outline-offset: -1px; }
        .project-item .cnt { color: var(--text-dim); font-size: 0.85em; }
        .project-list::-webkit-scrollbar { width: 8px; }
        .project-list::-webkit-scrollbar-thumb { background: var(--red-border); border-radius: 4px; }
        .sort-btn { margin-left: 6px; padding: 4px 9px; border: 1px solid var(--border-strong); border-radius: 14px; background: transparent; color: var(--text-muted); cursor: pointer; font-size: 0.78em; vertical-align: middle; }
        .sort-btn:hover { border-color: var(--z-red); color: var(--z-red); }
        .sort-btn.active { background: var(--red-soft); border-color: var(--z-red); color: var(--z-red); }
        .memories-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; contain: layout style; }
        .memory-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; transition: transform 0.2s, border-color 0.2s; }
        .memory-card:hover { transform: translateY(-2px); box-shadow: 0 10px 30px var(--shadow); border-color: var(--red-border); }
        .memory-card.new { animation: glow 2s ease-out; }
        /* Mode liste : tableau à colonnes alignées (Type · Étoiles · Titre · Desc · Projet · Date) */
        .memories-list { display: grid; grid-template-columns: max-content max-content max-content minmax(140px,1.4fr) minmax(180px,2fr) max-content max-content max-content; gap: 4px 14px; align-items: center; }
        .mem-list-head { display: grid; grid-template-columns: subgrid; grid-column: 1 / -1; padding: 4px 12px; font-size: 0.72em; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-dim); border-bottom: 1px solid var(--border-strong); }
        .memories-list .memory-card { display: grid; grid-template-columns: subgrid; grid-column: 1 / -1; align-items: center; padding: 7px 12px; border-radius: 6px; }
        .memories-list .memory-card:hover { transform: none; box-shadow: none; background: var(--hover); }
        .memories-list .memory-type { justify-self: start; }
        .memories-list .memory-importance { color: #f0a500; font-size: 0.85em; white-space: nowrap; }
        .memories-list .mem-title { font-weight: 600; color: var(--text-strong); }
        .memories-list .mem-title,
        .memories-list .mem-desc,
        .memories-list .mem-proj { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
        .memories-list .mem-desc { color: var(--text-muted); font-size: 0.85em; }
        .memories-list .mem-proj { color: var(--z-red); font-size: 0.8em; }
        .memories-list .mem-time { color: var(--text-dim); font-size: 0.75em; white-space: nowrap; }
        .memories-list .memory-card { cursor: pointer; }
        .memories-list .memory-card:focus-visible { outline: 2px solid var(--z-red); outline-offset: -2px; }
        /* Barre d'outils mémoires : projet à gauche, affichage à droite */
        .memories-toolbar { justify-content: space-between; align-items: center; gap: 12px; }
        .toolbar-left { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
        .combo-host { display: inline-flex; align-items: center; }
        .toolbar-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
        /* Vue détaillée d'une mémoire + animation morph (FLIP) */
        .mem-detail-backdrop { position: fixed; inset: 0; z-index: 1000; display: none; align-items: center; justify-content: center; padding: 20px; background: rgba(0,0,0,0); backdrop-filter: blur(0); transition: background 280ms ease, backdrop-filter 280ms ease; }
        .mem-detail-backdrop.open { display: flex; background: rgba(0,0,0,0.5); backdrop-filter: blur(4px); }
        .mem-detail { position: relative; display: none; flex-direction: column; width: min(680px, 92vw); max-height: 86vh; background: var(--surface-2); border: 1px solid var(--border-strong); border-radius: 14px; box-shadow: 0 24px 70px rgba(0,0,0,0.45); overflow: hidden; will-change: transform; }
        .mem-detail::before { content: ""; display: block; height: 3px; flex-shrink: 0; background: var(--z-gradient); }
        .mem-detail-head { display: flex; align-items: center; gap: 12px; padding: 16px 18px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
        .mem-detail-stars { color: #f0a500; }
        .mem-detail-actions { margin-left: auto; display: flex; align-items: center; gap: 4px; }
        .mem-detail-close, .mem-detail-nav { background: transparent; border: none; color: var(--text-muted); cursor: pointer; line-height: 1; border-radius: 6px; }
        .mem-detail-close { font-size: 1.2em; padding: 4px 9px; }
        .mem-detail-nav { font-size: 1.45em; padding: 2px 9px; }
        .mem-detail-close:hover, .mem-detail-nav:hover { color: var(--text-strong); background: var(--hover); }
        .memories-grid .memory-card { cursor: pointer; }
        .memories-grid .memory-card:focus-visible { outline: 2px solid var(--z-red); outline-offset: 2px; }
        .mem-detail-body { padding: 18px; overflow-y: auto; opacity: 0; transform: translateY(6px); transition: opacity 200ms ease 60ms, transform 200ms ease 60ms; }
        .mem-detail.body-in .mem-detail-body { opacity: 1; transform: none; }
        .mem-detail-title { font-size: 1.15em; color: var(--text-strong); margin-bottom: 12px; line-height: 1.4; }
        .mem-detail-content { color: var(--text); font-size: 0.9em; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
        .mem-detail-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 14px; }
        .mem-detail-meta { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border); font-size: 0.78em; color: var(--text-muted); }
        @media (prefers-reduced-motion: reduce) {
            .mem-detail-backdrop, .mem-detail, .mem-detail-body { transition-duration: 80ms; }
        }
        @keyframes glow { 0% { box-shadow: 0 0 20px var(--z-red); } 100% { box-shadow: none; } }
        .memory-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .memory-type { padding: 4px 10px; border-radius: 12px; font-size: 0.8em; font-weight: 600; color: #fff; text-shadow: 0 1px 1px rgba(0,0,0,0.3); }
        .type-bugfix { background: var(--z-gradient); }
        .type-error_solution { background: linear-gradient(135deg, #EB8581 0%, #EE2238 100%); }
        .type-decision { background: var(--g-yellow); }
        .type-preference { background: linear-gradient(135deg, #F4C042 0%, #00EB84 100%); }
        .type-feature { background: var(--g-mint); }
        .type-learning { background: linear-gradient(135deg, #00E3EC 0%, #4CA8E7 100%); }
        .type-discovery { background: var(--g-blue); }
        .type-refactor { background: linear-gradient(135deg, #7C86E9 0%, #4F8DF5 100%); }
        .type-pattern { background: var(--g-violet); }
        .type-change { background: linear-gradient(135deg, #B7B7B7 0%, #747775 100%); }
        .memory-importance { color: #f0a500; }
        .memory-similarity { color: #00B468; font-size: 0.85em; }
        .memory-summary { font-weight: 600; margin-bottom: 10px; color: var(--text-strong); }
        .memory-content { color: var(--text-muted); font-size: 0.85em; line-height: 1.6; max-height: 150px; overflow: hidden; white-space: pre-wrap; word-break: break-word; }
        .memory-content.expanded { max-height: none; }
        .expand-btn { background: none; border: none; color: var(--z-red); cursor: pointer; font-size: 0.8em; margin-top: 8px; }
        .memory-tags { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 10px; }
        .tag { padding: 2px 8px; background: var(--red-soft); border-radius: 10px; font-size: 0.75em; color: var(--z-red); }
        .memory-meta { display: flex; justify-content: space-between; margin-top: 10px; font-size: 0.75em; color: var(--text-dim); }
        .project-badge { background: var(--red-soft); color: var(--z-red); padding: 2px 8px; border-radius: 8px; }
        .prompt-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 15px 20px; margin-bottom: 10px; }
        .prompt-text { color: var(--text); font-size: 0.95em; line-height: 1.5; }
        .prompt-meta { color: var(--text-dim); font-size: 0.75em; margin-top: 8px; }
        .loading { text-align: center; padding: 40px; color: var(--text-muted); }
        .auto-refresh { display: flex; align-items: center; gap: 8px; color: var(--text-muted); font-size: 0.85em; }
        .auto-refresh input { accent-color: var(--z-red); }
        /* Mode Démo : les noms de projets deviennent des pseudonymes (JS),
           le texte libre est flouté et non sélectionnable. */
        .demo-badge { display: none; align-items: center; gap: 6px; white-space: nowrap; background: var(--red-soft); border: 1px solid var(--red-border); color: var(--z-red); font-size: 0.72em; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; padding: 4px 10px; border-radius: 12px; }
        body.demo-on .demo-badge { display: inline-flex; }
        body.demo-on .memory-summary,
        body.demo-on .memory-content,
        body.demo-on .mem-title,
        body.demo-on .mem-desc,
        body.demo-on .mem-detail-title,
        body.demo-on .mem-detail-content,
        body.demo-on .gr-txt,
        body.demo-on .gr-near a,
        body.demo-on .prompt-text,
        body.demo-on .tag {
            filter: blur(4.5px);
            user-select: none;
            -webkit-user-select: none;
            pointer-events: none;
        }
        body.demo-on .gr-near a { pointer-events: auto; }
        /* Selection multiple + suppression */
        .mem-select { accent-color: var(--z-red); width: 15px; height: 15px; cursor: pointer; flex-shrink: 0; }
        .memories-grid .memory-card .mem-select { margin-right: 8px; }
        .del-btn { background: transparent; border: none; color: var(--text-dim); cursor: pointer; font-size: 0.95em; line-height: 1; padding: 3px 6px; border-radius: 6px; flex-shrink: 0; }
        .del-btn:hover { color: var(--z-red); background: var(--red-soft); }
        .del-btn:focus-visible { outline: 2px solid var(--z-red); outline-offset: 1px; }
        .memories-grid .memory-card .del-btn { margin-left: 6px; }
        .memories-list .mem-actions { justify-self: end; }
        .bulk-bar { display: none; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 15px; padding: 10px 14px; background: var(--red-soft); border: 1px solid var(--red-border); border-radius: 8px; }
        .bulk-bar.open { display: flex; }
        .bulk-count { font-weight: 600; color: var(--z-red); }
        .bulk-bar .link-btn { background: transparent; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.85em; text-decoration: underline; padding: 2px 4px; }
        .bulk-bar .link-btn:hover { color: var(--text-strong); }
        .danger-btn { margin-left: auto; background: var(--z-gradient); color: #fff; border: none; padding: 8px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 0.88em; }
        .danger-btn:hover { filter: brightness(1.08); }
        .danger-btn:disabled { opacity: 0.55; cursor: not-allowed; }
        .mem-detail-del { background: transparent; border: none; color: var(--text-muted); cursor: pointer; font-size: 1.05em; padding: 4px 9px; border-radius: 6px; line-height: 1; }
        .mem-detail-del:hover { color: var(--z-red); background: var(--red-soft); }
        /* ---------- Onglet Graph (atlas mémoire) ---------- */
        #grQ { flex: 1 1 120px; min-width: 0; max-width: 360px; background: var(--input-bg); border: 1px solid var(--border); color: var(--text); font-size: 0.85em; padding: 8px 12px; border-radius: 8px; }
        #grQ:focus { outline: none; border-color: var(--z-red); }
        #graph-tab.active { display: flex; flex-direction: column; }
        /* Pleine largeur : on sort de la gouttière du conteneur sans décentrer l'en-tête */
        .gr-stage { position: relative; overflow: hidden; width: 100vw; margin-left: calc(50% - 50vw); flex: 1 1 auto; min-height: 360px; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); background:
            linear-gradient(var(--hover) 1px, transparent 1px) 0 0/100% 34px,
            linear-gradient(90deg, var(--hover) 1px, transparent 1px) 0 0/34px 100%, var(--surface); }
        .gr-stage svg { width: 100%; height: 100%; display: block; touch-action: none; cursor: grab; }
        .gr-stage svg.drag { cursor: grabbing; }
        #grG { transition: opacity 0.16s; }
        #grG.swap { opacity: 0; }
        .gr-stage .edge { fill: none; stroke-width: 1; opacity: 0.45; }
        .gr-stage .edge.thin { stroke-width: 0.6; opacity: 0.3; }
        .gr-stage .node { cursor: pointer; }
        .gr-stage .node.mute { opacity: 0.1; pointer-events: none; }
        .gr-stage .node.hit circle:last-of-type { stroke: var(--z-red); stroke-width: 2.2; }
        .gr-stage .node.sel circle:last-of-type { stroke: var(--text-strong); stroke-width: 2.2; }
        .gr-stage .node:hover circle:last-of-type { stroke: var(--text-strong); stroke-width: 1.6; }
        .gr-stage .ring { fill: none; stroke: var(--border-strong); stroke-width: 1; stroke-dasharray: 2 5; }
        .gr-stage text { pointer-events: none; user-select: none; }
        .gr-stage .plab { font-size: 15px; font-weight: 700; fill: var(--text-strong); }
        .gr-stage .psub { font-size: 9.5px; fill: var(--text-dim); }
        .gr-stage .clab { font-size: 10.5px; }
        .gr-stage .core { font-size: 13px; fill: var(--text-dim); font-style: italic; }
        .gr-crumb { position: absolute; left: 16px; top: 14px; font-size: 0.8em; color: var(--text-muted); display: flex; align-items: center; gap: 10px; }
        .gr-crumb b { color: var(--text-strong); }
        .gr-crumb button { background: var(--surface-2); border: 1px solid var(--border); color: var(--text-muted); font: inherit; padding: 4px 10px; border-radius: 6px; cursor: pointer; }
        .gr-crumb button:hover { border-color: var(--z-red); color: var(--z-red); }
        .gr-panel { position: absolute; top: 14px; right: 14px; width: 340px; max-height: calc(100% - 28px); background: var(--surface-2); border: 1px solid var(--border-strong); border-radius: 10px; display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 10px 30px var(--shadow); transform: translateX(calc(100% + 26px)); transition: transform 0.25s cubic-bezier(0.2,0.8,0.2,1); }
        .gr-panel.open { transform: none; }
        .gr-p-head { padding: 12px 14px; border-bottom: 1px solid var(--border); display: flex; gap: 8px; align-items: center; }
        .gr-p-head h3 { font-size: 0.72em; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; flex: 1; }
        .gr-p-body { padding: 14px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; }
        .gr-txt { font-size: 0.85em; line-height: 1.6; color: var(--text); white-space: pre-wrap; word-break: break-word; }
        .gr-meta { display: grid; grid-template-columns: 84px 1fr; gap: 6px 12px; font-size: 0.78em; }
        .gr-meta dt { color: var(--text-dim); }
        .gr-meta dd { color: var(--text); word-break: break-word; }
        .gr-bar { height: 4px; background: var(--hover); border-radius: 2px; overflow: hidden; margin-top: 3px; }
        .gr-bar i { display: block; height: 100%; background: currentColor; }
        .gr-near b { display: block; font-size: 0.7em; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-dim); margin-bottom: 6px; }
        .gr-near a { display: block; font-size: 0.78em; color: var(--text-muted); text-decoration: none; cursor: pointer; padding: 5px 0; border-bottom: 1px solid var(--border); }
        .gr-near a:hover { color: var(--text-strong); }
        .gr-near a em { font-style: normal; color: var(--z-red); font-weight: 700; }
        .gr-flag { font-size: 0.78em; line-height: 1.5; padding: 9px 11px; border-radius: 6px; background: var(--red-soft); border: 1px solid var(--red-border); color: var(--z-red); }
        .gr-footer { flex: 0 0 auto; }
        .gr-statline { display: flex; justify-content: flex-end; gap: 16px; padding: 8px 2px 0; color: var(--text-muted); font-size: 0.78em; }
        .gr-statline em { font-style: normal; color: var(--text-strong); font-weight: 700; }
        .gr-legend { display: flex; gap: 6px; align-items: center; padding: 8px 2px 0; overflow-x: auto; scrollbar-width: none; flex: 0 0 auto; }
        .gr-legend::-webkit-scrollbar { display: none; }
        .gr-chip { display: flex; align-items: center; gap: 7px; white-space: nowrap; flex: 0 0 auto; background: var(--surface-2); border: 1px solid var(--border); color: var(--text-muted); font-size: 0.75em; padding: 4px 10px; border-radius: 14px; cursor: pointer; }
        .gr-chip:hover { border-color: var(--border-strong); }
        .gr-chip.on { background: var(--text); border-color: var(--text); color: var(--bg); }
        .gr-chip i { width: 8px; height: 8px; border-radius: 50%; background: currentColor; font-style: normal; }
        .gr-chip u { text-decoration: none; color: var(--text-dim); font-size: 0.9em; }
        .gr-hint { margin-left: auto; color: var(--text-dim); font-size: 0.75em; flex: 0 0 auto; }
        @media (max-width: 900px) {
            .gr-panel { top: auto; bottom: 0; left: 0; right: 0; width: auto; max-height: 62%; border-radius: 12px 12px 0 0; transform: translateY(calc(100% + 26px)); }
            .gr-hint { display: none; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="topbar">
            <h1>SYNAPTIC-MEM</h1>

            <div class="tabs">
                <button class="tab-btn active" data-tab="memories">📚 Mémoires (<span id="memCount">-</span>)</button>
                <button class="tab-btn" data-tab="search">🔍 Recherche</button>
                <button class="tab-btn" data-tab="graph">🕸 Graph</button>
                <button class="tab-btn" data-tab="prompts">💬 Prompts (<span id="promptCount">-</span>)</button>
            </div>

            <!-- Outils de l'onglet Graph, remontés dans le bandeau -->
            <div class="topbar-tools" id="grTools" hidden>
                <input type="text" id="grQ" placeholder="🔍 Chercher dans les mémoires…" autocomplete="off" spellcheck="false">
                <button class="refresh-btn" type="button" onclick="graphReload()">🔄 Recharger l'atlas</button>
            </div>

            <div class="topbar-end">
            <span class="demo-badge" id="demoBadge" title="Mode Démo actif : projets pseudonymisés, contenus floutés">🕶 Mode Démo</span>
            <button class="settings-btn" id="settingsBtn" type="button" aria-haspopup="dialog" aria-expanded="false" aria-label="Réglages et état de la connexion" title="Réglages et état de la connexion">⚙️</button>
            </div>
        </div>

        <div class="settings-backdrop" id="settingsBackdrop"></div>
        <div class="settings-pop" id="settingsPop" role="dialog" aria-label="Réglages et état de la connexion">
            <div class="status-bar">
                <div class="status-left">
                    <div class="status-dot" id="statusDot"></div>
                    <span id="statusText">Connecté — PostgreSQL + pgvector + Ollama</span>
                </div>
                <div style="display:flex;gap:15px;align-items:center;">
                    <label class="auto-refresh" title="Masque les noms de projets et floute les contenus, pour les démos">
                        <input type="checkbox" id="demoMode" autocomplete="off">
                        🕶 Mode Démo
                    </label>
                    <label class="auto-refresh">
                        <input type="checkbox" id="autoRefresh" checked autocomplete="off">
                        Auto-refresh (5s)
                    </label>
                    <button class="theme-toggle" id="themeToggle" type="button" onclick="toggleTheme()" aria-label="Basculer thème clair/sombre" title="Basculer thème clair/sombre">🌙</button>
                    <button class="refresh-btn" onclick="loadAll()">🔄 Rafraîchir</button>
                </div>
            </div>
        </div>

        <div id="memories-tab" class="tab-content active">
            <div class="stats" id="statsGrid"></div>
            <div class="filters memories-toolbar">
                <div class="toolbar-left">
                    <div id="projectFilters" class="combo-host"></div>
                    <div id="categoryFilters" class="combo-host"></div>
                </div>
                <div id="viewToggle" class="toolbar-right">
                    <span style="color:#888;margin-right:5px;">Affichage:</span>
                    <button class="filter-btn active" id="viewCards" type="button" onclick="setMemoryView('cards')">▦ Cards</button>
                    <button class="filter-btn" id="viewList" type="button" onclick="setMemoryView('list')">≣ Liste</button>
                </div>
            </div>
            <div class="bulk-bar" id="bulkBar">
                <span class="bulk-count" id="bulkCount">0 sélectionnée(s)</span>
                <button class="link-btn" type="button" onclick="selectAllMemories()">Tout sélectionner</button>
                <button class="link-btn" type="button" onclick="clearSelection()">Tout désélectionner</button>
                <button class="danger-btn" id="bulkDeleteBtn" type="button" onclick="deleteSelectedMemories()">🗑 Supprimer la sélection</button>
            </div>
            <div class="memories-grid" id="memoriesGrid"><div class="loading">Chargement...</div></div>
        </div>

        <div class="mem-detail-backdrop" id="memDetailBackdrop" onclick="if(event.target===this)closeMemoryDetail()">
            <div class="mem-detail" id="memDetail" role="dialog" aria-modal="true" aria-label="Détail de la mémoire">
                <div class="mem-detail-head">
                    <span class="memory-type mem-detail-type"></span>
                    <span class="memory-importance mem-detail-stars"></span>
                    <div class="mem-detail-actions">
                        <button class="mem-detail-nav" type="button" aria-label="Mémoire précédente" onclick="navigateDetail(-1)">‹</button>
                        <button class="mem-detail-nav" type="button" aria-label="Mémoire suivante" onclick="navigateDetail(1)">›</button>
                        <button class="mem-detail-del" type="button" aria-label="Supprimer cette mémoire" title="Supprimer cette mémoire" onclick="deleteDetailMemory()">🗑</button>
                        <button class="mem-detail-close" type="button" aria-label="Fermer" onclick="closeMemoryDetail()">✕</button>
                    </div>
                </div>
                <div class="mem-detail-body">
                    <h2 class="mem-detail-title"></h2>
                    <div class="mem-detail-content"></div>
                    <div class="mem-detail-tags"></div>
                    <div class="mem-detail-meta"></div>
                </div>
            </div>
        </div>

        <div id="search-tab" class="tab-content">
            <div class="controls">
                <input type="text" class="search-box" id="searchInput" placeholder="🔍 Recherche sémantique..." onkeypress="if(event.key==='Enter')doSearch()">
                <button class="search-btn" onclick="doSearch()">Rechercher</button>
            </div>
            <div class="memories-grid" id="searchResults"><div class="loading" style="color:#666">Entrez une requête pour rechercher dans vos mémoires</div></div>
        </div>

        <div id="graph-tab" class="tab-content">
            <div class="gr-stage" id="grStage">
                <svg id="grSvg" viewBox="0 0 2000 1160" preserveAspectRatio="xMidYMid meet"><g id="grPan"><g id="grG"></g></g></svg>
                <div class="gr-crumb" id="grCrumb"></div>
                <aside class="gr-panel" id="grPanel">
                    <div class="gr-p-head">
                        <h3 id="grPTitle"></h3>
                        <button class="mem-detail-del" type="button" id="grPDel" aria-label="Supprimer cette mémoire" title="Supprimer cette mémoire">🗑</button>
                        <button class="mem-detail-close" type="button" id="grPClose" aria-label="Fermer">✕</button>
                    </div>
                    <div class="gr-p-body">
                        <div id="grPFlag"></div>
                        <div class="gr-txt" id="grPTxt"></div>
                        <dl class="gr-meta" id="grPMeta"></dl>
                        <div class="gr-near" id="grPNear"></div>
                        <div class="memory-tags" id="grPTags"></div>
                    </div>
                </aside>
            </div>
            <div class="gr-footer" id="grFooter">
                <div class="gr-statline">
                    <span><em id="grS1">0</em> mémoires</span>
                    <span><em id="grS2">0</em> projets</span>
                    <span><em id="grS3">0</em> sous le seuil d'activation</span>
                </div>
                <div class="gr-legend" id="grLegend"></div>
            </div>
        </div>

        <div id="prompts-tab" class="tab-content">
            <div id="promptsList"><div class="loading">Chargement...</div></div>
        </div>
    </div>

    <script>
        const API = '';
        const API_KEY = '__API_KEY__';
        const _origFetch = window.fetch.bind(window);
        window.fetch = function(input, init) {
            init = init || {};
            const headers = new Headers(init.headers || {});
            if (API_KEY) headers.set('X-API-Key', API_KEY);
            init.headers = headers;
            return _origFetch(input, init);
        };
        // Thème clair/sombre (persisté, clair par défaut)
        function applyTheme(mode) {
            document.documentElement.setAttribute('data-theme', mode);
            const btn = document.getElementById('themeToggle');
            if (btn) btn.textContent = mode === 'dark' ? '☀️' : '🌙';
            try { localStorage.setItem('synaptic-theme', mode); } catch (e) {}
        }
        function toggleTheme() {
            const cur = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
            applyTheme(cur === 'dark' ? 'light' : 'dark');
        }
        (function initTheme() {
            let saved = 'light';
            try { saved = localStorage.getItem('synaptic-theme') || 'light'; } catch (e) {}
            applyTheme(saved);
        })();

        // Pop-over réglages : état de connexion, auto-refresh, thème, rafraîchir
        (function () {
            const btn = document.getElementById('settingsBtn');
            const pop = document.getElementById('settingsPop');
            const bd = document.getElementById('settingsBackdrop');
            const setOpen = (open) => {
                pop.classList.toggle('open', open);
                bd.classList.toggle('open', open);
                btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            };
            btn.addEventListener('click', () => setOpen(!pop.classList.contains('open')));
            document.getElementById('demoMode').addEventListener('change', (e) => applyDemoMode(e.target.checked, true));
            bd.addEventListener('click', () => setOpen(false));
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && pop.classList.contains('open')) setOpen(false);
            });
        })();

        // ---------- Mode Démo : pseudonymisation des projets + floutage des contenus ----------
        let demoMode = false;
        try { demoMode = localStorage.getItem('synaptic-demo') === '1'; } catch (e) {}
        let demoAliases = new Map();

        function demoLetters(i) {
            let s = '';
            do { s = String.fromCharCode(65 + (i % 26)) + s; i = Math.floor(i / 26) - 1; } while (i >= 0);
            return s;
        }

        // Correspondance stable : ordre alphabétique des projets connus → Projet A, B, C…
        function rebuildDemoAliases() {
            const names = [...new Set([
                ...(window.allProjects || []).map(p => p.project),
                ...(window.graphProjects || []),
            ])].filter(Boolean).sort((a, b) => a.localeCompare(b, 'fr', { sensitivity: 'base' }));
            demoAliases = new Map(names.map((n, i) => [n, 'Projet ' + demoLetters(i)]));
        }

        function demoProject(name) {
            if (!demoMode || !name) return name;
            if (!demoAliases.has(name)) rebuildDemoAliases();
            return demoAliases.get(name) || 'Projet ?';
        }

        function applyDemoMode(on, rerender) {
            demoMode = on;
            try { localStorage.setItem('synaptic-demo', on ? '1' : '0'); } catch (e) {}
            document.body.classList.toggle('demo-on', on);
            const box = document.getElementById('demoMode');
            if (box) box.checked = on;
            if (!rerender) return;
            rebuildDemoAliases();
            renderMemories(false);
            renderProjectFilter();
            loadPrompts();
            if (window.graphApplyDemo) window.graphApplyDemo();
        }

        let currentCategory = null;
        let currentProject = null;
        let projectSort = 'count'; // 'count' = nb de mémoires, 'alpha' = ordre alphabétique
        let projHighlight = -1; // index surligné au clavier dans la liste projet (-1 = aucun)
        let memoryView = 'cards'; // 'cards' ou 'list'
        let lastDetailRow = null; // carte/rangée ayant ouvert le détail (cible du morph retour)
        let detailIndex = -1; // index de la mémoire affichée dans le détail (navigation ‹/›)
        let lastMemoryId = null;
        let autoRefreshInterval = null;
        const selectedIds = new Set(); // ids des mémoires cochées (survit aux rafraîchissements)
        let currentDetailMemory = null; // mémoire affichée dans le modal détail

        // Tabs
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                btn.classList.add('active');
                document.getElementById(btn.dataset.tab + '-tab').classList.add('active');
                document.getElementById('grTools').hidden = btn.dataset.tab !== 'graph';
                if (btn.dataset.tab === 'graph' && window.initGraphTab) window.initGraphTab();
            });
        });

        // Auto-refresh toggle
        document.getElementById('autoRefresh').addEventListener('change', (e) => {
            if (e.target.checked) {
                startAutoRefresh();
            } else {
                stopAutoRefresh();
            }
        });

        function startAutoRefresh() {
            if (autoRefreshInterval) clearInterval(autoRefreshInterval);
            autoRefreshInterval = setInterval(silentRefresh, 5000);
        }

        function stopAutoRefresh() {
            if (autoRefreshInterval) {
                clearInterval(autoRefreshInterval);
                autoRefreshInterval = null;
            }
        }

        // Refresh silencieux sans indicateur de chargement
        async function silentRefresh() {
            try {
                await Promise.all([loadStats(), loadMemories(), loadPrompts()]);
            } catch (err) {
                console.error('Erreur refresh:', err);
            }
        }

        let lastStatsHash = '';
        async function loadStats() {
            const res = await fetch(API + '/api/stats');
            const data = await res.json();

            // Hash pour détecter les changements
            const newHash = JSON.stringify([data.total_memories, data.total_prompts, data.recent_week]);

            // Mettre à jour les compteurs dans les tabs (toujours)
            document.getElementById('memCount').textContent = data.total_memories;
            document.getElementById('promptCount').textContent = data.total_prompts;

            // Ne reconstruire que si les données ont changé
            if (newHash === lastStatsHash) return;
            lastStatsHash = newHash;

            let statsHtml = `
                <div class="stat-card"><div class="stat-value">${data.total_memories}</div><div class="stat-label">Mémoires</div></div>
                <div class="stat-card"><div class="stat-value">${data.total_prompts}</div><div class="stat-label">Prompts</div></div>
                <div class="stat-card"><div class="stat-value">${data.recent_week}</div><div class="stat-label">Cette semaine</div></div>
            `;
            data.by_category.slice(0, 5).forEach(c => {
                statsHtml += `<div class="stat-card"><div class="stat-value">${c.count}</div><div class="stat-label">${escapeHtml(c.category)}</div></div>`;
            });
            document.getElementById('statsGrid').innerHTML = statsHtml;

            // Type (catégorie) : combobox identique au projet, alimenté par les 10 catégories + counts
            const ALL_CATEGORIES = ['bugfix', 'decision', 'feature', 'discovery', 'refactor', 'change', 'pattern', 'preference', 'learning', 'error_solution'];
            const catCounts = {};
            data.by_category.forEach(c => { catCounts[c.category] = c.count; });
            window.allCategories = ALL_CATEGORIES.map(cat => ({ category: cat, count: catCounts[cat] || 0 }));
            renderCategoryFilter();

            // Projet : combobox recherche + liste scrollable
            window.allProjects = (data.by_project || []).filter(p => p.project);
            // La liste des projets arrive après le premier rendu : on repasse une fois
            // sur les libellés dès que les pseudonymes sont calculables.
            const aliasesWereEmpty = demoAliases.size === 0;
            rebuildDemoAliases();
            if (demoMode && aliasesWereEmpty && demoAliases.size) {
                renderMemories(false);
                renderProjectFilter();
                loadPrompts();
            }
            renderProjectFilter();
        }

        let lastMemoriesHash = '';
        async function loadMemories() {
            let url = API + '/api/memories?limit=100';
            if (currentCategory) url += '&category=' + encodeURIComponent(currentCategory);
            if (currentProject) url += '&project=' + encodeURIComponent(currentProject);

            const res = await fetch(url);
            const data = await res.json();

            const grid = document.getElementById('memoriesGrid');
            if (data.memories.length === 0) {
                grid.innerHTML = '<div class="loading">Aucune mémoire trouvée</div>';
                lastMemoriesHash = '';
                window.memoriesData = [];
                return;
            }

            // Vérifier si les données ont changé
            const firstId = data.memories[0]?.id;
            const newHash = data.memories.map(m => m.id).join(',');

            if (newHash === lastMemoriesHash) return; // Pas de changement

            const isNew = lastMemoryId && firstId !== lastMemoryId;
            lastMemoryId = firstId;
            lastMemoriesHash = newHash;

            window.memoriesData = data.memories;
            renderMemories(isNew);
        }

        async function loadPrompts() {
            const res = await fetch(API + '/api/prompts?limit=100');
            const data = await res.json();

            const list = document.getElementById('promptsList');
            if (data.prompts.length === 0) {
                list.innerHTML = '<div class="loading">Aucun prompt</div>';
                return;
            }

            list.innerHTML = data.prompts.map(p => {
                const projectName = p.project ? (demoMode ? demoProject(p.project) : p.project.split('/').pop()) : '';
                const projectBadge = projectName ? `<span class="project-badge">${escapeHtml(projectName)}</span>` : '';
                return `
                <div class="prompt-card">
                    <div class="prompt-text">${escapeHtml(p.text || '')}</div>
                    <div class="prompt-meta">${projectBadge} #${p.number || '-'} | ${formatDate(p.created_at)}</div>
                </div>
            `}).join('');
        }

        async function doSearch() {
            const query = document.getElementById('searchInput').value.trim();
            if (!query) return;

            const results = document.getElementById('searchResults');
            results.innerHTML = '<div class="loading">Recherche en cours...</div>';

            try {
                const res = await fetch(API + '/api/search?q=' + encodeURIComponent(query) + '&limit=20');
                const data = await res.json();

                if (data.results.length === 0) {
                    results.innerHTML = '<div class="loading">Aucun résultat trouvé</div>';
                    return;
                }

                results.innerHTML = data.results.map(m => renderMemoryCard(m, false, true, false)).join('');
                attachExpandListeners();
                attachDeleteListeners(document.getElementById('searchResults'));
            } catch (err) {
                // Security: Don't expose detailed error messages
                console.error('Search error:', err);
                results.innerHTML = '<div class="loading" style="color:#ef4444">Une erreur est survenue. Veuillez réessayer.</div>';
            }
        }

        function renderMemoryCard(m, isNew = false, showSimilarity = false, selectable = true) {
            const stars = '★'.repeat(Math.round((m.importance || 0.5) * 5)) + '☆'.repeat(5 - Math.round((m.importance || 0.5) * 5));
            const tags = (m.tags || []).slice(0, 5).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('');
            const project = m.project ? `<span class="project-badge">${escapeHtml(demoProject(m.project).substring(0, 20))}</span>` : '';
            const similarity = showSimilarity && m.similarity ? `<span class="memory-similarity">Similarité: ${(m.similarity * 100).toFixed(1)}%</span>` : '';
            // Security: Escape data attributes to prevent XSS
            const safeCategory = escapeHtml(m.category || '');
            const safeProject = escapeHtml(m.project || '');
            const safeId = escapeHtml(m.id || '');
            const checked = selectedIds.has(m.id) ? 'checked' : '';

            return `
                <div class="memory-card ${isNew ? 'new' : ''}" data-id="${safeId}" data-type="${safeCategory}" data-project="${safeProject}">
                    <div class="memory-header">
                        ${selectable ? `<input type="checkbox" class="mem-select" data-id="${safeId}" ${checked} aria-label="Sélectionner cette mémoire">` : ''}
                        <span class="memory-type type-${safeCategory}">${safeCategory}</span>
                        <span class="memory-importance" style="margin-left:auto">${stars}</span>
                        <button class="del-btn" type="button" data-id="${safeId}" title="Supprimer cette mémoire" aria-label="Supprimer cette mémoire">🗑</button>
                    </div>
                    ${similarity}
                    <div class="memory-summary">${escapeHtml(m.summary || '')}</div>
                    <div class="memory-content">${escapeHtml(m.content || '')}</div>
                    <button class="expand-btn">Voir plus ▼</button>
                    <div class="memory-tags">${tags}</div>
                    <div class="memory-meta">
                        <span>${project}</span>
                        <span>Accès: ${m.access_count || 0} | ${formatDate(m.created_at)}</span>
                    </div>
                </div>
            `;
        }

        function renderMemoryRow(m) {
            const stars = '★'.repeat(Math.round((m.importance || 0.5) * 5)) + '☆'.repeat(5 - Math.round((m.importance || 0.5) * 5));
            const safeCategory = escapeHtml(m.category || '');
            const safeProject = escapeHtml(m.project || '');
            const title = escapeHtml(m.summary || '');
            const desc = escapeHtml(m.content || '');
            const proj = m.project ? escapeHtml(demoProject(m.project)) : '';
            const safeId = escapeHtml(m.id || '');
            const checked = selectedIds.has(m.id) ? 'checked' : '';
            return `
                <div class="memory-card" data-id="${safeId}" data-type="${safeCategory}" data-project="${safeProject}">
                    <input type="checkbox" class="mem-select" data-id="${safeId}" ${checked} aria-label="Sélectionner cette mémoire">
                    <span class="memory-type type-${safeCategory}">${safeCategory}</span>
                    <span class="memory-importance">${stars}</span>
                    <span class="mem-title" title="${title}">${title}</span>
                    <span class="mem-desc" title="${desc}">${desc}</span>
                    <span class="mem-proj" title="${proj}">${proj}</span>
                    <span class="mem-time">${formatDate(m.created_at)}</span>
                    <span class="mem-actions"><button class="del-btn" type="button" data-id="${safeId}" title="Supprimer cette mémoire" aria-label="Supprimer cette mémoire">🗑</button></span>
                </div>
            `;
        }

        function renderMemories(isNew) {
            const grid = document.getElementById('memoriesGrid');
            if (!grid) return;
            const mems = window.memoriesData || [];
            if (!mems.length) {
                grid.className = 'memories-grid';
                grid.innerHTML = '<div class="loading">Aucune mémoire trouvée</div>';
                return;
            }
            if (memoryView === 'list') {
                grid.className = 'memories-list';
                let html = '<div class="mem-list-head"><span><input type="checkbox" class="mem-select" id="selectAllBox" aria-label="Tout sélectionner" onclick="toggleSelectAll(this.checked)"></span><span>Type</span><span>Import.</span><span>Titre</span><span>Description</span><span>Projet</span><span>Date</span><span></span></div>';
                html += mems.map(m => renderMemoryRow(m)).join('');
                grid.innerHTML = html;
                grid.querySelectorAll('.memory-card').forEach((row, i) => {
                    row.tabIndex = 0;
                    row.addEventListener('click', (e) => {
                        if (e.target.closest('.mem-select') || e.target.closest('.del-btn')) return;
                        openMemoryDetail(mems[i], row, i);
                    });
                    row.addEventListener('keydown', (e) => {
                        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openMemoryDetail(mems[i], row, i); }
                    });
                });
                attachSelectionListeners(grid);
                attachDeleteListeners(grid);
            } else {
                grid.className = 'memories-grid';
                grid.innerHTML = mems.map((m, i) => renderMemoryCard(m, isNew && i === 0)).join('');
                attachExpandListeners();
                grid.querySelectorAll('.memory-card').forEach((card, i) => {
                    card.tabIndex = 0;
                    card.addEventListener('click', (e) => {
                        if (e.target.closest('.expand-btn')) return; // « Voir plus » ne déclenche pas le détail
                        if (e.target.closest('.mem-select') || e.target.closest('.del-btn')) return;
                        openMemoryDetail(mems[i], card, i);
                    });
                    card.addEventListener('keydown', (e) => {
                        if ((e.key === 'Enter' || e.key === ' ') && e.target === card) { e.preventDefault(); openMemoryDetail(mems[i], card, i); }
                    });
                });
                attachSelectionListeners(grid);
                attachDeleteListeners(grid);
            }
            updateBulkBar();
        }

        function attachExpandListeners() {
            document.querySelectorAll('.expand-btn').forEach(btn => {
                btn.onclick = () => {
                    const content = btn.previousElementSibling;
                    content.classList.toggle('expanded');
                    btn.textContent = content.classList.contains('expanded') ? 'Réduire ▲' : 'Voir plus ▼';
                };
            });
        }

        // Remplit le contenu du panneau détail pour une mémoire donnée
        function populateDetail(m) {
            const panel = document.getElementById('memDetail');
            if (!panel) return;
            currentDetailMemory = m;
            const cat = (m.category || '').replace(/[^a-z0-9_-]/gi, '');
            const stars = '★'.repeat(Math.round((m.importance || 0.5) * 5)) + '☆'.repeat(5 - Math.round((m.importance || 0.5) * 5));
            const typeEl = panel.querySelector('.mem-detail-type');
            typeEl.className = 'memory-type mem-detail-type type-' + cat;
            typeEl.textContent = m.category || '';
            panel.querySelector('.mem-detail-stars').textContent = stars;
            panel.querySelector('.mem-detail-title').textContent = m.summary || '';
            panel.querySelector('.mem-detail-content').textContent = m.content || '';
            panel.querySelector('.mem-detail-tags').innerHTML = (m.tags || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('');
            panel.querySelector('.mem-detail-meta').innerHTML =
                (m.project ? `<span>📁 ${escapeHtml(demoProject(m.project))}</span>` : '') +
                `<span>👁 ${m.access_count || 0} accès</span>` +
                `<span>🕒 ${formatDate(m.created_at)}</span>`;
        }

        // Ouvre la vue détaillée avec morph FLIP (carte/rangée → modal), navigable
        function openMemoryDetail(m, rowEl, index) {
            const backdrop = document.getElementById('memDetailBackdrop');
            const panel = document.getElementById('memDetail');
            if (!backdrop || !panel) return;
            detailIndex = (typeof index === 'number') ? index : -1;
            populateDetail(m);
            lastDetailRow = rowEl || null;
            const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            const body = panel.querySelector('.mem-detail-body');
            body.style.transition = ''; body.style.opacity = ''; body.style.transform = '';
            backdrop.classList.add('open');
            panel.style.display = 'flex';
            panel.style.transition = 'none';
            panel.style.transform = 'none';
            document.body.style.overflow = 'hidden';

            const closeBtn = panel.querySelector('.mem-detail-close');
            if (reduce || !rowEl) {
                panel.classList.add('body-in');
                closeBtn.focus();
                return;
            }
            const last = panel.getBoundingClientRect();
            const first = rowEl.getBoundingClientRect();
            const dx = first.left - last.left;
            const dy = first.top - last.top;
            const sx = Math.max(first.width / last.width, 0.05);
            const sy = Math.max(first.height / last.height, 0.05);
            panel.style.transformOrigin = 'top left';
            panel.style.transform = `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`;
            panel.classList.remove('body-in');
            requestAnimationFrame(() => requestAnimationFrame(() => {
                panel.style.transition = 'transform 340ms cubic-bezier(0.22, 1, 0.36, 1)';
                panel.style.transform = 'none';
                panel.classList.add('body-in');
            }));
            closeBtn.focus();
        }

        function closeMemoryDetail() {
            const backdrop = document.getElementById('memDetailBackdrop');
            const panel = document.getElementById('memDetail');
            if (!backdrop || !panel || panel.style.display === 'none') return;
            const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            const rowEl = (lastDetailRow && document.body.contains(lastDetailRow)) ? lastDetailRow : null;
            const finish = () => {
                panel.style.display = 'none';
                panel.style.transition = 'none';
                panel.style.transform = 'none';
                panel.classList.remove('body-in');
                backdrop.classList.remove('open');
                document.body.style.overflow = '';
                lastDetailRow = null;
            };
            if (reduce || !rowEl) { panel.classList.remove('body-in'); backdrop.classList.remove('open'); setTimeout(finish, 90); return; }
            const last = panel.getBoundingClientRect();
            const first = rowEl.getBoundingClientRect();
            const dx = first.left - last.left;
            const dy = first.top - last.top;
            const sx = Math.max(first.width / last.width, 0.05);
            const sy = Math.max(first.height / last.height, 0.05);
            panel.classList.remove('body-in');
            panel.style.transformOrigin = 'top left';
            panel.style.transition = 'transform 280ms cubic-bezier(0.4, 0, 1, 1)';
            panel.style.transform = `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`;
            backdrop.classList.remove('open');
            let done = false;
            const onEnd = () => { if (done) return; done = true; panel.removeEventListener('transitionend', onEnd); finish(); };
            panel.addEventListener('transitionend', onEnd);
            setTimeout(onEnd, 420);
        }

        // Navigation d'une mémoire à l'autre dans le modal (avec slide directionnel)
        function navigateDetail(delta) {
            const panel = document.getElementById('memDetail');
            const backdrop = document.getElementById('memDetailBackdrop');
            if (!panel || !backdrop || !backdrop.classList.contains('open')) return;
            const mems = window.memoriesData || [];
            if (mems.length < 2 || detailIndex < 0) return;
            const n = (detailIndex + delta + mems.length) % mems.length;
            detailIndex = n;
            // recaler la cible du morph-retour sur l'élément correspondant
            const els = document.querySelectorAll('#memoriesGrid .memory-card');
            if (els[n]) { lastDetailRow = els[n]; els[n].scrollIntoView({ block: 'nearest' }); }
            const body = panel.querySelector('.mem-detail-body');
            const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            if (reduce) { populateDetail(mems[n]); return; }
            body.style.transition = 'none';
            body.style.opacity = '0';
            body.style.transform = `translateX(${delta > 0 ? 16 : -16}px)`;
            populateDetail(mems[n]);
            requestAnimationFrame(() => requestAnimationFrame(() => {
                body.style.transition = 'opacity 170ms ease, transform 220ms cubic-bezier(0.22, 1, 0.36, 1)';
                body.style.opacity = '1';
                body.style.transform = 'none';
            }));
        }

        document.addEventListener('keydown', (e) => {
            const bd = document.getElementById('memDetailBackdrop');
            if (!bd || !bd.classList.contains('open')) return;
            if (e.key === 'Escape') closeMemoryDetail();
            else if (e.key === 'ArrowLeft') { e.preventDefault(); navigateDetail(-1); }
            else if (e.key === 'ArrowRight') { e.preventDefault(); navigateDetail(1); }
        });

        // ---------- Sélection multiple & suppression ----------
        function attachSelectionListeners(root) {
            root.querySelectorAll('.mem-select[data-id]').forEach(box => {
                box.addEventListener('click', (e) => e.stopPropagation());
                box.addEventListener('change', (e) => {
                    const id = box.dataset.id;
                    if (box.checked) selectedIds.add(id); else selectedIds.delete(id);
                    updateBulkBar();
                });
            });
        }

        function attachDeleteListeners(root) {
            root.querySelectorAll('.del-btn[data-id]').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    deleteMemory(btn.dataset.id);
                });
            });
        }

        function updateBulkBar() {
            const bar = document.getElementById('bulkBar');
            const count = document.getElementById('bulkCount');
            if (!bar || !count) return;
            const n = selectedIds.size;
            bar.classList.toggle('open', n > 0);
            count.textContent = n + ' mémoire(s) sélectionnée(s)';
            const all = document.getElementById('selectAllBox');
            const mems = window.memoriesData || [];
            if (all) all.checked = mems.length > 0 && mems.every(m => selectedIds.has(m.id));
        }

        function selectAllMemories() {
            (window.memoriesData || []).forEach(m => selectedIds.add(m.id));
            document.querySelectorAll('#memoriesGrid .mem-select[data-id]').forEach(b => b.checked = true);
            updateBulkBar();
        }

        function clearSelection() {
            selectedIds.clear();
            document.querySelectorAll('#memoriesGrid .mem-select').forEach(b => b.checked = false);
            updateBulkBar();
        }

        function toggleSelectAll(checked) {
            if (checked) selectAllMemories(); else clearSelection();
        }

        // Recharge la liste après suppression (le hash force le re-rendu)
        async function refreshAfterDelete() {
            lastMemoriesHash = '';
            lastMemoryId = null;
            await Promise.all([loadStats(), loadMemories()]);
        }

        async function deleteMemory(id) {
            if (!id) return;
            const mem = (window.memoriesData || []).find(m => m.id === id);
            const label = mem && mem.summary ? '\\n\\n« ' + mem.summary.substring(0, 120) + ' »' : '';
            if (!confirm('Supprimer définitivement cette mémoire ?' + label)) return;
            try {
                const res = await fetch(API + '/api/memories/' + encodeURIComponent(id), { method: 'DELETE' });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                selectedIds.delete(id);
                if (currentDetailMemory && currentDetailMemory.id === id) closeMemoryDetail();
                await refreshAfterDelete();
            } catch (err) {
                console.error('Delete error:', err);
                alert('La suppression a échoué. Veuillez réessayer.');
            }
        }

        async function deleteSelectedMemories() {
            const ids = Array.from(selectedIds);
            if (!ids.length) return;
            if (!confirm('Supprimer définitivement ' + ids.length + ' mémoire(s) ? Cette action est irréversible.')) return;
            const btn = document.getElementById('bulkDeleteBtn');
            if (btn) btn.disabled = true;
            try {
                const res = await fetch(API + '/api/memories/bulk-delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids })
                });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                selectedIds.clear();
                await refreshAfterDelete();
                if (data.deleted !== data.requested) {
                    alert(data.deleted + ' mémoire(s) supprimée(s) sur ' + data.requested + ' demandée(s).');
                }
            } catch (err) {
                console.error('Bulk delete error:', err);
                alert('La suppression a échoué. Veuillez réessayer.');
            } finally {
                if (btn) btn.disabled = false;
            }
        }

        function deleteDetailMemory() {
            if (currentDetailMemory && currentDetailMemory.id) deleteMemory(currentDetailMemory.id);
        }

        function setMemoryView(mode) {
            memoryView = mode;
            const grid = document.getElementById('memoriesGrid');
            if (grid) grid.className = (mode === 'list') ? 'memories-list' : 'memories-grid';
            const bc = document.getElementById('viewCards');
            const bl = document.getElementById('viewList');
            if (bc) bc.classList.toggle('active', mode === 'cards');
            if (bl) bl.classList.toggle('active', mode === 'list');
            renderMemories(false);
        }

        function filterCategory(cat) {
            currentCategory = cat;
            loadMemories();
            loadStats();
        }

        function filterProject(proj) {
            currentProject = proj;
            loadMemories();
            loadStats();
        }

        // Combobox générique réutilisable : recherche + liste scrollable + tri Nb/A–Z + navigation clavier
        function createCombo(cfg) {
            const combo = { sort: 'count', highlight: -1 };
            const id = (suffix) => cfg.key + suffix;
            combo.render = function() {
                const host = document.getElementById(cfg.hostId);
                if (!host) return;
                const input = document.getElementById(id('Search'));
                const list = document.getElementById(id('List'));
                const interacting = input && (document.activeElement === input || (list && list.classList.contains('open')));
                if (!document.getElementById(id('Combo'))) {
                    host.innerHTML =
                        '<label style="color:#888;margin-right:8px;">' + cfg.label + '</label>' +
                        '<div class="project-combo" id="' + id('Combo') + '">' +
                          '<input type="text" id="' + id('Search') + '" class="project-search" autocomplete="off" placeholder="' + cfg.placeholder + '">' +
                          '<button type="button" id="' + id('SortCount') + '" class="sort-btn">Nb ↓</button>' +
                          '<button type="button" id="' + id('SortAlpha') + '" class="sort-btn">A–Z</button>' +
                          '<div class="project-list" id="' + id('List') + '"></div>' +
                        '</div>';
                    combo.wire();
                }
                if (interacting) return; // ne pas écraser la saisie en cours pendant un auto-refresh
                const inp = document.getElementById(id('Search'));
                inp.value = cfg.getCurrent() || '';
                combo.build('');
            };
            combo.setSort = function(mode) {
                combo.sort = mode;
                const bc = document.getElementById(id('SortCount'));
                const ba = document.getElementById(id('SortAlpha'));
                if (bc) bc.classList.toggle('active', mode === 'count');
                if (ba) ba.classList.toggle('active', mode === 'alpha');
                const inp = document.getElementById(id('Search'));
                combo.build(inp ? inp.value : '');
                const list = document.getElementById(id('List'));
                if (list) list.classList.add('open');
            };
            combo.wire = function() {
                const inp = document.getElementById(id('Search'));
                const list = document.getElementById(id('List'));
                const bc = document.getElementById(id('SortCount'));
                const ba = document.getElementById(id('SortAlpha'));
                bc.classList.toggle('active', combo.sort === 'count');
                ba.classList.toggle('active', combo.sort === 'alpha');
                bc.addEventListener('click', () => combo.setSort('count'));
                ba.addEventListener('click', () => combo.setSort('alpha'));
                inp.addEventListener('focus', () => { inp.select(); combo.build(''); list.classList.add('open'); });
                inp.addEventListener('input', () => { combo.build(inp.value); list.classList.add('open'); });
                inp.addEventListener('keydown', (e) => {
                    if (e.key === 'ArrowDown') {
                        e.preventDefault();
                        if (!list.classList.contains('open')) { combo.build(inp.value); list.classList.add('open'); }
                        combo.move(1);
                    } else if (e.key === 'ArrowUp') {
                        e.preventDefault();
                        if (!list.classList.contains('open')) { combo.build(inp.value); list.classList.add('open'); }
                        combo.move(-1);
                    } else if (e.key === 'Escape') {
                        list.classList.remove('open'); inp.blur();
                    } else if (e.key === 'Enter') {
                        e.preventDefault();
                        const items = list.querySelectorAll('.project-item');
                        let target = combo.highlight >= 0 ? items[combo.highlight] : null;
                        if (!target) {
                            target = items[0];
                            if (inp.value.trim()) {
                                for (const it of items) { if (it.getAttribute('data-val')) { target = it; break; } }
                            }
                        }
                        if (target) target.click();
                    }
                });
                document.addEventListener('click', (e) => {
                    const c = document.getElementById(id('Combo'));
                    if (c && !c.contains(e.target)) list.classList.remove('open');
                });
            };
            combo.move = function(delta) {
                const list = document.getElementById(id('List'));
                if (!list) return;
                const items = Array.from(list.querySelectorAll('.project-item'));
                if (!items.length) return;
                if (combo.highlight < 0) combo.highlight = delta > 0 ? 0 : items.length - 1;
                else combo.highlight = (combo.highlight + delta + items.length) % items.length;
                items.forEach((it, i) => it.classList.toggle('kb-active', i === combo.highlight));
                items[combo.highlight].scrollIntoView({ block: 'nearest' });
            };
            combo.build = function(filter) {
                const list = document.getElementById(id('List'));
                if (!list) return;
                combo.highlight = -1; // reset surlignage à chaque reconstruction
                const f = (filter || '').toLowerCase();
                let items = (cfg.getItems() || []).slice();
                if (combo.sort === 'alpha') items.sort((a, b) => a.value.localeCompare(b.value, 'fr', { sensitivity: 'base' }));
                else items.sort((a, b) => b.count - a.count);
                const cur = cfg.getCurrent();
                let html = '<div class="project-item" data-val="">' + cfg.allLabel + '</div>';
                items.forEach(p => {
                    const shown = cfg.display ? cfg.display(p.value) : p.value;
                    if (!f || p.value.toLowerCase().includes(f) || shown.toLowerCase().includes(f)) {
                        const act = cur === p.value ? 'active' : '';
                        html += '<div class="project-item ' + act + '" data-val="' + escapeHtml(p.value) + '">' + escapeHtml(shown) + ' <span class="cnt">(' + p.count + ')</span></div>';
                    }
                });
                list.innerHTML = html;
                list.querySelectorAll('.project-item').forEach(item => {
                    item.onclick = () => {
                        const v = item.getAttribute('data-val') || null;
                        const inp = document.getElementById(id('Search'));
                        if (inp) inp.value = v ? (cfg.display ? cfg.display(v) : v) : '';
                        list.classList.remove('open');
                        cfg.onSelect(v);
                    };
                });
            };
            return combo;
        }

        const projectCombo = createCombo({
            key: 'project', hostId: 'projectFilters', label: 'Projet:', allLabel: 'Tous',
            placeholder: 'Tous (taper pour filtrer…)',
            getItems: () => (window.allProjects || []).map(p => ({ value: p.project, count: p.count })),
            display: (v) => demoProject(v),
            getCurrent: () => currentProject,
            onSelect: (v) => filterProject(v)
        });

        const categoryCombo = createCombo({
            key: 'cat', hostId: 'categoryFilters', label: 'Type:', allLabel: 'Tous',
            placeholder: 'Tous (taper pour filtrer…)',
            getItems: () => (window.allCategories || []).map(c => ({ value: c.category, count: c.count })),
            getCurrent: () => currentCategory,
            onSelect: (v) => filterCategory(v)
        });

        function renderProjectFilter() { projectCombo.render(); }
        function renderCategoryFilter() { categoryCombo.render(); }

        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
        }

        // Security: Escape for use in HTML attributes (onclick handlers)
        function escapeAttr(str) {
            if (!str) return '';
            return str
                .replace(/\\\\/g, '\\\\\\\\')
                .replace(/'/g, "\\\\'")
                .replace(/"/g, '\\\\"')
                .replace(/</g, '\\\\x3c')
                .replace(/>/g, '\\\\x3e')
                .replace(/\\n/g, '\\\\n')
                .replace(/\\r/g, '\\\\r');
        }

        function formatDate(iso) {
            if (!iso) return 'N/A';
            const d = new Date(iso);
            return d.toLocaleDateString('fr-FR') + ' ' + d.toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit'});
        }

        // ================= Onglet Graph : atlas radial des mémoires =================
        // Deux niveaux : projets → catégories ; clic sur un projet pour déplier ses mémoires.
        (function () {
            const PAL = ['#4F8DF5','#00B468','#E0A21C','#8B6CE0','#16B8C0','#EE2238','#8a8f9c','#BF1D67','#7CB342','#E06A66'];
            const TAU = Math.PI * 2;
            // Le viewBox épouse le format de la scène : la couronne remplit la hauteur
            // disponible et les libellés disposent de la largeur restante.
            const VB_H = 1160;
            let VB_W = 2000, CX = 1000, CY = VB_H / 2;
            let D = null, M = [], EDG = [], CATS = [], PROJ = [], CC = {}, byId = {}, nb = {}, dupN = new Set();
            let groups = [], focus = null, loaded = false, loading = false;
            const f = { q: '', cats: new Set(), sel: null };
            const clip = (t, n) => t.length > n ? t.slice(0, n - 1) + '…' : t;
            const $ = id => document.getElementById(id);

            function indexEdges() {
                nb = {};
                for (const e of EDG) { (nb[e.a] = nb[e.a] || []).push(e); (nb[e.b] = nb[e.b] || []).push(e); }
                dupN = new Set(EDG.filter(e => e.s >= D.dupThreshold).flatMap(e => [e.a, e.b]));
            }

            async function load() {
                if (loading) return;
                loading = true;
                $('grCrumb').innerHTML = '<span>Chargement de l\\'atlas…</span>';
                try {
                    const res = await fetch(API + '/api/graph');
                    if (!res.ok) throw new Error('HTTP ' + res.status);
                    D = await res.json();
                    M = D.memories; EDG = []; CATS = D.categories; PROJ = D.projects;
                    CC = {}; CATS.forEach((c, i) => CC[c] = PAL[i % PAL.length]);
                    window.graphProjects = PROJ;
                    rebuildDemoAliases();
                    byId = Object.fromEntries(M.map(m => [m.i, m]));
                    indexEdges();
                    groups = PROJ.map(pr => ({ name: pr, items: M.filter(m => m.p === pr) }))
                                 .filter(g => g.items.length)
                                 .sort((a, b) => b.items.length - a.items.length);
                    $('grS1').textContent = M.length;
                    $('grS2').textContent = groups.length;
                    $('grS3').textContent = M.filter(m => m.act <= 0).length;
                    renderLegend();
                    fitStage();
                    focus = null;
                    $('grCrumb').innerHTML = '';
                    render();
                    loaded = true;
                } catch (err) {
                    console.error('Graph load error:', err);
                    $('grCrumb').innerHTML = '<span style="color:var(--z-red)">Chargement de l\\'atlas impossible.</span>';
                } finally {
                    loading = false;
                }
            }

            // Voisins sémantiques : calculés à la demande, pour le projet déplié seulement
            async function loadEdges(project) {
                try {
                    const res = await fetch(API + '/api/graph/edges?project=' + encodeURIComponent(project));
                    if (!res.ok) throw new Error('HTTP ' + res.status);
                    const data = await res.json();
                    EDG = data.edges || [];
                } catch (err) {
                    console.error('Graph edges error:', err);
                    EDG = [];
                }
                indexEdges();
            }

            function render() {
                if (!D) return;
                const gs = focus ? groups.filter(g => g.name === focus) : groups;
                const tot = gs.reduce((a, g) => a + g.items.length, 0);
                if (!tot) { $('grG').innerHTML = ''; return; }
                const gap = focus ? 0 : 0.10, span = TAU - gap * gs.length;
                // rayons calés sur le viewBox 2000x1250 : la couronne externe reste dans le cadre
                const R = focus ? { p: 130, c: 275, m: 355, step: 38, rings: 5 } : { p: 235, c: 465 };
                const p = [];
                p.push(`<circle class="ring" cx="${CX}" cy="${CY}" r="${R.p}"/><circle class="ring" cx="${CX}" cy="${CY}" r="${R.c}"/>`);
                p.push(`<circle cx="${CX}" cy="${CY}" r="4" fill="var(--text-dim)"/>`);
                if (!focus) p.push(`<text class="core" x="${CX}" y="${CY + 24}" text-anchor="middle">banque de mémoires</text>`);

                let a = -Math.PI / 2 + gap / 2;
                for (const g of gs) {
                    const arc = span * g.items.length / tot, mid = a + arc / 2;
                    const hx = CX + R.p * Math.cos(mid), hy = CY + R.p * Math.sin(mid);
                    const cats = {}; g.items.forEach(m => (cats[m.c] = cats[m.c] || []).push(m));
                    const ks = Object.keys(cats).sort((x, y) => cats[y].length - cats[x].length);
                    p.push(`<path class="edge" d="M${CX},${CY} L${hx.toFixed(1)},${hy.toFixed(1)}" stroke="var(--text-dim)"/>`);

                    let ca = a + arc * 0.03; const cspan = arc * 0.94;
                    for (const k of ks) {
                        const carc = cspan * cats[k].length / g.items.length, cmid = ca + carc / 2;
                        const kx = CX + R.c * Math.cos(cmid), ky = CY + R.c * Math.sin(cmid);
                        p.push(`<path class="edge" d="M${hx.toFixed(1)},${hy.toFixed(1)} L${kx.toFixed(1)},${ky.toFixed(1)}" stroke="${CC[k]}"/>`);

                        if (focus) {
                            cats[k].forEach((m, i) => {
                                const n = cats[k].length, t = n === 1 ? 0.5 : i / (n - 1);
                                const ang = ca + carc * 0.05 + carc * 0.90 * t, r = R.m + (i % R.rings) * R.step;
                                const mx = CX + r * Math.cos(ang), my = CY + r * Math.sin(ang);
                                p.push(`<path class="edge thin" d="M${kx.toFixed(1)},${ky.toFixed(1)} L${mx.toFixed(1)},${my.toFixed(1)}" stroke="${CC[k]}"/>`);
                                const rad = (3 + m.imp * 2.6).toFixed(1);
                                const dormant = m.act <= 0 || m.st !== 'active';
                                p.push(`<g class="node" data-i="${escapeHtml(m.i)}" transform="translate(${mx.toFixed(1)},${my.toFixed(1)})">`
                                    + (dupN.has(m.i) ? `<circle r="${+rad + 4}" fill="none" stroke="var(--z-red)" stroke-width="1.1"/>` : '')
                                    + `<circle r="${rad}" fill="${dormant ? 'var(--surface)' : CC[k]}" stroke="${CC[k]}" stroke-width="${dormant ? 1.4 : 1}"/></g>`);
                            });
                        }
                        const cd = cmid * 180 / Math.PI, cf = Math.cos(cmid) < 0;
                        const crad = focus ? 6 : (4 + Math.sqrt(cats[k].length) * 0.75);
                        p.push(`<g class="node cat" data-cat="${escapeHtml(k)}" transform="translate(${kx.toFixed(1)},${ky.toFixed(1)})">`
                            + `<circle r="${crad.toFixed(1)}" fill="${CC[k]}" opacity=".16"/>`
                            + `<circle r="${(crad * 0.55).toFixed(1)}" fill="${CC[k]}" stroke="var(--surface)" stroke-width="1"/>`
                            + `<text class="clab" x="${cf ? -(crad + 7) : crad + 7}" y="3.5" text-anchor="${cf ? 'end' : 'start'}" `
                            + `transform="rotate(${cf ? cd + 180 : cd})" fill="${CC[k]}">${escapeHtml(k)} · ${cats[k].length}</text></g>`);
                        ca += carc;
                    }
                    const hd = mid * 180 / Math.PI, hf = Math.cos(mid) < 0;
                    p.push(`<g class="node proj" data-proj="${escapeHtml(g.name)}" transform="translate(${hx.toFixed(1)},${hy.toFixed(1)})">`
                        + `<circle r="11" fill="var(--surface)" stroke="var(--text)" stroke-width="1.4"/>`
                        + `<circle r="4" fill="var(--text)"/>`
                        + `<text class="plab" x="${hf ? -18 : 18}" y="-1" text-anchor="${hf ? 'end' : 'start'}" `
                        + `transform="rotate(${hf ? hd + 180 : hd})">${escapeHtml(clip(demoProject(g.name), 24))}</text>`
                        + `<text class="psub" x="${hf ? -18 : 18}" y="13" text-anchor="${hf ? 'end' : 'start'}" `
                        + `transform="rotate(${hf ? hd + 180 : hd})">${g.items.length} mémoires · ${ks.length} catégories</text></g>`);
                    a += arc + gap;
                }
                $('grG').innerHTML = p.join('');
                apply();
            }

            async function setFocus(name) {
                focus = name;
                const gv = $('grG');
                gv.classList.add('swap');
                closePanel();
                $('grCrumb').innerHTML = name
                    ? `<button type="button" id="grBack">← tous les projets</button><b>${escapeHtml(demoProject(name))}</b>`
                    : '';
                const b = $('grBack'); if (b) b.onclick = () => setFocus(null);
                if (name) { await loadEdges(name); } else { EDG = []; indexEdges(); }
                render(); gv.classList.remove('swap'); resetView();
            }

            function pass(m) {
                if (f.cats.size && !f.cats.has(m.c)) return false;
                if (f.q) {
                    const q = f.q.toLowerCase();
                    if (!((m.s || '').toLowerCase().includes(q) || (m.t || '').toLowerCase().includes(q)
                        || (m.g || []).join(' ').toLowerCase().includes(q) || m.p.toLowerCase().includes(q))) return false;
                }
                return true;
            }

            function apply() {
                const q = f.q.trim();
                document.querySelectorAll('#grG .node[data-i]').forEach(el => {
                    const m = byId[el.dataset.i], ok = m ? pass(m) : false;
                    el.classList.toggle('mute', !ok);
                    el.classList.toggle('hit', ok && !!q);
                    el.classList.toggle('sel', el.dataset.i === f.sel);
                });
                document.querySelectorAll('#grG .node.cat').forEach(el =>
                    el.classList.toggle('mute', f.cats.size > 0 && !f.cats.has(el.dataset.cat)));
            }

            function openPanel(m) {
                f.sel = m.i;
                const h = $('grPTitle');
                h.textContent = m.c + ' · ' + demoProject(m.p);
                h.style.color = CC[m.c] || 'var(--text-strong)';
                $('grPFlag').innerHTML = dupN.has(m.i)
                    ? `<div class="gr-flag">Quasi-doublon détecté au-delà de ${(D.dupThreshold * 100).toFixed(0)} % de similarité. Vérifiez les voisins avant toute purge.</div>` : '';
                $('grPTxt').textContent = m.t || m.s || '(vide)';
                $('grPMeta').innerHTML =
                    `<dt>statut</dt><dd>${escapeHtml(m.st)}</dd>`
                    + `<dt>importance</dt><dd>${m.imp.toFixed(2)}<div class="gr-bar" style="color:${CC[m.c]}"><i style="width:${m.imp * 100}%"></i></div></dd>`
                    + `<dt>activation</dt><dd>${m.act.toFixed(2)}${m.act <= 0 ? ' <span style="color:var(--z-red)">sous le seuil</span>' : ''}</dd>`
                    + `<dt>accès</dt><dd>${m.n}× · dernier il y a ${m.age} j</dd>`
                    + `<dt>date</dt><dd>${escapeHtml(m.d || '—')}</dd>`
                    + `<dt>id</dt><dd style="font-size:0.85em">${escapeHtml(m.i)}</dd>`;
                const nn = (nb[m.i] || []).sort((a, b) => b.s - a.s).slice(0, 6);
                $('grPNear').innerHTML = focus
                    ? '<b>Voisins sémantiques</b>' + (nn.length ? nn.map(e => {
                        const o = byId[e.a === m.i ? e.b : e.a];
                        if (!o) return '';
                        return `<a data-grgo="${escapeHtml(o.i)}">${e.s >= D.dupThreshold ? '<em>◆</em> ' : ''}${(e.s * 100).toFixed(0)} % · ${escapeHtml(clip(o.s || '', 56))}</a>`;
                      }).join('') : '<span style="color:var(--text-dim);font-size:0.78em">aucun au-dessus du seuil</span>')
                    : '<span style="color:var(--text-dim);font-size:0.78em">Dépliez un projet pour calculer ses voisins sémantiques.</span>';
                $('grPTags').innerHTML = (m.g || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('');
                $('grPanel').classList.add('open');
                apply();
            }

            function closePanel() { $('grPanel').classList.remove('open'); f.sel = null; apply(); }

            $('grPClose').onclick = closePanel;

            // Suppression depuis le panneau (même contrat que les autres vues)
            $('grPDel').onclick = async () => {
                const m = byId[f.sel];
                if (!m) return;
                const label = m.s ? '\\n\\n« ' + m.s.substring(0, 120) + ' »' : '';
                if (!confirm('Supprimer définitivement cette mémoire ?' + label)) return;
                try {
                    const res = await fetch(API + '/api/memories/' + encodeURIComponent(m.i), { method: 'DELETE' });
                    if (!res.ok) throw new Error('HTTP ' + res.status);
                    closePanel();
                    const keep = focus;
                    await load();
                    lastMemoriesHash = '';
                    loadStats(); loadMemories();
                    if (keep && groups.some(g => g.name === keep)) await setFocus(keep);
                } catch (err) {
                    console.error('Graph delete error:', err);
                    alert('La suppression a échoué. Veuillez réessayer.');
                }
            };

            $('grStage').addEventListener('click', e => {
                const go = e.target.closest('[data-grgo]');
                if (go) {
                    const o = byId[go.dataset.grgo];
                    if (!o) return;
                    if (focus && o.p !== focus) { setFocus(o.p).then(() => openPanel(o)); } else { openPanel(o); }
                    return;
                }
                const mn = e.target.closest('.node[data-i]');
                if (mn) { openPanel(byId[mn.dataset.i]); return; }
                const pr = e.target.closest('.node.proj');
                if (pr) { setFocus(focus ? null : pr.dataset.proj); return; }
                if (e.target.closest('svg')) closePanel();
            });

            document.addEventListener('keydown', e => {
                if (e.key !== 'Escape') return;
                if (!$('graph-tab').classList.contains('active')) return;
                if ($('grPanel').classList.contains('open')) closePanel();
                else if (focus) setFocus(null);
            });

            $('grQ').oninput = e => { f.q = e.target.value; apply(); };

            function renderLegend() {
                $('grLegend').innerHTML = CATS.map(c =>
                    `<button class="gr-chip" type="button" data-c="${escapeHtml(c)}" style="color:${CC[c]}"><i></i>`
                    + `<span style="color:var(--text)">${escapeHtml(c)}</span><u>${M.filter(m => m.c === c).length}</u></button>`
                ).join('') + '<span class="gr-hint">clic sur un projet : déplie ses mémoires · Échap : revenir</span>';
                document.querySelectorAll('#grLegend .gr-chip[data-c]').forEach(c => c.onclick = () => {
                    const k = c.dataset.c;
                    f.cats.has(k) ? f.cats.delete(k) : f.cats.add(k);
                    c.classList.toggle('on');
                    apply();
                });
            }

            // Pan & zoom
            const svg = $('grSvg'), pn = $('grPan');
            let v = { x: 0, y: 0, k: 1 }, dg = null;
            const ap = () => pn.setAttribute('transform', `translate(${v.x},${v.y}) scale(${v.k})`);
            const resetView = () => { v = { x: 0, y: 0, k: 1 }; ap(); };
            svg.addEventListener('wheel', e => {
                e.preventDefault();
                const k = Math.min(6, Math.max(0.55, v.k * (e.deltaY < 0 ? 1.13 : 0.88)));
                const r = svg.getBoundingClientRect(), sc = VB_W / r.width;
                const mx = (e.clientX - r.left) * sc, my = (e.clientY - r.top) * sc;
                v.x = mx - (mx - v.x) * (k / v.k); v.y = my - (my - v.y) * (k / v.k); v.k = k; ap();
            }, { passive: false });
            svg.addEventListener('pointerdown', e => { dg = { x: e.clientX, y: e.clientY, vx: v.x, vy: v.y }; svg.classList.add('drag'); });
            svg.addEventListener('pointermove', e => {
                if (!dg) return;
                const r = svg.getBoundingClientRect(), sc = VB_W / r.width;
                v.x = dg.vx + (e.clientX - dg.x) * sc; v.y = dg.vy + (e.clientY - dg.y) * sc; ap();
            });
            addEventListener('pointerup', () => { dg = null; svg.classList.remove('drag'); });

            // La scène descend jusqu'au bas de la fenêtre, quelle que soit la hauteur de l'en-tête
            function fitStage() {
                const tab = $('graph-tab');
                if (!tab.classList.contains('active')) return;
                const stage = $('grStage');
                const top = stage.getBoundingClientRect().top;
                const legend = $('grFooter').offsetHeight;
                const pad = parseFloat(getComputedStyle(document.body).paddingBottom) || 0;
                stage.style.height = Math.max(360, window.innerHeight - top - legend - pad - 10) + 'px';
                const r = stage.getBoundingClientRect();
                const w = Math.round(VB_H * Math.max(1, r.width / Math.max(1, r.height)));
                if (w !== VB_W) {
                    VB_W = w; CX = VB_W / 2;
                    svg.setAttribute('viewBox', `0 0 ${VB_W} ${VB_H}`);
                    if (loaded) render();
                }
            }
            addEventListener('resize', fitStage);

            window.initGraphTab = () => { fitStage(); if (!loaded) load(); };
            window.graphReload = () => { loaded = false; focus = null; EDG = []; load(); };
            // Bascule du mode démo : re-rendu des libellés (le fil d'Ariane et le panneau inclus)
            window.graphApplyDemo = () => {
                if (!loaded) return;
                if (focus) {
                    $('grCrumb').innerHTML = `<button type="button" id="grBack">← tous les projets</button><b>${escapeHtml(demoProject(focus))}</b>`;
                    const b = $('grBack'); if (b) b.onclick = () => setFocus(null);
                }
                if (f.sel && byId[f.sel]) openPanel(byId[f.sel]);
                render();
            };
        })();

        applyDemoMode(demoMode, false);
        // Filet : si le navigateur restaure l'état des cases après le parsing, on réaligne
        addEventListener('load', () => applyDemoMode(demoMode, false));

        async function loadAll() {
            try {
                await Promise.all([loadStats(), loadMemories(), loadPrompts()]);
            } catch (err) {
                console.error('Erreur:', err);
            }
        }

        // Initial load
        loadAll();
        startAutoRefresh();
    </script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    print("🚀 Démarrage du serveur MCP-Claude-mem-local...")
    print("📍 Interface: http://localhost:8080")
    print("📚 API: http://localhost:8080/api/stats")
    # Security: Bind to localhost only (use reverse proxy for external access)
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8080"))
    uvicorn.run(app, host=host, port=port)
