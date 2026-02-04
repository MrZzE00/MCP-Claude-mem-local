#!/usr/bin/env python3
"""MCP-Claude-mem-local - Serveur MCP pour mémoire persistante locale"""

import logging
import os
import sys
from uuid import UUID

import asyncpg
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

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
if not PG_PASSWORD:
    raise RuntimeError("PG_PASSWORD environment variable is required. Set it in .env file.")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

# Initialiser le serveur MCP
mcp = FastMCP("claude-memory-local")

# Pool de connexions global
pool = None


async def get_pool():
    """Obtenir le pool de connexions PostgreSQL"""
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(
            host=PG_HOST,
            port=PG_PORT,
            database=PG_DATABASE,
            user=PG_USER,
            password=PG_PASSWORD,
            min_size=2,
            max_size=10
        )
    return pool


async def get_embedding(text: str) -> list[float]:
    """Générer un embedding via Ollama local"""
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
    try:
        embedding = await get_embedding(content)
        
        if not summary:
            summary = content[:150] + "..." if len(content) > 150 else content
        
        db = await get_pool()
        async with db.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO memories 
                (content, summary, category, tags, embedding, importance_score, project_context)
                VALUES ($1, $2, $3, $4, $5::vector, $6, $7)
                RETURNING id
            """, content, summary, category, tags or [], format_embedding(embedding), importance, project)
        
        return f"Memoire stockee avec ID: {result['id']}"
    except Exception as e:
        logger.error(f"store_memory failed: {e}", exc_info=True)
        return "Erreur: impossible de stocker la memoire. Verifiez la connexion a la base de donnees."


@mcp.tool()
async def retrieve_memories(
    query: str,
    max_results: int = 5,
    category: str = None,
    min_similarity: float = 0.5
) -> str:
    """
    Recupere les memoires pertinentes pour une requete.
    
    Args:
        query: La requete de recherche
        max_results: Nombre maximum de resultats (defaut: 5)
        category: Filtrer par categorie (optionnel)
        min_similarity: Similarite minimum 0.0 a 1.0 (defaut: 0.5)
    
    Returns:
        Les memoires pertinentes formatees
    """
    try:
        query_embedding = await get_embedding(query)
        embedding_str = format_embedding(query_embedding)

        db = await get_pool()
        async with db.acquire() as conn:
            if category:
                rows = await conn.fetch("""
                    SELECT
                        id, content, summary, category, tags,
                        importance_score,
                        1 - (embedding <=> $1::vector) as sim
                    FROM memories
                    WHERE category = $4
                      AND 1 - (embedding <=> $1::vector) >= $2
                    ORDER BY (1 - (embedding <=> $1::vector)) * importance_score DESC
                    LIMIT $3
                """, embedding_str, min_similarity, max_results, category)
            else:
                rows = await conn.fetch("""
                    SELECT
                        id, content, summary, category, tags,
                        importance_score,
                        1 - (embedding <=> $1::vector) as sim
                    FROM memories
                    WHERE 1 - (embedding <=> $1::vector) >= $2
                    ORDER BY (1 - (embedding <=> $1::vector)) * importance_score DESC
                    LIMIT $3
                """, embedding_str, min_similarity, max_results)
            
            if not rows:
                return "Aucune memoire pertinente trouvee."
            
            ids = [row['id'] for row in rows]
            await conn.execute("""
                UPDATE memories 
                SET last_accessed_at = NOW(), access_count = access_count + 1
                WHERE id = ANY($1)
            """, ids)
        
        results = []
        for row in rows:
            results.append(f"""
---
**[{row['category']}]** (similarite: {row['sim']:.2f}, importance: {row['importance_score']:.1f})
{row['content']}
Tags: {', '.join(row['tags']) if row['tags'] else 'aucun'}
""")
        
        return f"## {len(rows)} memoire(s) trouvee(s):\n" + "\n".join(results)

    except Exception as e:
        logger.error(f"retrieve_memories failed: {e}", exc_info=True)
        return "Erreur: impossible de recuperer les memoires. Verifiez la connexion a la base de donnees."


@mcp.tool()
async def list_memories(
    limit: int = 20,
    category: str = None
) -> str:
    """
    Liste les memoires recentes.
    
    Args:
        limit: Nombre de memoires a afficher (defaut: 20)
        category: Filtrer par categorie (optionnel)
    
    Returns:
        Liste des memoires avec leurs metadonnees
    """
    try:
        db = await get_pool()
        async with db.acquire() as conn:
            if category:
                rows = await conn.fetch("""
                    SELECT id, summary, category, tags, importance_score, created_at, access_count
                    FROM memories
                    WHERE category = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                """, category, limit)
            else:
                rows = await conn.fetch("""
                    SELECT id, summary, category, tags, importance_score, created_at, access_count
                    FROM memories
                    ORDER BY created_at DESC
                    LIMIT $1
                """, limit)
        
        if not rows:
            return "Aucune memoire stockee."
        
        results = []
        for row in rows:
            results.append(
                f"- **{row['category']}** | {row['summary'][:80]}... | "
                f"importance: {row['importance_score']:.1f} | acces: {row['access_count']}"
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
        db = await get_pool()
        async with db.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM memories WHERE id = $1",
                UUID(memory_id)
            )
        
        if result == "DELETE 1":
            return f"Memoire {memory_id} supprimee."
        else:
            return f"Memoire {memory_id} non trouvee."

    except Exception as e:
        logger.error(f"delete_memory failed: {e}", exc_info=True)
        return "Erreur: impossible de supprimer la memoire. Verifiez l'ID et la connexion."


@mcp.tool()
async def memory_stats() -> str:
    """
    Affiche les statistiques de la base de memoires.
    
    Returns:
        Statistiques detaillees
    """
    try:
        db = await get_pool()
        async with db.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM memories")
            by_category = await conn.fetch("""
                SELECT category, COUNT(*) as count 
                FROM memories 
                GROUP BY category 
                ORDER BY count DESC
            """)
            recent = await conn.fetchval("""
                SELECT COUNT(*) FROM memories 
                WHERE created_at > NOW() - INTERVAL '7 days'
            """)
            most_accessed = await conn.fetch("""
                SELECT summary, access_count 
                FROM memories 
                ORDER BY access_count DESC 
                LIMIT 5
            """)
        
        stats = f"""## Statistiques Memoire

**Total**: {total} memoires
**Cette semaine**: {recent} nouvelles

### Par categorie:
"""
        for row in by_category:
            stats += f"- {row['category']}: {row['count']}\n"
        
        stats += "\n### Plus consultees:\n"
        for row in most_accessed:
            if row['summary']:
                stats += f"- ({row['access_count']}x) {row['summary'][:60]}...\n"

        return stats

    except Exception as e:
        logger.error(f"memory_stats failed: {e}", exc_info=True)
        return "Erreur: impossible de recuperer les statistiques. Verifiez la connexion a la base de donnees."


if __name__ == "__main__":
    mcp.run(transport="stdio")
