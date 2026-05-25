#!/usr/bin/env python3
"""MCP-Claude-mem-local - Serveur MCP pour mémoire persistante locale"""
# Dummy change to test source change detection


import logging
import os
import sys
from uuid import UUID

from contextlib import asynccontextmanager

import asyncpg
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from urllib.parse import urlparse

# ACT-R cognitive scoring
from actr_scoring import ACTRConfig, score_and_rank_memories
from forgetting import run_forgetting_cycle
from hybrid_search import build_search_queries, reciprocal_rank_fusion

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("claude-memory-local")

# Charger la config
load_dotenv()

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DATABASE = os.getenv("PG_DATABASE", "claude_memory")
PG_USER = os.getenv("PG_USER", "claude")
PG_PASSWORD = os.getenv("PG_PASSWORD")

USE_IAM_AUTH = os.getenv("USE_IAM_AUTH", "false").lower() == "true"
ALLOYDB_INSTANCE_URI = os.getenv("ALLOYDB_INSTANCE_URI")

if not USE_IAM_AUTH and not PG_PASSWORD:
    raise RuntimeError("PG_PASSWORD environment variable is required. Set it in .env file.")
# Security: Validate OLLAMA_HOST to prevent SSRF
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
_parsed_ollama = urlparse(OLLAMA_HOST)
ALLOWED_OLLAMA_HOSTS = {"localhost", "127.0.0.1"}
if _parsed_ollama.hostname not in ALLOWED_OLLAMA_HOSTS:
    raise RuntimeError(f"OLLAMA_HOST must be localhost or 127.0.0.1 for security. Got: {_parsed_ollama.hostname}")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

# Valid categories for input validation
VALID_CATEGORIES = frozenset({
    "bugfix", "decision", "feature", "discovery", "refactor",
    "change", "learning", "pattern", "error_solution", "preference"
})

# User isolation
USER_ID = os.getenv("USER_ID", "default")

# Load ACT-R configuration
actr_config = ACTRConfig.from_env()

# Pool de connexions global et connecteur AlloyDB IAM
pool = None
connector = None


async def _init_connection(conn):
    """Set RLS session variable on each new connection."""
    # SET does not support $1 parameters in PostgreSQL; sanitize and interpolate
    safe_id = USER_ID.replace("'", "''")
    await conn.execute(f"SET app.current_user_id = '{safe_id}'")


async def get_pool():
    """Obtenir le pool de connexions PostgreSQL"""
    global pool, connector
    if pool is None:
        if USE_IAM_AUTH and ALLOYDB_INSTANCE_URI:
            logger.info(f"Initialisation de la connexion IAM AlloyDB vers {ALLOYDB_INSTANCE_URI}...")
            from google.cloud.alloydb.connector import AsyncConnector, IPTypes
            connector = AsyncConnector()
            
            async def getconn(*args, **kwargs):
                return await connector.connect(
                    ALLOYDB_INSTANCE_URI,
                    "asyncpg",
                    user=PG_USER,
                    db=PG_DATABASE,
                    enable_iam_auth=True,
                    ip_type=IPTypes.PRIVATE
                )
            
            pool = await asyncpg.create_pool(
                connect=getconn,
                min_size=2,
                max_size=10,
                command_timeout=30,
                init=_init_connection,
            )
        else:
            logger.info(f"Connexion PostgreSQL classique vers {PG_DATABASE} ({PG_HOST}:{PG_PORT})...")
            pool = await asyncpg.create_pool(
                host=PG_HOST,
                port=PG_PORT,
                database=PG_DATABASE,
                user=PG_USER,
                password=PG_PASSWORD,
                min_size=2,
                max_size=10,
                command_timeout=30,
                init=_init_connection,
            )
    return pool


