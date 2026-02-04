#!/usr/bin/env python3
"""API Server pour MCP-Claude-mem-local - Interface dynamique temps réel"""

import hashlib
import logging
import os
import secrets
from contextlib import asynccontextmanager
from functools import wraps
from urllib.parse import urlparse

import asyncpg
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request, HTTPException, Depends, Header
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
ALLOWED_OLLAMA_HOSTS = {"localhost", "127.0.0.1", "host.docker.internal"}
if _parsed_ollama.hostname not in ALLOWED_OLLAMA_HOSTS:
    raise RuntimeError(f"OLLAMA_HOST must be localhost or 127.0.0.1 for security. Got: {_parsed_ollama.hostname}")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

# Security: API Key authentication (optional but recommended)
API_KEY = os.getenv("API_KEY")  # If set, all API endpoints require this key
API_KEY_HEADER = "X-API-Key"

# Security: Rate limiting configuration
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))  # requests per minute
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # window in seconds

# Simple in-memory rate limiter
_rate_limit_store: dict[str, list[float]] = {}


def get_client_ip(request: Request) -> str:
    """Get client IP from request"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(client_ip: str) -> bool:
    """Check if client has exceeded rate limit"""
    import time
    current_time = time.time()

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
    # Skip auth for web interface
    if request.url.path == "/" or request.url.path.startswith("/static"):
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
        # CSP for the web interface
        if request.url.path == "/":
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application"""
    global pool
    pool = await asyncpg.create_pool(
        host=PG_HOST, port=PG_PORT, database=PG_DATABASE,
        user=PG_USER, password=PG_PASSWORD,
        min_size=2, max_size=10
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    allow_credentials=False,
)


