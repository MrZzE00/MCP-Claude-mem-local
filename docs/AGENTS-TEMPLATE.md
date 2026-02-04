# AGENTS.md Template

> Template de configuration pour intégrer MCP-Claude-mem-local dans vos projets.
> Copiez ce fichier dans votre projet et adaptez-le à vos besoins.

---

# AGENTS.md

Configuration des agents IA pour **[NOM_DU_PROJET]**.

## ⚠️ DIRECTIVE CRITIQUE - AUTO-ACTIVATION OBLIGATOIRE

> **RÈGLE ABSOLUE**: Claude DOIT utiliser AUTOMATIQUEMENT 100% de ses capacités disponibles (Skills, MCP, Agents) sans que l'utilisateur ait besoin de le demander explicitement.

### 🎯 Matrice d'Auto-Activation

| Situation Détectée | Actions Automatiques Obligatoires |
|-------------------|-----------------------------------|
| **Création composant UI** | 1. `Skill: frontend-design:frontend-design`<br>2. `MCP: context7` (patterns React/Next.js) |
| **Implémentation feature** | 1. `Skill: sc:implement`<br>2. `MCP: context7`<br>3. **FIN:** `store_memory` category="feature" |
| **Design/Architecture** | 1. `Skill: sc:design`<br>2. `Agent: system-architect`<br>3. `MCP: sequential-thinking`<br>4. **FIN:** `store_memory` category="decision" |
| **Bug/Problème** | 1. `Skill: sc:troubleshoot`<br>2. `MCP: sequential-thinking`<br>3. **FIN:** `store_memory` category="bugfix" |
| **Tests** | 1. `Skill: sc:test`<br>2. `Agent: quality-engineer` si stratégie |
| **Début session** | 1. `Skill: sc:load`<br>2. `retrieve_memories` (contexte pertinent) |
| **Fin session** | 1. `store_memory` (enseignements)<br>2. `Skill: sc:save` |
| **Découverte importante** | `store_memory` category="discovery" |
| **Refactoring** | `store_memory` category="refactor" |

### 🚫 Interdictions

- **JAMAIS** résoudre un bug sans `store_memory` category="bugfix"
- **JAMAIS** prendre une décision architecturale sans `store_memory` category="decision"
- **JAMAIS** commencer une session sans `retrieve_memories`
- **JAMAIS** terminer une session sans `store_memory`

---

## 🧠 MCP-Claude-mem-local - Mémoire Persistante Locale

### Configuration

| Propriété | Valeur |
|-----------|--------|
| **Type** | MCP Server local |
| **Stockage** | PostgreSQL + pgvector |
| **Embeddings** | Ollama (nomic-embed-text) |
| **Tokens API** | Zéro consommé |

### Outils Disponibles

#### `store_memory` — Stocker un enseignement

```typescript
store_memory({
  content: "Description complète du problème et de la solution",
  category: "bugfix",           // bugfix|decision|feature|discovery|refactor|change
  summary: "Résumé court",      // optionnel, auto-généré si absent
  tags: ["auth", "api"],        // optionnel
  importance: 0.9,              // 0.0 à 1.0, défaut: 0.5
  project: "mon-projet"         // optionnel
})
```

#### `retrieve_memories` — Rechercher le contexte pertinent

```typescript
retrieve_memories({
  query: "problème d'authentification",
  max_results: 5,               // défaut: 5
  category: "bugfix",           // optionnel
  min_similarity: 0.5           // défaut: 0.5
})
```

#### `list_memories` — Lister les mémoires récentes

```typescript
list_memories({ limit: 20, category: "decision" })
```

#### `memory_stats` — Statistiques

```typescript
memory_stats()
```

#### `delete_memory` — Supprimer une mémoire

```typescript
delete_memory({ memory_id: "uuid" })
```

### Catégories et Icônes

| Catégorie | Icône | Usage |
|-----------|-------|-------|
| `bugfix` | 🔴 | Correction de bug avec cause et solution |
| `decision` | 🟠 | Décision architecturale avec contexte |
| `feature` | 🟢 | Nouvelle fonctionnalité implémentée |
| `discovery` | 🔵 | Découverte, apprentissage technique |
| `refactor` | 🟣 | Refactoring avec motivation |
| `change` | ⚪ | Modification générale |

