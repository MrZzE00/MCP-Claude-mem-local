#!/usr/bin/env python3
"""Interface web pour visualiser les mémoires"""

import asyncio
import html
import os
from datetime import datetime

import asyncpg
from dotenv import load_dotenv

load_dotenv()

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DATABASE = os.getenv("PG_DATABASE", "claude_memory")
PG_USER = os.getenv("PG_USER", "claude")
PG_PASSWORD = os.getenv("PG_PASSWORD")
if not PG_PASSWORD:
    raise RuntimeError("PG_PASSWORD environment variable is required. Set it in .env file.")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MCP-Claude-mem-local</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 {
            text-align: center;
            margin-bottom: 30px;
            background: linear-gradient(90deg, #00d9ff, #a855f7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 2.5em;
        }
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        .tab-btn {
            padding: 12px 24px;
            border: none;
            border-radius: 8px 8px 0 0;
            background: rgba(255,255,255,0.1);
            color: #888;
            cursor: pointer;
            font-size: 1em;
            transition: all 0.3s;
        }
        .tab-btn.active {
            background: rgba(168,85,247,0.3);
            color: #fff;
        }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }
        .stat-value {
            font-size: 2em;
            font-weight: bold;
            color: #00d9ff;
        }
        .stat-label { color: #888; font-size: 0.9em; }
        .filters {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        .filter-btn {
            padding: 8px 16px;
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 20px;
            background: transparent;
            color: #eee;
            cursor: pointer;
            transition: all 0.3s;
            font-size: 0.85em;
        }
        .filter-btn:hover, .filter-btn.active {
            background: #a855f7;
            border-color: #a855f7;
        }
        .project-btn {
            padding: 8px 16px;
            border: 1px solid rgba(0,217,255,0.3);
            border-radius: 20px;
            background: transparent;
            color: #00d9ff;
            cursor: pointer;
            transition: all 0.3s;
            font-size: 0.85em;
        }
        .project-btn:hover, .project-btn.active {
            background: rgba(0,217,255,0.3);
            border-color: #00d9ff;
        }
        .search-box {
            width: 100%;
            padding: 12px 20px;
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 25px;
            background: rgba(255,255,255,0.05);
            color: #eee;
            font-size: 1em;
            margin-bottom: 20px;
        }
        .search-box:focus { outline: none; border-color: #00d9ff; }
        .search-box::placeholder { color: #666; }
        .memories-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
        }
        .memory-card {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .memory-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }
        .memory-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .memory-type {
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: 500;
        }
        .type-bugfix { background: #ef4444; }
        .type-decision { background: #f59e0b; }
        .type-feature { background: #10b981; }
        .type-discovery { background: #3b82f6; }
        .type-refactor { background: #8b5cf6; }
        .type-change { background: #6b7280; }
        .type-learning { background: #06b6d4; }
        .type-pattern { background: #ec4899; }
        .memory-importance { color: #fbbf24; font-size: 0.9em; }
        .memory-summary {
            font-weight: 600;
            margin-bottom: 10px;
            color: #fff;
            font-size: 0.95em;
        }
        .memory-content {
            color: #aaa;
            font-size: 0.85em;
            line-height: 1.5;
            max-height: 100px;
            overflow: hidden;
            position: relative;
            white-space: pre-wrap;
        }
        .memory-content.expanded { max-height: none; }
        .memory-content:not(.expanded)::after {
            content: '';
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 40px;
            background: linear-gradient(transparent, rgba(22,33,62,1));
        }
        .memory-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin-top: 10px;
        }
        .tag {
            padding: 2px 8px;
            background: rgba(168,85,247,0.2);
            border-radius: 10px;
            font-size: 0.75em;
            color: #c084fc;
        }
        .memory-meta {
            display: flex;
            justify-content: space-between;
            margin-top: 10px;
            font-size: 0.75em;
            color: #666;
        }
        .expand-btn {
            background: none;
            border: none;
            color: #00d9ff;
            cursor: pointer;
            font-size: 0.8em;
            margin-top: 8px;
            padding: 0;
        }
        .project-badge {
            background: rgba(0,217,255,0.2);
            color: #00d9ff;
            padding: 2px 8px;
            border-radius: 8px;
            font-size: 0.75em;
        }
        .prompt-card {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(0,217,255,0.2);
            border-radius: 12px;
            padding: 15px 20px;
            margin-bottom: 10px;
        }
        .prompt-text {
            color: #eee;
            font-size: 0.95em;
            line-height: 1.5;
        }
        .prompt-meta {
            color: #666;
            font-size: 0.75em;
            margin-top: 8px;
        }
        .status-bar {
            background: rgba(16,185,129,0.2);
            border: 1px solid #10b981;
            border-radius: 8px;
            padding: 10px 15px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .status-dot {
            width: 10px;
            height: 10px;
            background: #10b981;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🧠 MCP-Claude-mem-local</h1>
        
        <div class="status-bar">
            <div class="status-dot"></div>
            <span>Système connecté — PostgreSQL + pgvector + Ollama</span>
        </div>
        
        <div class="tabs">
            <button class="tab-btn active" data-tab="memories">📚 Mémoires ({total_memories})</button>
            <button class="tab-btn" data-tab="prompts">💬 Prompts ({total_prompts})</button>
        </div>
        
        <div id="memories-tab" class="tab-content active">
            <div class="stats">
                {stats_html}
            </div>
            
            <input type="text" class="search-box" placeholder="🔍 Rechercher dans les mémoires..." id="searchBox">
            
            <div class="filters" id="filters">
                <span style="color:#888;margin-right:5px;">Type:</span>
                <button class="filter-btn active" data-filter="all">Toutes</button>
                {filter_buttons}
            </div>
            
            <div class="filters" id="projectFilters">
                <span style="color:#888;margin-right:5px;">Projet:</span>
                <button class="project-btn active" data-project="all">Tous</button>
                {project_buttons}
            </div>
            
            <div class="memories-grid" id="memoriesGrid">
                {memories_html}
            </div>
        </div>
        
        <div id="prompts-tab" class="tab-content">
            <input type="text" class="search-box" placeholder="🔍 Rechercher dans les prompts..." id="searchPrompts">
            <div id="promptsList">
                {prompts_html}
            </div>
        </div>
    </div>
    
    <script>
        // Tabs
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                btn.classList.add('active');
                document.getElementById(btn.dataset.tab + '-tab').classList.add('active');
            });
        });
        
        // Filters
        let activeType = 'all';
        let activeProject = 'all';
        
        function filterCards() {
            document.querySelectorAll('.memory-card').forEach(card => {
                const typeMatch = activeType === 'all' || card.dataset.type === activeType;
                const projectMatch = activeProject === 'all' || card.dataset.project === activeProject;
                card.style.display = (typeMatch && projectMatch) ? 'block' : 'none';
            });
        }
        
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                activeType = btn.dataset.filter;
                filterCards();
            });
        });
        
        document.querySelectorAll('.project-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.project-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                activeProject = btn.dataset.project;
                filterCards();
            });
        });
        
        // Search memories
        document.getElementById('searchBox').addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            document.querySelectorAll('.memory-card').forEach(card => {
                card.style.display = card.textContent.toLowerCase().includes(query) ? 'block' : 'none';
            });
        });
        
        // Search prompts
        document.getElementById('searchPrompts').addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            document.querySelectorAll('.prompt-card').forEach(card => {
                card.style.display = card.textContent.toLowerCase().includes(query) ? 'block' : 'none';
            });
        });
        
        // Expand/collapse
        document.querySelectorAll('.expand-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const content = btn.previousElementSibling;
                content.classList.toggle('expanded');
                btn.textContent = content.classList.contains('expanded') ? 'Réduire ▲' : 'Voir plus ▼';
            });
        });
    </script>