@app.get("/api/stats")
async def get_stats(request: Request, _: None = Depends(verify_api_key)):
    """Statistiques globales des mémoires"""
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM memories")
        by_category = await conn.fetch(
            "SELECT category, COUNT(*) as count FROM memories GROUP BY category ORDER BY count DESC"
        )
        by_project = await conn.fetch(
            "SELECT project_context, COUNT(*) as count FROM memories "
            "WHERE project_context IS NOT NULL GROUP BY project_context ORDER BY count DESC LIMIT 10"
        )
        total_prompts = await conn.fetchval("SELECT COUNT(*) FROM user_prompts")
        recent = await conn.fetchval(
            "SELECT COUNT(*) FROM memories WHERE created_at > NOW() - INTERVAL '7 days'"
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
        WHERE ($1::text IS NULL OR category = $1)
          AND ($2::text IS NULL OR project_context = $2)
        ORDER BY created_at DESC
        LIMIT $3 OFFSET $4
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, category, project, limit, offset)

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
        ORDER BY (1 - (embedding <=> $1::vector)) * importance_score DESC
        LIMIT $2
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, embedding_str, limit)

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
            "ORDER BY created_at DESC LIMIT $1", limit
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
    return HTML_TEMPLATE


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MCP-Claude-mem-local - Live</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #eee; min-height: 100vh; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { text-align: center; margin-bottom: 10px; background: linear-gradient(90deg, #00d9ff, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.5em; }
        .subtitle { text-align: center; color: #888; margin-bottom: 20px; }
        .status-bar { background: rgba(16,185,129,0.2); border: 1px solid #10b981; border-radius: 8px; padding: 10px 15px; margin-bottom: 20px; display: flex; align-items: center; gap: 10px; justify-content: space-between; min-height: 44px; }
        .status-left { display: flex; align-items: center; gap: 10px; min-width: 350px; }
        .status-dot { width: 10px; height: 10px; min-width: 10px; min-height: 10px; max-width: 10px; max-height: 10px; background: #10b981; border-radius: 50%; flex-shrink: 0; }
        .status-dot.loading { background: #f59e0b; animation: blink 0.5s ease-in-out infinite; }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        #statusText { min-width: 300px; }
        .refresh-btn { background: rgba(168,85,247,0.3); border: 1px solid #a855f7; color: #fff; padding: 8px 16px; border-radius: 8px; cursor: pointer; }
        .refresh-btn:hover { background: rgba(168,85,247,0.5); }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab-btn { padding: 12px 24px; border: none; border-radius: 8px 8px 0 0; background: rgba(255,255,255,0.1); color: #888; cursor: pointer; font-size: 1em; transition: all 0.3s; }
        .tab-btn.active { background: rgba(168,85,247,0.3); color: #fff; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 15px; margin-bottom: 30px; min-height: 90px; }
        .stat-card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; text-align: center; min-height: 80px; }
        .stat-value { font-size: 2em; font-weight: bold; color: #00d9ff; }
        .stat-label { color: #888; font-size: 0.9em; }
        .controls { display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap; align-items: center; }
        .search-box { flex: 1; min-width: 250px; padding: 12px 20px; border: 1px solid rgba(255,255,255,0.2); border-radius: 25px; background: rgba(255,255,255,0.05); color: #eee; font-size: 1em; }
        .search-box:focus { outline: none; border-color: #00d9ff; }
        .search-btn { background: #a855f7; border: none; color: #fff; padding: 12px 24px; border-radius: 25px; cursor: pointer; }
        .search-btn:hover { background: #9333ea; }
        .filters { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 15px; min-height: 36px; align-items: center; }
        .filter-btn { padding: 6px 14px; border: 1px solid rgba(255,255,255,0.2); border-radius: 20px; background: transparent; color: #eee; cursor: pointer; font-size: 0.85em; transition: all 0.2s; }
        .filter-btn:hover, .filter-btn.active { background: #a855f7; border-color: #a855f7; }
        .project-btn { padding: 6px 14px; border: 1px solid rgba(0,217,255,0.3); border-radius: 20px; background: transparent; color: #00d9ff; cursor: pointer; font-size: 0.85em; }
        .project-btn:hover, .project-btn.active { background: rgba(0,217,255,0.3); }
        .memories-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; contain: layout style; }
        .memory-card { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; transition: transform 0.2s; }
        .memory-card:hover { transform: translateY(-2px); box-shadow: 0 10px 30px rgba(0,0,0,0.3); }
        .memory-card.new { animation: glow 2s ease-out; }
        @keyframes glow { 0% { box-shadow: 0 0 20px #10b981; } 100% { box-shadow: none; } }
        .memory-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .memory-type { padding: 4px 10px; border-radius: 12px; font-size: 0.8em; font-weight: 500; }
        .type-bugfix { background: #ef4444; }
        .type-decision { background: #f59e0b; }
        .type-feature { background: #10b981; }
        .type-discovery { background: #3b82f6; }
        .type-refactor { background: #8b5cf6; }
        .type-change { background: #6b7280; }
        .type-pattern { background: #92400e; }
        .type-preference { background: #eab308; }
        .type-learning { background: #0ea5e9; }
        .type-error_solution { background: #f97316; }
        .memory-importance { color: #fbbf24; }
        .memory-similarity { color: #10b981; font-size: 0.85em; }
        .memory-summary { font-weight: 600; margin-bottom: 10px; color: #fff; }
        .memory-content { color: #aaa; font-size: 0.85em; line-height: 1.6; max-height: 150px; overflow: hidden; white-space: pre-wrap; word-break: break-word; }
        .memory-content.expanded { max-height: none; }
        .expand-btn { background: none; border: none; color: #00d9ff; cursor: pointer; font-size: 0.8em; margin-top: 8px; }
        .memory-tags { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 10px; }
        .tag { padding: 2px 8px; background: rgba(168,85,247,0.2); border-radius: 10px; font-size: 0.75em; color: #c084fc; }
        .memory-meta { display: flex; justify-content: space-between; margin-top: 10px; font-size: 0.75em; color: #666; }
        .project-badge { background: rgba(0,217,255,0.2); color: #00d9ff; padding: 2px 8px; border-radius: 8px; }
        .prompt-card { background: rgba(255,255,255,0.05); border: 1px solid rgba(0,217,255,0.2); border-radius: 12px; padding: 15px 20px; margin-bottom: 10px; }
        .prompt-text { color: #eee; font-size: 0.95em; line-height: 1.5; }
        .prompt-meta { color: #666; font-size: 0.75em; margin-top: 8px; }
        .loading { text-align: center; padding: 40px; color: #888; }
        .auto-refresh { display: flex; align-items: center; gap: 8px; color: #888; font-size: 0.85em; }
        .auto-refresh input { accent-color: #a855f7; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🧠 MCP-Claude-mem-local</h1>
        <p class="subtitle">Interface dynamique temps réel</p>

        <div class="status-bar">
            <div class="status-left">
                <div class="status-dot" id="statusDot"></div>
                <span id="statusText">Connecté — PostgreSQL + pgvector + Ollama</span>
            </div>
            <div style="display:flex;gap:15px;align-items:center;">
                <label class="auto-refresh">
                    <input type="checkbox" id="autoRefresh" checked>
                    Auto-refresh (5s)
                </label>
                <button class="refresh-btn" onclick="loadAll()">🔄 Rafraîchir</button>
            </div>
        </div>

        <div class="tabs">
            <button class="tab-btn active" data-tab="memories">📚 Mémoires (<span id="memCount">-</span>)</button>
            <button class="tab-btn" data-tab="search">🔍 Recherche</button>
            <button class="tab-btn" data-tab="prompts">💬 Prompts (<span id="promptCount">-</span>)</button>
        </div>

        <div id="memories-tab" class="tab-content active">
            <div class="stats" id="statsGrid"></div>
            <div class="filters" id="categoryFilters"></div>
            <div class="filters" id="projectFilters"></div>
            <div class="memories-grid" id="memoriesGrid"><div class="loading">Chargement...</div></div>
        </div>

        <div id="search-tab" class="tab-content">
            <div class="controls">
                <input type="text" class="search-box" id="searchInput" placeholder="🔍 Recherche sémantique..." onkeypress="if(event.key==='Enter')doSearch()">
                <button class="search-btn" onclick="doSearch()">Rechercher</button>
            </div>
            <div class="memories-grid" id="searchResults"><div class="loading" style="color:#666">Entrez une requête pour rechercher dans vos mémoires</div></div>
        </div>

        <div id="prompts-tab" class="tab-content">
            <div id="promptsList"><div class="loading">Chargement...</div></div>
        </div>
    </div>

    <script>
        const API = '';
        let currentCategory = null;
        let currentProject = null;
        let lastMemoryId = null;
        let autoRefreshInterval = null;

        // Tabs
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                btn.classList.add('active');
                document.getElementById(btn.dataset.tab + '-tab').classList.add('active');
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
                statsHtml += `<div class="stat-card"><div class="stat-value">${c.count}</div><div class="stat-label">${c.category}</div></div>`;
            });
            document.getElementById('statsGrid').innerHTML = statsHtml;

            // Category filters - use escapeHtml and escapeAttr for XSS prevention
            let catHtml = '<span style="color:#888;margin-right:5px;">Type:</span>';
            catHtml += `<button class="filter-btn ${!currentCategory ? 'active' : ''}" onclick="filterCategory(null)">Toutes</button>`;
            data.by_category.forEach(c => {
                const safeCat = escapeAttr(c.category);
                catHtml += `<button class="filter-btn ${currentCategory === c.category ? 'active' : ''}" onclick="filterCategory('${safeCat}')">${escapeHtml(c.category)} (${c.count})</button>`;
            });
            document.getElementById('categoryFilters').innerHTML = catHtml;

            // Project filters - use escapeHtml and escapeAttr for XSS prevention
            let projHtml = '<span style="color:#888;margin-right:5px;">Projet:</span>';
            projHtml += `<button class="project-btn ${!currentProject ? 'active' : ''}" onclick="filterProject(null)">Tous</button>`;
            data.by_project.forEach(p => {
                if (p.project) {
                    const safeProj = escapeAttr(p.project);
                    projHtml += `<button class="project-btn ${currentProject === p.project ? 'active' : ''}" onclick="filterProject('${safeProj}')">${escapeHtml(p.project.substring(0,20))} (${p.count})</button>`;
                }
            });
            document.getElementById('projectFilters').innerHTML = projHtml;
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
                return;
            }

            // Vérifier si les données ont changé
            const firstId = data.memories[0]?.id;
            const newHash = data.memories.map(m => m.id).join(',');

            if (newHash === lastMemoriesHash) return; // Pas de changement

            const isNew = lastMemoryId && firstId !== lastMemoryId;
            lastMemoryId = firstId;
            lastMemoriesHash = newHash;

            grid.innerHTML = data.memories.map((m, i) => renderMemoryCard(m, isNew && i === 0)).join('');
            attachExpandListeners();
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
                const projectName = p.project ? p.project.split('/').pop() : '';
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

                results.innerHTML = data.results.map(m => renderMemoryCard(m, false, true)).join('');
                attachExpandListeners();
            } catch (err) {
                // Security: Don't expose detailed error messages
                console.error('Search error:', err);
                results.innerHTML = '<div class="loading" style="color:#ef4444">Une erreur est survenue. Veuillez réessayer.</div>';
            }
        }

        function renderMemoryCard(m, isNew = false, showSimilarity = false) {
            const stars = '★'.repeat(Math.round((m.importance || 0.5) * 5)) + '☆'.repeat(5 - Math.round((m.importance || 0.5) * 5));
            const tags = (m.tags || []).slice(0, 5).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('');
            const project = m.project ? `<span class="project-badge">${escapeHtml(m.project.substring(0, 20))}</span>` : '';
            const similarity = showSimilarity && m.similarity ? `<span class="memory-similarity">Similarité: ${(m.similarity * 100).toFixed(1)}%</span>` : '';
            // Security: Escape data attributes to prevent XSS
            const safeCategory = escapeHtml(m.category || '');
            const safeProject = escapeHtml(m.project || '');

            return `
                <div class="memory-card ${isNew ? 'new' : ''}" data-type="${safeCategory}" data-project="${safeProject}">
                    <div class="memory-header">
                        <span class="memory-type type-${safeCategory}">${safeCategory}</span>
                        <span class="memory-importance">${stars}</span>
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

        function attachExpandListeners() {
            document.querySelectorAll('.expand-btn').forEach(btn => {
                btn.onclick = () => {
                    const content = btn.previousElementSibling;
                    content.classList.toggle('expanded');
                    btn.textContent = content.classList.contains('expanded') ? 'Réduire ▲' : 'Voir plus ▼';
                };
            });
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

        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        // Security: Escape for use in HTML attributes (onclick handlers)
        function escapeAttr(str) {
            if (!str) return '';
            return str
                .replace(/\\/g, '\\\\')
                .replace(/'/g, "\\'")
                .replace(/"/g, '\\"')
                .replace(/</g, '\\x3c')
                .replace(/>/g, '\\x3e')
                .replace(/\n/g, '\\n')
                .replace(/\r/g, '\\r');
        }

        function formatDate(iso) {
            if (!iso) return 'N/A';
            const d = new Date(iso);
            return d.toLocaleDateString('fr-FR') + ' ' + d.toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit'});
        }

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
