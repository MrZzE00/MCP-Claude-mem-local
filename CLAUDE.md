# CLAUDE.md

## ⚠️ DIRECTIVE PRINCIPALE - UTILISATION OBLIGATOIRE DES CAPACITÉS

> **RÈGLE ABSOLUE**: Claude DOIT utiliser 100% de ses capacités disponibles (Skills, MCP, Agents) de manière **AUTOMATIQUE** sans que l'utilisateur ait besoin de le demander explicitement.

### Auto-Activation Obligatoire

| Trigger | Action Automatique |
|---------|-------------------|
| **Création UI/composants** | `Skill: frontend-design:frontend-design` |
| **Implémentation feature** | `Skill: sc:implement` ou `Skill: speckit.implement` |
| **Design architecture** | `Skill: sc:design` + `Task: system-architect` |
| **Analyse de code** | `Skill: sc:analyze` |
| **Problème/bug** | `Skill: sc:troubleshoot` + `MCP: sequential-thinking` |
| **Questions framework** | `MCP: context7` (query-docs) |
| **Tâche complexe (>3 étapes)** | `Skill: sc:task` ou `Skill: sc:spawn` |
| **Tests** | `Skill: sc:test` |
| **Git operations** | `Skill: sc:git` |
| **Début de session** | `Skill: sc:load` + `retrieve_memories` |
| **Fin de session** | `Skill: sc:save` + `store_memory` |

### Règles Impératives

1. **TOUJOURS** utiliser `frontend-design:frontend-design` pour créer des composants UI
2. **TOUJOURS** utiliser `sc:implement` pour implémenter des features
3. **TOUJOURS** utiliser `context7` MCP pour les patterns React/Next.js/Prisma/Supabase
4. **TOUJOURS** utiliser `sequential-thinking` MCP pour l'analyse complexe
5. **TOUJOURS** utiliser les agents spécialisés pour leur domaine d'expertise
6. **TOUJOURS** utiliser `store_memory` après un bugfix, une décision ou une découverte
7. **JAMAIS** coder manuellement ce qu'un skill peut faire mieux

---

## Communication

**Langue**: Toujours répondre en français.

---

## Project Overview

**MCP-Claude-mem-local** - Système de mémoire persistante locale pour Claude Code avec PostgreSQL et pgvector.

| Attribut | Valeur |
|----------|--------|
| **License** | MIT |
| **Status** | Production |
| **Stack** | Python · FastAPI · PostgreSQL · pgvector · Ollama |

---

## Commandes de Développement

```bash
# Développement
npm run dev              # Serveur de développement (localhost:3000)
npm run build            # Build de production
npm run start            # Serveur de production

# Qualité de code
npm run lint             # ESLint
npm run lint:fix         # ESLint avec corrections automatiques
npm run typecheck        # Vérification TypeScript
npm run format           # Prettier formatting
npm run format:check     # Vérification formatting

# Tests
npm run test             # Tests Vitest (run once)
npm run test:watch       # Tests en mode watch
npm run test:coverage    # Tests avec couverture

# Base de données
npm run db:generate      # Génère le client Prisma
npm run db:push          # Push schema vers DB
npm run db:studio        # Ouvre Prisma Studio
```

---

## Architecture

### Stack Technique
| Couche | Technologie | Version |
|--------|-------------|---------|
| Frontend | Next.js (App Router) | 16.1.4 |
| UI | shadcn/ui + Tailwind CSS | 4.x |
| Forms | React Hook Form + Zod | 7.x / 4.x |
| ORM | Prisma | 7.3.0 |
| Database | PostgreSQL (Supabase) | - |
| Auth | Supabase Auth | 2.91.0 |
| AI | Google Gemini API (gemini-2.5-flash) | - |
| Charts | Tremor (prévu) | - |
| Tests | Vitest + Testing Library | 4.x |
| CI/CD | GitHub Actions | - |

### Structure du Projet
```
src/
├── app/                    # Next.js App Router
│   ├── (auth)/            # Routes authentification (login, register)
│   ├── (dashboard)/       # Routes protégées (dashboard)
│   └── api/               # API Routes
├── components/
│   ├── ui/                # shadcn/ui (button, card, input, dialog, form, label)
│   ├── auth/              # Composants authentification
│   ├── objectives/        # Composants OKR
│   ├── layout/            # Sidebar, Header, Nav
│   └── charts/            # Visualisations Tremor
├── lib/
│   ├── supabase/          # Clients Supabase (browser, server, middleware)
│   ├── validations/       # Schémas Zod
│   ├── services/          # Services métier
│   └── utils/             # Utilitaires
├── types/                 # Types TypeScript
└── test/                  # Tests Vitest
```