### Workflow de Session

```
┌─────────────────────────────────────────────────────────────┐
│                    DÉBUT DE SESSION                          │
├─────────────────────────────────────────────────────────────┤
│ 1. /sc:load                                                 │
│ 2. retrieve_memories({ query: "contexte projet" })          │
│ 3. Lire CLAUDE.md (contexte injecté par MCP-Claude-mem-local)          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  PENDANT LA SESSION                          │
├─────────────────────────────────────────────────────────────┤
│ • Après bugfix    → store_memory category="bugfix"          │
│ • Après décision  → store_memory category="decision"        │
│ • Découverte      → store_memory category="discovery"       │
│ • Feature         → store_memory category="feature"         │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    FIN DE SESSION                            │
├─────────────────────────────────────────────────────────────┤
│ 1. store_memory (enseignements importants de la session)    │
│ 2. /sc:save                                                 │
│ 3. (optionnel) mcp-claude-mem-local-context pour MAJ CLAUDE.md         │
└─────────────────────────────────────────────────────────────┘
```

### Interface Web

```bash
cd ~/mcp-claude-mem-local && python3 -m http.server 8080
# Ouvrir http://localhost:8080/viewer.html
```

---

## 🌐 MCP Servers

| Server | Usage | Status |
|--------|-------|--------|
| **mcp-claude-mem-local** | Mémoire persistante locale | ✅ Active |
| **context7** | Documentation librairies | ✅ Active |
| **sequential-thinking** | Analyse complexe | ✅ Active |

### MCP-Claude-mem-local (Mémoire)

**Déclencheurs automatiques:**
- Début de session → `retrieve_memories`
- Après bugfix/décision/feature → `store_memory`
- Fin de session → `store_memory` + mise à jour contexte

### Context7 (Documentation)

**Déclencheurs automatiques:**
- Import de librairie (`import`, `from`)
- Questions sur frameworks (React, Next.js, etc.)
- Patterns officiels

### Sequential Thinking (Analyse)

**Déclencheurs automatiques:**
- Problème multi-composants (>3 fichiers)
- Debugging complexe
- Design architecture

---

## 📋 Matrice de Décision Automatique

```
IF création_composant_UI THEN
  → Skill: frontend-design
  → MCP: context7

IF implémentation_feature THEN
  → Skill: sc:implement
  → MCP: context7
  → FIN: store_memory category="feature"

IF design_architecture THEN
  → Skill: sc:design
  → MCP: sequential-thinking
  → FIN: store_memory category="decision"

IF bug_ou_problème THEN
  → Skill: sc:troubleshoot
  → MCP: sequential-thinking
  → FIN: store_memory category="bugfix"

IF début_session THEN
  → Skill: sc:load
  → retrieve_memories

IF fin_session THEN
  → store_memory (enseignements)
  → Skill: sc:save

IF découverte_importante THEN
  → store_memory category="discovery"

IF refactoring THEN
  → store_memory category="refactor"
```

---

## 📁 Fichiers de Contexte

| Fichier | Priorité | Usage |
|---------|----------|-------|
| `AGENTS.md` | 🔴 Haute | Configuration agents et règles |
| `CLAUDE.md` | 🔴 Haute | Instructions Claude Code + contexte MCP-Claude-mem-local |
| `README.md` | 🟡 Moyenne | Vue d'ensemble projet |

---

## 🔧 Commandes Rapides

| Commande | Action |
|----------|--------|
| `status` | Afficher tâche courante |
| `go` / `lance` | Lancer la tâche |
| `/sc:load` | Charger contexte projet |
| `/sc:save` | Sauvegarder contexte |

---

<mcp-claude-mem-local-context>
# Recent Activity

<!-- This section is auto-generated by MCP-Claude-mem-local. Edit content outside the tags. -->
<!-- Run: mcp-claude-mem-local-context /path/to/project -->

</mcp-claude-mem-local-context>