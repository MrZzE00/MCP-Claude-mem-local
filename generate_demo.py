import os
import sys
import html
from datetime import datetime

# Mock environment variable to bypass check on import
os.environ["PG_PASSWORD"] = "mock_password"

from web_ui import HTML_TEMPLATE

# Mock data
total_memories = 142
total_prompts = 356

# Categories and their counts
categories = [
    {"category": "feature", "count": 48},
    {"category": "bugfix", "count": 29},
    {"category": "decision", "count": 22},
    {"category": "refactor", "count": 18},
    {"category": "discovery", "count": 12},
    {"category": "learning", "count": 8},
    {"category": "pattern", "count": 5}
]

projects = [
    {"project_context": "MCP-Claude-mem-local", "count": 64},
    {"project_context": "test-open-code", "count": 42},
    {"project_context": "infra-ops", "count": 18}
]

# Build stats HTML
stats_html = f"""
    <div class="stat-card"><div class="stat-value">{total_memories}</div><div class="stat-label">Mémoires</div></div>
    <div class="stat-card"><div class="stat-value">{total_prompts}</div><div class="stat-label">Prompts</div></div>
"""
for row in categories[:6]:
    stats_html += f'<div class="stat-card"><div class="stat-value">{row["count"]}</div><div class="stat-label">{row["category"]}</div></div>'

# Build filters HTML
filter_buttons = "".join(
    f'<button class="filter-btn" data-filter="{row["category"]}">{row["category"]} ({row["count"]})</button>'
    for row in categories
)

# Build project filters HTML
project_buttons = "".join(
    f'<button class="project-btn" data-project="{row["project_context"]}">{row["project_context"]} ({row["count"]})</button>'
    for row in projects
)

# Build memories HTML
memories_mock_data = [
    {
        "category": "feature",
        "importance": 0.8,
        "summary": "Ajout du support AlloyDB pour le stockage des mémoires",
        "content": "Déploiement et intégration du connecteur AlloyDB de Google Cloud avec authentification IAM. Cette fonctionnalité permet de stocker les embeddings vectoriels générés par Gemini de manière sécurisée et performante sans mot de passe en dur, en utilisant le rôle IAM Cloud Run.",
        "tags": ["alloydb", "gcp", "iam", "embeddings"],
        "project": "MCP-Claude-mem-local",
        "access": 24,
        "created": "28/05/2026 15:30"
    },
    {
        "category": "bugfix",
        "importance": 0.9,
        "summary": "Correction du KeyError dans le visualiseur HTML_TEMPLATE",
        "content": "Résolution d'un crash critique survenant lors de la génération de viewer.html. L'utilisation originelle de .format() sur HTML_TEMPLATE levait une KeyError à cause des accolades simples utilisées dans les sélecteurs CSS. Remplacement par un chaînage robuste de .replace() qui préserve la syntaxe CSS standard.",
        "tags": ["bugfix", "css", "rendering", "python"],
        "project": "MCP-Claude-mem-local",
        "access": 15,
        "created": "28/05/2026 15:15"
    },
    {
        "category": "decision",
        "importance": 0.6,
        "summary": "Adoption du Thème Clair Zenika pour l'interface de visualisation",
        "content": "Sélection et implémentation de l'Option B (Thème Clair Zenika) suite aux retours de l'utilisateur. Le style graphique reprend les polices modernisées 'Outfit' et 'Inter' avec des bordures et effets au survol de couleur rouge Zenika (#E31937) sur un fond dégradé gris/blanc très épuré.",
        "tags": ["design", "css-variables", "zenika"],
        "project": "test-open-code",
        "access": 7,
        "created": "28/05/2026 14:45"
    },
    {
        "category": "refactor",
        "importance": 0.7,
        "summary": "Optimisation des requêtes hybrides PostgreSQL",
        "content": "Refactoring de la méthode de recherche hybride combinant recherche plein texte (FTS) et recherche vectorielle pgvector. Les coefficients ACTR ont été ajustés pour accorder une pondération équilibrée à la récence d'accès et au score de similarité cosinus.",
        "tags": ["refactor", "postgres", "pgvector", "actr"],
        "project": "MCP-Claude-mem-local",
        "access": 11,
        "created": "27/05/2026 18:22"
    },
    {
        "category": "discovery",
        "importance": 0.5,
        "summary": "Comportement des requêtes réseau lors du déploiement Terraform",
        "content": "Découverte de latences inattendues lors de l'appel au point d'accès Ollama distant sous certaines topologies VPC GCP. Résolu en mettant en place un miroir local du service ou en augmentant le timeout de gunicorn.",
        "tags": ["terraform", "vpc", "gcp", "ollama"],
        "project": "infra-ops",
        "access": 4,
        "created": "26/05/2026 10:57"
    }
]

memories_html = ""
for mem in memories_mock_data:
    tags_html = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in mem["tags"])
    project_badge = f'<span class="project-badge">{html.escape(mem["project"])}</span>' if mem["project"] else ""
    importance_stars = "★" * int(mem["importance"] * 5) + "☆" * (5 - int(mem["importance"] * 5))
    
    memories_html += f"""
    <div class="memory-card" data-type="{mem["category"]}" data-project="{mem["project"]}">
        <div class="memory-header">
            <span class="memory-type type-{mem["category"]}">{mem["category"]}</span>
            <span class="memory-importance">{importance_stars}</span>
        </div>
        <div class="memory-summary">{html.escape(mem["summary"])}</div>
        <div class="memory-content">{html.escape(mem["content"])}</div>
        <button class="expand-btn">Voir plus ▼</button>
        <div class="memory-tags">{tags_html}</div>
        <div class="memory-meta">
            <span>{project_badge}</span>
            <span>Accès: {mem["access"]} | {mem["created"]}</span>
        </div>
    </div>
    """

# Build prompts HTML
prompts_mock_data = [
    {"text": "Mettre à jour la page aux couleurs de Zenika en analysant test-open-code/frontend et zenika.com.", "number": 3, "created": "28/05/2026 15:34"},
    {"text": "Comment configurer les permissions IAM AlloyDB pour le rôle Cloud Run sur GCP ?", "number": 2, "created": "28/05/2026 13:12"},
    {"text": "Lance les tests unitaires sur la recherche hybride avec pytest.", "number": 1, "created": "27/05/2026 09:40"}
]

prompts_html = ""
for p in prompts_mock_data:
    prompts_html += f"""
    <div class="prompt-card">
        <div class="prompt-text">{html.escape(p["text"])}</div>
        <div class="prompt-meta">#{p["number"]} | {p["created"]}</div>
    </div>
    """

# Format output using .replace() chain
rendered_html = (
    HTML_TEMPLATE
    .replace("{total_memories}", str(total_memories))
    .replace("{total_prompts}", str(total_prompts))
    .replace("{stats_html}", stats_html)
    .replace("{filter_buttons}", filter_buttons)
    .replace("{project_buttons}", project_buttons)
    .replace("{memories_html}", memories_html)
    .replace("{prompts_html}", prompts_html)
)

status_text = "AlloyDB + Gemini"
rendered_html = rendered_html.replace("PostgreSQL + pgvector + Ollama", status_text)

# Write to viewer_demo.html in workspace root
viewer_path = os.path.join(os.path.dirname(__file__), "viewer_demo.html")
with open(viewer_path, "w") as f:
    f.write(rendered_html)

print(f"✅ Interface de démo générée avec succès : {viewer_path}")