</body>
</html>
"""

async def generate_html():
    conn = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, database=PG_DATABASE,
        user=PG_USER, password=PG_PASSWORD
    )
    
    # Stats memories
    total_memories = await conn.fetchval("SELECT COUNT(*) FROM memories")
    by_category = await conn.fetch("""
        SELECT category, COUNT(*) as count FROM memories GROUP BY category ORDER BY count DESC
    """)
    by_project = await conn.fetch("""
        SELECT project_context, COUNT(*) as count FROM memories 
        WHERE project_context IS NOT NULL 
        GROUP BY project_context ORDER BY count DESC LIMIT 10
    """)
    
    # Stats prompts
    total_prompts = await conn.fetchval("SELECT COUNT(*) FROM user_prompts")
    
    stats_html = f"""
        <div class="stat-card"><div class="stat-value">{total_memories}</div><div class="stat-label">Mémoires</div></div>
        <div class="stat-card"><div class="stat-value">{total_prompts}</div><div class="stat-label">Prompts</div></div>
    """
    for row in by_category[:6]:
        cat_safe = html.escape(str(row["category"]))
        stats_html += f'<div class="stat-card"><div class="stat-value">{row["count"]}</div><div class="stat-label">{cat_safe}</div></div>'

    # Filter buttons (escape to prevent XSS)
    filter_buttons = "".join(
        f'<button class="filter-btn" data-filter="{html.escape(str(row["category"]))}">{html.escape(str(row["category"]))} ({row["count"]})</button>'
        for row in by_category
    )

    # Project buttons (escape to prevent XSS)
    project_buttons = "".join(
        f'<button class="project-btn" data-project="{html.escape(str(row["project_context"]))}">{html.escape(str(row["project_context"])[:20])} ({row["count"]})</button>'
        for row in by_project if row["project_context"]
    )
    
    # Memories
    memories = await conn.fetch("""
        SELECT id, content, summary, category, tags, project_context, importance_score, created_at, access_count
        FROM memories ORDER BY created_at DESC LIMIT 500
    """)
    
    memories_html = ""
    for mem in memories:
        # Escape all user-provided data to prevent XSS
        tags_html = "".join(f'<span class="tag">{html.escape(str(tag))}</span>' for tag in (mem["tags"] or [])[:5])
        project = html.escape(str(mem["project_context"] or ""))
        project_badge = f'<span class="project-badge">{project[:20]}</span>' if project else ""
        importance_stars = "★" * int((mem["importance_score"] or 0.5) * 5) + "☆" * (5 - int((mem["importance_score"] or 0.5) * 5))
        category_safe = html.escape(str(mem["category"] or ""))

        content_preview = html.escape((mem["content"] or "")[:500])
        summary = html.escape((mem["summary"] or "")[:100])
        created = mem["created_at"].strftime("%d/%m/%Y %H:%M") if mem["created_at"] else "N/A"

        memories_html += f"""
        <div class="memory-card" data-type="{category_safe}" data-project="{project}">
            <div class="memory-header">
                <span class="memory-type type-{category_safe}">{category_safe}</span>
                <span class="memory-importance">{importance_stars}</span>
            </div>
            <div class="memory-summary">{summary}</div>
            <div class="memory-content">{content_preview}</div>
            <button class="expand-btn">Voir plus ▼</button>
            <div class="memory-tags">{tags_html}</div>
            <div class="memory-meta">
                <span>{project_badge}</span>
                <span>Accès: {mem["access_count"] or 0} | {created}</span>
            </div>
        </div>
        """
    
    # Prompts
    prompts = await conn.fetch("""
        SELECT prompt_text, created_at, prompt_number, session_id
        FROM user_prompts ORDER BY created_at DESC LIMIT 300
    """)
    
    prompts_html = ""
    for p in prompts:
        text = (p["prompt_text"] or "").replace("<", "&lt;").replace(">", "&gt;")
        created = p["created_at"].strftime("%d/%m/%Y %H:%M") if p["created_at"] else "N/A"
        prompts_html += f"""
        <div class="prompt-card">
            <div class="prompt-text">{text}</div>
            <div class="prompt-meta">#{p["prompt_number"]} | {created}</div>
        </div>
        """
    
    await conn.close()
    
    return HTML_TEMPLATE.format(
        total_memories=total_memories,
        total_prompts=total_prompts,
        stats_html=stats_html,
        filter_buttons=filter_buttons,
        project_buttons=project_buttons,
        memories_html=memories_html,
        prompts_html=prompts_html
    )

async def main():
    html = await generate_html()
    
    html_path = os.path.join(os.path.dirname(__file__), "..", "viewer.html")
    with open(html_path, "w") as f:
        f.write(html)
    
    print(f"✅ Interface générée: {os.path.abspath(html_path)}")
    print(f"\n🌐 Pour voir l'interface:")
    print(f"   cd ~/claude-memory-local && python -m http.server 8080")
    print(f"   Puis ouvre http://localhost:8080/viewer.html")

if __name__ == "__main__":
    asyncio.run(main())