### Modèle de Données (Prisma)
```
Organization → Team → TeamMember → User
           ↓
       Objective → KeyResult → Initiative
                          ↓
                      CheckIn / Comment
```

---

## 🌐 MCP SERVERS - UTILISATION OBLIGATOIRE

### Disponibles et Actifs

| Server | Usage | Déclencheurs |
|--------|-------|--------------|
| **claude-memory-local** | Mémoire persistante locale (pgvector) | Début/fin session, bugfix, décisions |
| **context7** | Documentation officielle des librairies | `import`, frameworks, patterns officiels |
| **sequential-thinking** | Analyse complexe, debugging multi-étapes | `--think`, `--think-hard`, `--ultrathink` |
| **morphllm-fast-apply** | Transformations de code bulk, refactoring | Modifications multi-fichiers |
| **supabase** | Gestion DB, migrations, SQL, auth, storage | Opérations DB directes, RLS policies |

---

### Claude-Memory-Local (Mémoire Locale) ⭐ NOUVEAU

**Configuration**: Serveur MCP local avec PostgreSQL + pgvector. **Zéro token API consommé.**

**Outils disponibles**:

#### `store_memory` — Stocker un enseignement
```typescript
store_memory({
  content: "Description complète du problème et de la solution",
  category: "bugfix",           // bugfix|decision|feature|discovery|refactor|change
  summary: "Résumé court",      // optionnel, auto-généré si absent
  tags: ["auth", "supabase"],   // optionnel
  importance: 0.9,              // 0.0 à 1.0, défaut: 0.5
  project: "transfo-ia-okr"     // optionnel
})
```

#### `retrieve_memories` — Rechercher le contexte pertinent
```typescript
retrieve_memories({
  query: "authentication supabase RLS",
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

**Déclencheurs automatiques**:
| Moment | Action |
|--------|--------|
| Début de tâche | `retrieve_memories` avec le contexte de la tâche |
| Après bugfix | `store_memory` category="bugfix" |
| Décision architecture | `store_memory` category="decision" |
| Découverte importante | `store_memory` category="discovery" |
| Nouvelle feature | `store_memory` category="feature" |
| Refactoring | `store_memory` category="refactor" |

**Catégories et icônes**:
| Catégorie | Icône | Usage |
|-----------|-------|-------|
| `bugfix` | 🔴 | Correction de bug |
| `decision` | 🟠 | Décision architecturale |
| `feature` | 🟢 | Nouvelle fonctionnalité |
| `discovery` | 🔵 | Découverte, apprentissage |
| `refactor` | 🟣 | Refactoring |
| `change` | ⚪ | Modification générale |

**Interface Web**: http://localhost:8080/viewer.html
```bash
cd ~/claude-memory-local && python3 -m http.server 8080
```

---

### Context7 (Documentation)

**Déclencheurs automatiques**:
- Import de librairie (`import`, `require`, `from`)
- Patterns framework (React, Next.js, Prisma, Supabase, Tailwind)
- Questions "comment faire X avec Y"

```typescript
mcp__context7__resolve-library-id({ query: "...", libraryName: "next.js" })
mcp__context7__query-docs({ libraryId: "/vercel/next.js", query: "..." })
```

---

### Sequential Thinking (Analyse)

**Déclencheurs automatiques**:
- Problème multi-composants (>3 fichiers)
- Debugging complexe
- Design architecture
- Flags: `--think`, `--think-hard`, `--ultrathink`

```typescript
mcp__sequential-thinking__sequentialthinking({
  thought: "...",
  thoughtNumber: 1,
  totalThoughts: 5,
  nextThoughtNeeded: true
})
```

---

### Supabase (Base de Données)

**Déclencheurs automatiques**:
- Opérations DB directes (inspection tables, données)
- Debug de données ou requêtes
- Création/modification de RLS policies
- Migrations de schéma

```typescript
mcp__supabase__list_tables()
mcp__supabase__execute_sql({ query: "SELECT * FROM objectives LIMIT 10" })
mcp__supabase__apply_migration({ name: "add_field", sql: "ALTER TABLE..." })
mcp__supabase__get_logs({ service: "postgres" })
```

---

## Skills Disponibles (Antigravity)

### Prioritaires pour ce Projet

| Skill | Usage | Commande |
|-------|-------|----------|
| **brainstorming** | Exploration des besoins, idéation | Avant toute feature complexe |
| **plan-writing** | Planification structurée | `/executing-plans` |
| **tdd** | Test-Driven Development | Implémentation robuste |
| **app-builder** | Orchestration full-stack | Architecture globale |
| **api-patterns** | Design d'APIs REST/GraphQL | Endpoints OKR |
| **architecture** | Patterns et trade-offs | Décisions structurelles |
| **frontend-design** | UI/UX production-grade | Interfaces utilisateur |
| **supabase-integration** | Auth, DB, Realtime | Configuration Supabase |
| **clean-code** | Qualité et maintenabilité | Refactoring |
| **code-review-checklist** | Revue de code | PR reviews |

### Par Domaine

```yaml
Backend:
  - api-patterns
  - backend-dev-guidelines
  - database-design
  - supabase-integration

