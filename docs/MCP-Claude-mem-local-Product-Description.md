# 🧠 MCP-Claude-mem-local

## La mémoire collective pour les équipes qui codent avec l'IA

---

## Le Problème

Chaque jour, des millions de développeurs utilisent Claude, Copilot et d'autres assistants IA pour coder. Chaque jour, ces assistants **oublient tout** à la fin de la conversation.

**Le résultat ?**

- 🔄 Les mêmes erreurs sont répétées encore et encore
- 📚 Les décisions architecturales sont perdues
- 🧩 Chaque développeur reconstruit sa propre connaissance en silo
- 💸 Des tokens (et de l'argent) gaspillés à ré-expliquer le contexte
- 🤯 L'IA ne s'améliore jamais sur VOTRE codebase

**Et dans les équipes, c'est pire :**

- Alice a résolu ce bug la semaine dernière, mais Bob le redécouvre aujourd'hui
- L'équipe Frontend a documenté un pattern, l'équipe Backend ne le sait pas
- Les décisions d'architecture sont enterrées dans des conversations Slack
- Le nouveau développeur passe 3 mois à comprendre ce que l'IA aurait pu lui dire en 3 secondes

---

## La Solution : MCP-Claude-mem-local

**MCP-Claude-mem-local** est un système de mémoire persistante, locale et collaborative pour Claude Code (et bientôt d'autres assistants IA).

```
🧠 Personal Memory  →  👥 Team Memory  →  🏢 Organization Memory
```

### Comment ça marche

1. **Claude apprend** — Chaque bugfix, décision, découverte est automatiquement capturée
2. **Vous gardez le contrôle** — Tout reste sur votre machine ou votre infra (100% local possible)
3. **L'équipe partage** — Synchronisez les connaissances importantes avec votre équipe
4. **L'organisation capitalise** — Agrégez les patterns et best practices à l'échelle

---

## Fonctionnalités

### 🔒 100% Local & Privé

- **PostgreSQL + pgvector** pour le stockage vectoriel
- **Ollama** pour les embeddings (aucune donnée envoyée à l'extérieur)
- **Zéro token API** consommé pour la mémoire
- Vos données restent sur votre machine

### 🧠 Mémoire Intelligente

| Outil | Description |
|-------|-------------|
| `store_memory` | Capture bugfixes, décisions, découvertes, patterns |
| `retrieve_memories` | Recherche sémantique dans vos connaissances |
| `list_memories` | Parcourez votre historique |
| `memory_stats` | Analysez votre base de connaissances |

### 📁 Contexte Automatique

MCP-Claude-mem-local injecte automatiquement le contexte pertinent dans vos fichiers `CLAUDE.md` :

```markdown
<mcp-claude-mem-local-context>
### Jan 28, 2026

| ID | Type | Titre | Tokens |
|----|------|-------|--------|
| #a1b2c3 | 🔴 bugfix | Fixed auth token refresh race condition | ~450 |
| #d4e5f6 | 🟠 decision | Switched to Server Components for dashboard | ~820 |
| #g7h8i9 | 🔵 discovery | Prisma batch queries 10x faster than loops | ~340 |
</mcp-claude-mem-local-context>
```

### 👥 Collaboration d'Équipe (Coming Soon)

```
┌─────────────────────────────────────────────────────┐
│                 🏢 Org Knowledge                     │
│   "Company-wide architectural decisions"            │
│   "Security patterns" · "Deployment procedures"     │
└─────────────────────────────────────────────────────┘
                         ▲
         ┌───────────────┴───────────────┐
         │                               │
┌────────▼────────┐           ┌──────────▼──────┐
│  👥 Team Alpha   │           │  👥 Team Beta   │
│  "API patterns"  │           │  "UI patterns"  │
│  "Auth decisions"│           │  "A11y fixes"   │
└─────────────────┘           └─────────────────┘
    ▲         ▲                   ▲         ▲
┌───┴───┐ ┌───┴───┐         ┌────┴──┐ ┌────┴──┐
│👤 Alice│ │👤 Bob │         │👤 Carol│ │👤 Dave│
│Personal│ │Personal│        │Personal│ │Personal│
└────────┘ └────────┘        └────────┘ └────────┘
```

**Scopes de visibilité :**
- `personal` — Visible uniquement par vous
- `team` — Partagé avec votre équipe
- `org` — Accessible à toute l'organisation

**Synchronisation intelligente :**
- Push vos découvertes importantes vers l'équipe
- Pull les connaissances de l'équipe automatiquement
- Merge intelligent des mémoires similaires
- Détection de patterns récurrents cross-équipes

---

## Cas d'Usage

### 👤 Développeur Solo

> *"J'ai passé 2 heures à débugger ce problème de CORS il y a 3 mois. Aujourd'hui, Claude me rappelle la solution en 3 secondes."*

- Capitalise sur tes erreurs passées
- Garde trace de tes décisions architecturales
- Retrouve instantanément le contexte de n'importe quel projet

### 👥 Équipe de Développement

> *"Le nouveau dev a posé une question sur notre système d'auth. Claude lui a répondu avec les 5 décisions clés qu'on a prises ces 6 derniers mois, avec le contexte de chacune."*

- Onboarding 10x plus rapide
- Connaissance partagée, pas silotée
- Les patterns de l'équipe sont automatiquement suggérés

### 🏢 Organisation / Enterprise

> *"On a détecté que 3 équipes différentes avaient résolu le même problème de performance de 3 façons différentes. MCP-Claude-mem-local nous a permis d'identifier la meilleure solution et de la propager."*

- Identifie les patterns récurrents
- Propage les best practices
- Évite la duplication d'efforts

---

## Stack Technique

| Composant | Technologie | Rôle |
|-----------|-------------|------|
| **Stockage** | PostgreSQL + pgvector | Base vectorielle pour recherche sémantique |
| **Embeddings** | Ollama (nomic-embed-text) | Génération locale des vecteurs |
| **Interface** | MCP Server (Python) | Intégration Claude Code |
| **UI** | Web Dashboard | Visualisation des mémoires |
| **Sync** | API REST + WebSocket | Synchronisation équipe (optionnel) |

### Déploiement Flexible

```bash
# Solo — Tout en local
docker-compose -f docker-compose.local.yml up

# Équipe — Serveur partagé
docker-compose -f docker-compose.team.yml up

# Enterprise — Multi-équipes avec agrégation
docker-compose -f docker-compose.enterprise.yml up
```

---

## Comparaison

| Aspect | Claude Vanilla | claude-mem | **MCP-Claude-mem-local** |
|--------|----------------|------------|--------------|
| Mémoire persistante | ❌ | ✅ | ✅ |
| 100% local | ❌ | ❌ | ✅ |
| Zéro token consommé | ❌ | ❌ | ✅ |
| Recherche sémantique | ❌ | ✅ | ✅ |
| Partage équipe | ❌ | ❌ | ✅ |
| Agrégation org | ❌ | ❌ | ✅ |
| Open Source | N/A | ❌ | ✅ |
| Self-hosted | N/A | ❌ | ✅ |

---

## Quick Start

### Installation (5 minutes)

```bash
# Clone le repo
git clone https://github.com/votre-org/mcp-claude-mem-local.git
cd mcp-claude-mem-local

# Lance avec Docker
docker-compose up -d

# Configure Claude Code
mcp-claude-mem-local init

# C'est prêt !
```

### Premier usage

Dans Claude Code :
```
> Utilise retrieve_memories pour voir si on a déjà résolu des problèmes similaires
> ...
> Stocke ce bugfix avec store_memory category="bugfix"
```

---

## Roadmap

### v1.0 — Solo Developer ✅
- [x] Stockage local PostgreSQL + pgvector
- [x] Embeddings locaux avec Ollama
- [x] 5 outils MCP (store, retrieve, list, stats, delete)
- [x] Interface web de visualisation
- [x] Injection contexte dans CLAUDE.md
- [x] Migration depuis claude-mem

### v1.5 — Enhanced Solo
- [ ] Support multi-projets
- [ ] Tags et catégories personnalisables
- [ ] Export/Import de mémoires
- [ ] Recherche avancée (filtres, dates, etc.)
- [ ] Interface web améliorée (édition, bulk actions)

### v2.0 — Team Collaboration
- [ ] Serveur de synchronisation
- [ ] Scopes de visibilité (personal/team/org)
- [ ] Push/Pull de mémoires
- [ ] Merge intelligent
- [ ] Gestion des conflits
- [ ] Dashboard équipe

### v3.0 — Enterprise
- [ ] Multi-équipes avec hiérarchie
- [ ] Agrégation automatique de patterns
- [ ] Analytics et insights
- [ ] SSO / SAML
- [ ] Audit logs
- [ ] API pour intégrations tierces

---

## Contribuer

MCP-Claude-mem-local est **open source** (MIT License). Contributions bienvenues !

- 🐛 Signaler un bug
- 💡 Proposer une feature
- 📖 Améliorer la documentation
- 🔧 Soumettre une PR

---

## Pourquoi "MCP-Claude-mem-local" ?

Les synapses sont les connexions entre les neurones qui permettent la transmission de l'information et la formation de la mémoire.

**MCP-Claude-mem-local** crée ces connexions entre :
- 🧠 Vos sessions de code
- 👥 Les membres de votre équipe
- 🏢 Les équipes de votre organisation

Chaque mémoire stockée renforce le réseau. Chaque connexion améliore l'intelligence collective.

---

## License

MIT — Utilisez-le, modifiez-le, partagez-le.

---

<p align="center">
  <b>🧠 MCP-Claude-mem-local</b><br>
  <i>Your AI never forgets. Your team always learns.</i>
</p>