@asynccontextmanager
async def lifespan(server):
    """Gère le cycle de vie du serveur : cleanup du pool et du connecteur à l'arrêt."""
    logger.info("Lifespan: démarrage")
    try:
        yield
    finally:
        global pool, connector
        if pool is not None:
            logger.info("Lifespan: fermeture du pool PostgreSQL")
            await pool.close()
            pool = None
        if connector is not None:
            logger.info("Lifespan: fermeture du connecteur AlloyDB IAM")
            await connector.close()
            connector = None
        logger.info("Lifespan: cleanup terminé")


# Initialiser le serveur MCP avec lifespan
# Security: MCP stdio transport is inherently trusted — the calling process
# (Claude Code) controls the pipe. No additional auth layer is needed for stdio.
# If the transport is ever changed to SSE/HTTP, authentication MUST be added.
mcp = FastMCP("claude-memory-local", lifespan=lifespan)


EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama").lower()
_vertex_model = None

def get_embedding_vertex(text: str) -> list[float]:
    """Générer un embedding via Vertex AI (Google Cloud)"""
    global _vertex_model
    if _vertex_model is None:
        import vertexai
        from vertexai.language_models import TextEmbeddingModel
        project = os.getenv("GCP_PROJECT")
        location = os.getenv("GCP_REGION", "europe-west9")
        # Initialize Vertex AI with ambient credentials in GCP environment
        vertexai.init(project=project, location=location)
        _vertex_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    
    # Request embeddings with 768 dimensions (text-embedding-004 default)
    embeddings = _vertex_model.get_embeddings([text])
    return embeddings[0].values

async def get_embedding(text: str) -> list[float]:
    """Générer un embedding via Ollama local ou Vertex AI"""
    if EMBEDDING_PROVIDER == "vertexai":
        import asyncio
        return await asyncio.to_thread(get_embedding_vertex, text)
    
    # Fallback to local Ollama embedding
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{OLLAMA_HOST}/api/embeddings",
            json={"model": EMBEDDING_MODEL, "prompt": text}
        )
        response.raise_for_status()
        return response.json()["embedding"]

def format_embedding(embedding: list[float]) -> str:
    """Formater l'embedding pour pgvector"""
    return "[" + ",".join(str(x) for x in embedding) + "]"