Frontend:
  - frontend-design
  - frontend-dev-guidelines
  - core-components

Testing:
  - tdd
  - vitest-testing

DevOps:
  - github-workflow-automation
  - deployment-procedures

AI Integration:
  - ai-agents-architect
  - langgraph
  - rag-retrieval
```

---

## Agents Spécialisés (15 disponibles)

### Pour ce Projet

| Agent | Quand l'utiliser |
|-------|------------------|
| `system-architect` | Décisions d'architecture, scalabilité |
| `backend-architect` | API design, intégrité données |
| `frontend-architect` | UI/UX, accessibilité, performance |
| `security-engineer` | Audit sécurité, conformité |
| `quality-engineer` | Stratégies de test, edge cases |
| `refactoring-expert` | Dette technique, clean code |

### Invocation
```typescript
Task({
  subagent_type: "system-architect",
  prompt: "Analyser l'architecture OKR"
})
```

---

## Slash Commands (/sc:*)

### Développement
| Commande | Usage |
|----------|-------|
| `/sc:implement` | Implémentation feature avec MCP |
| `/sc:build` | Build avec gestion d'erreurs |
| `/sc:test` | Tests avec analyse couverture |
| `/sc:design` | Design système/API/composants |

### Qualité
| Commande | Usage |
|----------|-------|
| `/sc:analyze` | Analyse code complète |
| `/sc:improve` | Améliorations systématiques |
| `/sc:cleanup` | Suppression code mort |
| `/sc:reflect` | Validation avec Serena MCP |

### Planification
| Commande | Usage |
|----------|-------|
| `/sc:brainstorm` | Découverte besoins (Socratique) |
| `/sc:workflow` | Workflows depuis PRDs |
| `/sc:estimate` | Estimations développement |

### Session
| Commande | Usage |
|----------|-------|
| `/sc:load` | Charger contexte projet |
| `/sc:save` | Sauvegarder contexte session |
| `/sc:git` | Opérations Git intelligentes |

---

## Ralph Loop (Développement Itératif)

### Configuration
```yaml
ralph_defaults:
  max_iterations: 15
  checkpoint_interval: 5
  auto_commit: true
  auto_test: true
  coverage_min: 80

completion_promises:
  task_complete: "<promise>TASK COMPLETE</promise>"
  phase_complete: "<promise>PHASE COMPLETE</promise>"
  tests_pass: "<promise>TESTS PASS</promise>"
  blocked: "<promise>BLOCKED - NEED INPUT</promise>"
