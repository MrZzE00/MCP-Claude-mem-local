# Architecture Memoire Cognitive ACT-R x LLM

> **Memory ID**: `5cadfc64-4eb0-4b3b-9dae-12e33d0734ca`
> **Category**: discovery | **Created**: 2026-02-10 15:49 CET
> **Tags**: ACT-R, cognitive-architecture, memory-scoring, forgetting, activation-function, pgvector, synaptic, research-paper, PyACTUp, MemoryBank, A-MEM, hybrid-scoring, spreading-activation

---

## Etude de reference

**"Human-Like Remembering and Forgetting in LLM Agents"** — Honda, Fujita, Zempo, Fukushima (HAI '25, Jan 2026)

Source : https://dl.acm.org/doi/10.1145/3765766.3765803

---

## Formule d'activation ACT-R complete (source CMU)

```
Ai = Bi + Si + Pi + ei
```

| Composante | Formule | Description |
|---|---|---|
| **B(m)** | `ln(Sum(t - ti)^-d)` | Base-level activation (frequence + decroissance power-law, d=0.5) |
| **S(m)** | `Sum_j Wj * (S - ln(fan_j))` | Spreading activation — force associative diluee par le "fan" (mappable sur tags partages entre memoires) |
| **P(m)** | partial matching | Similarite partielle des attributs |
| **e** | `~ N(0, sigma)` | Bruit gaussien (sigma=1.2), variabilite probabiliste du rappel |

### Parametres cles

- **Retrieval threshold tau** : chunk recuperable seulement si `Ai > tau` (formalise active/dormant/forgotten)
- **Latence** : `T = F * e^(-Ai)` (ordre de priorite des resultats)
- **Simplification Honda** : `A(m) = B(m) + w * cosine_similarity + e` (w=11.0 optimal)

---

## Paysage concurrentiel actualise (fevrier 2026)

| Systeme | Approche | Limites vs Synaptic |
|---|---|---|
| **MemoryBank** (AAAI 2024) | Oubli Ebbinghaus simple `R=e^(-t/S)` | Pas de frequence d'acces ni spreading |
| **A-MEM** (NeurIPS 2025) | Auto-organisation Zettelkasten, liens inter-memoires, code open-source | Inspiration complementaire pour structuration |
| **Zep/Graphiti** | Knowledge graph bi-temporel Neo4j, hybrid BM25+semantic+graph, 300ms P95 | Pas d'oubli mathematique |
| **Mem0** | Decay metrics + confidence scoring | Dependant LLM externe (gpt-4.1-nano) — incompatible local-first |
| **LangMem** | Consolidation/invalidation via LLM-as-judge | Aucun scoring mathematique |
| **MemGPT/Letta** | Architecture OS-like 2 tiers | Pas de scoring d'activation cognitif |

**Differenciation Synaptic** : seul systeme combinant scoring ACT-R composite (frequence + decroissance + contexte + bruit) en 100% local-first/air-gapped.

---

## Ressource d'implementation

**PyACTUp** (pypi: `pyactup`) — implementation Python legere de la memoire declarative ACT-R par DDM Lab CMU.

Implemente : base-level activation, blended retrieval, noise, partial matching.

> S'en inspirer plutot que reimplementer from scratch.

---

## Surveys de reference

- **"Memory in the Age of AI Agents"** (arXiv:2512.13564, jan 2026) — lifecycle Formation → Evolution → Retrieval, taxonomie Factual/Experiential/Working Memory
- **"Cognitive Memory in Large Language Models"** (arXiv:2504.02441, avr 2025)

---

## Prerequis PostgreSQL pour le refactoring

```sql
-- 1. Timestamps d'acces
ALTER TABLE memories ADD COLUMN access_timestamps TIMESTAMP[] DEFAULT '{}';

-- 2. Statut memoire
ALTER TABLE memories ADD COLUMN memory_status VARCHAR(10) DEFAULT 'active'
  CHECK (memory_status IN ('active', 'dormant', 'forgotten'));

-- 3. Trigger enregistrement des acces
-- trigger record_access() pour peupler access_timestamps a chaque retrieval

-- 4. Index GIN pour performance
CREATE INDEX idx_memories_access_timestamps ON memories USING GIN (access_timestamps);
```

---

## Plan de refactoring (5 phases, ~12-16h)

### Phase 1 — Schema PostgreSQL (1-2h)

- Ajout colonnes `access_timestamps`, `memory_status`
- Trigger d'enregistrement des acces
- Migration des `access_count` existants vers timestamps synthetiques

### Phase 2 — Scoring ACT-R dans FastAPI (3-4h)

- Implementer `compute_activation()` : `B(m) + w * cosine + e`
- S'inspirer de PyACTUp pour la logique de base
- Spreading activation via tags : `Sji = S - ln(fan_tag)`
- Parametre `w` configurable (defaut 11.0)
- Conserver fallback cosine similarity pure (flag `use_actr_scoring`)

### Phase 3 — Oubli strategique automatise (2-3h)

- Cron job quotidien calculant l'activation de toutes les memoires
- Transitions :
  - `A > 0` → **active**
  - `-2 < A < 0` → **dormant**
  - `A < -2` → **forgotten**
- `forgotten` ≠ supprime : reste en base, exclu des resultats par defaut, requetable explicitement
- Seuil `tau` configurable via variable d'environnement

### Phase 4 — w adaptatif par contexte (2-3h)

- Classifier le type de requete :
  - debugging : `w=15-20`
  - architecture : `w=10-12`
  - recurrent : `w=5-8`
- Heuristique basee sur les tags/categories de la requete

### Phase 5 — Hybrid scoring PostgreSQL (2-3h)

- Remplacer le scoring lineaire recency par `B(m)` ACT-R (power-law)
- Pattern : `FinalScore = ACT-R_activation` au lieu de `VectorSim*0.5 + Recency*0.2`
- Optionnel : ajouter BM25 via `pg_trgm` ou ParadeDB pour keyword matching

---

## Limites connues (Honda et al.)

1. Validation par simulation uniquement, pas sur vrais dialogues
2. Chunks independants — pas de relations hierarchiques (compense par tags/categories)
3. Pas de saillance emotionnelle (compense par champ `importance`)
4. Parametres (d, w, sigma) calibres sur simulations — a ajuster empiriquement sur donnees reelles Synaptic