@mcp.tool()
async def store_memory(
    content: str,
    category: str,
    summary: str = None,
    tags: list[str] = None,
    importance: float = 0.5,
    project: str = None
) -> str:
    """
    Stocke une memoire (enseignement, pattern, decision, erreur).
    
    Args:
        content: Le contenu complet de la memoire
        category: Type de memoire (bugfix, decision, feature, discovery, refactor, change, pattern, preference, learning, error_solution)
        summary: Resume court (auto-genere si absent)
        tags: Liste de tags pour le filtrage
        importance: Score d importance 0.0 a 1.0
        project: Contexte projet (optionnel)
    
    Returns:
        ID de la memoire creee
    """
    # Input validation
    if category not in VALID_CATEGORIES:
        return f"Invalid category '{category}'. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}"
    importance = max(0.0, min(1.0, importance))
    if len(content) > 50000:
        return "Content too long (max 50000 characters)."

    try:
        embedding = await get_embedding(content)

        if not summary:
            summary = content[:150] + "..." if len(content) > 150 else content
        
        db = await get_pool()
        async with db.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO memories
                (content, summary, category, tags, embedding, importance_score, project_context, user_id)
                VALUES ($1, $2, $3, $4, $5::vector, $6, $7, $8)
                RETURNING id
            """, content, summary, category, tags or [], format_embedding(embedding), importance, project, USER_ID)
        
        return f"Memoire stockee avec ID: {result['id']}"
    except Exception as e:
        logger.error(f"store_memory failed: {e}", exc_info=True)
        return "Erreur: impossible de stocker la memoire. Verifiez la connexion a la base de donnees."


@mcp.tool()
async def retrieve_memories(
    query: str,
    max_results: int = 5,
    category: str = None,
    min_similarity: float = 0.3,
    tags: list[str] = None,
    project: str = None,
    include_forgotten: bool = False
) -> str:
    """
    Recupere les memoires pertinentes pour une requete (recherche hybride vector + trigramme).

    Args:
        query: La requete de recherche
        max_results: Nombre maximum de resultats (defaut: 5)
        category: Filtrer par categorie (optionnel)
        min_similarity: Similarite minimum 0.0 a 1.0 (defaut: 0.3)
        tags: Filtrer par tags (optionnel, ex: ["setup", "mac"])
        project: Filtrer par projet (optionnel, ex: "project-m4")
        include_forgotten: Inclure les memoires oubliees (defaut: false)

    Returns:
        Les memoires pertinentes formatees
    """
    # Input validation
    max_results = max(1, min(100, max_results))
    min_similarity = max(0.0, min(1.0, min_similarity))

    try:
        query_embedding = await get_embedding(query)
        embedding_str = format_embedding(query_embedding)

        db = await get_pool()
        async with db.acquire() as conn:
            prefetch = actr_config.prefetch_limit if actr_config.use_actr else max_results

            # Build hybrid search queries (vector + trigram)
            vec_sql, vec_params, trgm_sql, trgm_params = build_search_queries(
                embedding_str=embedding_str,
                query_text=query,
                min_similarity=min_similarity,
                prefetch=prefetch,
                category=category,
                tags=tags,
                project=project,
                include_forgotten=include_forgotten,
                user_id=USER_ID,
            )

            # Stage 1a: Vector search (always available)
            vec_rows = await conn.fetch(vec_sql, *vec_params)

            # Stage 1b: Trigram search (graceful fallback if pg_trgm unavailable)
            trgm_rows = []
            try:
                trgm_rows = await conn.fetch(trgm_sql, *trgm_params)
            except Exception as trgm_err:
                logger.warning(f"Trigram search unavailable, falling back to vector-only: {trgm_err}")

            # Stage 2: Reciprocal Rank Fusion
            vec_dicts = [dict(r) for r in vec_rows]
            trgm_dicts = [dict(r) for r in trgm_rows]
            fused = reciprocal_rank_fusion(vec_dicts, trgm_dicts)

            if not fused:
                return "Aucune memoire pertinente trouvee."

            # Stage 3: ACT-R re-ranking (or fallback to original scoring)
            if actr_config.use_actr:
                tag_counts = await conn.fetch("""
                    SELECT unnest(tags) as tag, COUNT(*) as cnt
                    FROM memories
                    WHERE tags IS NOT NULL AND array_length(tags, 1) > 0
                    GROUP BY tag
                """)
                tag_fan = {r["tag"].lower(): r["cnt"] for r in tag_counts}

                scored = score_and_rank_memories(
                    rows=fused,
                    query_tags=tags,
                    tag_fan_counts=tag_fan,
                    config=actr_config,
                    query=query,
                    category=category,
                )
                final_rows = scored[:max_results]
            else:
                fused.sort(
                    key=lambda r: r["sim"] * r["importance_score"],
                    reverse=True,
                )
                final_rows = fused[:max_results]

            # Record access timestamps for retrieved memories (ring buffer: cap at 1000)
            ids = [row['id'] for row in final_rows]
            await conn.execute("""
                UPDATE memories
                SET last_accessed_at = NOW(),
                    access_count = access_count + 1,
                    access_timestamps = (
                        CASE
                            WHEN array_length(COALESCE(access_timestamps, '{}'), 1) >= 1000
                            THEN array_append(access_timestamps[2:], NOW())
                            ELSE array_append(COALESCE(access_timestamps, '{}'), NOW())
                        END
                    )
                WHERE id = ANY($1) AND (user_id = $2 OR user_id IS NULL)
            """, ids, USER_ID)

        # Format results
        results = []
        for row in final_rows:
            activation_info = ""
            if actr_config.use_actr and "activation_score" in row:
                activation_info = f", activation: {row['activation_score']:.2f}"
            rrf_info = ""
            if "rrf_score" in row:
                rrf_info = f", rrf: {row['rrf_score']:.4f}"
            project_info = ""
            if row.get("project_context"):
                project_info = f"\nProjet: {row['project_context']}"
            results.append(f"""