```

### Commandes
| Commande | Action |
|----------|--------|
| `status` | Afficher tâche courante |
| `go` / `lance` | Lancer ralph-loop |
| `next` / `suivante` | Prochaine tâche pending |
| `/cancel-ralph` | Annuler ralph-loop actif |

---

## Conventions de Code

### TypeScript
- Strict mode activé
- Types explicites pour fonctions publiques
- Interfaces préférées aux types pour objets

### React/Next.js
- Server Components par défaut
- Client Components marqués `'use client'`
- Server Actions pour mutations

### Naming
| Type | Convention | Exemple |
|------|------------|---------|
| Fichiers composants | kebab-case | `objective-card.tsx` |
| Composants | PascalCase | `ObjectiveCard` |
| Fonctions | camelCase | `calculateProgress` |
| Types/Interfaces | PascalCase | `Objective`, `KeyResult` |
| Constantes | SCREAMING_SNAKE_CASE | `MAX_KEY_RESULTS` |

---

## Workflow de Session

### Démarrage
```bash
/sc:load                           # Charger contexte projet
retrieve_memories                  # Récupérer mémoires pertinentes
status                             # Voir tâche courante
```

### Pendant la Session
```bash
go                                 # Lancer tâche courante
npm run lint && npm run typecheck  # Validation continue
# Après chaque bugfix/décision → store_memory
```

### Fin de Session
```bash
store_memory                       # Sauvegarder enseignements importants
/sc:save                           # Sauvegarder contexte
claude-context                     # Mettre à jour CLAUDE.md (optionnel)
```

---

## Fichiers de Contexte

| Fichier | Priorité | Usage |
|---------|----------|-------|
| `.specify/memory/constitution.md` | 🔴 Haute | Principes fondamentaux du projet |
| `CLAUDE.md` | 🔴 Haute | Instructions Claude Code |
| `AGENTS.md` | 🔴 Haute | Configuration agents, MCP, skills |
| `.taskmaster/TASKS/tasks-ralph.md` | 🔴 Haute | Backlog tâches |
| `specs/phase1-core-features/spec.md` | 🟡 Moyenne | Spécification Phase 1 |
| `docs/ARCHITECTURE.md` | 🟡 Moyenne | Architecture technique |
| `claudedocs/SESSION_*.md` | 🟢 Basse | Historique sessions |

---

## Constitution du Projet

Le projet est régi par 6 principes fondamentaux définis dans `.specify/memory/constitution.md`:

| # | Principe | Résumé |
|---|----------|--------|
| I | **User-Centric OKR Design** | Interfaces intuitives, accessibles, responsive |
| II | **Type-Safe Development** | TypeScript strict, Prisma types, Zod schemas |
| III | **Test-Driven Quality** | 80% coverage, tests avant merge |
| IV | **Server-First Architecture** | RSC par défaut, Server Actions pour mutations |
| V | **Data Integrity & Security** | RLS obligatoire, isolation multi-tenant |
| VI | **Simplicity & YAGNI** | Pas de sur-ingénierie, MVP first |

---

## Flags Comportementaux

| Flag | Effet |
|------|-------|
| `--think` | Analyse structurée (~4K tokens) |
| `--think-hard` | Analyse profonde (~10K tokens) |
| `--ultrathink` | Analyse maximale (~32K tokens) |
| `--delegate` | Délégation à sous-agents |
| `--loop` | Cycles d'amélioration itératifs |
| `--uc` | Mode ultra-compressé (économie tokens) |
| `--c7` | Activer Context7 MCP |
| `--seq` | Activer Sequential-thinking MCP |

---

## Tâches Actuelles

Voir `.taskmaster/TASKS/tasks-ralph.md` pour le backlog complet.

**Phase 1 - Core Features** (9/9 complétées) ✅

**Phase 2 - Advanced Features** (en cours):
- ⏳ P2-01: Analytics & Reporting (Tremor)
- ⏳ P2-02: Real-time Updates (Supabase Realtime)
- ⏳ P2-03: Export Functionality (PDF/CSV)
- ⏳ P2-04: AI-Powered Suggestions (Google Gemini API)
- ⏳ P2-05: Agent Conversationnel Variables (Modèle INIT1)

---

## 📋 MATRICE DE DÉCISION AUTOMATIQUE

```
IF création_composant_UI THEN
  → Skill: frontend-design:frontend-design
  → MCP: context7 (React/Next.js patterns)

IF implémentation_feature THEN
  → Skill: sc:implement
  → MCP: context7 (framework patterns)
  → FIN: store_memory category="feature"

IF design_architecture THEN
  → Skill: sc:design
  → Agent: system-architect
  → MCP: sequential-thinking
  → FIN: store_memory category="decision"

IF bug_ou_problème THEN
  → Skill: sc:troubleshoot
  → Agent: root-cause-analyst
  → MCP: sequential-thinking
  → FIN: store_memory category="bugfix"

IF tests THEN
  → Skill: sc:test
  → Agent: quality-engineer

IF début_session THEN
  → Skill: sc:load
  → retrieve_memories (contexte pertinent)

IF fin_session THEN
  → store_memory (enseignements importants)
  → Skill: sc:save

IF commande_git THEN
  → Skill: sc:git

IF tâche_complexe (>3 étapes) THEN
  → Skill: sc:task OU ralph-loop:ralph-loop
  → TodoWrite pour tracking

IF découverte_importante THEN
  → store_memory category="discovery"

IF refactoring THEN
  → store_memory category="refactor"
```

---

<claude-memory-local-context>
# Recent Activity

<!-- This section is auto-generated by claude-memory-local. Edit content outside the tags. -->
<!-- Pour mettre à jour: cd /chemin/projet && claude-context -->

</claude-memory-local-context>