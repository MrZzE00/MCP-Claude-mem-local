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
| **Création composant UI** | `Skill:` <br>`Agent:` <br>`MCP:` <br>`FIN:` store_memory category="feature" |
| **Implémentation feature** | `Skill:` <br>`Agent:` <br>`MCP:` <br>`FIN:` store_memory category="feature" |
| **Design/Architecture** | `Skill:` <br>`Agent:` <br>`MCP:` <br>`FIN:` store_memory category="decision" |
| **Bug/Problème** | `Skill:` <br>`Agent:` <br>`MCP:` <br>`FIN:` store_memory category="bugfix" |
| **Tests** | `Skill:` <br>`Agent:` <br>`MCP:` |
| **Début session** | `Skill:` <br>`retrieve_memories` (contexte pertinent) |
| **Fin session** | `store_memory` (enseignements)<br>`Skill:` |
| **Découverte importante** | `store_memory` category="discovery" |
| **Refactoring** | `store_memory` category="refactor" |
| **Pattern identifié** | `store_memory` category="pattern" |
| **Préférence utilisateur** | `store_memory` category="preference" |
| **Leçon apprise** | `store_memory` category="learning" |
| **Solution erreur** | `store_memory` category="error_solution" |

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
  category: "bugfix",           // bugfix|decision|feature|discovery|refactor|change|pattern|preference|learning|error_solution
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
| `pattern` | 🟤 | Pattern réutilisable identifié |
| `preference` | 🟡 | Préférence utilisateur |
| `learning` | 📘 | Enseignement, leçon apprise |
| `error_solution` | 🩹 | Solution à une erreur spécifique |

### Workflow de Session

```
┌─────────────────────────────────────────────────────────────┐
│                    DÉBUT DE SESSION                          │
├─────────────────────────────────────────────────────────────┤
│ 1. [Votre skill de chargement]                              │
│ 2. retrieve_memories({ query: "contexte projet" })          │
│ 3. Lire CLAUDE.md (contexte injecté par claude-memory-local)│
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
│ 2. [Votre skill de sauvegarde]                              │
│ 3. (optionnel) claude-context pour MAJ CLAUDE.md            │
└─────────────────────────────────────────────────────────────┘
```

### Interface Web

```bash
cd ~/claude-memory-local && python3 -m http.server 8080
# Ouvrir http://localhost:8080/viewer.html
```

---

## 🌐 MCP Servers

| Server | Usage | Status |
|--------|-------|--------|
| **claude-memory-local** | Mémoire persistante locale | ✅ Active |
| **[votre-mcp-server]** | [Description] | ⬚ À configurer |

### Claude-Memory-Local (Mémoire)

**Déclencheurs automatiques:**
- Début de session → `retrieve_memories`
- Après bugfix/décision/feature → `store_memory`
- Fin de session → `store_memory` + mise à jour contexte

### Autres MCP Servers

Ajoutez ici vos MCP servers et leurs déclencheurs automatiques.

```
### [Nom du MCP Server]

**Déclencheurs automatiques:**
- [Trigger 1] → [Action]
- [Trigger 2] → [Action]
```

---

## 📋 Matrice de Décision Automatique

```
IF création_composant_UI THEN
  → Skill:
  → Agent:
  → MCP:
  → FIN: store_memory category="feature"

IF implémentation_feature THEN
  → Skill:
  → Agent:
  → MCP:
  → FIN: store_memory category="feature"

IF design_architecture THEN
  → Skill:
  → Agent:
  → MCP:
  → FIN: store_memory category="decision"

IF bug_ou_problème THEN
  → Skill:
  → Agent:
  → MCP:
  → FIN: store_memory category="bugfix"

IF tests THEN
  → Skill:
  → Agent:
  → MCP:

IF début_session THEN
  → Skill:
  → retrieve_memories (contexte pertinent)

IF fin_session THEN
  → store_memory (enseignements importants)
  → Skill:

IF commande_git THEN
  → Skill:
  → Agent:
  → MCP:

IF tâche_complexe (>3 étapes) THEN
  → Skill:
  → Agent:
  → MCP:

IF découverte_importante THEN
  → store_memory category="discovery"

IF refactoring THEN
  → store_memory category="refactor"

IF pattern_identifié THEN
  → store_memory category="pattern"

IF préférence_utilisateur THEN
  → store_memory category="preference"

IF leçon_apprise THEN
  → store_memory category="learning"

IF solution_erreur_spécifique THEN
  → store_memory category="error_solution"
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
| `retrieve_memories` | Charger contexte pertinent |
| `store_memory` | Sauvegarder un enseignement |
| `list_memories` | Voir mémoires récentes |
| `memory_stats` | Statistiques mémoire |
| `[vos skills]` | Ajoutez vos commandes ici |

---

<claude-memory-local-context>
# Recent Activity

<!-- This section is auto-generated by claude-memory-local. Edit content outside the tags. -->
<!-- Pour mettre à jour: cd /chemin/projet && claude-context -->

</claude-memory-local-context>