---
**[{row['category']}]** (similarite: {row['sim']:.2f}, importance: {row['importance_score']:.1f}{activation_info}{rrf_info})
{row['content']}
Tags: {', '.join(row['tags']) if row['tags'] else 'aucun'}{project_info}
""")

        return f"## {len(final_rows)} memoire(s) trouvee(s):\n" + "\n".join(results)

    except Exception as e:
        logger.error(f"retrieve_memories failed: {e}", exc_info=True)
        return "Erreur: impossible de recuperer les memoires. Verifiez la connexion a la base de donnees."


@mcp.tool()
async def list_memories(
    limit: int = 20,
    category: str = None,
    tags: list[str] = None,
    project: str = None
) -> str:
    """
    Liste les memoires recentes.

    Args:
        limit: Nombre de memoires a afficher (defaut: 20)
        category: Filtrer par categorie (optionnel)
        tags: Filtrer par tags (optionnel, ex: ["setup", "mac"])
        project: Filtrer par projet (optionnel, ex: "project-m4")

    Returns:
        Liste des memoires avec leurs metadonnees
    """
    # Input validation
    limit = max(1, min(100, limit))
    if category and category not in VALID_CATEGORIES:
        return f"Invalid category '{category}'. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}"

    try:
        db = await get_pool()
        async with db.acquire() as conn:
            # Build dynamic WHERE clause with positional params
            conditions = ["(user_id = $1 OR user_id IS NULL)"]
            params = [USER_ID]
            param_idx = 2

            if category:
                conditions.append(f"category = ${param_idx}")
                params.append(category)
                param_idx += 1

            if tags:
                conditions.append(f"tags @> ${param_idx}")
                params.append(tags)
                param_idx += 1

            if project:
                conditions.append(f"project_context = ${param_idx}")
                params.append(project)
                param_idx += 1

            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)

            params.append(limit)
            limit_param = f"${param_idx}"

            rows = await conn.fetch(f"""
                SELECT id, summary, category, tags, importance_score,
                       created_at, access_count, project_context
                FROM memories
                {where_clause}
                ORDER BY created_at DESC
                LIMIT {limit_param}
            """, *params)

        if not rows:
            return "Aucune memoire stockee."

        results = []
        for row in rows:
            project_info = f" | projet: {row['project_context']}" if row.get('project_context') else ""
            results.append(
                f"- **{row['category']}** | {row['summary'][:80]}... | "
                f"importance: {row['importance_score']:.1f} | acces: {row['access_count']}{project_info}"
            )

        return f"## {len(rows)} memoire(s):\n" + "\n".join(results)

    except Exception as e:
        logger.error(f"list_memories failed: {e}", exc_info=True)
        return "Erreur: impossible de lister les memoires. Verifiez la connexion a la base de donnees."


@mcp.tool()
async def delete_memory(memory_id: str) -> str:
    """
    Supprime une memoire par son ID.
    
    Args:
        memory_id: L UUID de la memoire a supprimer
    
    Returns:
        Confirmation de suppression
    """
    try:
        parsed_id = UUID(memory_id)
    except (ValueError, AttributeError):
        return "Invalid memory ID format. Must be a valid UUID."

    try:
        db = await get_pool()
        async with db.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM memories WHERE id = $1 AND (user_id = $2 OR user_id IS NULL)",
                parsed_id, USER_ID
            )
        
        if result == "DELETE 1":
            return f"Memoire {memory_id} supprimee."
        else:
            return f"Memoire {memory_id} non trouvee."

    except Exception as e:
        logger.error(f"delete_memory failed: {e}", exc_info=True)
        return "Erreur: impossible de supprimer la memoire. Verifiez l'ID et la connexion."


def get_version() -> str:
    """Read version from VERSION file, falling back to '1.0.0' if not present."""
    try:
        # Check if the VERSION file exists in the current directory or parent directory
        version_path = os.path.join(os.path.dirname(__file__), "..", "VERSION")
        if not os.path.exists(version_path):
            version_path = os.path.join(os.path.dirname(__file__), "VERSION")
        if not os.path.exists(version_path):
            version_path = "VERSION"
            
        with open(version_path, "r") as f:
            return f.read().strip()
    except Exception:
        return "1.0.0"


@mcp.tool()
async def memory_stats() -> str:
    """
    Affiche les statistiques de la base de memoires.

    Returns:
        Statistiques detaillees incluant indicateurs ACT-R
    """
    try:
        db = await get_pool()
        async with db.acquire() as conn:
            _uf = "(user_id = $1 OR user_id IS NULL)"
            total = await conn.fetchval(f"SELECT COUNT(*) FROM memories WHERE {_uf}", USER_ID)
            by_category = await conn.fetch(f"""
                SELECT category, COUNT(*) as count
                FROM memories WHERE {_uf}
                GROUP BY category
                ORDER BY count DESC
            """, USER_ID)
            recent = await conn.fetchval(f"""
                SELECT COUNT(*) FROM memories
                WHERE created_at > NOW() - INTERVAL '7 days' AND {_uf}
            """, USER_ID)
            most_accessed = await conn.fetch(f"""
                SELECT summary, access_count
                FROM memories WHERE {_uf}
                ORDER BY access_count DESC
                LIMIT 5
            """, USER_ID)

            # ACT-R status counts
            by_status = await conn.fetch(f"""
                SELECT COALESCE(memory_status, 'active') as status, COUNT(*) as count
                FROM memories WHERE {_uf}
                GROUP BY COALESCE(memory_status, 'active')
                ORDER BY count DESC
            """, USER_ID)
            avg_activation = await conn.fetchval(f"""
                SELECT AVG(actr_activation) FROM memories
                WHERE actr_activation IS NOT NULL AND {_uf}
            """, USER_ID)

        stats = f"""## Statistiques Memoire (Version: {get_version()})

**Total**: {total} memoires
**Cette semaine**: {recent} nouvelles
**Scoring**: {'ACT-R cognitif' if actr_config.use_actr else 'Cosine classique'}

### Par categorie:
"""
        for row in by_category:
            stats += f"- {row['category']}: {row['count']}\n"

        stats += "\n### Par statut memoire:\n"
        for row in by_status:
            stats += f"- {row['status']}: {row['count']}\n"

        if avg_activation is not None:
            stats += f"\n**Activation moyenne**: {avg_activation:.2f}\n"

        stats += "\n### Plus consultees:\n"
        for row in most_accessed:
            if row['summary']:
                stats += f"- ({row['access_count']}x) {row['summary'][:60]}...\n"

        return stats

    except Exception as e:
        logger.error(f"memory_stats failed: {e}", exc_info=True)
        return "Erreur: impossible de recuperer les statistiques. Verifiez la connexion a la base de donnees."


@mcp.tool()
async def memory_forgetting_cycle() -> str:
    """
    Execute un cycle d'oubli strategique ACT-R.

    Recalcule l'activation de toutes les memoires et met a jour
    leurs statuts: active (A>0), dormant (-2<A<=0), forgotten (A<=-2).
    Les memoires forgotten restent en base mais sont exclues des
    resultats par defaut.

    Returns:
        Resume des transitions effectuees
    """
    try:
        db = await get_pool()
        result = await run_forgetting_cycle(db, actr_config)
        return result
    except Exception as e:
        logger.error(f"memory_forgetting_cycle failed: {e}", exc_info=True)
        return "Erreur: impossible d'executer le cycle d'oubli. Verifiez la connexion."


if __name__ == "__main__":
    mcp.run(transport="stdio")
